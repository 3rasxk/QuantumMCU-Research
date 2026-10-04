#!/usr/bin/env python3
# run_test.py — mocked-only tests for pc/run.py (the manual runner). No
# hardware, no `pio`, no real serial port is ever touched by this file --
# every test that would otherwise reach a real subprocess call monkeypatches
# `subprocess.run` first and asserts on what WOULD have been called.
#
# ไม่ใช้ pytest (รูปแบบเดียวกับ pc/shared/*_test.py) รันด้วย:
#   .venv/bin/python pc/run_test.py

import contextlib
import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
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
    check("build_command resolves correctly for all 3*4*2=24 combinations",
          all_ok and len(table_rows) == 24, f"{len(table_rows)} combinations checked")


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
    # (board, phase, ref, settle, counter_port, port)
    cases_should_raise = []
    for board in run_mod.BOARDS:
        cases_should_raise.append((board, 3, True, None, "/dev/cu.C", "/dev/cu.T"))   # counter on any phase 3
        cases_should_raise.append((board, 2, True, None, None, "/dev/cu.T"))          # --ref counter without --counter-port
        cases_should_raise.append((board, 2, True, None, "/dev/cu.T", "/dev/cu.T"))   # counter port == target port
        cases_should_raise.append((board, 2, False, None, "/dev/cu.C", "/dev/cu.T"))  # --counter-port without --ref counter
    for board in ("esp8266", "esp32"):
        cases_should_raise.append((board, 2, False, 2.0, None, None))  # --upload-retry-settle-s non-uno
    cases_should_raise.append(("uno", 3, False, 2.0, None, None))  # --upload-retry-settle-s phase3

    all_raised = True
    for board, phase, ref, settle, cport, port in cases_should_raise:
        try:
            run_mod.validate_combination(board, "h_all", phase, ref, settle, cport, port)
            all_raised = False
        except run_mod.RunnerError:
            pass
    check("every known-unsupported (board, phase, flag) combination raises RunnerError",
          all_raised, f"{len(cases_should_raise)} cases checked")

    # supported: --ref counter with a distinct explicit counter port on every board, phase 2
    raised_when_should_not = False
    for board in run_mod.BOARDS:
        try:
            run_mod.validate_combination(board, "h_all", 2, True, 2.0 if board == "uno" else None, "/dev/cu.C", "/dev/cu.T")
        except run_mod.RunnerError:
            raised_when_should_not = True
    check("--ref counter with a distinct --counter-port is accepted on uno, esp8266, esp32 (phase 2)",
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


def test_dirty_tree_warns_but_does_not_block_a_real_run():
    """2026-09-21 standing-decision change: a dirty tree is now a WARNING for
    the owner's own runs, not a refusal -- the exact commit/dirty flag is
    still recorded automatically (telemetry.write_environment_metadata's
    existing git_commit/git_dirty fields, untouched by this change)."""
    def real_run(rec):
        saved = (run_mod.git_state, run_mod.port_exists,
                 run_mod.port_matches_board, run_mod.port_holder_pids)
        run_mod.git_state = lambda: (False, "fake-dirty-ref")
        run_mod.port_exists = lambda port: True
        run_mod.port_matches_board = lambda board, port: True
        run_mod.port_holder_pids = lambda port: []
        try:
            with captured_stdout() as out:
                code = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                                      "--port", "/dev/cu.FAKE", "--yes"])
            text = out.getvalue()
            check("dirty tree prints a WARNING but does not refuse the run",
                  "WARNING" in text and "dirty" in text.lower() and code == 0,
                  f"exit code: {code}")
            check("a dirty real run still reaches the delegated (mocked) subprocess",
                  rec.touched_hardware())
        finally:
            (run_mod.git_state, run_mod.port_exists,
             run_mod.port_matches_board, run_mod.port_holder_pids) = saved

    with_mocked_subprocess(real_run)

    with captured_stdout() as out2:
        code2 = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                               "--port", "/dev/cu.FAKE", "--dry-run"])
    check("a dirty tree does NOT block --dry-run either (still just previews the command)",
          code2 == 0, f"exit code: {code2}")


def test_busy_port_is_refused():
    def real_run(rec):
        saved = (run_mod.port_exists, run_mod.port_matches_board, run_mod.port_holder_pids)
        run_mod.port_exists = lambda port: True
        run_mod.port_matches_board = lambda board, port: True
        run_mod.port_holder_pids = lambda port: ["12345"]  # "another process" holds it
        try:
            with captured_stdout():
                code = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                                      "--port", "/dev/cu.FAKE", "--yes"])
            check("a port already held by another process is refused",
                  code != 0, f"exit code: {code}")
            check("a busy-port refusal never reaches the delegated subprocess",
                  not rec.touched_hardware())
        finally:
            (run_mod.port_exists, run_mod.port_matches_board,
             run_mod.port_holder_pids) = saved

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


def test_n_range_note_for_fixed_n_circuits():
    saved = dict(run_mod.FIXED_N_CIRCUITS)
    run_mod.FIXED_N_CIRCUITS["fixed_demo"] = 7  # no fixed-n circuit exists in the plan any more
    try:
        inside = run_mod.n_range_note("fixed_demo", 2, 14)
        outside = run_mod.n_range_note("fixed_demo", 2, 5)
    finally:
        run_mod.FIXED_N_CIRCUITS.clear()
        run_mod.FIXED_N_CIRCUITS.update(saved)
    not_fixed = run_mod.n_range_note("h_all", 2, 14)
    check("fixed-n circuit inside range: informational note, not an error",
          inside is not None and "OUTSIDE" not in inside)
    check("fixed-n circuit outside range: note says so explicitly",
          outside is not None and "OUTSIDE" in outside)
    check("no circuit in the plan is fixed-n", run_mod.FIXED_N_CIRCUITS == {})
    check("non-fixed-n circuit: no note", not_fixed is None)


def test_removed_circuits_are_rejected_with_a_clear_message():
    import io
    for algorithm in ("qpe", "steane_encode"):
        err = io.StringIO()
        saved_err = sys.stderr
        sys.stderr = err
        try:
            with captured_stdout():
                code = run_mod.main(["--board", "uno", "--algorithm", algorithm, "--phase", "2",
                                      "--port", "/dev/cu.FAKE", "--dry-run"])
        finally:
            sys.stderr = saved_err
        check(f"{algorithm}: runner refuses (exit 1) with the removal message",
              code == 1 and f"{algorithm} removed from the experiment plan on 2026-10-03" in err.getvalue(),
              err.getvalue().strip())
    check("plan scope is exactly the four circuits",
          run_mod.ALGORITHMS == ("h_all", "bell_ghz", "qft", "grover"))


# ---------------------------------------------------------------------------
# --fresh / archive / min-n clamping (2026-09-21 standing-decision change)
# ---------------------------------------------------------------------------

def test_fresh_default_n_start_is_the_circuit_minimum_and_clamping_works():
    expected = {"h_all": 1, "bell_ghz": 2, "qft": 1, "grover": 2}
    all_default_ok = True
    for algorithm, minimum in expected.items():
        n, notice = run_mod.effective_n_start_for_fresh(algorithm, None)
        all_default_ok = all_default_ok and (n == minimum) and (notice is None)
    check("fresh run, --n-start omitted, defaults to each circuit's own minimum "
          "(not the legacy uniform 2)", all_default_ok, str(expected))

    n, notice = run_mod.effective_n_start_for_fresh("grover", 1)
    check("fresh run, explicit --n-start below the circuit minimum: clamped up",
          n == 2 and notice is not None and "clamped" in notice.lower())
    check("clamp notice says never a failure/wall",
          "never" in notice.lower() and ("failure" in notice.lower() or "wall" in notice.lower()))

    n2, notice2 = run_mod.effective_n_start_for_fresh("h_all", 5)
    check("fresh run, explicit --n-start at/above the minimum: passed through unclamped",
          n2 == 5 and notice2 is None)


def test_fresh_dry_run_cli_shows_clamp_and_archive_destination():
    with captured_stdout() as out:
        code = run_mod.main(["--board", "uno", "--algorithm", "grover", "--phase", "2",
                              "--port", "/dev/cu.FAKE", "--fresh", "--n-start", "1", "--dry-run"])
    text = out.getvalue()
    check("fresh dry-run with a too-low --n-start: exits 0, shows the clamp notice, "
          "shows the resulting --n-start 2 in the command",
          code == 0 and "clamped" in text.lower() and "--n-start 2" in text)

    h_all_archive_dir = run_mod.REPO_ROOT / "data" / "archive" / "phase2" / "uno" / "h_all"
    before_archives = sorted(h_all_archive_dir.glob("*")) if h_all_archive_dir.exists() else []
    with captured_stdout() as out2:
        code2 = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                               "--port", "/dev/cu.FAKE", "--fresh", "--dry-run"])
    text2 = out2.getvalue()
    check("fresh dry-run: exits 0 and either names the planned archive destination "
          "under data/archive/ (data exists) or says nothing exists yet (post-restart tree)",
          code2 == 0 and ("data/archive/" in text2 or "nothing exists yet" in text2))
    after_archives = sorted(h_all_archive_dir.glob("*")) if h_all_archive_dir.exists() else []
    check("fresh dry-run never actually creates an archive for (uno, h_all, phase2) "
          "-- no file moved despite naming the destination in its preview",
          after_archives == before_archives)


def _make_fake_dataset(root, board, algorithm, phase, n_points=2, ref=False):
    """Build a minimal but realistic data/raw + figures + docs tree for one
    (board, algorithm, phase, ref), entirely inside a scratch root -- never
    touches the real repo's data/. `ref` picks the no_ref/with_ref bucket
    (2026-09-22, see pc/shared/paths.py)."""
    bucket = "with_ref" if ref else "no_ref"
    raw_dir = root / "data" / "raw" / f"phase{phase}" / board / algorithm / bucket
    (raw_dir / "env").mkdir(parents=True, exist_ok=True)
    with open(raw_dir / "raw.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "rep", "exec_time_us"])
        for n in range(2, 2 + n_points):
            for rep in range(3):
                w.writerow([board, algorithm, n, rep, 100 + n])
    with open(raw_dir / "memory_wall.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "status"])
        for n in range(2, 2 + n_points):
            w.writerow([board, algorithm, n, "ok"])
    (raw_dir / "env" / "fake-session.json").write_text('{"schema_version": 2}')

    figures_dir = root / "data" / "figures" / board / algorithm / bucket
    figures_dir.mkdir(parents=True, exist_ok=True)
    (figures_dir / "exec_time_vs_n.png").write_bytes(b"fake-png-bytes")

    docs_dir = root / "docs" / "analysis" / board
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / f"{algorithm}.md").write_text("# fake analysis doc\n")
    return raw_dir, figures_dir, docs_dir / f"{algorithm}.md"


def test_archive_move_and_manifest_correctness():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw_dir, figures_dir, doc_path = _make_fake_dataset(root, "uno", "h_all", 2)

        saved_root = run_mod.REPO_ROOT
        saved_sp_root = sp_module().REPO_ROOT
        run_mod.REPO_ROOT = root
        sp_module().REPO_ROOT = root
        try:
            # pre-move byte content, for post-move identity comparison
            originals = {}
            for f in list(raw_dir.rglob("*")) + list(figures_dir.rglob("*")) + [doc_path]:
                if f.is_file():
                    originals[f.name] = f.read_bytes()

            dest = run_mod.perform_fresh_archive(
                "uno", "h_all", 2, "fake command", timestamp="20260101T000000Z")

            check("archive move returns the expected destination path",
                  dest == run_mod.archive_dest_dir("uno", "h_all", 2, "20260101T000000Z"))
            check("original raw dir no longer exists after the move",
                  not raw_dir.exists())
            check("original figures dir no longer exists after the move",
                  not figures_dir.exists())
            check("original analysis doc no longer exists after the move",
                  not doc_path.exists())

            manifest_path = dest / "MANIFEST.json"
            check("MANIFEST.json was written", manifest_path.exists())
            manifest = json.loads(manifest_path.read_text())
            check("manifest reason is 'fresh run'", manifest["reason"] == "fresh run")
            check("manifest lists raw, figures, and docs categories",
                  {"raw", "figures", "docs"} <= {e["category"] for e in manifest["files"]})

            moved_files = {f.name: f for f in dest.rglob("*") if f.is_file()
                           and f.name != "MANIFEST.json"}
            same_bytes = all(moved_files.get(name) is not None
                              and moved_files[name].read_bytes() == content
                              for name, content in originals.items())
            check("every moved file's bytes are byte-identical to the pre-move original",
                  same_bytes, f"{len(originals)} files compared")

            raw_csv_entry = next(e for e in manifest["files"]
                                  if e["relative_path"] == "raw.csv")
            check("manifest's raw.csv row count matches the real row count (6 data rows)",
                  raw_csv_entry["rows"] == 6)
            expected_sha = hashlib.sha256(originals["raw.csv"]).hexdigest()
            check("manifest's raw.csv sha256 matches the pre-move file's real hash",
                  raw_csv_entry["sha256"] == expected_sha)
        finally:
            run_mod.REPO_ROOT = saved_root
            sp_module().REPO_ROOT = saved_sp_root


def test_archive_abort_on_failure_leaves_original_byte_identical():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw_dir, figures_dir, doc_path = _make_fake_dataset(root, "uno", "h_all", 2)
        before = {f: f.read_bytes() for f in
                  list(raw_dir.rglob("*")) + list(figures_dir.rglob("*")) + [doc_path]
                  if f.is_file()}

        saved_root = run_mod.REPO_ROOT
        saved_sp_root = sp_module().REPO_ROOT
        run_mod.REPO_ROOT = root
        sp_module().REPO_ROOT = root
        try:
            # pre-create the destination so perform_fresh_archive must refuse
            # (never overwrite an existing archive folder) before moving anything
            dest = run_mod.archive_dest_dir("uno", "h_all", 2, "20260101T000000Z")
            dest.mkdir(parents=True)
            (dest / "placeholder").write_text("pre-existing")

            raised = False
            try:
                run_mod.perform_fresh_archive("uno", "h_all", 2, "fake command",
                                               timestamp="20260101T000000Z")
            except run_mod.RunnerError:
                raised = True
            check("archiving into an already-existing destination raises RunnerError "
                  "instead of overwriting", raised)

            after = {f: f.read_bytes() for f in
                     list(raw_dir.rglob("*")) + list(figures_dir.rglob("*")) + [doc_path]
                     if f.is_file()}
            check("original data is completely untouched after an aborted archive "
                  "(same files, same bytes)", before == after, f"{len(before)} files compared")
        finally:
            run_mod.REPO_ROOT = saved_root
            sp_module().REPO_ROOT = saved_sp_root


def test_second_fresh_run_creates_a_different_timestamped_archive():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fake_dataset(root, "uno", "h_all", 2)

        saved_root = run_mod.REPO_ROOT
        saved_sp_root = sp_module().REPO_ROOT
        run_mod.REPO_ROOT = root
        sp_module().REPO_ROOT = root
        try:
            dest1 = run_mod.perform_fresh_archive(
                "uno", "h_all", 2, "cmd1", timestamp="20260101T000000Z")
            # a second dataset appears (as if collection had run and produced new data)
            _make_fake_dataset(root, "uno", "h_all", 2)
            dest2 = run_mod.perform_fresh_archive(
                "uno", "h_all", 2, "cmd2", timestamp="20260101T000100Z")

            check("two fresh archives of the same (board, algorithm, phase) get two "
                  "distinct timestamped destinations", dest1 != dest2)
            check("both archive folders still exist independently (nothing overwritten)",
                  dest1.exists() and dest2.exists())
        finally:
            run_mod.REPO_ROOT = saved_root
            sp_module().REPO_ROOT = saved_sp_root


def sp_module():
    import shared.paths as sp
    return sp


def _make_scratch_uno_h_all(root):
    """Realistic enough scratch Uno h_all dataset for phase2_uno_run_plots.py
    (the real one was archived in the 2026-10-03 restart): raw.csv + memory_wall.csv."""
    raw_dir = root / "data" / "raw" / "phase2" / "uno" / "h_all" / "no_ref"
    (raw_dir / "env").mkdir(parents=True)
    with open(raw_dir / "raw.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "rep", "exec_time_us", "free_heap_before",
                    "free_heap_after", "timeout_budget_s"])
        for n in range(2, 8):
            for rep in range(100):
                w.writerow(["uno", "h_all", n, rep, 280 * 2 ** (n - 2) + rep % 3, 1780, 1780, 90])
    with open(raw_dir / "memory_wall.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "theoretical_bytes", "compile_ram_used_bytes",
                    "compile_ram_pct", "status", "timestamp_utc", "retry_count",
                    "timeout_budget_s", "expected_point_s", "retry_policy"])
        for n in range(2, 8):
            w.writerow(["uno", "h_all", n, 8 * 2 ** n, 200 + 8 * 2 ** n, 11.0, "ok",
                        "2026-10-03T00:00:00+00:00", 0, 90, 0.1, "allowed"])
        w.writerow(["uno", "h_all", 8, 2048, 2250, 109.9, "build_overflow",
                    "2026-10-03T00:00:00+00:00", 0, 90, 6.0, "allowed"])


def test_archive_independence():
    """(3) Independence proof: nothing outside pc/run.py / pc/run_test.py
    references the new data/archive/ concept anywhere in the codebase, and
    deleting data/archive/ changes nothing about what the analysis pipeline
    produces (proven by actually running it, on a scratch copy, before and
    after deletion, and comparing sha256 of every generated figure)."""
    grep = subprocess.run(
        ["grep", "-rniE", "archive", "--include=*.py",
         str(run_mod.REPO_ROOT / "pc"), str(run_mod.REPO_ROOT / "analysis")],
        capture_output=True, text=True)
    hits = [ln for ln in grep.stdout.splitlines()
            if "/pc/run.py:" not in ln and "/pc/run_test.py:" not in ln
            # paths_test.py verifies the 2026-10-03 restart archive's MANIFEST
            # hashes -- a test reading the archive, not pipeline code
            and "/pc/shared/paths_test.py:" not in ln]
    new_concept_markers = ("data/archive", "archive_dest_dir", "perform_fresh_archive",
                           "plan_fresh_archive", "_archive_sources", "MANIFEST.json")
    check("grep for 'archive' across pc/ and analysis/: every hit outside this runner "
          "is the pre-existing resume.archive_existing (in-place *.pre-fresh rename, a "
          "different, untouched mechanism) -- none reference the new data/archive/ "
          "concept, its path helper, or its functions",
          all(not any(m in ln for m in new_concept_markers) for ln in hits),
          f"{len(hits)} hit(s) outside pc/run.py/run_test.py")

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        copy_root = Path(tmp) / "repo"
        shutil.copytree(run_mod.REPO_ROOT / "pc" / "shared", copy_root / "pc" / "shared")
        shutil.copytree(run_mod.REPO_ROOT / "analysis", copy_root / "analysis")
        _make_scratch_uno_h_all(copy_root)
        (copy_root / "data" / "figures").mkdir(parents=True)
        (copy_root / "docs" / "analysis" / "uno").mkdir(parents=True)

        script = copy_root / "analysis" / "phase2_uno_run_plots.py"
        cmd = [sys.executable, str(script), "--board", "uno", "--circuit", "h_all"]

        def run_and_hash():
            subprocess.run(cmd, cwd=copy_root, capture_output=True, text=True, timeout=60)
            fig_dir = copy_root / "data" / "figures" / "uno" / "h_all" / "no_ref"
            return {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                    for f in sorted(fig_dir.glob("*.png"))} if fig_dir.exists() else {}

        before = run_and_hash()
        check("analysis pipeline (on a real scratch copy, real h_all data) produced "
              "at least one figure before touching data/archive/ at all",
              len(before) > 0, f"{len(before)} figure(s)")

        archive_dummy = copy_root / "data" / "archive" / "phase2" / "uno" / "h_all" / "20260101T000000Z"
        archive_dummy.mkdir(parents=True)
        (archive_dummy / "MANIFEST.json").write_text('{"reason": "fake, for this test only"}')
        (archive_dummy / "raw" / "raw.csv").parent.mkdir(parents=True)
        (archive_dummy / "raw" / "raw.csv").write_text("board,circuit,n,rep,exec_time_us\n")

        shutil.rmtree(copy_root / "data" / "archive")

        after = run_and_hash()
        check("analysis pipeline output is byte-identical (same figures, same sha256) "
              "after data/archive/ is populated then deleted",
              before == after and len(after) > 0, f"{len(before)} vs {len(after)} figures")


def main():
    # run_mod.main() now writes to the run-history ledger (pc/shared/run_history.py)
    # on every call -- redirect it to a scratch file for this WHOLE test module
    # (not just the tests that also redirect REPO_ROOT/sp.REPO_ROOT) so no test
    # run here ever appends to the real repo's data/run_history.jsonl. See
    # pc/run_history_test.py for the ledger's own dedicated tests.
    import tempfile
    real_ledger = REPO_ROOT / "data" / "run_history.jsonl"
    real_ledger_before = real_ledger.read_bytes() if real_ledger.exists() else None
    ledger_scratch = Path(tempfile.mkdtemp(prefix="run_test_ledger_")) / "run_history.jsonl"
    run_mod.rh.LEDGER_PATH = ledger_scratch

    test_build_command_matches_every_board_algorithm_phase_combination()
    test_dry_run_cli_all_combinations_no_hardware_subprocess()
    test_unsupported_combinations_rejected()
    test_missing_port_is_rejected_by_argparse()
    test_dirty_tree_warns_but_does_not_block_a_real_run()
    test_busy_port_is_refused()
    test_reps_flag_validates_against_the_real_compile_time_constant()
    test_n_range_note_for_fixed_n_circuits()
    test_removed_circuits_are_rejected_with_a_clear_message()
    test_fresh_default_n_start_is_the_circuit_minimum_and_clamping_works()
    test_fresh_dry_run_cli_shows_clamp_and_archive_destination()
    test_archive_move_and_manifest_correctness()
    test_archive_abort_on_failure_leaves_original_byte_identical()
    test_second_fresh_run_creates_a_different_timestamped_archive()
    test_archive_independence()

    check("no test run touched the real data/run_history.jsonl ledger",
          (real_ledger.read_bytes() if real_ledger.exists() else None) == real_ledger_before)

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
