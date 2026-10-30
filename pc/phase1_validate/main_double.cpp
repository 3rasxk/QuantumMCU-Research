// main_double.cpp -- Phase 4 item 1: the Phase 1 runner of main.cpp, built against the double-precision qsim stand-in.
// Same CLI and CSV output as main.cpp (index,re,im), 17 significant digits. Build with build_double.sh (PC only).
// standard headers first: qsim.hpp (included by circuits.hpp) defines `float` as a macro, which must only see the circuit text
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <vector>
#include "circuits.hpp"
#undef float
#undef sqrtf
#undef fmodf

int main(int argc, char** argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s <h_all|bell_ghz|qft|grover> <n>\n", argv[0]);
        return 1;
    }
    const char* circuit = argv[1];
    int n = atoi(argv[2]);
    if (n < 1 || n > 20) { fprintf(stderr, "error: n out of range (1..20)\n"); return 1; }
    qsize_t n_states = (qsize_t)1 << n;
    std::vector<Cplx> state(n_states);
    if (strcmp(circuit, "h_all") == 0) circuit_h_all(state.data(), n_states, n);
    else if (strcmp(circuit, "bell_ghz") == 0) circuit_bell_ghz(state.data(), n_states, n);
    else if (strcmp(circuit, "qft") == 0) circuit_qft(state.data(), n_states, n);
    else if (strcmp(circuit, "grover") == 0) circuit_grover(state.data(), n_states, n);
    else { fprintf(stderr, "error: unknown circuit '%s'\n", circuit); return 1; }
    printf("n=%d\n", n);
    printf("index,re,im\n");
    for (qsize_t i = 0; i < n_states; i++) printf("%u,%.17g,%.17g\n", (unsigned)i, state[i].re, state[i].im);
    return 0;
}
