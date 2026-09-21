#!/usr/bin/env python3
# run_test.py — mocked-only tests for pc/run.py (the manual runner). No
# hardware, no `pio`, no real serial port is ever touched by this file --
# every test that would otherwise reach a real subprocess call monkeypatches
# `subprocess.run` first and asserts on what WOULD have been called.
#
# ไม่ใช้ pytest (รูปแบบเดียวกับ pc/shared/*_test.py) รันด้วย:
#   .venv/bin/python pc/run_test.py

import io
import sys
import contextlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))

import run as run_mod  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((name, status))
    print(f"[{status}] {name}  {detail}")


class RecordingSubprocess:
    """Replaces subprocess.run for the duration of a test. Records every call
    and returns a fake successful CompletedProcess-like object -- nothing it
    does can reach real hardware or a real `pio`/sweep-script subprocess."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, *args, **kwargs):
        self.calls.append(list(argv) if isinstance(argv, (list, tuple)) else argv)

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return _Result()

    def touched_hardware(self):
        """True if any recorded call looks like it would touch a real board:
        the delegated sweep scripts, or `pio` directly. git/lsof calls (used
        by the read-only preflight checks) are not hardware."""
        hw_markers = (
            str(run_mod.PHASE2_SCRIPTS["uno"]), str(run_mod.PHASE2_SCRIPTS["esp8266"]),
            str(run_mod.PHASE2_SCRIPTS["esp32"]), str(run_mod.PHASE3_SCRIPT), "pio",
        )
        for call in self.calls:
            if isinstance(call, list) and any(m in call for m in hw_markers):
                return True
        return False


@contextlib.contextmanager
def captured_stdout():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def with_mocked_subprocess(fn):
    """Run fn(rec) with subprocess.run replaced, then restore it unconditionally."""
    rec = RecordingSubprocess()
    original = run_mod.subprocess.run
    run_mod.subprocess.run = rec
    try:
        fn(rec)
    finally:
        run_mod.subprocess.run = original


# ---------------------------------------------------------------------------

def test_build_command_matches_every_board_algorithm_phase_combination():
    """The core deliverable: for EVERY (board, algorithm, phase) combination,
    build_command() -- the same pure function --dry-run and a real run both
    use -- resolves to the correct delegated script and flags. Produces a
    table as a side effect (printed), per the task's requirement."""
    table_rows = []
    all_ok = True
    for board in run_mod.BOARDS:
        for algorithm in run_mod.ALGORITHMS:
            for phase in run_mod.PHASES:
                argv = run_mod.build_command(
                    "PYTHON", board, algorithm, phase, port="/dev/cu.FAKE")
                if phase == 2:
                    expected_script = str(run_mod.PHASE2_SCRIPTS[board])
                    ok = (argv[:2] == ["PYTHON", expected_script]
                          and "--board" not in argv
                          and argv[2:6] == ["--port", "/dev/cu.FAKE", "--circuits", algorithm])
                else:
                    expected_script = str(run_mod.PHASE3_SCRIPT)
                    ok = (argv[:2] == ["PYTHON", expected_script]
                          and argv[2:8] == ["--board", board, "--port", "/dev/cu.FAKE",
                                             "--circuits", algorithm])
                all_ok = all_ok and ok
                table_rows.append((board, algorithm, phase, ok, " ".join(argv)))

    print("\n--- dry-run command table (board x algorithm x phase) ---")
    for board, algorithm, phase, ok, cmd in table_rows:
        print(f"  [{'OK' if ok else 'WRONG'}] board={board:8s} algorithm={algorithm:14s} "
              f"phase={phase}  ->  {cmd}")
    check("build_command resolves correctly for all 3*6*2=36 combinations",
          all_ok and len(table_rows) == 36, f"{len(table_rows)} combinations checked")


def test_dry_run_cli_all_combinations_no_hardware_subprocess():
    """Invoke the real CLI (main()) with --dry-run for every combination and
    assert: exit code 0, 'command:' printed, and -- critically -- no
    subprocess call ever touches a sweep script or pio."""

    def run_all(rec):
        all_zero = True
        any_command_line = True
        for board in run_mod.BOARDS:
            for algorithm in run_mod.ALGORITHMS:
                for phase in run_mod.PHASES:
                    with captured_stdout() as out:
                        code = run_mod.main(["--board", board, "--algorithm", algorithm,
                                              "--phase", str(phase), "--port", "/dev/cu.FAKE",
                                              "--dry-run"])
                    all_zero = all_zero and (code == 0)
                    any_command_line = any_command_line and ("command:" in out.getvalue())
        check("dry-run exits 0 for every combination", all_zero)
        check("dry-run prints a 'command:' line for every combination", any_command_line)
        check("dry-run never starts a subprocess that touches a sweep script or pio",
              not rec.touched_hardware(), f"{len(rec.calls)} subprocess call(s) recorded")

    with_mocked_subprocess(run_all)


def test_unsupported_combinations_rejected():
    cases_should_raise = []
    for board in ("esp8266", "esp32"):
        cases_should_raise.append((board, 2, True, None))  # --la on non-uno, phase2
    for board in run_mod.BOARDS:
        cases_should_raise.append((board, 3, True, None))  # --la on any phase3
    for board in ("esp8266", "esp32"):
        cases_should_raise.append((board, 2, False, 2.0))  # --upload-retry-settle-s non-uno
    cases_should_raise.append(("uno", 3, False, 2.0))  # --upload-retry-settle-s phase3

    all_raised = True
    for board, phase, la, settle in cases_should_raise:
        try:
            run_mod.validate_combination(board, "h_all", phase, la, settle)
            all_raised = False
        except run_mod.RunnerError:
            pass
    check("every known-unsupported (board, phase, flag) combination raises RunnerError",
          all_raised, f"{len(cases_should_raise)} cases checked")

    # the one combination that IS supported must NOT raise
    raised_when_should_not = False
    try:
        run_mod.validate_combination("uno", "h_all", 2, True, 2.0)
    except run_mod.RunnerError:
        raised_when_should_not = True
    check("--la and --upload-retry-settle-s together on (uno, phase2) is accepted",
          not raised_when_should_not)

    # unknown board/algorithm/phase themselves must also raise
    all_raised_2 = True
    for args in (("not-a-board", "h_all", 2, False, None),
                 ("uno", "not-a-circuit", 2, False, None),
                 ("uno", "h_all", 4, False, None)):
        try:
            run_mod.validate_combination(*args)
            all_raised_2 = False
        except run_mod.RunnerError:
            pass
    check("unknown board / algorithm / phase values are rejected", all_raised_2)


def test_missing_port_is_rejected_by_argparse():
    exited_with = None
    with captured_stdout():
        try:
            run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2"])
        except SystemExit as e:
            exited_with = e.code
    check("missing --port causes argparse to exit non-zero (required=True, never auto-guessed)",
          exited_with is not None and exited_with != 0, f"exit code: {exited_with}")


def test_dirty_tree_is_rejected_for_a_real_run_but_not_for_dry_run():
    def real_run(rec):
        original = run_mod.git_state
        run_mod.git_state = lambda: (False, "fake-dirty-ref")
        try:
            with captured_stdout() as out:
                code = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                                      "--port", "/dev/cu.FAKE", "--yes"])
            check("a dirty tree causes a real run to exit non-zero",
                  code != 0, f"exit code: {code}")
            check("a dirty tree's rejection never reaches a hardware-touching subprocess call",
                  not rec.touched_hardware())

            with captured_stdout() as out2:
                code2 = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                                       "--port", "/dev/cu.FAKE", "--dry-run"])
            check("a dirty tree does NOT block --dry-run (still just previews the command)",
                  code2 == 0, f"exit code: {code2}")
        finally:
            run_mod.git_state = original

    with_mocked_subprocess(real_run)


def test_reps_flag_validates_against_the_real_compile_time_constant():
    with captured_stdout():
        ret = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                            "--port", "/dev/cu.FAKE", "--reps", "30", "--dry-run"])
    check("--reps not matching the real REPS constant (100) is refused", ret != 0, f"ret={ret}")
    with captured_stdout():
        ret_ok = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                               "--port", "/dev/cu.FAKE", "--reps", "100", "--dry-run"])
    check("--reps matching the real REPS constant (100) is accepted", ret_ok == 0, f"ret={ret_ok}")


def test_n_range_note_for_steane_encode():
    inside = run_mod.n_range_note("steane_encode", 2, 14)
    outside = run_mod.n_range_note("steane_encode", 2, 5)
    not_fixed = run_mod.n_range_note("h_all", 2, 14)
    check("steane_encode inside range: informational note, not an error",
          inside is not None and "OUTSIDE" not in inside)
    check("steane_encode outside range: note says so explicitly",
          outside is not None and "OUTSIDE" in outside)
    check("non-fixed-n circuit: no note", not_fixed is None)


def main():
    test_build_command_matches_every_board_algorithm_phase_combination()
    test_dry_run_cli_all_combinations_no_hardware_subprocess()
    test_unsupported_combinations_rejected()
    test_missing_port_is_rejected_by_argparse()
    test_dirty_tree_is_rejected_for_a_real_run_but_not_for_dry_run()
    test_reps_flag_validates_against_the_real_compile_time_constant()
    test_n_range_note_for_steane_encode()

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
