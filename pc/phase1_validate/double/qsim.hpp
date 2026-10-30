// qsim.hpp (DOUBLE-precision variant) -- PC-only, never built for a board.
// Stand-in for firmware/common/qsim.hpp: same kernels, same loop structure, same gate sequence, but every `float` is a `double`.
// pc/phase1_validate/build_double.sh copies the UNMODIFIED firmware/common/circuits.hpp next to this file (so `#include "qsim.hpp"`
// finds THIS header), and this header ends with macros that turn the circuit file's own `float`, `sqrtf` and QSIM_PI into double,
// so the circuit definitions (gate order, iteration count, angles) are exactly the firmware's source text, evaluated in double.
// Purpose (Phase 4 item 1): separate "float32 rounding" from "definition or bug" in the grover infidelity. firmware/ is not changed.
#pragma once
#include <math.h>
#include <stdint.h>

typedef uint32_t qsize_t;

struct Cplx {
    double re;
    double im;
};

static inline Cplx cplx_mul(Cplx a, Cplx b) {
    Cplx r;
    r.re = a.re * b.re - a.im * b.im;
    r.im = a.re * b.im + a.im * b.re;
    return r;
}

static inline void qsim_init0(Cplx* state, qsize_t n_states) {
    state[0].re = 1.0;
    state[0].im = 0.0;
    for (qsize_t i = 1; i < n_states; i++) {
        state[i].re = 0.0;
        state[i].im = 0.0;
    }
}

static inline void qsim_h(Cplx* state, qsize_t n_states, int target) {
    const double INV_SQRT2 = 0.70710678118654752440;
    qsize_t mask = (qsize_t)1 << target;
    for (qsize_t i = 0; i < n_states; i++) {
        if ((i & mask) == 0) {
            qsize_t j = i | mask;
            Cplx a = state[i];
            Cplx b = state[j];
            state[i].re = (a.re + b.re) * INV_SQRT2;
            state[i].im = (a.im + b.im) * INV_SQRT2;
            state[j].re = (a.re - b.re) * INV_SQRT2;
            state[j].im = (a.im - b.im) * INV_SQRT2;
        }
    }
}

static inline void qsim_cnot(Cplx* state, qsize_t n_states, int control, int target) {
    qsize_t cmask = (qsize_t)1 << control;
    qsize_t tmask = (qsize_t)1 << target;
    for (qsize_t i = 0; i < n_states; i++) {
        if ((i & cmask) && !(i & tmask)) {
            qsize_t j = i | tmask;
            Cplx tmp = state[i];
            state[i] = state[j];
            state[j] = tmp;
        }
    }
}

static inline void qsim_cphase(Cplx* state, qsize_t n_states, int control, int target, double theta) {
    qsize_t cmask = (qsize_t)1 << control;
    qsize_t tmask = (qsize_t)1 << target;
    Cplx phase;
    phase.re = cos(theta);
    phase.im = sin(theta);
    for (qsize_t i = 0; i < n_states; i++) {
        if ((i & cmask) && (i & tmask)) {
            state[i] = cplx_mul(state[i], phase);
        }
    }
}

// The circuit file is included AFTER this header's own definitions, so these macros only affect circuits.hpp's text:
//   float -> double (angles, iteration-count arithmetic), sqrtf/fmodf -> double versions, QSIM_PI -> the double constant.
#define QSIM_PI 3.14159265358979323846
#define float double
#define sqrtf sqrt
#define fmodf fmod
