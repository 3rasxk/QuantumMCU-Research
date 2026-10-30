"""The one definition of a 'weak' point (Phase 4 item 5). A point is weak if it rests on fewer than WEAK_MIN repetitions
(Phase 2: reps of raw.csv; Phase 3: requests; counter comparison: paired reps). Weak points are drawn hollow, kept out of the model fit
and out of the primary test MAPE, and never used as primary evidence; they are reported as a secondary number."""
WEAK_MIN = 30


def is_weak(reps):
    return int(reps) < WEAK_MIN


# ---- data-quality part of the rule: independent repetitions, not recorded rows -------------------------------------------------------
# ESP32 grover n=10 (Phase 2) has 100 rows but only 16 distinct values: rows 20..99 repeat rows 10..19 exactly (period 10); n=9 repeats from
# row 39 on. A real timer cannot reproduce 80 microsecond-exact values, so rows after the first period are copies and are not independent
# repetitions (cause UNVERIFIED: host-side duplication of serial lines is the likely candidate, the firmware prints one fresh value per rep).
MIN_PERIOD = 4          # shortest repeating block considered
MIN_DISTINCT = 5        # a repeating block must contain at least this many distinct values (a constant series is not a copy)
MIN_COVER = 0.4         # the exact repetition must cover at least this fraction of the rows


def effective_reps(values):
    """number of rows before an exact periodic repetition takes over (= len(values) if there is none)"""
    v = list(values)
    n = len(v)
    best = n
    for p in range(MIN_PERIOD, n // 2 + 1):
        i = n - 1
        while i - p >= 0 and v[i] == v[i - p]:
            i -= 1
        start = max(i + 1 - p, 0)
        covered = n - (start + p)
        if covered >= max(n * MIN_COVER, p) and len(set(v[start:start + p])) >= MIN_DISTINCT:
            best = min(best, start + p)
    return best


def is_weak_values(values):
    """weak by the rule above: fewer than WEAK_MIN independent repetitions"""
    return effective_reps(values) < WEAK_MIN
