"""The one definition of a 'weak' point (Phase 4 item 5). A point is weak if it rests on fewer than WEAK_MIN repetitions
(Phase 2: reps of raw.csv; Phase 3: requests; counter comparison: paired reps). Weak points are drawn hollow, kept out of the model fit
and out of the primary test MAPE, and never used as primary evidence; they are reported as a secondary number."""
WEAK_MIN = 30


def is_weak(reps):
    return int(reps) < WEAK_MIN
