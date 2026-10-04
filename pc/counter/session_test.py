#!/usr/bin/env python3
# session_test.py -- session manager, reference files and cross-check on synthetic data, using the
# counter simulator as transport (no hardware): clean, missing pulse, glitch, count mismatch, counter
# disconnect mid-point, ARM refusal, abort, REPLAY duplicates, schema guard.
import csv
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from counter import crosscheck as cc  # noqa: E402
from counter import proto as cp  # noqa: E402
from counter import ref_schema as rs  # noqa: E402
from counter.client import CounterClient, SimTransport  # noqa: E402
from counter.session import CounterSession, max_width_for  # noqa: E402
from counter.sim import CounterSim  # noqa: E402

R = []
REPS = 10


def check(name, cond, detail=""):
    R.append(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


def make(tmp, reps=REPS):
    sim = CounterSim()
    tr = SimTransport(sim)
    cl = CounterClient(tr)
    # heartbeat so alive() is true
    tr.push([sim.heartbeat()])
    time.sleep(0.15)
    cs = CounterSession(cl, "esp32", "h_all", Path(tmp) / "ref", reps=reps, session_id="S1")
    return sim, tr, cl, cs


def run_point(cs, sim, tr, n, widths_ns, micros, **kw):
    ok = cs.arm_point(n)
    for w in widths_ns:
        tr.push(sim.pulse(w))
    time.sleep(0.15)
    return ok, cs.finish_point(n, micros, **kw)


def rows(tmp, name):
    return rs.read_rows(Path(tmp) / "ref" / name)


def main():
    check("max width scales with the model and has a floor", max_width_for("esp32", "h_all", 2) == 130
          and max_width_for("esp8266", "grover", 12) > 65_535 * 5)

    # clean point
    with tempfile.TemporaryDirectory() as tmp:
        sim, tr, cl, cs = make(tmp)
        widths = [90_000 + 100 * i for i in range(REPS)]
        micros = [w / 1000.0 + 2.0 for w in widths]          # board reads 2 us longer than the counter
        ok, st = run_point(cs, sim, tr, 6, widths, micros)
        check("clean point: ARM ok and ref_status ok", ok and st == "ok", st)
        pl = rows(tmp, "ref_pulses.csv")
        check("per-pulse file has one row per pulse, own schema version, width_us", len(pl) == REPS and pl[0]["schema_version"] == "1"
              and abs(float(pl[0]["width_us"]) - 90.0) < 1e-6 and pl[3]["seq"] == "3")
        pt = rows(tmp, "ref_points.csv")[0]
        check("per-point summary: counts and counter protocol", pt["pulses_received"] == "10" and pt["report_pulses"] == "10"
              and pt["counter_proto"] == "2" and pt["ref_status"] == "ok")
        cmp_ = rows(tmp, "ref_compare.csv")
        check("per-rep comparison: diff_us = micros - counter = +2.0 for every rep", len(cmp_) == REPS and all(abs(float(r["diff_us"]) - 2.0) < 1e-6 for r in cmp_))
        cp_ = rows(tmp, "ref_compare_points.csv")[0]
        check("point summary: median diff 2.0 us, not flagged", abs(float(cp_["median_diff_us"]) - 2.0) < 1e-6 and cp_["flagged"] == "False")
        check("no issues logged for a clean point", not (Path(tmp) / "ref" / "ref_issues.log").exists())
        cs.close()

    # large systematic difference is flagged
    with tempfile.TemporaryDirectory() as tmp:
        sim, tr, cl, cs = make(tmp)
        widths = [100_000] * REPS
        ok, st = run_point(cs, sim, tr, 6, widths, [120.0] * REPS)   # 20 % longer
        c = rows(tmp, "ref_compare_points.csv")[0]
        check("20 % systematic micros() excess is flagged", c["flagged"] == "True" and abs(float(c["median_diff_pct"]) - 20.0) < 1e-6)
        cs.close()

    # missing pulse
    with tempfile.TemporaryDirectory() as tmp:
        sim, tr, cl, cs = make(tmp)
        ok, st = run_point(cs, sim, tr, 4, [90_000] * (REPS - 1), [90.0] * REPS)
        check("missing pulse: status count_mismatch, code 1 recorded", st == "count_mismatch" and "1" in rows(tmp, "ref_points.csv")[0]["anomaly_codes"].split())
        c = rows(tmp, "ref_compare_points.csv")[0]
        check("missing pulse: comparison REFUSED, no per-rep rows, micros() untouched",
              c["ref_status"] == "refused_count_mismatch" and not rows(tmp, "ref_compare.csv"))
        check("missing pulse is in the issues log", "anomaly code 1" in (Path(tmp) / "ref" / "ref_issues.log").read_text())
        cs.close()

    # glitch
    with tempfile.TemporaryDirectory() as tmp:
        sim, tr, cl, cs = make(tmp)
        widths = [90_000] * 5 + [100] + [90_000] * 5   # a 100 ns glitch plus 10 good pulses
        ok, st = run_point(cs, sim, tr, 4, widths, [90.0] * REPS)
        check("glitch: status anomaly, glitch pulse kept in the file with flag, dropped from the pairing",
              st == "anomaly" and any(r["flags"] == "1" for r in rows(tmp, "ref_pulses.csv")) and len(rows(tmp, "ref_compare.csv")) == REPS)
        cs.close()

    # counter pcnt mismatch
    with tempfile.TemporaryDirectory() as tmp:
        sim, tr, cl, cs = make(tmp)
        cs.arm_point(4)
        for _ in range(REPS):
            tr.push(sim.pulse(90_000))
        sim.pcnt += 3
        time.sleep(0.15)
        st = cs.finish_point(4, [90.0] * REPS)
        check("ISR/PCNT mismatch (code 5) is an anomaly and logged, micros() join still allowed (10 clean pulses)",
              st == "anomaly" and "5" in rows(tmp, "ref_points.csv")[0]["anomaly_codes"].split() and len(rows(tmp, "ref_compare.csv")) == REPS)
        cs.close()

    # counter disconnect mid-point
    with tempfile.TemporaryDirectory() as tmp:
        sim, tr, cl, cs = make(tmp)
        cs.arm_point(4)
        for _ in range(4):
            tr.push(sim.pulse(90_000))
        tr.fail_after_writes = tr.writes            # END cannot be written any more
        time.sleep(0.15)
        import counter.session as cs_mod
        old = cs_mod.REPORT_TIMEOUT_S
        cs_mod.REPORT_TIMEOUT_S = 0.3
        try:
            st = cs.finish_point(4, [90.0] * REPS)
        finally:
            cs_mod.REPORT_TIMEOUT_S = old
        check("counter disconnect mid-point: ref_status counter_lost, partial pulses kept", st == "counter_lost" and len(rows(tmp, "ref_pulses.csv")) == 4)
        check("disconnect never writes a joined comparison", not rows(tmp, "ref_compare.csv") and
              rows(tmp, "ref_compare_points.csv")[0]["ref_status"].startswith("refused"))
        check("disconnect is logged", "END send failed" in (Path(tmp) / "ref" / "ref_issues.log").read_text())
        st2 = cs.finish_point(5, [90.0] * REPS)
        check("two consecutive points without a counter -> should_stop()", cs.should_stop() or st2 in ("arm_failed", "counter_lost"))
        cs.close()

    # ARM refused (busy) and arm timeout
    with tempfile.TemporaryDirectory() as tmp:
        sim, tr, cl, cs = make(tmp)
        sim.armed = True                                     # counter already busy
        import counter.session as cs_mod
        cs_mod.ARM_ACK_TIMEOUT_S, old = 0.5, cs_mod.ARM_ACK_TIMEOUT_S
        try:
            ok = cs.arm_point(4)
        finally:
            cs_mod.ARM_ACK_TIMEOUT_S = old
        check("ARM refused when busy: arm_point False, logged", ok is False and "ARM refused" in (Path(tmp) / "ref" / "ref_issues.log").read_text())
        st = cs.finish_point(4, [90.0] * REPS)
        check("point still finishes with ref_status arm_failed", st == "arm_failed")
        cs.close()
    with tempfile.TemporaryDirectory() as tmp:
        sim, tr, cl, cs = make(tmp)
        for i in range(2):
            sim.armed = True
            import counter.session as cs_mod
            cs_mod.ARM_ACK_TIMEOUT_S, old = 0.3, cs_mod.ARM_ACK_TIMEOUT_S
            cs.arm_point(4 + i); cs_mod.ARM_ACK_TIMEOUT_S = old
            cs.finish_point(4 + i, None)
        check("2 consecutive arm failures trigger should_stop()", cs.should_stop())
        cs.close()

    # abort
    with tempfile.TemporaryDirectory() as tmp:
        sim, tr, cl, cs = make(tmp)
        cs.arm_point(4)
        tr.push(sim.pulse(90_000)); time.sleep(0.1)
        cs.abort()
        check("Ctrl+C abort: counter disarmed, partial pulses saved with ref_status aborted, nothing joined",
              sim.armed is False and rows(tmp, "ref_points.csv")[0]["ref_status"] == "aborted" and not rows(tmp, "ref_compare.csv"))
        cs.close()

    # target never ran
    with tempfile.TemporaryDirectory() as tmp:
        sim, tr, cl, cs = make(tmp)
        ok, st = run_point(cs, sim, tr, 4, [], None, target_ran=False)
        check("target build/upload failure: ref_status no_target_run", st == "no_target_run")
        cs.close()

    # two target runs (upload restart + serial-open restart): the LAST run is paired
    with tempfile.TemporaryDirectory() as tmp:
        sim, tr, cl, cs = make(tmp)
        cs.arm_point(4)
        for i in range(4):                       # first run cut short after 4 pulses
            tr.push(sim.pulse(90_000, gap_us=2000))
        sim.advance(2_300_000)                   # 2.3 s restart gap
        for i in range(REPS):
            tr.push(sim.pulse(90_000 + 10 * i, gap_us=2000))
        time.sleep(0.2)
        st = cs.finish_point(4, [90.0 + 0.01 * i + 1.0 for i in range(REPS)])
        cmpp = rows(tmp, "ref_compare_points.csv")[0]
        check("two runs seen: last run paired, comparison joined (diff +1 us), status not count_mismatch",
              st != "count_mismatch" and cmpp["ref_status"] in ("ok", "anomaly") and cmpp["n_pairs"] == "10", f"{st} {cmpp['ref_status']}")
        check("all pulses of both runs are kept in ref_pulses.csv and the split is logged",
              len(rows(tmp, "ref_pulses.csv")) == 14 and "2 target runs" in (Path(tmp) / "ref" / "ref_issues.log").read_text())
        cs.close()
    runs = cc.split_runs([(i, i * 3000, 0, 100_000, 0, 0) for i in range(5)] + [(5 + i, 2_000_000 + i * 3000, 0, 100_000, 0, 0) for i in range(5)])
    check("split_runs finds one split and keeps pulse order", [len(r) for r in runs] == [5, 5])
    check("split_runs: a uniform stream is one run", len(cc.split_runs([(i, i * 3000, 0, 100_000, 0, 0) for i in range(20)])) == 1)

    # join logic, direct
    pulses = [(i, 0, 0, 90_000, 0, 0) for i in range(REPS)]
    check("join refuses when raw.csv is short", cc.join_point(pulses, [90.0] * 3, REPS, "uno")["status"] == "refused_short_raw")
    check("join refuses when raw.csv missing", cc.join_point(pulses, None, REPS, "uno")["status"] == "refused_no_micros")
    uno = cc.join_point(pulses, [94.0] * REPS, REPS, "uno")        # +4 us = one Uno micros() tick = 4.4 %
    check("a one-tick (4 us) difference on the Uno is not flagged", uno["status"] == "joined" and not uno["summary"]["flagged"])
    uno2 = cc.join_point([(i, 0, 0, 40_000, 0, 0) for i in range(REPS)], [48.0] * REPS, REPS, "uno")   # +8 us = 20 %
    check("an 8 us / 20 % difference on the Uno is flagged", uno2["summary"]["flagged"])
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.csv"
        raw.write_text("board,circuit,n,rep,exec_time_us\n" + "".join(f"esp32,h_all,6,{i},{90 + i}\n" for i in range(REPS))
                       + "esp32,h_all,7,0,5\n")
        m = cc.load_micros(raw, "h_all", 6)
        check("load_micros reads one point's reps in order", m == [90.0 + i for i in range(REPS)])
        check("load_micros: unknown point -> None", cc.load_micros(raw, "h_all", 9) is None)

    # schema guard
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "ref_pulses.csv"
        rs.append_rows(p, [{"session_id": "x", "n": 1}])
        p.write_text(p.read_text().replace("schema_version", "schema_versionX", 1))
        try:
            rs.append_rows(p, [{"session_id": "x"}]); ok = False
        except rs.RefSchemaError:
            ok = True
        check("writers refuse a file with a different header", ok)
        q = Path(tmp) / "ref_points.csv"
        rs.append_rows(q, [{"session_id": "x"}])
        q.write_text(q.read_text().replace("\n1,", "\n9,", 1))
        try:
            rs.append_rows(q, [{"session_id": "x"}]); ok = False
        except rs.RefSchemaError:
            ok = True
        check("writers refuse a file holding another schema_version", ok)
    check("reference schema constants are separate from telemetry SCHEMA_VERSION",
          rs.REF_PULSES_SCHEMA_VERSION == 1 and __import__("shared.telemetry", fromlist=["x"]).SCHEMA_VERSION == 2)

    n_fail = R.count(False)
    print(f"\n{len(R)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
