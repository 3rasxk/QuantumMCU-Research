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


def raw_dir(board: str, circuit: str, phase: int = 2) -> Path:
    """data/raw/phase<N>/<board>/<circuit>/ -- everything collected for one
    algorithm on one board in one phase: raw.csv, memory_wall.csv (phase 2) or
    session_log.csv (phase 3), points.csv, sessions.csv, env/, la/."""
    return REPO_ROOT / "data" / "raw" / f"phase{phase}" / board / circuit


def la_dir(board: str, circuit: str, phase: int = 2) -> Path:
    """.../<circuit>/la/ -- Logic Analyzer captures + capture_plan.csv +
    capture_issues.log for this one (board, circuit)."""
    return raw_dir(board, circuit, phase) / "la"


def env_dir(board: str, circuit: str, phase: int = 2) -> Path:
    """.../<circuit>/env/ -- one environment-metadata JSON per session."""
    return raw_dir(board, circuit, phase) / "env"


def raw_csv_path(board: str, circuit: str, phase: int = 2) -> Path:
    return raw_dir(board, circuit, phase) / "raw.csv"


def memory_wall_csv_path(board: str, circuit: str, phase: int = 2) -> Path:
    """Phase 2 terminal-record file. Phase 3 uses session_log_csv_path instead
    (same directory, different name and schema -- session_log.csv doesn't key
    on n the same way, see pc/phase3_offload/sweep.py)."""
    return raw_dir(board, circuit, phase) / "memory_wall.csv"


def session_log_csv_path(board: str, circuit: str, phase: int = 3) -> Path:
    return raw_dir(board, circuit, phase) / "session_log.csv"


def points_csv_path(board: str, circuit: str, phase: int = 2) -> Path:
    return raw_dir(board, circuit, phase) / "points.csv"


def sessions_csv_path(board: str, circuit: str, phase: int = 2) -> Path:
    return raw_dir(board, circuit, phase) / "sessions.csv"


def figures_dir(board: str, circuit: str = None) -> Path:
    """data/figures/<board>/<circuit>/ for a single algorithm's charts, or
    data/figures/<board>/ (circuit=None) for the board's cumulative chart."""
    base = REPO_ROOT / "data" / "figures" / board
    return base / circuit if circuit else base


def analysis_doc_path(board: str, circuit: str = None) -> Path:
    """docs/analysis/<board>/<circuit>.md, or docs/analysis/<board>/comparison.md
    (circuit=None) for the cross-algorithm write-up."""
    base = REPO_ROOT / "docs" / "analysis" / board
    return base / (f"{circuit}.md" if circuit else "comparison.md")
