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
#
# 2026-09-21 standing-decision change (see run_log.md): the owner may now run
# any algorithm/board/phase at any time via this runner without a Claude Code
# approval round, and --fresh here means something new -- it ARCHIVES existing
# data (data/archive/, moved not deleted, with a MANIFEST.json) instead of the
# delegated scripts' own in-place *.pre-fresh-<ts>.csv rename, and a fresh run
# starts at each circuit's own minimum *meaningful* n (not always 2) rather
# than sending a degenerate point to real hardware. All of that logic is new
# code in THIS file only -- pc/shared/circuit_ids.py, resume.py, telemetry.py,
# and every delegated sweep script are untouched, and this file still never
# passes --fresh through to them (see build_command): by the time it would
# delegate, the archive step has already cleared the directory, so the
# delegated script's own resume logic already sees a true fresh start on its
# own, with no flag needed.

import argparse
import csv
import glob
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))

from shared.circuit_ids import (CIRCUIT_IDS, EXPERIMENT_CIRCUITS, FIXED_N_CIRCUITS,  # noqa: E402
                                REMOVED_CIRCUITS, removed_message)
from shared import paths as sp  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared import run_history as rh  # noqa: E402
from shared import eta  # noqa: E402
from shared.telemetry import check_sleep_prevention  # noqa: E402

BOARDS = ("uno", "esp8266", "esp32")
ALGORITHMS = EXPERIMENT_CIRCUITS  # h_all, bell_ghz, qft, grover (qpe/steane_encode removed 2026-10-03)
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

# The delegated scripts' own uniform default when --n-start is omitted (every
# one of them: uno_sweep.py:325, esp8266_sweep.py:220, esp32_sweep.py:210,
# phase3_offload/sweep.py:279 -- all "type=int, default=2", identical across
# every circuit). Only used to describe today's status quo in notices below;
# never changed for a non-fresh run (standing decision, see module docstring).
LEGACY_UNIFORM_N_START_DEFAULT = 2

# Per-circuit minimum n at which the circuit is actually MEANINGFUL, not just
# "doesn't crash." Investigated read-only against firmware/common/circuits.hpp,
# pc/shared/timing_model.py, and analysis/phase1_compare.py -- see run_log.md's
# 2026-09-21 entry for the full table and citations. None of the six circuits
# crash the C++ firmware at n=1 (confirmed: no assert in qsim.hpp, every
# circuit's own gate-count formula in timing_model.py evaluates cleanly at
# n=1), but four of them are semantically degenerate below this value:
#   h_all:         1  -- 1-qubit superposition is a real, valid state (no stated minimum)
#   qft:           1  -- 1-qubit QFT literally IS a single H gate (no stated minimum)
#   bell_ghz:      2  -- circuits.hpp:28 "n=2 คือ Bell state แท้ ๆ" -- n=1 runs
#                        (just H(0), the CNOT loop is empty) but produces no
#                        entanglement at all, not a Bell/GHZ state by any reading
#   grover:        2  -- circuits.hpp:150 AND analysis/phase1_compare.py:32,
#                        both independently state n>=2 ("no control qubit left
#                        for the oracle's multi-controlled-Z" / "-phase")
#
# (qpe and steane_encode were removed from the experiment plan on 2026-10-03.)
#
# No circuit has ever been Phase 1 (Qiskit) validated at n=1 --
# analysis/phase1_compare.py:31's own N_VALUES_DEFAULT starts at 2 for every
# circuit. The 2026-10-03 re-validation (data/raw/phase1/) covers every n the
# new plan collects, including n=1 for h_all/qft.
MIN_VALID_N = {
    "h_all": 1,
    "bell_ghz": 2,
    "qft": 1,
    "grover": 2,
}

# --ref counter (ESP32 pulse counter) is implemented in all three Phase 2 sweep scripts through
# pc/counter/hooks.py; Phase 3 does not use the counter (docs/design/system_design.md, open decision 4).
REF_SUPPORTED = {(2, "uno"), (2, "esp8266"), (2, "esp32")}
REF_CHOICES = ("none", "counter")

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
                   upload_retry_settle_s=None, ref=False, counter_port=None, counter_cal=None, port):
    """Return the exact argv list that would be delegated to, given already-
    validated arguments. Pure function, no I/O, no hardware -- used directly by
    --dry-run and by the tests, and reused unchanged for a real run.

    Deliberately never adds --fresh: when args.fresh is set, main() archives
    the existing directory away BEFORE calling this (see perform_fresh_archive),
    so the delegated script always finds a clean/absent directory and takes its
    own default (empty) resume path on its own -- no flag needed, and the
    delegated scripts' own, different --fresh semantics (in-place
    *.pre-fresh-<ts>.csv rename) is never invoked by this runner."""
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
    if ref:
        argv += ["--ref", "counter", "--counter-port", counter_port]
        if counter_cal:
            argv += ["--counter-cal", counter_cal]
    return argv


def validate_combination(board, algorithm, phase, ref, upload_retry_settle_s, counter_port=None, port=None):
    """Raise RunnerError for any (board, algorithm, phase, flag) combination this
    project's own code does not support. Never invents a restriction -- every
    check here maps to a concrete fact read from the underlying scripts."""
    if board not in BOARDS:
        raise RunnerError(f"unknown board {board!r} (choices: {', '.join(BOARDS)})")
    if algorithm in REMOVED_CIRCUITS:
        raise RunnerError(removed_message(algorithm))
    if algorithm not in ALGORITHMS:
        raise RunnerError(f"unknown algorithm {algorithm!r} (choices: {', '.join(ALGORITHMS)})")
    if phase not in PHASES:
        raise RunnerError(f"unknown phase {phase!r} (choices: 2, 3)")
    if ref and (phase, board) not in REF_SUPPORTED:
        raise RunnerError(
            "--ref counter is only implemented for Phase 2 (uno, esp8266, esp32); Phase 3 does not use the "
            f"counter. Not available for board={board!r}, phase={phase}."
        )
    if ref and not counter_port:
        raise RunnerError("--ref counter requires --counter-port (never auto-guessed)")
    if ref and port and counter_port == port:
        raise RunnerError("--counter-port must differ from --port: the counter port is never shared with the target port")
    if counter_port and not ref:
        raise RunnerError("--counter-port given without --ref counter")
    if upload_retry_settle_s is not None and (phase, board) not in UPLOAD_RETRY_SETTLE_SUPPORTED:
        raise RunnerError(
            "--upload-retry-settle-s is only implemented for Phase 2 on the Uno "
            f"(uno_sweep.py). Not available for board={board!r}, phase={phase}."
        )


def n_range_note(algorithm, n_start, n_max_effective):
    """Read-only informational note about a fixed-n circuit (none exist in the
    current plan, FIXED_N_CIRCUITS is empty; kept generic -- no collection
    logic duplicated, pc/shared/circuit_ids.n_values_for_sweep is still the
    single source of truth the delegated script itself uses)."""
    fixed = FIXED_N_CIRCUITS.get(algorithm)
    if fixed is None:
        return None
    if n_start <= fixed <= n_max_effective:
        return f"{algorithm} is fixed at n={fixed}; only that point will be attempted."
    return (f"{algorithm} is fixed at n={fixed}, which is OUTSIDE the requested "
            f"range [{n_start}, {n_max_effective}] -- the delegated script will "
            f"print 'skip: ... is fixed-n and its n is outside [...]' and do nothing.")


def effective_n_start_for_fresh(algorithm, requested_n_start):
    """Only called when --fresh is set (standing decision, see module docstring
    -- non-fresh runs never clamp, never get an auto default beyond what the
    delegated script itself already defaults to, per "keep current
    append/resume behavior unchanged"). Returns (n_start_to_use, notice_or_None).

    Default when omitted: the circuit's own MIN_VALID_N (not the legacy
    uniform 2). Clamp when explicitly requested below that minimum: never
    silently send a degenerate point to real hardware, never log it as a
    failure or a wall -- it's just never attempted."""
    minimum = MIN_VALID_N[algorithm]
    if requested_n_start is None:
        return minimum, None
    if requested_n_start < minimum:
        notice = (f"NOTICE: --n-start {requested_n_start} is below {algorithm!r}'s "
                  f"minimum meaningful n ({minimum}) -- clamped up to {minimum} for "
                  f"this fresh run. n={requested_n_start} is never sent to the board "
                  f"and is not logged as a failure or a wall. See MIN_VALID_N in "
                  f"pc/run.py / docs/run/<board>.md for why.")
        return minimum, notice
    return requested_n_start, None


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


def git_commit_hash():
    """Read-only full commit hash -- for the archive MANIFEST.json. Empty
    string on any failure (best-effort, never raises -- matches
    telemetry._git_commit_and_dirty()'s own fallback shape, though this is an
    independent read, not a call into telemetry.py)."""
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                               capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


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


def resume_summary(board, algorithm, phase, ref=False):
    """Read-only summary of what already exists under data/raw/ for this
    (board, algorithm, phase, ref) -- reads memory_wall.csv (phase 2) or
    session_log.csv (phase 3) directly with csv.DictReader; never writes
    anything, never imports pc/shared/resume.py's write-side logic. `ref`
    selects the no_ref/with_ref bucket (2026-09-22, pc/shared/paths.py) --
    resume must only ever compare within the same bucket a run would
    actually write into."""
    directory = sp.raw_dir(board, algorithm, phase, ref)
    if not directory.exists():
        return f"{directory} does not exist yet -- fresh start."
    path = sp.memory_wall_csv_path(board, algorithm, phase, ref) if phase == 2 \
        else sp.session_log_csv_path(board, algorithm, phase, ref)
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


def point_counts_by_status(board, algorithm, phase, ref=False):
    """Read-only status->count dict from the terminal-record file, for the
    run-history ledger's "point/status counts if it completed" field (see
    pc/shared/run_history.py) -- same file resume_summary() reads, just
    returned as data instead of a formatted string. None if the file doesn't
    exist (e.g. a dry-run, or a run that never wrote a single point)."""
    path = sp.memory_wall_csv_path(board, algorithm, phase, ref) if phase == 2 \
        else sp.session_log_csv_path(board, algorithm, phase, ref)
    if not path.exists():
        return None
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Archive (--fresh) -- new in this file only. Nothing under pc/shared/,
# analysis/, or any delegated sweep script reads from data/archive/ -- proven
# by pc/run_test.py's archive-independence test (greps the whole tree for
# "archive" and shows every hit is in this file, its tests, or docs).
# ---------------------------------------------------------------------------

def archive_dest_dir(board, algorithm, phase, timestamp):
    """data/archive/phase<N>/<board>/<circuit>/<UTC timestamp>/ -- deliberately
    phase-outermost, mirroring pc/shared/paths.raw_dir()'s own established
    convention (data/raw/phase<N>/<board>/<circuit>/, fixed that way on
    purpose per run_log.md's 2026-09-20 "folder structure correction" entry)
    rather than the board/algorithm/phase order first suggested for this
    archive path -- kept consistent with the rest of the project instead."""
    return REPO_ROOT / "data" / "archive" / f"phase{phase}" / board / algorithm / timestamp


def _utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _csv_row_count(path):
    """Data rows only (header excluded). None if the file can't be read as a
    CSV with a header row at all (e.g. a truly empty file)."""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        return max(0, len(rows) - 1) if rows else 0
    except Exception:  # noqa: BLE001
        return None


def _archive_sources(board, algorithm, phase, ref=False):
    """Read-only: what exists right now for this (board, algorithm, phase, ref)
    that a fresh run would archive. Returns a list of (category, Path)
    for whichever of raw/figures/docs actually exist and are non-empty. `ref`
    selects the no_ref/with_ref bucket for raw/figures (2026-09-22, see
    pc/shared/paths.py) -- a fresh run only ever archives the bucket it is
    about to write into, never the other one. docs are board+algorithm-keyed
    regardless of phase OR ref (see pc/shared/paths.analysis_doc_path -- one
    write-up per (board, algorithm), not split by ref), so a fresh run in
    either bucket would archive the SAME doc. Documented, not invented:
    reflects pc/shared/paths.py exactly as it stands."""
    sources = []
    raw_src = sp.raw_dir(board, algorithm, phase, ref)
    if raw_src.exists() and any(raw_src.iterdir()):
        sources.append(("raw", raw_src))
    figures_src = sp.figures_dir(board, algorithm, ref)
    if figures_src.exists() and any(figures_src.iterdir()):
        sources.append(("figures", figures_src))
    doc_src = sp.analysis_doc_path(board, algorithm)
    if doc_src.exists():
        sources.append(("docs", doc_src))
    return sources


def plan_fresh_archive(board, algorithm, phase, ref=False):
    """Read-only preview for --dry-run and for the pre-confirmation notice on
    a real run: what WOULD be archived and to where, without touching
    anything. Returns (dest_path_or_None, sources) -- dest is None if there
    is nothing to archive."""
    sources = _archive_sources(board, algorithm, phase, ref)
    if not sources:
        return None, []
    return archive_dest_dir(board, algorithm, phase, _utc_timestamp()), sources


def _manifest_entries(sources):
    """Pre-move hashing/row-counts, read from the ORIGINAL location -- called
    strictly before any move happens, so a failure here means nothing has
    been touched yet."""
    entries = []
    for category, src in sources:
        if src.is_file():
            entries.append({
                "category": category,
                "relative_path": src.name,
                "sha256": _sha256_file(src),
                "rows": _csv_row_count(src) if src.suffix == ".csv" else None,
            })
            continue
        for f in sorted(src.rglob("*")):
            if f.is_file():
                entries.append({
                    "category": category,
                    "relative_path": str(f.relative_to(src)),
                    "sha256": _sha256_file(f),
                    "rows": _csv_row_count(f) if f.suffix == ".csv" else None,
                })
    return entries


def perform_fresh_archive(board, algorithm, phase, command_str, timestamp=None,
                           reason="fresh run", ref=False):
    """Actually moves data aside. Returns the archive dest Path, or None if
    there was nothing to archive (no-op, not an error). Raises RunnerError,
    with everything already rolled back to its original location, if any step
    fails -- guaranteeing the original data is untouched and no collection
    starts. Never overwrites an existing archive folder. `ref` selects the
    no_ref/with_ref bucket, see _archive_sources."""
    sources = _archive_sources(board, algorithm, phase, ref)
    if not sources:
        return None

    ts = timestamp or _utc_timestamp()
    dest = archive_dest_dir(board, algorithm, phase, ts)
    if dest.exists():
        raise RunnerError(f"archive destination {dest} already exists -- refusing to "
                           f"overwrite it. This should not happen (timestamps are "
                           f"second-resolution); try again.")

    # Hash/count everything BEFORE any move -- if this raises, nothing has
    # been touched yet, so there is nothing to roll back.
    manifest_entries = _manifest_entries(sources)

    try:
        dest.mkdir(parents=True, exist_ok=False)
    except OSError as e:
        raise RunnerError(f"could not create archive directory {dest}: {e} -- "
                           f"original data untouched, no collection started.")

    moved = []  # [(original_src, moved_to)] -- for rollback
    try:
        for category, src in sources:
            target = dest / category if category != "docs" else dest / "docs" / src.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(target))
            moved.append((src, target))
    except Exception as e:  # noqa: BLE001
        for original, moved_to in reversed(moved):
            try:
                shutil.move(str(moved_to), str(original))
            except Exception:  # noqa: BLE001
                pass  # best-effort rollback; the error below still surfaces
        shutil.rmtree(dest, ignore_errors=True)
        raise RunnerError(f"archive move failed ({e}) -- rolled back, original data "
                           f"untouched, no collection started.")

    clean, git_ref_desc = git_state()
    manifest = {
        "reason": reason,
        "command": command_str,
        "timestamp_utc": ts,
        "git_commit": git_commit_hash(),
        "git_dirty": not clean,
        "git_ref": git_ref_desc,
        "board": board,
        "algorithm": algorithm,
        "phase": phase,
        "files": manifest_entries,
    }
    try:
        (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    except OSError as e:
        for original, moved_to in reversed(moved):
            try:
                shutil.move(str(moved_to), str(original))
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(dest, ignore_errors=True)
        raise RunnerError(f"could not write MANIFEST.json ({e}) -- rolled back, "
                           f"original data untouched, no collection started.")

    return dest


def check_counter_port(counter_port, target_port):
    """Read-only preflight of the counter's serial port. Never guesses: the port is always explicit, and when
    more than one candidate device exists (two ESP32 boards both look like usbserial*) the operator's explicit
    choice is trusted but both are listed so a swapped cable is visible before anything is armed or flashed."""
    if not counter_port:
        raise RunnerError("--ref counter requires --counter-port")
    if counter_port == target_port:
        raise RunnerError("--counter-port must differ from --port (the counter port is never shared)")
    if not port_exists(counter_port):
        raise RunnerError(f"counter port {counter_port!r} does not exist (no such device file); "
                          "this runner never auto-guesses which ESP32 is the counter")
    holders = port_holder_pids(counter_port)
    if holders:
        raise RunnerError(f"counter port {counter_port!r} is already held by process(es) {holders}")
    candidates = sorted({p for pats in PORT_GLOBS.values() for pat in pats for p in glob.glob(pat)})
    print(f"counter port: {counter_port!r} exists and is free; target port {target_port!r}")
    if len(candidates) > 1:
        print(f"NOTE: {len(candidates)} serial candidates present {candidates}: confirm by hand that "
              f"{counter_port!r} is the COUNTER ESP32 and {target_port!r} the target (never guessed here)")


def print_preflight(board, algorithm, phase, port, dry_run, ref=False, counter_port=None):
    """`ref` = --ref counter requested (selects the with_ref bucket for the resume-state line); `counter_port`
    is the counter's serial port, checked here read-only (exists, not held, differs from the target port)."""
    print("--- preflight ---")
    clean, git_ref_desc = git_state()
    print(f"git: {'clean' if clean else 'DIRTY'}  ({git_ref_desc})")
    if not clean:
        print("WARNING: working tree is dirty -- the run continues (owner-run standing "
              "decision, 2026-09-21), but the exact commit and dirty flag are recorded "
              "automatically in this session's environment JSON "
              "(telemetry.write_environment_metadata's existing git_commit/git_dirty "
              "fields -- no code changed for this).")

    sleep_check = check_sleep_prevention()
    print(f"sleep prevention: prevented={sleep_check.get('prevented')} "
          f"({sleep_check.get('note')})")

    print(f"resume state: {resume_summary(board, algorithm, phase, ref)}")

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

    if ref:
        check_counter_port(counter_port, port)

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


def completed_ns(board, algorithm, phase, ref=False):
    """Read-only: n values already recorded in the terminal-record file (resume
    skips them), for the run-time table."""
    path = sp.memory_wall_csv_path(board, algorithm, phase, ref) if phase == 2 \
        else sp.session_log_csv_path(board, algorithm, phase, ref)
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        out = set()
        for r in csv.DictReader(f):
            try:
                out.add(int(r["n"]))
            except (KeyError, ValueError):
                pass
    return out


def plan_main(argv):
    """`pc/run.py --plan`: run-time table for every board x circuit x phase of
    the current scope, with per-board and grand totals. No hardware access."""
    ap = argparse.ArgumentParser(prog="pc/run.py --plan")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--board", choices=BOARDS, default=None)
    ap.add_argument("--algorithm", default=None)
    ap.add_argument("--phase", type=int, choices=PHASES, default=None)
    ap.add_argument("--brief", action="store_true", help="summary matrix and totals only")
    args = ap.parse_args(argv)
    if args.algorithm in REMOVED_CIRCUITS:
        print(f"error: {removed_message(args.algorithm)}", file=sys.stderr)
        return 1
    if args.algorithm is not None and args.algorithm not in ALGORITHMS:
        print(f"error: unknown algorithm {args.algorithm!r} (choices: {', '.join(ALGORITHMS)})",
              file=sys.stderr)
        return 1
    eta.plan_report(boards=[args.board] if args.board else None,
                    circuits=[args.algorithm] if args.algorithm else None,
                    phases=[args.phase] if args.phase else None, brief=args.brief)
    return 0


def generate_figures(python_exe, board, algorithm, ref=False):
    """After a completed Phase 2 run, regenerate this algorithm's plots (plus the
    cumulative chart) into data/figures/<board>/<algorithm>/<bucket>/ via
    analysis/phase2_uno_run_plots.py. Never affects the run's outcome: any
    failure is printed and swallowed, the returncode of the sweep is unchanged."""
    cmd = [python_exe, str(REPO_ROOT / "analysis" / "phase2_uno_run_plots.py"),
           "--board", board, "--circuit", algorithm]
    if ref:
        cmd.append("--ref")
    print("\n--- generating figures ---\n" + " ".join(cmd))
    (REPO_ROOT / "data" / "figures" / board / algorithm / ("with_ref" if ref else "no_ref")
     ).mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(cmd, cwd=REPO_ROOT)
        if r.returncode != 0:
            print(f"warning: figure generation exited {r.returncode} "
                  "(run itself is unaffected; re-run the command above by hand)")
        elif not any((REPO_ROOT / "data" / "figures" / board / algorithm).rglob("*.png")):
            print(f"note: no plottable data for {algorithm} (e.g. only wall points) -- "
                  f"empty folder data/figures/{board}/{algorithm}/ created")
    except Exception as e:  # noqa: BLE001
        print(f"warning: figure generation failed: {e} (run itself is unaffected)")


def main(argv=None):
    if "--plan" in (argv if argv is not None else sys.argv[1:]):
        return plan_main(argv if argv is not None else sys.argv[1:])
    ap = argparse.ArgumentParser(
        description="Run one algorithm on one board for one phase, by delegating to "
                    "the existing sweep script. See docs/run/<board>.md and "
                    "docs/manual_run_guide.md for details.")
    ap.add_argument("--board", required=True, choices=BOARDS)
    ap.add_argument("--algorithm", required=True,
                     help="one of: " + ", ".join(ALGORITHMS) + " (validated in validate_combination)")
    ap.add_argument("--phase", required=True, type=int, choices=PHASES)
    ap.add_argument("--port", required=True,
                     help="e.g. /dev/cu.usbmodem1101 -- never auto-guessed")
    ap.add_argument("--n-start", type=int, default=None,
                     help="passed through as --n-start; for a non-fresh run, omit to use "
                          "the delegated script's own default (2, unchanged); for a "
                          "--fresh run, omit to use the circuit's own minimum meaningful "
                          "n (see MIN_VALID_N) -- and an explicit value below that "
                          "minimum is clamped up with a notice, never sent to the board")
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
    ap.add_argument("--ref", choices=REF_CHOICES, default="none",
                     help="timing reference: 'counter' = ESP32 pulse counter (official runs REQUIRE it, bucket with_ref/); "
                          "'none' = micros() only (bucket no_ref/, warned, not for official runs)")
    ap.add_argument("--counter-port", default=None, dest="counter_port",
                     help="serial port of the counter ESP32; required with --ref counter; never auto-guessed")
    ap.add_argument("--counter-cal", default=None, dest="counter_cal",
                     help="calibration JSON (pc/counter/calibration.py) copied into the session sidecar")
    ap.add_argument("--fresh", action="store_true",
                     help="archive (move, never delete) any existing data/figures/analysis "
                          "doc for this (board, algorithm, phase) to data/archive/ with a "
                          "MANIFEST.json, THEN start collection at the circuit's minimum "
                          "meaningful n by default. Does not pass --fresh through to the "
                          "delegated script -- see build_command's docstring.")
    ap.add_argument("--dry-run", action="store_true",
                     help="validate and print the exact command (and, for --fresh, the "
                          "planned archive destination and n-range clamp); never touch "
                          "hardware, never call pio, never move any file, never prompt")
    ap.add_argument("--yes", action="store_true",
                     help="skip the interactive y/n confirmation before touching hardware")
    args = ap.parse_args(argv)
    args.ref_mode = args.ref
    args.ref = args.ref == "counter"   # bool from here on: selects the with_ref/no_ref bucket
    argv_for_history = ["pc/run.py"] + (list(argv) if argv is not None else sys.argv[1:])
    command_str = " ".join(argv_for_history)

    # run-history ledger (2026-09-22, pc/shared/run_history.py): "started" is
    # written HERE, before any validation, so a refused run (unknown board,
    # unsupported --ref, busy port) or a crash still leaves a record -- every
    # exit path below (including the except RunnerError block) calls
    # rh.finish_invocation exactly once with a terminal event.
    inv = rh.start_invocation(argv_for_history, args.board, args.algorithm, args.phase,
                               ref=args.ref, fresh=args.fresh, dry_run=args.dry_run)

    try:
        validate_combination(args.board, args.algorithm, args.phase, args.ref,
                              args.upload_retry_settle_s, args.counter_port, args.port)
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

        if not args.ref:
            print("*** WARNING: --ref none: no timing reference. Data goes to the no_ref/ bucket and is NOT valid for "
                  "official runs (official runs REQUIRE --ref counter --counter-port PORT, see docs/design/readiness.md). ***")
        else:
            print(f"timing reference: ESP32 counter on {args.counter_port} (bucket with_ref/); the counter port is never "
                  f"shared with the target port {args.port}")

        n_max_effective = args.n_max if args.n_max is not None else DEFAULT_N_MAX[args.phase][args.board]

        fresh_timestamp = _utc_timestamp() if args.fresh else None
        if args.fresh:
            n_start_for_command, clamp_notice = effective_n_start_for_fresh(
                args.algorithm, args.n_start)
            if clamp_notice:
                print(clamp_notice)
        else:
            n_start_for_command = args.n_start

        n_start_effective_for_notice = n_start_for_command if n_start_for_command is not None \
            else LEGACY_UNIFORM_N_START_DEFAULT
        note = n_range_note(args.algorithm, n_start_effective_for_notice, n_max_effective)
        if note:
            print(note)

        python_exe = sys.executable
        argv_cmd = build_command(
            python_exe, args.board, args.algorithm, args.phase,
            n_start=n_start_for_command, n_max=args.n_max, build_timeout=args.build_timeout,
            upload_retry_settle_s=args.upload_retry_settle_s, ref=args.ref,
            counter_port=args.counter_port, counter_cal=args.counter_cal, port=args.port)

        print("command:", " ".join(argv_cmd))

        # run-time table (pc/shared/eta.py): estimates only, no hardware, also in --dry-run
        run_start_bkk = eta.now_bangkok()
        eta_n_start = n_start_for_command if n_start_for_command is not None \
            else LEGACY_UNIFORM_N_START_DEFAULT
        eta_done = set() if args.fresh else completed_ns(args.board, args.algorithm, args.phase, args.ref)
        eta_points = eta.print_run_table(args.board, args.algorithm, args.phase,
                                         n_start=eta_n_start, n_max=args.n_max,
                                         completed=eta_done, start=run_start_bkk)

        archive_dest = None
        if args.fresh:
            planned_dest, planned_sources = plan_fresh_archive(
                args.board, args.algorithm, args.phase, args.ref)
            if planned_dest is None:
                print("archive: nothing exists yet for this (board, algorithm, phase, ref) "
                      "-- fresh run starts clean, no archive needed")
            else:
                # re-plan with the SAME timestamp already picked above, so the
                # preview and the real move (later) always agree exactly
                planned_dest = archive_dest_dir(args.board, args.algorithm, args.phase,
                                                 fresh_timestamp)
                cats = ", ".join(c for c, _ in planned_sources)
                print(f"archive: existing data ({cats}) will be moved to {planned_dest} "
                      f"(with MANIFEST.json) before collection starts")

        if args.dry_run:
            print_preflight(args.board, args.algorithm, args.phase, args.port, dry_run=True,
                             ref=args.ref, counter_port=args.counter_port)
            print("[dry-run] stopping here -- no subprocess started, no file moved")
            rh.finish_invocation(inv, "dry_run")
            return 0

        print_preflight(args.board, args.algorithm, args.phase, args.port, dry_run=False,
                         ref=args.ref, counter_port=args.counter_port)

        if not confirm(args.yes):
            print("not confirmed -- exiting without touching hardware or moving any file")
            rh.finish_invocation(inv, "failed", error="not confirmed by operator")
            return 1

        if args.fresh:
            archive_dest = perform_fresh_archive(
                args.board, args.algorithm, args.phase, command_str, timestamp=fresh_timestamp,
                ref=args.ref)
            if archive_dest is not None:
                print(f"archived -> {archive_dest}")

    except RunnerError as e:
        print(f"error: {e}", file=sys.stderr)
        rh.finish_invocation(inv, "failed", error=str(e))
        return 1

    interrupted = False
    watcher = None
    if eta_points:
        record_csv = sp.memory_wall_csv_path(args.board, args.algorithm, args.phase, args.ref) \
            if args.phase == 2 else sp.session_log_csv_path(args.board, args.algorithm, args.phase, args.ref)
        watcher = eta.PointWatcher(record_csv, eta_points, run_start=eta.now_bangkok(),
                                   skip_existing=True)
        watcher.start()
    try:
        result = subprocess.run(argv_cmd, cwd=REPO_ROOT)
        returncode = result.returncode
    except KeyboardInterrupt:
        print("\ninterrupted -- the delegated script's own resume logic (default, no "
              "flag needed) means you can safely re-run the exact same command above "
              "and it will pick up where it left off (see docs/manual_run_guide.md, "
              "'Resume ทำงานอย่างไร'). Any in-flight point without a terminal record "
              "row will be re-run from its first rep, not resumed mid-point.")
        returncode = 130
        interrupted = True
    finally:
        if watcher is not None:
            watcher.stop()

    if returncode == 0 and args.phase == 2:
        generate_figures(argv_cmd[0], args.board, args.algorithm, args.ref)

    if archive_dest is not None:
        print(f"\n--- fresh run summary ---")
        print(f"archive of previous data: {archive_dest}")
        print(f"delete it any time with:  rm -r {archive_dest}")
        print(f"deleting it affects NOTHING in the pipeline -- nothing under pc/, "
              f"analysis/, or any delegated sweep script ever reads from "
              f"data/archive/ (see pc/run_test.py's archive-independence test).")

    # point_counts uses args.ref (the REQUESTED flag), which may not match
    # (legacy sigrok-era comment; the counter is required when --ref counter is given) --
    # same known limitation as print_preflight's resume-state line above,
    # see its docstring.
    point_counts = point_counts_by_status(args.board, args.algorithm, args.phase, args.ref)
    if interrupted:
        rh.finish_invocation(inv, "interrupted", returncode=returncode,
                              point_counts=point_counts, archive_dest=archive_dest)
    elif returncode == 0:
        rh.finish_invocation(inv, "completed", returncode=returncode,
                              point_counts=point_counts, archive_dest=archive_dest)
    else:
        rh.finish_invocation(inv, "failed", returncode=returncode,
                              point_counts=point_counts, archive_dest=archive_dest,
                              error=f"delegated script exited with returncode={returncode}")

    return returncode


if __name__ == "__main__":
    sys.exit(main())
