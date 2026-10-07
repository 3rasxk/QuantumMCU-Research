# session.py -- per-run manager of the reference (counter) side of a sweep. The sweep scripts call
# these hooks around each point; every problem here is logged to ref_issues.log and recorded in the
# reference files, and NEVER changes a micros() row, a point status, or the sweep's control flow
# (except `should_stop()`, which the sweep may use to stop a run whose counter has been gone for
# two consecutive points -- an owner-policy decision documented in docs/design/system_design.md).
#
# Order per point:  arm_point -> (sweep builds/uploads/runs the target, reads micros() rows)
#                   -> finish_point(micros) -> pulses + report written, comparison joined.
# The counter port belongs to this session's client only; the target port is the sweep's own.

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from counter import crosscheck as cc
from counter import proto as cp
from counter import ref_schema as rs

ARM_ACK_TIMEOUT_S = 3.0
REPORT_TIMEOUT_S = 10.0
HEARTBEAT_MAX_AGE_S = 5.0
SAFETY_FACTOR = 5.0
MIN_MAX_WIDTH_S = 130
MAX_CONSECUTIVE_LOST = 2


def max_width_for(board, circuit, n, phase=2):
    """Longest plausible single pulse (one rep) in seconds for ARM's max_width_s (u32): the model's
    per-rep time x a safety factor, never below 130 s. The model is an ESTIMATE, hence the factor.
    Phase 3: one pulse is one request/response round trip; the offload firmware gives up after 5 s
    (RESPONSE_TIMEOUT_MS), so the 130 s floor already covers it and the Phase 2 model does not apply."""
    if phase == 3:
        return MIN_MAX_WIDTH_S
    from shared import timing_model as tm
    per_rep = tm.expected_exec_time_us(board, circuit, n) / 1e6
    return max(MIN_MAX_WIDTH_S, int(per_rep * SAFETY_FACTOR) + 10)


class CounterSession:
    def __init__(self, client, board, circuit, ref_dir, reps=100, session_id="", counter_session_base=0x10000000,
                 start_timeout_s=0, live=None, phase=2):
        self.client = client
        self.phase = phase
        self.board, self.circuit = board, circuit
        self.ref_dir = Path(ref_dir)
        self.reps = reps
        self.session_id = session_id
        self.base = counter_session_base
        self.start_timeout_s = start_timeout_s
        self.armed_n = None
        self.armed_ok = False
        self.consecutive_lost = 0
        self.log_path = self.ref_dir / "ref_issues.log"
        self.live = live            # optional counter.live.LiveState: read-only view, never affects the run

    # -------------------------------------------------------------- logging
    def _ctx(self, **kw):
        if self.live is not None:
            try:
                self.live.set_context(**kw)
            except Exception:  # noqa: BLE001
                pass

    def _publish(self, n, status, pulses, micros_us):
        if self.live is None:
            return
        try:
            import statistics as st
            good = [p[3] / 1000.0 for p in pulses if not p[5] & 1]
            row = {"n": n, "ref_status": status, "pulses": len(pulses), "clean": len(good), "reps": self.reps,
                   "counter_median_us": round(st.median(good), 3) if good else None,
                   "micros_median_us": round(st.median(micros_us), 3) if micros_us else None}
            if row["counter_median_us"] and row["micros_median_us"]:
                row["diff_us"] = round(row["micros_median_us"] - row["counter_median_us"], 3)
                row["diff_pct"] = round(row["diff_us"] / row["counter_median_us"] * 100, 3)
            self.live.point_result(row)
            self.live.set_context(phase="idle", ref_status=status)
        except Exception:  # noqa: BLE001
            pass

    def issue(self, n, message):
        try:
            self.ref_dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat()}  {self.board}/{self.circuit}/n={n}  {message}\n")
        except OSError:
            pass   # logging must never take the sweep down

    # -------------------------------------------------------------- per point
    def arm_point(self, n):
        """ARM the counter for this point. Returns True if armed. A failure is logged and the point
        simply runs without a reference."""
        self.armed_n, self.armed_ok = n, False
        self._ctx(board=self.board, circuit=self.circuit, n=n, reps=self.reps, phase="arming", reset_pulses=True, ref_status=None)
        self.client.drain()
        hb = self.client.last_heartbeat
        if hb is not None and hb[1][2] == 1:   # counter still ARMED from an interrupted run: ARM would be refused (BUSY)
            try:
                self.client.send(cp.encode(cp.T_END, self.base + n))
                self.client.wait_for(cp.T_REPORT, ARM_ACK_TIMEOUT_S)
                self.client.drain()
                self.issue(n, "counter was still ARMED from an earlier interrupted run: sent END to clear it before ARM")
            except Exception as e:  # noqa: BLE001
                self.issue(n, f"could not clear a stale ARMED state: {e}")
        try:
            frame = cp.encode_arm(self.base + n, self.board, self._circuit_id(), n, self.reps, 500,
                                  max_width_for(self.board, self.circuit, n, self.phase), self.start_timeout_s)
            self.client.send(frame)
        except Exception as e:  # noqa: BLE001
            self.issue(n, f"ARM send failed: {e}")
            return False
        got = self.client.wait_for(cp.T_ARM_ACK, ARM_ACK_TIMEOUT_S)
        if got is None:
            self.issue(n, "no ARM_ACK within timeout")
            return False
        _, (sess, status, ver) = got
        if status != cp.ACK_OK:
            self.issue(n, f"ARM refused: status={status} counter_proto={ver}")
            return False
        self.armed_ok = True
        self._ctx(phase="armed: target running")
        return True

    def _circuit_id(self):
        from shared.circuit_ids import CIRCUIT_IDS
        return CIRCUIT_IDS[self.circuit]

    def finish_point(self, n, micros_us=None, target_ran=True, aborted=False, reps_expected=None):
        """Disarm, collect, write reference files, join. `micros_us`: exec_time_us per rep from this
        point's raw.csv (None if the target produced none). Returns the ref_status string."""
        # a time-capped point (sweep stopped after fewer reps than armed for) compares only the reps it collected;
        # the board keeps running after the sweep stops reading, so later pulses are not paired
        reps = self.reps if reps_expected is None else reps_expected
        collected = []
        report = None
        status = "ok"
        self.last_result = None
        self._ctx(phase="point done: collecting reference")
        if not self.armed_ok:
            status = "arm_failed"
        else:
            alive = self.client.alive(HEARTBEAT_MAX_AGE_S)
            try:
                self.client.send(cp.encode(cp.T_END, self.base + n))
            except Exception as e:  # noqa: BLE001
                self.issue(n, f"END send failed: {e}")
                alive = False
            got = self.client.wait_for(cp.T_REPORT, REPORT_TIMEOUT_S, collect=collected)
            if got is None:
                status = "counter_lost"
                self.issue(n, "no REPORT after END (counter lost or silent)")
            else:
                report = got[1]
            collected += self.client.drain()
            if report is not None:
                self._recover_gaps(n, collected, report)
            if status == "ok" and not alive:
                self.issue(n, "heartbeat stale at END (report still received)")
        pulses = [f for t, f in collected if t == cp.T_PULSE]
        anomalies = [(f[0], f[1], f[2]) for t, f in collected if t == cp.T_ANOMALY]
        pulses = self._dedupe(pulses)
        all_pulses = pulses
        # Phase 3: between two reps the line is idle only ~20 ms (the firmware's delay(20); the wait for the PC is INSIDE
        # the pulse), so the restart gap (~0.32 s on the ESP8266) is only ~16x the median gap, not 50x: lower the factor
        runs = cc.split_runs(pulses, gap_factor=5) if self.phase == 3 else cc.split_runs(pulses)
        if len(runs) > 1:
            self.issue(n, f"{len(runs)} target runs seen by the counter ({[len(r) for r in runs]} pulses); pairing the LAST run (the one whose rows the sweep read)")
            pulses = runs[-1]
            if len([p for p in pulses if not p[5] & 1]) == reps:
                # the counter's own 'extra pulse' flag (code 2) came from the earlier, cut-short run: not an anomaly of the paired run
                anomalies = [x for x in anomalies if x[1] != cp.A_EXTRA]
        if reps < self.reps:
            pulses = pulses[:reps]
            anomalies = [a for a in anomalies if a[0] in {p[0] for p in pulses}]
        codes = sorted({a[1] for a in anomalies})
        if status == "ok":
            if aborted:
                status = "aborted"
            elif not target_ran:
                status = "no_target_run"
            elif len([p for p in pulses if not p[5] & 1]) != reps:
                status = "count_mismatch"
            elif codes:
                status = "anomaly"
        if status in ("arm_failed", "counter_lost"):
            self.consecutive_lost += 1
        else:
            self.consecutive_lost = 0
        for code in codes:
            self.issue(n, f"anomaly code {code} ({cp.ANOMALY_NAMES.get(code, '?')})")
        self._write(n, all_pulses, anomalies, report, status, codes, used=pulses)
        if status in ("ok", "anomaly", "count_mismatch") and micros_us is not None:
            result = cc.join_point(pulses, micros_us, reps, self.board)
            self.last_result = result
            cc.write_compare(self.ref_dir, self.session_id, self.board, self.circuit, n, result, status)
            if result["status"] != "joined":
                self.issue(n, f"comparison refused: {result['status']} {result['notes']}")
        elif status in ("arm_failed", "counter_lost", "no_target_run", "aborted"):
            self.last_result = {"status": f"refused_{status}", "summary": {}, "notes": status}
            cc.write_compare(self.ref_dir, self.session_id, self.board, self.circuit, n, self.last_result, status)
        self.armed_ok = False
        self._publish(n, status, pulses, micros_us)
        return status

    def _recover_gaps(self, n, collected, report, tries=2, wait_s=3.0):
        """Frames lost on the link (WiFi drop) show up as missing sequence numbers below the counter's own pulse
        count: ask the counter to REPLAY from the first missing seq (it keeps the last 512 pulses) and merge.
        The counter raises code 6 when asked; the point is then an `anomaly`, never silently repaired."""
        for _ in range(tries):
            have = {f[0] for t, f in collected if t == cp.T_PULSE}
            missing = [q for q in range(report[2]) if q not in have]
            if not missing:
                return
            self.issue(n, f"sequence gap: missing {missing[:5]}{'...' if len(missing) > 5 else ''}; requesting REPLAY from {missing[0]}")
            try:
                self.client.send(cp.encode(cp.T_REPLAY, self.base + n, missing[0]))
            except Exception as e:  # noqa: BLE001
                self.issue(n, f"REPLAY send failed: {e}")
                return
            end = time.monotonic() + wait_s
            while time.monotonic() < end:
                time.sleep(0.05)
                collected += self.client.drain()
                have = {f[0] for t, f in collected if t == cp.T_PULSE}
                if all(q in have for q in missing):
                    break

    @staticmethod
    def _dedupe(pulses):
        """REPLAY can resend pulses already received: keep the first copy of each seq, in seq order."""
        seen, out = set(), []
        for p in pulses:
            if p[0] not in seen:
                seen.add(p[0])
                out.append(p)
        return sorted(out, key=lambda p: p[0])

    def _write(self, n, pulses, anomalies, report, status, codes, used=None):
        used = pulses if used is None else used
        by_seq = {a[0]: a[1] for a in anomalies}
        rs.append_rows(self.ref_dir / "ref_pulses.csv", [{
            "session_id": self.session_id, "counter_session": self.base + n, "board": self.board,
            "circuit": self.circuit, "n": n, "seq": p[0], "rise_us": p[1], "width_ticks": p[2],
            "width_us": round(p[3] / 1000.0, 3), "wraps": p[4], "flags": p[5], "anomaly_code": by_seq.get(p[0], 0)}
            for p in pulses])
        widths = sorted(p[3] for p in pulses)
        rs.append_rows(self.ref_dir / "ref_points.csv", [{
            "session_id": self.session_id, "board": self.board, "circuit": self.circuit, "n": n,
            "reps_expected": self.reps, "pulses_received": len(pulses), "pulses_used": len([p for p in used if not p[5] & 1]),
            "ref_status": status, "anomaly_mask": report[3] if report else "", "anomaly_codes": " ".join(map(str, codes)),
            "min_ns": widths[0] if widths else "", "median_ns": widths[len(widths) // 2] if widths else "",
            "max_ns": widths[-1] if widths else "", "report_pulses": report[2] if report else "",
            "pcnt_count": report[7] if report else "", "overruns": report[8] if report else "",
            "counter_proto": cp.PROTO_VERSION, "timestamp_utc": datetime.now(timezone.utc).isoformat()}])

    def should_stop(self):
        return self.consecutive_lost >= MAX_CONSECUTIVE_LOST

    def abort(self, n=None):
        """Ctrl+C / error path: best-effort END, then record what arrived. Never raises."""
        try:
            if self.armed_ok and self.armed_n is not None:
                self.finish_point(self.armed_n, None, target_ran=False, aborted=True)
        except Exception as e:  # noqa: BLE001
            self.issue(self.armed_n, f"abort handling failed: {e}")

    def close(self):
        try:
            self.client.close()
        except Exception:  # noqa: BLE001
            pass


def write_env_sidecar(path, *, counter_port, counter_fw_sha256="", pin_map=None, divider=None, calibration=None,
                      selftest_note="self-loopback only", extra=None):
    doc = {"schema_version": rs.REF_ENV_SCHEMA_VERSION, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
           "counter_port": counter_port, "counter_fw_sha256": counter_fw_sha256, "counter_proto": cp.PROTO_VERSION,
           "pin_map": pin_map or {}, "divider": divider or {}, "calibration": calibration or {},
           "selftest": selftest_note, "counter_wifi": "off"}
    if extra:
        doc.update(extra)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1) + "\n")
    return doc
