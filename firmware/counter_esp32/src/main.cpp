// main.cpp -- ESP32 pulse counter, stage S1 (docs/design/counter_design.md).
//
// Input-only capture of one pin (never driven), hardware edge timestamps from the
// MCPWM capture unit (CAP0 = rising, CAP1 = falling, same pad), 32-bit APB-clock
// timestamps unwrapped with the 64-bit esp_timer as coarse clock, PCNT as an
// independent rising-edge count, CRC-8 framed serial protocol identical to
// pc/shared/counter_proto.py, anomaly codes 1-9, 1 Hz heartbeat, and a self-test
// that generates known widths on GPIO25 and measures them back on GPIO35.
//
// SELF-LOOPBACK ONLY: generator and counter share one crystal, so the self-test says
// nothing about absolute clock accuracy (design section 7).
//
// Protocol version 2 (pc/counter/proto.py). WiFi/dashboard are NOT part of S1.
// Pins: IN_DUT=34, IN_SELF=35, GEN_OUT=25.
// STATUS: UNFLASHED until the owner approves (docs/design/readiness.md).

#include <Arduino.h>
#include <driver/mcpwm.h>
#include <driver/pcnt.h>
#include <driver/timer.h>
#include <soc/gpio_struct.h>
#include <esp_timer.h>
#include <esp32/clk.h>
#if __has_include("wifi_config.h")
  #include "wifi_config.h"
  #include <WiFi.h>
  #define COUNTER_WIFI 1
#endif
#include "protocol.hpp"   // crc8() -- CRC-8/SMBUS shared with the PC side

#define PIN_IN_DUT   34
#define PIN_IN_SELF  35
#define PIN_GEN_OUT  25
#define PIN_LED      2
#define BAUD         115200   // CH340 USB bridges do not decode 921600 reliably (seen on the first flash, 2026-10-04)
#define PROTO_VERSION 2
#ifndef COUNTER_DEBUG
#define COUNTER_DEBUG 1   // once a second an ASCII "#D ..." line on the USB serial (NOT protocol: frames start with 0xD7, decoders resync)
#endif

static uint32_t dbg_loop_max_us = 0, dbg_send_max_us = 0, dbg_last_loop_us = 0;

// --------------------------------------------------------------------- frame layer
enum : uint8_t { M_TO_COUNTER = 0xC7, M_TO_PC = 0xD7 };
enum : uint8_t { T_ARM = 0xC0, T_END = 0xC1, T_ACK = 0xC2, T_REPLAY = 0xC3, T_REFVAL = 0xC4,
                 T_SELFTEST = 0xC5, T_STATUS = 0xC6,
                 T_PULSE = 0xD0, T_ANOMALY = 0xD1, T_REPORT = 0xD2, T_HEARTBEAT = 0xD3,
                 T_ARM_ACK = 0xD4, T_SELFTEST_RESULT = 0xD5 };
enum : uint8_t { ACK_BUSY = 0, ACK_OK = 1, ACK_BAD_VERSION = 2, ACK_MALFORMED = 3 };
enum : uint8_t { A_MISSING = 1, A_EXTRA, A_GLITCH, A_STUCK_HIGH, A_COUNT_MISMATCH, A_SEQ_GAP,
                 A_NEVER_STARTED, A_CLOCK_FAULT, A_RING_OVERFLOW };

struct Frame { uint8_t b[64]; uint8_t n; };
static void put8(Frame& f, uint8_t v) { f.b[f.n++] = v; }
static void put16(Frame& f, uint16_t v) { put8(f, v >> 8); put8(f, v); }
static void put32(Frame& f, uint32_t v) { put16(f, v >> 16); put16(f, v); }
static void put64(Frame& f, uint64_t v) { put32(f, v >> 32); put32(f, (uint32_t)v); }
static void begin(Frame& f, uint8_t type) { f.n = 0; put8(f, M_TO_PC); put8(f, type); put8(f, 0); }
static void finish(Frame& f) { f.b[2] = f.n - 3; put8(f, crc8(f.b, f.n)); }
#ifdef COUNTER_WIFI
static WiFiClient net;           // TCP client to the PC (same frames as the USB serial link)
static uint32_t net_retry_ms = 0;
#endif
// Frames go to BOTH links: USB serial (always) and the TCP link to the PC when connected.
static void send(Frame& f) {
    uint32_t t0 = micros();
    Serial.write(f.b, f.n);
#ifdef COUNTER_WIFI
    if (net.connected()) net.write(f.b, f.n);
#endif
    uint32_t dt = micros() - t0;
    if (dt > dbg_send_max_us) dbg_send_max_us = dt;
}

// --------------------------------------------------------------------- state
enum Mode : uint8_t { IDLE = 0, ARMED = 1, SELFTEST = 2 };
static volatile Mode mode = IDLE;
static uint32_t session = 0;
static uint16_t reps = 0;
static uint32_t min_width_ns = 500;
static uint32_t max_width_s = 130;
static uint16_t start_timeout_s = 0;
static int64_t arm_us = 0;
static bool start_flagged = false;
static int cap_pin = PIN_IN_DUT;

static uint16_t seq = 0;
static uint32_t anomaly_mask = 0;
static uint16_t dropped = 0;
static uint64_t w_min = ~0ULL, w_max = 0, w_sum = 0;
static uint32_t rises = 0, falls = 0;
static bool have_rise = false, stuck_flagged = false;
static int64_t t0_us = 0, rise_us = 0;
static uint32_t rise_cap = 0;
static uint32_t apb_hz = 80000000;

// edge ring (ISR -> loop), single producer / single consumer
struct Edge { uint32_t cap; int64_t us; uint8_t rising; };
#define EDGE_N 1024
static Edge edges[EDGE_N];
static volatile uint16_t e_head = 0, e_tail = 0;
static volatile uint16_t e_overflow = 0;

// replay ring of sent PULSE frames
#define REPLAY_N 512
static Frame replay[REPLAY_N];
static uint16_t replay_seq[REPLAY_N];
static bool replay_used[REPLAY_N];

// diagnostics (2026-10-07, grover n=10 noise burst): what the capture ISR and the main loop really see
static volatile uint32_t dbg_isr[2] = {0, 0}, dbg_dup_cap = 0, dbg_edge_mismatch = 0;
static volatile uint32_t dbg_last_cap[2] = {0, 0};

static bool IRAM_ATTR cap_cb(mcpwm_unit_t, mcpwm_capture_channel_id_t ch, const cap_event_data_t* e, void*) {
    int c = (ch == MCPWM_SELECT_CAP0) ? 0 : 1;
    dbg_isr[c]++;
    if (e->cap_value == dbg_last_cap[c]) dbg_dup_cap++;            // same capture value twice in a row on one channel
    dbg_last_cap[c] = e->cap_value;
    if ((e->cap_edge == MCPWM_POS_EDGE) != (c == 0)) dbg_edge_mismatch++;
    uint16_t h = e_head, nh = (h + 1) & (EDGE_N - 1);
    if (nh == e_tail) { e_overflow++; return false; }
    edges[h].cap = e->cap_value;
    edges[h].us = esp_timer_get_time();
    edges[h].rising = (ch == MCPWM_SELECT_CAP0);
    e_head = nh;
    return false;
}

static void flag(uint8_t code, uint16_t sq, uint32_t detail) {
    anomaly_mask |= (1u << code);
    Frame f; begin(f, T_ANOMALY); put16(f, sq); put8(f, code); put32(f, detail); finish(f); send(f);
}

static void route_capture(int pin) {
    cap_pin = pin;
    pinMode(pin, INPUT);
    mcpwm_gpio_init(MCPWM_UNIT_0, MCPWM_CAP_0, pin);
    mcpwm_gpio_init(MCPWM_UNIT_0, MCPWM_CAP_1, pin);
    pcnt_set_pin(PCNT_UNIT_0, PCNT_CHANNEL_0, pin, PCNT_PIN_NOT_USED);
}

static void capture_init() {
    mcpwm_capture_config_t c;
    c.cap_edge = MCPWM_POS_EDGE; c.cap_prescale = 1; c.capture_cb = cap_cb; c.user_data = nullptr;
    mcpwm_capture_enable_channel(MCPWM_UNIT_0, MCPWM_SELECT_CAP0, &c);
    c.cap_edge = MCPWM_NEG_EDGE;
    mcpwm_capture_enable_channel(MCPWM_UNIT_0, MCPWM_SELECT_CAP1, &c);
    pcnt_config_t p = {};
    p.pulse_gpio_num = PIN_IN_DUT; p.ctrl_gpio_num = PCNT_PIN_NOT_USED;
    p.pos_mode = PCNT_COUNT_INC; p.neg_mode = PCNT_COUNT_DIS;
    p.lctrl_mode = PCNT_MODE_KEEP; p.hctrl_mode = PCNT_MODE_KEEP;
    p.counter_h_lim = 32767; p.counter_l_lim = -32768;
    p.unit = PCNT_UNIT_0; p.channel = PCNT_CHANNEL_0;
    pcnt_unit_config(&p);
    pcnt_filter_disable(PCNT_UNIT_0);
    apb_hz = esp_clk_apb_freq();
}

static void clear_point() {
    e_tail = e_head; e_overflow = 0;
    seq = 0; anomaly_mask = 0; dropped = 0; w_min = ~0ULL; w_max = 0; w_sum = 0;
    rises = falls = 0; have_rise = false; stuck_flagged = false; start_flagged = false;
    for (int i = 0; i < REPLAY_N; i++) replay_used[i] = false;
    pcnt_counter_clear(PCNT_UNIT_0);
    t0_us = esp_timer_get_time();
    arm_us = t0_us;
}

// width from the two 32-bit stamps + the 64-bit coarse clock (overflow counting)
static uint64_t unwrap_ticks(uint32_t r32, uint32_t f32, uint64_t coarse_ticks, uint16_t* wraps) {
    uint32_t fine = f32 - r32;                       // mod 2^32
    int64_t k = (int64_t)(((double)coarse_ticks - (double)fine) / 4294967296.0 + 0.5);
    if (k < 0) k = 0;
    *wraps = (uint16_t)k;
    return (uint64_t)fine + ((uint64_t)k << 32);
}
static uint64_t ticks_to_ns(uint64_t t) { return (uint64_t)((double)t * 1e9 / (double)apb_hz + 0.5); }

static uint64_t pulse_widths[64];   // self-test scenario record
static uint8_t n_pw = 0;

static void emit_pulse(uint64_t ticks, uint64_t width_ns, uint16_t wraps, int64_t r_us, uint8_t flags) {
    Frame f; begin(f, T_PULSE); put16(f, seq); put64(f, (uint64_t)(r_us - t0_us)); put64(f, ticks); put64(f, width_ns);
    put16(f, wraps); put8(f, flags); finish(f);
    send(f);
    int slot = seq % REPLAY_N;
    if (replay_used[slot]) { dropped++; flag(A_RING_OVERFLOW, seq, replay_seq[slot]); }   // overwrote an unACKed frame
    replay[slot] = f; replay_seq[slot] = seq; replay_used[slot] = true;
    if (mode == SELFTEST && n_pw < 64) pulse_widths[n_pw++] = width_ns;
    seq++;
}

static void handle_edge(const Edge& e) {
    if (e.rising) {
        rises++;
        if (have_rise) { flag(A_COUNT_MISMATCH, seq, 1); }   // two rising edges, no falling between
        have_rise = true; rise_us = e.us; rise_cap = e.cap;
    } else {
        falls++;
        if (!have_rise) { flag(A_COUNT_MISMATCH, seq, 2); return; }  // falling edge without a rise
        have_rise = false;
        uint64_t coarse = (uint64_t)(e.us - rise_us) * (apb_hz / 1000000ULL);
        uint16_t wraps = 0;
        uint64_t w_ticks = unwrap_ticks(rise_cap, e.cap, coarse, &wraps);
        uint64_t w_ns = ticks_to_ns(w_ticks);
        uint8_t fl = 0;
        if (w_ns < min_width_ns) { fl |= 1; flag(A_GLITCH, seq, (uint32_t)w_ns); }
        if (w_ns < w_min) w_min = w_ns;
        if (w_ns > w_max) w_max = w_ns;
        w_sum += w_ns;
        emit_pulse(w_ticks, w_ns, wraps, rise_us, fl);
    }
}

static void do_end(bool quiet) {
    // drain what the ISR already queued
    while (e_tail != e_head) { Edge e = edges[e_tail]; e_tail = (e_tail + 1) & (EDGE_N - 1); handle_edge(e); }
    if (have_rise || gpio_get_level((gpio_num_t)cap_pin)) flag(A_STUCK_HIGH, falls, have_rise ? 0 : 1);
    if (falls == 0) flag(A_NEVER_STARTED, 0, 0);
    else if (falls < reps) flag(A_MISSING, falls, reps - falls);
    else if (falls > reps) flag(A_EXTRA, falls, falls - reps);
    int16_t pc = 0; pcnt_get_counter_value(PCNT_UNIT_0, &pc);
    if ((uint16_t)pc != (uint16_t)rises) flag(A_COUNT_MISMATCH, falls, (uint16_t)pc);
    if (e_overflow) flag(A_RING_OVERFLOW, seq, e_overflow);
    Frame f; begin(f, T_REPORT);
    put32(f, session); put8(f, anomaly_mask ? 1 : 0); put16(f, falls); put16(f, (uint16_t)anomaly_mask);
    put64(f, falls ? w_min : 0); put64(f, w_max); put64(f, w_sum); put16(f, (uint16_t)pc); put16(f, e_overflow);
    finish(f); send(f);
    (void)quiet;
}

// --------------------------------------------------------------------- generator (self-test)
// One hardware timer (group 1, timer 0, 1 MHz). ISR toggles GPIO25 with direct register writes.
#define GEN_MAX 64
struct GenStep { uint32_t width_us; uint32_t gap_us; };
static GenStep gen_steps[GEN_MAX];
static volatile uint8_t gen_n = 0, gen_i = 0, gen_phase = 0;
static volatile bool gen_done = true;

static bool IRAM_ATTR gen_isr(void*) {
    uint64_t now = timer_group_get_counter_value_in_isr(TIMER_GROUP_1, TIMER_0);
    if (gen_phase == 0) {                       // rising edge now, falling after width
        if (gen_i >= gen_n) { gen_done = true; return false; }
        GPIO.out_w1ts = (1u << PIN_GEN_OUT);
        if (gen_steps[gen_i].width_us == 0) { gen_done = true; return false; }   // rise and HOLD (still-high test)
        gen_phase = 1;
        timer_group_set_alarm_value_in_isr(TIMER_GROUP_1, TIMER_0, now + gen_steps[gen_i].width_us);
    } else {                                    // falling edge, next rising after gap
        GPIO.out_w1tc = (1u << PIN_GEN_OUT);
        gen_phase = 0;
        timer_group_set_alarm_value_in_isr(TIMER_GROUP_1, TIMER_0, now + gen_steps[gen_i].gap_us);
        gen_i++;
    }
    timer_group_enable_alarm_in_isr(TIMER_GROUP_1, TIMER_0);
    return false;
}

static void gen_init() {
    pinMode(PIN_GEN_OUT, OUTPUT); digitalWrite(PIN_GEN_OUT, LOW);
    timer_config_t c = {};
    c.divider = 80; c.counter_dir = TIMER_COUNT_UP; c.counter_en = TIMER_PAUSE;
    c.alarm_en = TIMER_ALARM_EN; c.auto_reload = TIMER_AUTORELOAD_DIS;
    timer_init(TIMER_GROUP_1, TIMER_0, &c);
    timer_isr_callback_add(TIMER_GROUP_1, TIMER_0, gen_isr, nullptr, ESP_INTR_FLAG_IRAM);
}

static void gen_start(uint8_t n) {
    gen_n = n; gen_i = 0; gen_phase = 0; gen_done = false;
    timer_pause(TIMER_GROUP_1, TIMER_0);
    timer_set_counter_value(TIMER_GROUP_1, TIMER_0, 0);
    timer_set_alarm_value(TIMER_GROUP_1, TIMER_0, 1000);   // first rising edge after 1 ms
    timer_enable_intr(TIMER_GROUP_1, TIMER_0);
    timer_set_alarm(TIMER_GROUP_1, TIMER_0, TIMER_ALARM_EN);
    timer_start(TIMER_GROUP_1, TIMER_0);
}

// --------------------------------------------------------------------- self-test scenarios
enum StState : uint8_t { ST_NONE, ST_RUN_CLEAN, ST_RUN_GLITCH, ST_RUN_MISSING, ST_RUN_STUCK, ST_RUN_GAP, ST_PAUSE, ST_FINISH };
static StState st_after_pause = ST_FINISH;
static StState st_state = ST_NONE;
static uint32_t st_wait_until = 0;

struct Group { uint32_t width_us; uint8_t count; };
static const Group groups[] = {{100, 20}, {1000, 20}, {100000, 10}, {1000000, 3}, {10000000, 2}, {60000000, 1}};
static const uint8_t N_GROUPS = sizeof(groups) / sizeof(groups[0]);

static void st_arm(uint32_t id, uint16_t r, uint32_t minw) {
    session = id; reps = r; min_width_ns = minw; max_width_s = 130;
    route_capture(PIN_IN_SELF); clear_point(); n_pw = 0; mode = SELFTEST;
}

static void st_start_clean() {
    uint8_t n = 0;
    for (uint8_t g = 0; g < N_GROUPS; g++)
        for (uint8_t i = 0; i < groups[g].count; i++) { gen_steps[n].width_us = groups[g].width_us; gen_steps[n].gap_us = 3000; n++; }
    st_arm(0xF0000001, n, 5000);
    gen_start(n); st_state = ST_RUN_CLEAN;
}
static void st_start_glitch() {      // 10 pulses of 10 ms, the 6th is a 20 us glitch (limit 50 us)
    for (uint8_t i = 0; i < 10; i++) { gen_steps[i].width_us = (i == 5) ? 20 : 10000; gen_steps[i].gap_us = 3000; }
    st_arm(0xF0000002, 10, 50000);
    gen_start(10); st_state = ST_RUN_GLITCH;
}
static void st_start_missing() {     // reps = 10 but only 9 pulses are generated
    for (uint8_t i = 0; i < 9; i++) { gen_steps[i].width_us = 10000; gen_steps[i].gap_us = 3000; }
    st_arm(0xF0000003, 10, 5000);
    gen_start(9); st_state = ST_RUN_MISSING;
}

static void st_start_stuck() {       // 3 pulses, then the line rises and STAYS high; END must raise code 4
    for (uint8_t i = 0; i < 3; i++) { gen_steps[i].width_us = 10000; gen_steps[i].gap_us = 3000; }
    gen_steps[3].width_us = 0; gen_steps[3].gap_us = 0;
    st_arm(0xF0000004, 4, 5000);
    gen_start(4); st_state = ST_RUN_STUCK;
}
static void st_start_gap() {         // 10 pulses; the PC deliberately drops one frame and sends REPLAY (code 6)
    for (uint8_t i = 0; i < 10; i++) { gen_steps[i].width_us = 10000; gen_steps[i].gap_us = 3000; }
    st_arm(0xF0000005, 10, 5000);
    gen_start(10); st_state = ST_RUN_GAP;
}

static void st_group_results() {
    uint8_t idx = 0;
    for (uint8_t g = 0; g < N_GROUPS; g++) {
        uint64_t sum = 0; uint8_t c = 0;
        for (uint8_t i = 0; i < groups[g].count && idx < n_pw; i++, idx++) { sum += pulse_widths[idx]; c++; }
        uint64_t mean = c ? sum / c : 0, exp_ns = (uint64_t)groups[g].width_us * 1000ULL;
        Frame f; begin(f, T_SELFTEST_RESULT); put8(f, g + 1); put64(f, exp_ns); put64(f, mean); finish(f); send(f);
        if (groups[g].width_us >= 100000 && c) {
            double ppm = fabs((double)mean - (double)exp_ns) / (double)exp_ns * 1e6;
            if (ppm > 50.0) flag(A_CLOCK_FAULT, g + 1, (uint32_t)ppm);
        }
    }
}

static void st_poll() {
    if (st_state == ST_NONE) return;
    if (st_state == ST_FINISH) { st_state = ST_NONE; mode = IDLE; return; }
    if (st_state == ST_PAUSE) { if ((int32_t)(millis() - st_wait_until) >= 0) { st_wait_until = 0; st_state = st_after_pause; } return; }
    if (!gen_done) return;
    if (st_wait_until == 0) { st_wait_until = millis() + 100; return; }   // let the last edge arrive
    if ((int32_t)(millis() - st_wait_until) < 0) return;
    st_wait_until = 0;
    do_end(false);
    if (st_state == ST_RUN_CLEAN) { st_group_results(); st_start_glitch(); }
    else if (st_state == ST_RUN_GLITCH) st_start_missing();
    else if (st_state == ST_RUN_MISSING) st_start_stuck();
    else if (st_state == ST_RUN_STUCK) { GPIO.out_w1tc = (1u << PIN_GEN_OUT); st_start_gap(); }
    else if (st_state == ST_RUN_GAP) { st_after_pause = ST_FINISH; st_wait_until = millis() + 2500; st_state = ST_PAUSE; }  // window for the PC's REPLAY
}

// --------------------------------------------------------------------- host commands
static uint8_t rx[96]; static uint8_t rx_n = 0;
static uint16_t rd16(const uint8_t* p) { return (p[0] << 8) | p[1]; }
static uint32_t rd32(const uint8_t* p) { return ((uint32_t)rd16(p) << 16) | rd16(p + 2); }

static void send_heartbeat() {
    Frame f; begin(f, T_HEARTBEAT);
    put8(f, PROTO_VERSION); put64(f, (uint64_t)esp_timer_get_time()); put8(f, (uint8_t)mode);
    put16(f, (e_head - e_tail) & (EDGE_N - 1)); put16(f, dropped);
#ifdef COUNTER_WIFI
    put8(f, net.connected() ? 1 : 0);   // ws_clients field: 1 = TCP link to the PC up
#else
    put8(f, 0);
#endif
    
    put32(f, ESP.getFreeHeap()); put16(f, seq ? seq - 1 : 0); finish(f); send(f);
}

static void on_frame(uint8_t type, const uint8_t* p, uint8_t n) {
    if (type == T_ARM) {
        uint32_t sess = n >= 5 ? rd32(p + 1) : 0;
        uint8_t status = ACK_OK;
        if (n != 20) status = ACK_MALFORMED;
        else if (p[0] != PROTO_VERSION) status = ACK_BAD_VERSION;
        else if (mode != IDLE) status = ACK_BUSY;
        if (status == ACK_OK) {
            session = sess; reps = rd16(p + 8); min_width_ns = rd32(p + 10); max_width_s = rd32(p + 14);
            start_timeout_s = rd16(p + 18);
            route_capture(PIN_IN_DUT); clear_point(); mode = ARMED;
        }
        Frame f; begin(f, T_ARM_ACK); put32(f, sess); put8(f, status); put8(f, PROTO_VERSION); finish(f); send(f);
    } else if (type == T_END && mode == ARMED) { do_end(false); mode = IDLE;
    } else if (type == T_REPLAY && n == 6) {
        uint16_t from = rd16(p + 4);
        flag(A_SEQ_GAP, from, 0);
        for (uint16_t s = from; s != seq; s++) { int slot = s % REPLAY_N; if (replay_used[slot] && replay_seq[slot] == s) send(replay[slot]); }
    } else if (type == T_ACK && n == 6) {          // free every replay slot up to and including the acked seq
        uint16_t upto = rd16(p + 4);
        for (int i = 0; i < REPLAY_N; i++) if (replay_used[i] && (uint16_t)(upto - replay_seq[i]) < 0x8000) replay_used[i] = false;
    } else if (type == T_SELFTEST && mode == IDLE) { st_start_clean();
    } else if (type == T_STATUS) { send_heartbeat(); }
    // T_REFVAL: accepted, not shown in S1
}

static void feed_byte(uint8_t b) {
    if (rx_n == 0 && b != M_TO_COUNTER) return;
    rx[rx_n++] = b;
    if (rx_n >= 3 && rx_n == (uint8_t)(4 + rx[2])) {
        if (crc8(rx, rx_n - 1) == rx[rx_n - 1]) on_frame(rx[1], rx + 3, rx[2]);
        rx_n = 0;
    } else if (rx_n >= sizeof(rx)) rx_n = 0;
}

static void poll_serial() {
    while (Serial.available()) feed_byte(Serial.read());
#ifdef COUNTER_WIFI
    while (net.connected() && net.available()) feed_byte(net.read());
#endif
}

#ifdef COUNTER_WIFI
// Non-blocking WiFi + TCP keep-alive: (re)join WiFi, (re)connect to the PC every 2 s. Never blocks capture:
// the capture ISRs and the frame ring do not depend on this link; lost frames are re-requested by the PC (REPLAY).
static void wifi_poll() {
    // WiFi.begin() would rewrite the credentials to flash (NVS); a flash write stalls the cache and can freeze the capture ISRs for
    // seconds (grover n=6/n=7 runs lost pulses that way). persistent(false) in setup() stops the writes; autoReconnect does the
    // rejoining, so this only nudges it slowly with reconnect() instead of calling begin() every 5 s.
    if (WiFi.status() != WL_CONNECTED) { if (millis() - net_retry_ms > 15000) { net_retry_ms = millis(); WiFi.reconnect(); } return; }
    if (!net.connected() && millis() - net_retry_ms > 2000) {
        net_retry_ms = millis();
        net.stop();
        if (net.connect(PC_HOST, PC_PORT, 1000)) net.setNoDelay(true);
    }
}
#endif

void setup() {
    Serial.begin(BAUD);
#ifdef COUNTER_WIFI
    WiFi.persistent(false);          // never write SSID/password to flash (see wifi_poll)
    WiFi.setAutoReconnect(true);
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);   // no modem sleep: steadier latency for the serial/TCP side (capture itself is hardware)
    WiFi.begin(WIFI_SSID, WIFI_PASS);
#endif
    pinMode(PIN_LED, OUTPUT);
    pinMode(PIN_IN_DUT, INPUT); pinMode(PIN_IN_SELF, INPUT);   // input-only pads: firmware cannot drive them
    capture_init(); route_capture(PIN_IN_DUT);
    gen_init();
}

static uint32_t last_hb = 0;
void loop() {
    { uint32_t now = micros(); if (dbg_last_loop_us && now - dbg_last_loop_us > dbg_loop_max_us) dbg_loop_max_us = now - dbg_last_loop_us; dbg_last_loop_us = now; }
    poll_serial();
#ifdef COUNTER_WIFI
    wifi_poll();
#endif
    while (e_tail != e_head && mode != IDLE) {
        Edge e = edges[e_tail]; e_tail = (e_tail + 1) & (EDGE_N - 1);
        handle_edge(e);
    }
    if (mode == IDLE) e_tail = e_head;                   // nothing armed: discard edges
    if (mode == ARMED && have_rise && !stuck_flagged && max_width_s &&
        (esp_timer_get_time() - rise_us) > (int64_t)max_width_s * 1000000LL) {
        stuck_flagged = true; flag(A_STUCK_HIGH, falls, 2);
    }
    if (mode == ARMED && start_timeout_s && !start_flagged && falls == 0 && !have_rise &&
        (esp_timer_get_time() - arm_us) > (int64_t)start_timeout_s * 1000000LL) {
        start_flagged = true; flag(A_NEVER_STARTED, 0, 1);   // no first pulse within the start timeout
    }
    st_poll();
    if (millis() - last_hb >= 1000) {
        last_hb = millis(); digitalWrite(PIN_LED, !digitalRead(PIN_LED)); send_heartbeat();
#if COUNTER_DEBUG
        int16_t pcv = 0; pcnt_get_counter_value(PCNT_UNIT_0, &pcv);
        char dl[260];
        int dn = snprintf(dl, sizeof(dl), "\n#D mode=%d isr_r=%lu isr_f=%lu dup=%lu edge_mis=%lu ovf=%u ring=%u rises=%lu falls=%lu pcnt=%d level=%d loop_max_us=%lu send_max_us=%lu seq=%u dropped=%u heap=%lu\n",
                      (int)mode, (unsigned long)dbg_isr[0], (unsigned long)dbg_isr[1], (unsigned long)dbg_dup_cap, (unsigned long)dbg_edge_mismatch,
                      (unsigned)e_overflow, (unsigned)((e_head - e_tail) & (EDGE_N - 1)), (unsigned long)rises, (unsigned long)falls, (int)pcv,
                      gpio_get_level((gpio_num_t)cap_pin), (unsigned long)dbg_loop_max_us, (unsigned long)dbg_send_max_us, (unsigned)seq,
                      (unsigned)dropped, (unsigned long)ESP.getFreeHeap());
        Serial.write((const uint8_t*)dl, dn);
#ifdef COUNTER_WIFI
        if (net.connected()) net.write((const uint8_t*)dl, dn);   // same line on the TCP link: the sweep's client logs it (QLAB_COUNTER_DEBUGLOG)
#endif
        dbg_loop_max_us = 0; dbg_send_max_us = 0;
#endif
    }
}
