// Prints "circuit,n,init,h,cnot,cphase" for the four paper circuits, n = 2..N_MAX (argv[1]).
#include <stdio.h>
#include <stdlib.h>
#include "circuits.hpp"
unsigned long long g_cnt_init, g_cnt_h, g_cnt_cnot, g_cnt_cphase;
typedef void (*Fn)(Cplx*, qsize_t, int);
int main(int argc, char** argv) {
    int nmax = argc > 1 ? atoi(argv[1]) : 14;
    const char* names[4] = {"h_all", "bell_ghz", "qft", "grover"};
    Fn fns[4] = {circuit_h_all, circuit_bell_ghz, circuit_qft, circuit_grover};
    for (int c = 0; c < 4; c++)
        for (int n = 2; n <= nmax; n++) {
            g_cnt_init = g_cnt_h = g_cnt_cnot = g_cnt_cphase = 0;
            fns[c](0, (qsize_t)1 << n, n);
            printf("%s,%d,%llu,%llu,%llu,%llu\n", names[c], n, g_cnt_init, g_cnt_h, g_cnt_cnot, g_cnt_cphase);
        }
    return 0;
}
