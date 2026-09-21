#!/usr/bin/env python3
# run.py — single manual entry point: "run this one algorithm, on this one
# board, for this one phase." Contains NO data-collection logic of its own —
# every byte of collection/resume/retry/wall-classification behavior lives in
# the existing per-board sweep scripts (pc/phase2_sweep/{uno,esp8266,esp32}_sweep.py,
# pc/phase3_offload/sweep.py) and this file only validates inputs, runs
# read-only preflight checks, prints the exact command, and delegates to that
# script as a subprocess. Every flag, default, and path below was read from
# those scripts' own argparse blocks and from pc/shared/paths.py, not invented.
#
# This file never opens a serial port, never imports `serial`, and never calls
# `pio` itself — hardware access happens exclusively inside the delegated
# subprocess, which is the same subprocess a human would start by hand
# (see docs/manual_run_guide.md).

import argparse
import glob
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))

from shared.circuit_ids import CIRCUIT_IDS, FIXED_N_CIRCUITS  # noqa: E402
from shared import paths as sp  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared.telemetry import check_sleep_prevention  # noqa: E402

BOARDS = ("uno", "esp8266", "esp32")
ALGORITHMS = tuple(CIRCUIT_IDS.keys())  # h_all, bell_ghz, qft, grover, qpe, steane_encode
PHASES = (2, 3)

# One script per board for Phase 2; one shared script (--board selects) for Phase 3.
# Paths read directly from the repo layout -- pc/run.py does not duplicate any
# of these scripts' own logic, only invokes them.
PHASE2_SCRIPTS = {
    "uno": REPO_ROOT / "pc" / "phase2_sweep" / "uno_sweep.py",
    "esp8266": REPO_ROOT / "pc" / "phase2_sweep" / "esp8266_sweep.py",
    "esp32": REPO_ROOT / "pc" / "phase2_sweep" / "esp32_sweep.py",
}
PHASE3_SCRIPT = REPO_ROOT / "pc" / "phase3_offload" / "sweep.py"

# Each underlying script's own --n-max default (uno_sweep.py:326, esp8266_sweep.py:221,
# esp32_sweep.py:211; phase3's is None -> its own N_SAFETY_CAP=22, sweep.py:280-284).
# pc/run.py never overrides these unless the user passes --n-max explicitly --
# this table exists only so --dry-run and the preflight summary can report the
# value that will actually be used.
DEFAULT_N_MAX = {
    2: {"uno": 14, "esp8266": 16, "esp32": 18},
    3: {"uno": 22, "esp8266": 22, "esp32": 22},  # phase3_offload/sweep.py N_SAFETY_CAP
}

# --la exists ONLY on uno_sweep.py (Phase 2). Confirmed absent from esp8266_sweep.py,
# esp32_sweep.py, and pc/phase3_offload/sweep.py's argparse blocks.
LA_SUPPORTED = {(2, "uno")}

# --upload-retry-settle-s exists ONLY on uno_sweep.py. esp8266/esp32/phase3 use a
# different (currently non-configurable) settle path -- see their own argparse.
UPLOAD_RETRY_SETTLE_SUPPORTED = {(2, "uno")}

# Port-name sanity check only (a WARNING, never fatal -- see build_command's
# caller) mirroring pc/phase3_offload/sweep.py's own BOARDS[...]["port_globs"]
# and pc/phase2_sweep/uno_sweep.py's hardcoded "/dev/cu.usbmodem*".
PORT_GLOBS = {
    "uno": ["/dev/cu.usbmodem*"],
    "esp8266": ["/dev/cu.usbserial*", "/dev/cu.wchusbserial*", "/dev/cu.SLAB_USBtoUART*"],
    "esp32": ["/dev/cu.usbserial*", "/dev/cu.wchusbserial*", "/dev/cu.SLAB_USBtoUART*"],
}

UNVERIFIED_BOARDS = {"esp8266", "esp32"}  # never run on real hardware as of this file


class RunnerError(Exception):
    """Validation/preflight failure -- caller prints str(e) and exits non-zero."""


def build_command(python_exe, board, algorithm, phase, *,
                   n_start=None, n_max=None, build_timeout=None,
                   upload_retry_settle_s=None, la=False, port, fresh=False):
    """Return the exact argv list that would be delegated to, given already-
    validated arguments. Pure function, no I/O, no hardware -- used directly by
    --dry-run and by the tests, and reused unchanged for a real run."""
    if phase == 2:
        script = PHASE2_SCRIPTS[board]
        argv = [python_exe, str(script), "--port", port, "--circuits", algorithm]
    else:
        argv = [python_exe, str(PHASE3_SCRIPT), "--board", board, "--port", port,
                "--circuits", algorithm]

    if n_start is not None:
        argv += ["--n-start", str(n_start)]
    if n_max is not None:
        argv += ["--n-max", str(n_max)]
    if build_timeout is not None:
        argv += ["--build-timeout", str(build_timeout)]
    if upload_retry_settle_s is not None:
        argv += ["--upload-retry-settle-s", str(upload_retry_settle_s)]
    if la:
        argv += ["--la"]
    if fresh:
        argv += ["--fresh"]
    return argv


def validate_combination(board, algorithm, phase, la, upload_retry_settle_s):
    """Raise RunnerError for any (board, algorithm, phase, flag) combination this
    project's own code does not support. Never invents a restriction -- every
    check here maps to a concrete fact read from the underlying scripts."""
    if board not in BOARDS:
        raise RunnerError(f"unknown board {board!r} (choices: {', '.join(BOARDS)})")
    if algorithm not in ALGORITHMS:
        raise RunnerError(f"unknown algorithm {algorithm!r} (choices: {', '.join(ALGORITHMS)})")
    if phase not in PHASES:
        raise RunnerError(f"unknown phase {phase!r} (choices: 2, 3)")
    if la and (phase, board) not in LA_SUPPORTED:
        raise RunnerError(
            "--la is only implemented for Phase 2 on the Uno (uno_sweep.py). "
            f"Not available for board={board!r}, phase={phase}."
        )
    if upload_retry_settle_s is not None and (phase, board) not in UPLOAD_RETRY_SETTLE_SUPPORTED:
        raise RunnerError(
            "--upload-retry-settle-s is only implemented for Phase 2 on the Uno "
            f"(uno_sweep.py). Not available for board={board!r}, phase={phase}."
        )


def n_range_note(algorithm, n_start, n_max_effective):
    """Read-only informational note about steane_encode's fixed n (no collection
    logic duplicated -- pc/shared/circuit_ids.n_values_for_sweep is still the
    single source of truth the delegated script itself uses)."""
    fixed = FIXED_N_CIRCUITS.get(algorithm)
    if fixed is None:
        return None
    if n_start <= fixed <= n_max_effective:
        return f"steane_encode is fixed at n={fixed}; only that point will be attempted."
    return (f"steane_encode is fixed at n={fixed}, which is OUTSIDE the requested "
            f"range [{n_start}, {n_max_effective}] -- the delegated script will "
            f"print 'skip: ... is fixed-n and its n is outside [...]' and do nothing.")


def git_state():
    """Read-only. Returns (clean: bool, description: str)."""
    try:
        status = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                                 capture_output=True, text=True, timeout=10).stdout
        ref = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"],
                              cwd=REPO_ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        return (status.strip() == "", ref)
    except Exception as e:  # noqa: BLE001 -- best-effort informational check
        return (False, f"git check failed: {e}")


def port_matches_board(board, port):
    """Read-only glob check -- never opens the port."""
    return any(Path(port) == Path(p) for pattern in PORT_GLOBS[board] for p in glob.glob(pattern))


def port_exists(port):
    return Path(port).exists()


def port_holder_pids(port):
    """Read-only: which OS processes currently have this device file open, if
    any (via `lsof`, never by opening the port ourselves). Empty list if lsof
    is unavailable or finds nothing -- best-effort, matches
    telemetry.check_sleep_prevention()'s own "best-effort" precedent."""
    if not shutil.which("lsof"):
        return None  # unknown, not "none" -- caller must distinguish
    try:
        out = subprocess.run(["lsof", "-t", port], capture_output=True, text=True, timeout=5).stdout
        return [pid for pid in out.split() if pid]
    except Exception:  # noqa: BLE001
        return None


def resume_summary(board, algorithm, phase):
    """Read-only summary of what already exists under data/raw/ for this
    (board, algorithm, phase) -- reads memory_wall.csv (phase 2) or
    session_log.csv (phase 3) directly with csv.DictReader; never writes
    anything, never imports pc/shared/resume.py's write-side logic."""
    import csv
    directory = sp.raw_dir(board, algorithm, phase)
    if not directory.exists():
        return f"{directory} does not exist yet -- fresh start."
    path = sp.memory_wall_csv_path(board, algorithm, phase) if phase == 2 \
        else sp.session_log_csv_path(board, algorithm, phase)
    if not path.exists():
        return f"{directory} exists but {path.name} does not -- fresh start."
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return f"{path} exists but is empty -- fresh start."
    by_status = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    ns = sorted({r["n"] for r in rows}, key=lambda x: int(x))
    parts = ", ".join(f"{k}={v}" for k, v in sorted(by_status.items()))
    return f"{path}: {len(rows)} point(s) recorded (n={','.join(ns)}), {parts}"


def print_preflight(board, algorithm, phase, port, dry_run):
    print("--- preflight ---")
    clean, ref = git_state()
    print(f"git: {'clean' if clean else 'DIRTY'}  ({ref})")
    if not clean and not dry_run:
        raise RunnerError(
            f"working tree is dirty ({ref}) -- refusing to start real hardware "
            f"collection against an uncommitted/uncertain source state. "
            f"`git status` to see what's dirty, then commit or stash it first "
            f"(see docs/manual_run_guide.md's preflight checklist). "
            f"(--dry-run ignores this so the command can still be previewed.)")

    sleep_check = check_sleep_prevention()
    print(f"sleep prevention: prevented={sleep_check.get('prevented')} "
          f"({sleep_check.get('note')})")

    print(f"resume state: {resume_summary(board, algorithm, phase)}")

    if dry_run:
        print("port: [dry-run] skipping pio device list / port checks -- no hardware access")
        return

    if not port_exists(port):
        raise RunnerError(f"port {port!r} does not exist (no such device file). "
                           f"Run `pio device list` yourself to find the current name -- "
                           f"this runner never auto-guesses --port.")
    if not port_matches_board(board, port):
        print(f"WARNING: {port!r} does not match board {board!r}'s usual pattern "
              f"({PORT_GLOBS[board]}) -- continuing, since custom setups exist, "
              f"but double check this is the right device.")
    holders = port_holder_pids(port)
    if holders is None:
        print("port lock check: lsof unavailable, could not verify -- proceed with care "
              "(never run two sweeps against the same port at once, see "
              "docs/manual_run_guide.md's \"never do this\" list)")
    elif holders:
        raise RunnerError(f"port {port!r} is already held by process(es) {holders} -- "
                           f"refusing to start a second one against the same port "
                           f"(this exact collision has corrupted a real run before; "
                           f"see run_log.md).")
    else:
        print(f"port lock check: {port!r} is free")

    result = subprocess.run(["pio", "device", "list"], capture_output=True, text=True, timeout=15)
    if port not in result.stdout:
        print(f"WARNING: {port!r} not seen in `pio device list` output right now -- "
              f"it may still work (ports re-enumerate during upload) but confirm "
              f"the board is actually connected.")
    else:
        print(f"pio device list: {port!r} confirmed present")


def confirm(auto_yes):
    if auto_yes:
        return True
    if not sys.stdin.isatty():
        print("refusing to prompt on a non-interactive stdin -- pass --yes to proceed "
              "without a prompt (e.g. when running under a scheduler or background job)")
        return False
    resp = input("Proceed and touch hardware? [y/N] ").strip().lower()
    return resp in ("y", "yes")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Run one algorithm on one board for one phase, by delegating to "
                    "the existing sweep script. See docs/run/<board>.md and "
                    "docs/manual_run_guide.md for details.")
    ap.add_argument("--board", required=True, choices=BOARDS)
    ap.add_argument("--algorithm", required=True, choices=ALGORITHMS)
    ap.add_argument("--phase", required=True, type=int, choices=PHASES)
    ap.add_argument("--port", required=True,
                     help="e.g. /dev/cu.usbmodem1101 -- never auto-guessed")
    ap.add_argument("--n-start", type=int, default=None,
                     help="passed through as --n-start; omit to use the delegated "
                          "script's own default (2)")
    ap.add_argument("--n-max", type=int, default=None,
                     help="passed through as --n-max; omit to use the delegated "
                          "script's own per-board default -- see DEFAULT_N_MAX in this file")
    ap.add_argument("--reps", type=int, default=None,
                     help="VALIDATION ONLY, not passed through -- REPS is a compile-time "
                          "firmware constant (pc/shared/timing_model.REPS, currently "
                          f"{tm.REPS}) with no CLI equivalent in any delegated script. "
                          "If given, this must equal that constant or the run is refused.")
    ap.add_argument("--build-timeout", type=int, default=None, dest="build_timeout")
    ap.add_argument("--upload-retry-settle-s", type=float, default=None,
                     dest="upload_retry_settle_s")
    ap.add_argument("--la", action="store_true")
    ap.add_argument("--fresh", action="store_true",
                     help="passed through as --fresh -- see docs/manual_run_guide.md's "
                          "warning against using this 'just in case'")
    ap.add_argument("--dry-run", action="store_true",
                     help="validate and print the exact command; never touch hardware, "
                          "never call pio, never prompt")
    ap.add_argument("--yes", action="store_true",
                     help="skip the interactive y/n confirmation before touching hardware")
    args = ap.parse_args(argv)

    try:
        validate_combination(args.board, args.algorithm, args.phase, args.la,
                              args.upload_retry_settle_s)
        if args.reps is not None and args.reps != tm.REPS:
            raise RunnerError(
                f"--reps {args.reps} given, but REPS is fixed at {tm.REPS} at compile "
                f"time in firmware (pc/shared/timing_model.REPS) -- there is no way to "
                f"change it from the command line. Refusing rather than silently "
                f"ignoring your request.")

        if args.board in UNVERIFIED_BOARDS or args.phase == 3:
            print(f"*** UNVERIFIED: board={args.board!r} phase={args.phase} has never been "
                  f"run against real hardware as of this file. Timing/wall estimates below "
                  f"come only from pc/shared/timing_model.py and docs/preflight_report.md's "
                  f"compile-only build matrix -- treat every number as a prediction, not a "
                  f"measurement. Do not assume Uno's measured behavior transfers. ***")

        n_max_effective = args.n_max if args.n_max is not None else DEFAULT_N_MAX[args.phase][args.board]
        n_start_effective = args.n_start if args.n_start is not None else 2
        note = n_range_note(args.algorithm, n_start_effective, n_max_effective)
        if note:
            print(note)

        python_exe = sys.executable
        argv_cmd = build_command(
            python_exe, args.board, args.algorithm, args.phase,
            n_start=args.n_start, n_max=args.n_max, build_timeout=args.build_timeout,
            upload_retry_settle_s=args.upload_retry_settle_s, la=args.la,
            port=args.port, fresh=args.fresh)

        print("command:", " ".join(argv_cmd))

        if args.dry_run:
            print_preflight(args.board, args.algorithm, args.phase, args.port, dry_run=True)
            print("[dry-run] stopping here -- no subprocess started")
            return 0

        print_preflight(args.board, args.algorithm, args.phase, args.port, dry_run=False)

        if not confirm(args.yes):
            print("not confirmed -- exiting without touching hardware")
            return 1

    except RunnerError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    try:
        result = subprocess.run(argv_cmd, cwd=REPO_ROOT)
        return result.returncode
    except KeyboardInterrupt:
        print("\ninterrupted -- the delegated script's own resume logic (default, no "
              "flag needed) means you can safely re-run the exact same command above "
              "and it will pick up where it left off (see docs/manual_run_guide.md, "
              "'Resume ทำงานอย่างไร'). Any in-flight point without a terminal record "
              "row will be re-run from its first rep, not resumed mid-point.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
