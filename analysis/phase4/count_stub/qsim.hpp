// Counting stand-in for firmware/common/qsim.hpp. It replaces the gate kernels with counters so the
// UNMODIFIED firmware/common/circuits.hpp can be executed on the PC to count gate calls per kind.
#pragma once
#include <math.h>
#include <stdint.h>
typedef uint32_t qsize_t;
struct Cplx { float re; float im; };
extern unsigned long long g_cnt_init, g_cnt_h, g_cnt_cnot, g_cnt_cphase;
static inline void qsim_init0(Cplx*, qsize_t) { g_cnt_init++; }
static inline void qsim_h(Cplx*, qsize_t, int) { g_cnt_h++; }
static inline void qsim_cnot(Cplx*, qsize_t, int, int) { g_cnt_cnot++; }
static inline void qsim_cphase(Cplx*, qsize_t, int, int, float) { g_cnt_cphase++; }
