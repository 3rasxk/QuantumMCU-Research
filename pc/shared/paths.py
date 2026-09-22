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
# innermost `la: bool` split -- data/raw/phase<N>/<board>/<circuit>/no_la/ vs
# .../with_la/, and data/figures/<board>/<circuit>/no_la/ vs .../with_la/ (or
# data/figures/<board>/no_la/ vs .../with_la/ for the cumulative,
# circuit=None chart). Reason: timing-only data (no --la) and LA-cross-checked
# data (--la) measure different things and must never be mixed in the same
# analysis -- see run_log.md's "no_la/with_la data layout" entry. La_dir()
# stays with_la-only on purpose: LA capture files (capture_plan.csv,
# capture_issues.log, per-point CSVs) cannot exist without --la, there is no
# "no_la la/" directory to speak of. Every point collected before this date
# (all of it, so far) was collected without --la and now lives under no_la/ --
# migrated losslessly with `git mv` (verified via sha256 + row counts, see
# run_log.md), never rewritten.

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


def _la_bucket(la: bool) -> str:
    return "with_la" if la else "no_la"


def raw_dir(board: str, circuit: str, phase: int = 2, la: bool = False) -> Path:
    """data/raw/phase<N>/<board>/<circuit>/{no_la,with_la}/ -- everything
    collected for one algorithm on one board in one phase, split by whether
    the point was collected with --la: raw.csv, memory_wall.csv (phase 2) or
    session_log.csv (phase 3), points.csv, sessions.csv, env/, and (with_la
    only) la/. `la` must match how the data was actually collected -- see
    env_dir()'s environment-JSON cross-check note."""
    return REPO_ROOT / "data" / "raw" / f"phase{phase}" / board / circuit / _la_bucket(la)


def la_dir(board: str, circuit: str, phase: int = 2) -> Path:
    """.../<circuit>/with_la/la/ -- Logic Analyzer captures + capture_plan.csv
    + capture_issues.log for this one (board, circuit). Always under with_la/
    -- LA capture files cannot exist for a point collected without --la, so
    there is no `la=` parameter here (always with_la=True)."""
    return raw_dir(board, circuit, phase, la=True) / "la"


def env_dir(board: str, circuit: str, phase: int = 2, la: bool = False) -> Path:
    """.../<circuit>/{no_la,with_la}/env/ -- one environment-metadata JSON per
    session. The JSON itself also records whether LA was actually used
    (telemetry.write_environment_metadata's `la` argument) so a mismatch
    between "which directory this JSON lives in" and "what the JSON itself
    says" is detectable, not just trusted from the directory name alone."""
    return raw_dir(board, circuit, phase, la) / "env"


def raw_csv_path(board: str, circuit: str, phase: int = 2, la: bool = False) -> Path:
    return raw_dir(board, circuit, phase, la) / "raw.csv"


def memory_wall_csv_path(board: str, circuit: str, phase: int = 2, la: bool = False) -> Path:
    """Phase 2 terminal-record file. Phase 3 uses session_log_csv_path instead
    (same directory, different name and schema -- session_log.csv doesn't key
    on n the same way, see pc/phase3_offload/sweep.py)."""
    return raw_dir(board, circuit, phase, la) / "memory_wall.csv"


def session_log_csv_path(board: str, circuit: str, phase: int = 3, la: bool = False) -> Path:
    return raw_dir(board, circuit, phase, la) / "session_log.csv"


def points_csv_path(board: str, circuit: str, phase: int = 2, la: bool = False) -> Path:
    return raw_dir(board, circuit, phase, la) / "points.csv"


def sessions_csv_path(board: str, circuit: str, phase: int = 2, la: bool = False) -> Path:
    return raw_dir(board, circuit, phase, la) / "sessions.csv"


def figures_dir(board: str, circuit: str = None, la: bool = False) -> Path:
    """data/figures/<board>/<circuit>/{no_la,with_la}/ for a single
    algorithm's charts, or data/figures/<board>/{no_la,with_la}/
    (circuit=None) for the board's cumulative chart -- timing-only (no_la)
    and LA-cross-checked (with_la) figures are never mixed into the same
    directory, matching the raw-data split above."""
    base = REPO_ROOT / "data" / "figures" / board
    base = base / circuit if circuit else base
    return base / _la_bucket(la)


def analysis_doc_path(board: str, circuit: str = None) -> Path:
    """docs/analysis/<board>/<circuit>.md, or docs/analysis/<board>/comparison.md
    (circuit=None) for the cross-algorithm write-up."""
    base = REPO_ROOT / "docs" / "analysis" / board
    return base / (f"{circuit}.md" if circuit else "comparison.md")
