#include <stdlib.h>
#include <string.h>
#include "circuits.hpp"
int main(int argc, char** argv) {
    const char* name = argv[1];
    int n = atoi(argv[2]);
    qsize_t N = (qsize_t)1 << n;
    if (!strcmp(name, "grover")) circuit_grover(0, N, n);
    else if (!strcmp(name, "qft")) circuit_qft(0, N, n);
    else if (!strcmp(name, "bell_ghz")) circuit_bell_ghz(0, N, n);
    else if (!strcmp(name, "h_all")) circuit_h_all(0, N, n);
    return 0;
}
