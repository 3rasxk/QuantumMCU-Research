// Gate-SEQUENCE logging stand-in for firmware/common/qsim.hpp: the unmodified circuits.hpp is executed and every gate call is printed
// as "H q", "CX c t" or "CP c t theta" so the order, qubits and angles can be compared with the Qiskit circuit of Phase 1 / Phase 3.
#pragma once
#include <math.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t qsize_t;
struct Cplx { float re; float im; };
static inline void qsim_init0(Cplx*, qsize_t) {}
static inline void qsim_h(Cplx*, qsize_t, int q) { printf("H %d\n", q); }
static inline void qsim_cnot(Cplx*, qsize_t, int c, int t) { printf("CX %d %d\n", c, t); }
static inline void qsim_cphase(Cplx*, qsize_t, int c, int t, float th) { printf("CP %d %d %.9g\n", c, t, (double)th); }
