# Run Log

Record of every experimental run against this repository. Add one row per run
after it completes — do not edit past rows except to fix a factual error.

| Date | Reps | Boards/Circuits | Scope | Note | Git ref |
|------|------|------------------|-------|------|---------|
| 2026-09-16 | — | — | — | Original n=30 dataset (Phases 1-4, all 3 boards, all 3 circuits) fully superseded and deleted from the working tree as part of a repo reorganization. Recoverable from git history at the pre-reorg snapshot commit if any number already written into a report needs to be cross-checked. | `7669def` |
| 2026-09-16 | 100 | Uno/ESP8266/ESP32, all 3 circuits | prep, not yet run | **Methodology deviation from the n=30 run, applies once this rerun executes:** `pc/phase2_sweep/{uno,esp8266,esp32}_sweep.py` now retry a data point once at the same `n` if it fails with `runtime_hang_or_reset` (hang, serial timeout, or serial read error) — a failure that could be a transient USB/cable glitch rather than a real Memory Wall. `build_or_upload_fail` and `malloc_failed` are still not retried (deterministic outcomes). The n=30 run had no retry logic at all: its first failure at any `n`, of any kind, was immediately the Memory Wall. This means the two datasets' Memory Wall numbers are **not directly comparable** without checking the new `retry_count` column in `*_memory_wall.csv` (also surfaced as `first_failure_after_retry` in `data/processed/phase2/memory_wall_summary.csv`) — a wall that only appears after a retry in the n=100 run might have been recorded as the wall on the very first attempt in the n=30 run, or might not, depending on whether the n=30 failure was itself transient. | — |
