"""Chunked Aer simulation of the Phase 3 grover circuit (2026-10-08).

Same gate sequence as analysis/phase1_compare.build_qiskit_circuit("grover", n) (which mirrors firmware/common/circuits.hpp),
but built and run in slices: each step (the initial H layer, then per iteration the two multi-controlled phases and the H / X
layers) is built as its own small circuit, run through Aer with the previous statevector loaded by set_statevector, and
dropped. The PC still builds and simulates every gate, uncached, per request, so what Phase 3 measures does not change; only
the peak memory does. The one-shot run needs about 1.7 GB at grover n=11, 2.5 GB of Qiskit circuit alone at n=12 and 11 GB at
n=13 (15.7 M / 67 M gates), which got the sweep SIGKILLed on an 8.6 GB machine; chunked, the peak is one multi-controlled phase
(about 0.5 M gates at n=13).
"""
import numpy as np

# above this many gates the sweep uses the chunked path (grover n >= 12); smaller circuits keep the one-shot path the existing
# data (n <= 11) was measured with
CHUNK_THRESHOLD_GATES = 4_000_000


def _steps(n):
    """Yield functions qc -> None; applied in order they are exactly the grover circuit of build_qiskit_circuit."""
    from phase1_compare import _mc_phase_qiskit

    def h_layer(qc):
        for q in range(n):
            qc.h(q)

    def x_layer(qc):
        for q in range(n):
            qc.h(q)
            qc.p(np.pi, q)
            qc.h(q)

    def mc(qc):
        _mc_phase_qiskit(qc, n - 1, n - 1, np.pi)

    yield h_layer
    iterations = max(int((np.pi / 4) * np.sqrt(1 << n)), 1)
    for _ in range(iterations):
        for step in (mc, h_layer, x_layer, mc, x_layer, h_layer):
            yield step


def simulate_grover_chunked(sim, n):
    """Final statevector of grover on n qubits, built and run step by step."""
    from qiskit import QuantumCircuit

    state = None
    for step in _steps(n):
        qc = QuantumCircuit(n)
        if state is not None:
            qc.set_statevector(state)
        step(qc)
        qc.save_statevector()
        state = np.asarray(sim.run(qc).result().get_statevector(qc).data)
    return state
