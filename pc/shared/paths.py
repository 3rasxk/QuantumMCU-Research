# paths.py — single source of truth for where raw data, telemetry, Logic Analyzer
# captures, and figures live. Introduced 2026-09-20 (see run_log.md, "per-board
# per-algorithm layout") when data/raw/ moved from one flat directory per phase
# (data/raw/phase2/<board>_raw.csv, shared by every circuit) to one directory per
# (phase, board, algorithm) -- every sweep/analysis script must go through these
# functions instead of building the path by hand, so the layout only ever needs
# to change in one place. Corrected same day (still 2026-09-20) to put phase
# outermost -- data/raw/phase<N>/<board>/<circuit>/ -- matching the project's
# existing phase-first convention (data/raw/phase1/, docs/manual_run_guide.md's
# "data/raw/phase2/ and data/raw/phase3/" checks) instead of board-first.
#
# data/raw/phase1/ is untouched by this -- a different, pre-existing dataset with
# its own layout (analysis/phase1_compare.py owns it), not part of this scheme
# (it has no per-board/per-circuit split at all).
#
# 2026-09-22: every raw/points/sessions/env path (and figures_dir) gained an
# innermost bucket split; 2026-10-04: the buckets were renamed with the timing
# reference change (Logic Analyzer -> ESP32 counter):
#   data/raw/phase<N>/<board>/<circuit>/no_ref/   timing from micros() only (--ref none)
#   data/raw/phase<N>/<board>/<circuit>/with_ref/ micros() + counter reference (--ref counter),
#                                                 reference files beside raw.csv in with_ref/ref/
# and data/figures/<board>/<circuit>/{no_ref,with_ref}/ (or data/figures/<board>/{no_ref,with_ref}/
# for the cumulative circuit=None chart). Reason: points collected without a reference and points
# collected with one must never be mixed in one analysis; resume never crosses buckets. No data
# existed under either old name when the rename happened (all earlier data was deleted
# 2026-10-04), so the rename is path-only.

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# data/raw/ itself -- analysis/reporting scripts that scan across every
# board+circuit (phase2_summarize.py, phase2_plot.py, timing_report.py,
# phase3_summarize.py) used to each define their own REPO_ROOT/RAW_ROOT (or
# RAW_DIR for phase3_summarize.py, which only ever reads phase3) by hand; they
# now import this instead (2026-09-22, see run_log.md). Plain module-level
# constant, unlike the functions above -- these scripts are standalone CLI
# tools, not exercised by the REPO_ROOT-reassignment late-binding tests the
# sweep scripts' paths go through (see uno_upload_retry_test.py's
# "late-binding check").
RAW_ROOT = REPO_ROOT / "data" / "raw"


def _ref_bucket(ref: bool) -> str:
    return "with_ref" if ref else "no_ref"


def raw_dir(board: str, circuit: str, phase: int = 2, ref: bool = False) -> Path:
    """data/raw/phase<N>/<board>/<circuit>/{no_ref,with_ref}/ -- everything
    collected for one algorithm on one board in one phase, split by whether
    the point was collected with --ref counter: raw.csv, memory_wall.csv (phase 2) or
    session_log.csv (phase 3), points.csv, sessions.csv, env/, and (with_ref
    only) ref/. `ref` must match how the data was actually collected -- see
    env_dir()'s environment-JSON cross-check note."""
    return REPO_ROOT / "data" / "raw" / f"phase{phase}" / board / circuit / _ref_bucket(ref)


def ref_dir(board: str, circuit: str, phase: int = 2) -> Path:
    """.../<circuit>/with_ref/ref/ -- reference (counter) files for this one (board, circuit):
    ref_pulses.csv, ref_points.csv, ref_compare.csv, ref_compare_points.csv, ref_issues.log
    (schemas in pc/counter/ref_schema.py). Always under with_ref/: reference files cannot exist for
    a point collected with --ref none, so there is no `ref=` parameter here (always the with_ref bucket)."""
    return raw_dir(board, circuit, phase, ref=True) / "ref"


def env_dir(board: str, circuit: str, phase: int = 2, ref: bool = False) -> Path:
    """.../<circuit>/{no_ref,with_ref}/env/ -- one environment-metadata JSON per
    session. The JSON itself also records whether the counter reference was used
    (telemetry.write_environment_metadata's `ref` argument) so a mismatch
    between "which directory this JSON lives in" and "what the JSON itself
    says" is detectable, not just trusted from the directory name alone."""
    return raw_dir(board, circuit, phase, ref) / "env"


def raw_csv_path(board: str, circuit: str, phase: int = 2, ref: bool = False) -> Path:
    return raw_dir(board, circuit, phase, ref) / "raw.csv"


def memory_wall_csv_path(board: str, circuit: str, phase: int = 2, ref: bool = False) -> Path:
    """Phase 2 terminal-record file. Phase 3 uses session_log_csv_path instead
    (same directory, different name and schema -- session_log.csv doesn't key
    on n the same way, see pc/phase3_offload/sweep.py)."""
    return raw_dir(board, circuit, phase, ref) / "memory_wall.csv"


def predicted_csv_path(board: str, circuit: str, phase: int = 2, ref: bool = False) -> Path:
    """.../<circuit>/{no_ref,with_ref}/predicted.csv -- model/extrapolated values for points that
    were NOT run because one rep alone exceeds the per-point time cap (pc/shared/predicted.py).
    ESTIMATES, never mixed into raw.csv."""
    return raw_dir(board, circuit, phase, ref) / "predicted.csv"


def session_log_csv_path(board: str, circuit: str, phase: int = 3, ref: bool = False) -> Path:
    return raw_dir(board, circuit, phase, ref) / "session_log.csv"


def points_csv_path(board: str, circuit: str, phase: int = 2, ref: bool = False) -> Path:
    return raw_dir(board, circuit, phase, ref) / "points.csv"


def sessions_csv_path(board: str, circuit: str, phase: int = 2, ref: bool = False) -> Path:
    return raw_dir(board, circuit, phase, ref) / "sessions.csv"


def figures_dir(board: str, circuit: str = None, ref: bool = False, phase: int = 2) -> Path:
    """data/figures/phase<2|3>/<board>/<circuit>/ for a single algorithm's charts, or
    data/figures/phase<2|3>/<board>/ (circuit=None) for the board's cumulative chart. Phase-first like
    data/raw/phase<2|3>/. There is NO no_ref/with_ref level (2026-10-10): the whole dataset was collected
    with the counter, so the figures sit directly in the algorithm folder. `ref` is accepted only so the
    callers keep their signature; it does not change the path (a later no_ref run would overwrite the
    with_ref figures, so give it its own folder first if that ever happens)."""
    base = REPO_ROOT / "data" / "figures" / f"phase{3 if phase == 3 else 2}" / board
    return base / circuit if circuit else base


def analysis_doc_path(board: str, circuit: str = None) -> Path:
    """docs/analysis/<board>/<circuit>.md, or docs/analysis/<board>/comparison.md
    (circuit=None) for the cross-algorithm write-up."""
    base = REPO_ROOT / "docs" / "analysis" / board
    return base / (f"{circuit}.md" if circuit else "comparison.md")
