# upload_retry.py — shared logic for standing operator decision 1 (2026-09-20,
# see run_log.md): an upload failure (the uploader tool never got a working
# handshake with the board's bootloader -- avrdude's STK500 sync for Uno,
# esptool's ROM-bootloader sync for ESP8266/ESP32) gets up to
# UPLOAD_MAX_ATTEMPTS attempts total at the same n before the point is logged
# failed and the sweep moves on to the NEXT n in the SAME circuit (never
# abandons the circuit). Two consecutive n values that each exhaust all
# attempts stop the whole run -- that pattern means the point failures aren't
# independent (cable/port/hardware problem), not that a real wall was found.
#
# Originally implemented only in uno_sweep.py (2026-09-20); extracted here so
# esp8266_sweep.py and esp32_sweep.py share the exact same policy constants
# and stage-based classification instead of drifting copies. What stays
# per-board (deliberately NOT centralized here):
#   - the uploader-tool log-signature markers used only for the printed
#     label (STK500 text for avrdude vs esptool's own wording) -- each sweep
#     script keeps its own UPLOAD_SYNC_FAILURE_MARKERS tuple and calls
#     is_upload_sync_failure(log, markers) with it.
#   - port_still_enumerated(): the glob pattern for "is some board-shaped
#     port still present" differs per board family (Uno's native-USB-CDC
#     /dev/cu.usbmodem* vs the ESP boards' USB-UART bridge chip patterns
#     already used by their own find_*_port()).

UPLOAD_MAX_ATTEMPTS = 3
CONSECUTIVE_UPLOAD_FAIL_LIMIT = 2


class ConsecutiveUploadFailuresError(Exception):
    """Raised when CONSECUTIVE_UPLOAD_FAIL_LIMIT n-values in a row each
    exhausted all UPLOAD_MAX_ATTEMPTS upload attempts -- standing decision 1's
    stop condition (likely cable/port/hardware problem, not a per-point
    fluke)."""

    def __init__(self, board, circuit, n_prev, n_cur):
        self.board, self.circuit, self.n_prev, self.n_cur = board, circuit, n_prev, n_cur
        super().__init__(
            f"{board} circuit={circuit}: n={n_prev} and n={n_cur} each exhausted all "
            f"{UPLOAD_MAX_ATTEMPTS} upload attempts back-to-back -- stopping "
            "the whole run (likely cable/port/hardware problem)")


def is_upload_stage_failure(build_status: str, result: dict) -> bool:
    """True iff this failure happened during the upload step (avrdude /
    esptool), not during compile -- i.e. compile succeeded and the subsequent
    upload step is what failed. This is what standing decision 1 calls an
    "upload failure": stage-based, not log-signature-based, so it also covers
    failures whose log text doesn't match a board's own
    UPLOAD_SYNC_FAILURE_MARKERS. Deterministic compile-stage failures
    (build_status == "build_or_upload_fail" with result["stage"] ==
    "compile") are excluded on purpose -- those are never retried. Requires
    build_and_upload() to set result["stage"] to "compile" (early-return, no
    upload attempted) or "upload" (compile succeeded, upload step ran)."""
    return build_status == "build_or_upload_fail" and result.get("stage") == "upload"


def is_upload_sync_failure(log: str, markers) -> bool:
    """Signature match against a board-specific marker tuple -- used only for
    the printed label/log (not for retry eligibility, which is stage-based,
    see is_upload_stage_failure above) so this can never fire on a genuine
    build_overflow."""
    low = (log or "").lower()
    return any(m in low for m in markers)
