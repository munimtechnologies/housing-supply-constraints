# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Hand-checked tests for bartik.py (part 4). Expected numbers are worked out by hand in the
comments; none comes from running the code. The last test only checks that the whole analysis
path runs on synthetic data without error."""

import io
import math
import os
import tempfile
import unittest

import numpy as np

import bartik as bt


class TestParseCBP(unittest.TestCase):
    def test_2010_style_with_flags(self):
        text = "\n".join([
            '"fipstate","fipscty","naics","empflag","emp_nf","emp","qp1_nf","qp1"',
            '"01","001","------","","G",10000,"G",5',
            '"01","001","23----","","G",600,"G",5',   # 2-digit sector: not used
            '"01","001","236///","","G",500,"G",5',   # 3-digit: kept
            '"01","001","2361//","","G",300,"G",5',   # 4-digit: not used
            '"01","001","311///","C","",0,"",0',      # withheld, class C -> 175
            '"01","001","999///","A","",0,"",0',      # sector 99: left out
            '"01","999","------","","G",777,"G",5',   # statewide: left out
            '"01","003","------","","G",50,"G",5',
        ])
        ind, tot, info = bt.parse_cbp(io.StringIO(text))
        self.assertEqual(ind, {"01001": {"236": 500.0, "311": 175.0}})
        self.assertEqual(tot, {"01001": 10000.0, "01003": 50.0})
        self.assertEqual(info["imputed_cells"], 1)
        self.assertEqual(info["imputed_employment"], 175.0)
        self.assertEqual(info["rows_kept"], 4)

    def test_2019_style_no_flag_column(self):
        text = "\n".join([
            "FIPSTATE,FIPSCTY,NAICS,EMP_NF,EMP",
            '"06","037","------","G",4000000',
            '"06","037","541///","H",300000',
        ])
        ind, tot, info = bt.parse_cbp(io.StringIO(text))
        self.assertEqual(tot, {"06037": 4000000.0})
        self.assertEqual(ind, {"06037": {"541": 300000.0}})
        self.assertEqual(info["imputed_cells"], 0)

    def test_bad_header(self):
        ind, tot, info = bt.parse_cbp(io.StringIO("a,b,c\n1,2,3\n"))
        self.assertEqual((ind, tot), ({}, {}))
        self.assertIn("error", info)


class TestBartik(unittest.TestCase):
    def test_leave_one_out(self):
        ind0 = {"A": {"1": 10.0, "2": 30.0, "3": 5.0}, "B": {"1": 90.0, "2": 70.0}}
        ind1 = {"A": {"1": 20.0, "2": 30.0, "3": 5.0}, "B": {"1": 180.0, "2": 35.0}}
        out = bt.bartik(ind0, ind1)
        # County A. Industry 1: N0 = 100, N1 = 200; without A: 90 -> 180, growth 100 ln 2.
        # Industry 2: N0 = 100, N1 = 65; without A: 70 -> 35, growth 100 ln 0.5.
        # Industry 3 exists only in A, so its leave-one-out base is 0: left out.
        # Shares of the covered 40: 10/40 and 30/40 -> B = (1000 ln2 - 3000 ln2) / 40 = -50 ln 2.
        self.assertAlmostEqual(out["A"]["bartik"], -50.0 * math.log(2), places=9)
        self.assertAlmostEqual(out["A"]["covered"], 40.0 / 45.0, places=12)
        # County B. Industry 1 without B: 10 -> 20 (100 ln 2). Industry 2 without B: 30 -> 30 (0).
        # B = 90 * 100 ln2 / 160 = 56.25 ln 2.
        self.assertAlmostEqual(out["B"]["bartik"], 56.25 * math.log(2), places=9)
        self.assertAlmostEqual(out["B"]["covered"], 1.0, places=12)

    def test_county_missing_in_end_year(self):
        # County A vanishes in the end year: its end-year employment counts as 0.
        ind0 = {"A": {"1": 10.0}, "B": {"1": 90.0}}
        ind1 = {"B": {"1": 180.0}}
        out = bt.bartik(ind0, ind1)
        # A: without A, 90 -> 180: 100 ln 2. B: without B, 10 -> 0: left out, so B has no shock.
        self.assertAlmostEqual(out["A"]["bartik"], 100.0 * math.log(2), places=9)
        self.assertNotIn("B", out)


def _bea(p0, p1, i0=1000.0, i1=1000.0):
    return {"pop": {2010: p0, 2019: p1}, "pi": {2010: i0, 2019: i1}, "pci": {}}


class TestAssembly(unittest.TestCase):
    def test_build_rows(self):
        groups = {"01001": 0, "01003": 2, "09001": 1, "01005": 1}
        bk = {"01001": {"bartik": 5.0, "covered": 1.0}, "01003": {"bartik": 2.0, "covered": 0.9},
              "09001": {"bartik": 1.0, "covered": 1.0}}           # 01005 has no shock
        tot0, tot1 = {"01001": 100.0, "01003": 10.0}, {"01001": 120.0}
        bea = {"01001": _bea(50000.0, 55000.0, 1000.0, 1500.0), "01003": _bea(8000.0, 8000.0),
               "09001": _bea(1.0, 1.0)}
        hpi = {"01001": {2010: 100.0, 2019: 130.0}}
        hu = {"01001": {"c2000": 18000.0, "c2010": 20000.0, 2019: 22000.0},
              "01003": {"c2010": 4000.0, 2019: 4000.0}}
        permits = {y: {"01001": 100, "01003": 1} for y in range(2011, 2020)}
        del permits[2015]["01003"]
        land = {"01001": 500.0}
        delin = {"01001": {"cbsa": "10000", "metro": True}}
        rows = bt.build_rows(groups, bk, tot0, tot1, bea, hpi, hu, permits, land, delin)
        self.assertEqual([r["fips"] for r in rows], ["01001", "01003"])  # CT and no-shock dropped
        a, b = rows
        self.assertEqual((a["grp"], a["w"], a["cbsa"], a["metro"], a["state"]), (0, 50000.0, "10000", True, "01"))
        self.assertAlmostEqual(a["emp_growth"], 100 * math.log(1.2), places=9)
        self.assertAlmostEqual(a["inc_growth"], 100 * math.log(1.5), places=9)
        self.assertAlmostEqual(a["pop_growth"], 100 * math.log(1.1), places=9)
        self.assertAlmostEqual(a["price_growth"], 100 * math.log(1.3), places=9)
        self.assertAlmostEqual(a["hu_growth"], 100 * math.log(1.1), places=9)
        self.assertAlmostEqual(a["hu_growth_00_10"], 100 * math.log(20000.0 / 18000.0), places=9)
        self.assertAlmostEqual(a["permits_per_1000hu"], 45.0, places=9)  # 9 x 100 / 20000 x 1000
        self.assertAlmostEqual(a["log_density"], math.log(100.0), places=9)  # 50000 / 500
        # 01003: no 2019 employment, no prices, a permit year missing, no land area, not in a metro.
        self.assertIsNone(b["emp_growth"])
        self.assertIsNone(b["price_growth"])
        self.assertIsNone(b["permits_per_1000hu"])
        self.assertIsNone(b["log_density"])
        self.assertEqual((b["cbsa"], b["metro"]), (None, False))
        self.assertAlmostEqual(b["hu_growth"], 0.0, places=12)

    def test_metro_rows(self):
        members = {"10000": ["01001", "01003"], "20000": ["02001", "02003"],
                   "30000": ["03001", "03003"]}
        divs = {"20000": {"20001": ["02001"], "20002": ["02003"]}}
        m_groups = {"10000": 1, "20000": 0, "30000": 2}
        bk = {f: {"bartik": b, "covered": 1.0} for f, b in
              (("01001", 10.0), ("01003", 4.0), ("02001", 1.0), ("02003", 1.0), ("03001", 1.0))}
        tot0 = {"01001": 300.0, "01003": 100.0, "02001": 50.0, "02003": 50.0, "03001": 5.0, "03003": 5.0}
        tot1 = {"01001": 330.0, "01003": 110.0, "02001": 50.0, "02003": 50.0}
        bea = {"01001": _bea(1000.0, 1100.0), "01003": _bea(500.0, 550.0),
               "02001": _bea(100.0, 100.0), "02003": _bea(100.0, 100.0)}
        hu = {"01001": {"c2010": 400.0, 2019: 440.0}, "01003": {"c2010": 200.0, 2019: 230.0},
              "02001": {"c2010": 300.0, 2019: 300.0}, "02003": {"c2010": 100.0, 2019: 100.0}}
        permits = {y: {"01001": 2, "01003": 2, "02001": 0} for y in range(2011, 2020)}
        cbsa_hpi = {"10000": {2010: 100.0, 2019: 150.0},
                    "20001": {2010: 100.0, 2019: 200.0}, "20002": {2010: 100.0, 2019: 100.0}}
        rows = bt.metro_rows(members, divs, m_groups, bk, tot0, tot1, bea, hu, permits, cbsa_hpi)
        self.assertEqual([r["fips"] for r in rows], ["10000", "20000"])  # 03003 has no shock
        m1, m2 = rows
        self.assertAlmostEqual(m1["bartik"], 8.5, places=12)            # (300x10 + 100x4) / 400
        self.assertAlmostEqual(m1["emp_growth"], 100 * math.log(1.1), places=9)   # 440 / 400
        self.assertAlmostEqual(m1["pop_growth"], 100 * math.log(1.1), places=9)   # 1650 / 1500
        self.assertAlmostEqual(m1["hu_growth"], 100 * math.log(670.0 / 600.0), places=9)
        self.assertAlmostEqual(m1["price_growth"], 100 * math.log(1.5), places=9)
        self.assertEqual(m1["price_source"], "fhfa_cbsa")
        self.assertAlmostEqual(m1["permits_per_1000hu"], 60.0, places=9)  # 9 x 2 x 2 / 600 x 1000
        self.assertEqual((m1["grp"], m1["w"], m1["n_counties"]), (1, 1500.0, 2))
        # Metro 2: no CBSA index, so the two divisions are weighted by 2010 homes (300 and 100):
        # (300 x 100 ln 2 + 100 x 0) / 400 = 75 ln 2. Permits: 02003 is missing -> None.
        self.assertAlmostEqual(m2["price_growth"], 75.0 * math.log(2), places=9)
        self.assertEqual(m2["price_source"], "fhfa_divisions")
        self.assertIsNone(m2["permits_per_1000hu"])


def _iv_rows(n_per=20, exact=True, seed=0):
    th = [2.0, 1.0, 0.5]
    rng = np.random.RandomState(seed)
    rows = []
    for i in range(3 * n_per):
        g, s = i % 3, (i // 3) % 4 if exact else (i // 3) % 30
        if exact:
            z = float((i * 7) % 11) - 5.0
            # No state term in y, so the model without fixed effects is also exact.
            x = 0.5 * z + ((i * 3) % 5) * 0.2 + 0.1 * s
            y = th[g] * x + 0.3 * g
        else:
            z, v, eps = rng.normal(), rng.normal(), rng.normal()
            x = 0.5 * z + v + 0.2 * s
            y = th[g] * x + 0.8 * v + 0.5 * eps + 0.3 * g + 0.1 * s
        rows.append({"fips": "f%d" % i, "state": "s%d" % s, "grp": g, "w": 1.0,
                     "price_growth": y, "hu_growth": x, "bartik": z})
    return rows


class TestIV(unittest.TestCase):
    def test_exact_recovery_with_and_without_fe(self):
        # y is exactly theta_k * x plus tercile and state effects, so 2SLS must return theta_k.
        rows = _iv_rows(exact=True)
        for fe in ("state", None):
            r = bt.iv_by_tercile(rows, fe=fe, cluster="state", min_n=5)
            self.assertEqual(r["n"], 60)
            for k, t in enumerate([2.0, 1.0, 0.5]):
                self.assertAlmostEqual(r["theta"][k]["est"], t, places=6)
            self.assertAlmostEqual(r["theta_low_minus_high"]["est"], 1.5, places=6)

    def test_endogenous_noise(self):
        # x and y share the shock v, so least squares is biased up by 0.8 / 1.25 = 0.64; 2SLS is
        # not. With 1,000 units per tercile the 2SLS standard error is about 0.06, so 0.3 is
        # five standard errors and still well short of the 0.64 bias.
        r = bt.iv_by_tercile(_iv_rows(n_per=1000, exact=False), fe="state", cluster="state")
        self.assertEqual((r["n"], r["n_clusters"]), (3000, 30))
        for k, t in enumerate([2.0, 1.0, 0.5]):
            self.assertLess(abs(r["theta"][k]["est"] - t), 0.3)
        self.assertLess(abs(r["theta_low_minus_high"]["est"] - 1.5), 0.4)

    def test_too_few(self):
        self.assertIn("skipped", bt.iv_by_tercile(_iv_rows(n_per=5), min_n=45))


class TestJudging(unittest.TestCase):
    def test_first_stage_ok(self):
        sl = [{"est": 1.0, "se": 0.25}, {"est": 0.1, "se": 1.0}, {"est": 0.5, "se": 0.1}]
        ok, ts = bt.first_stage_ok({"hu_growth": {"split": {"slopes": sl}}})
        self.assertTrue(ok)
        self.assertEqual([round(t, 9) for t in ts], [4.0, 0.1, 5.0])
        sl[0] = {"est": 1.0, "se": 0.5}  # t = 2 in the lowest tercile
        self.assertFalse(bt.first_stage_ok({"hu_growth": {"split": {"slopes": sl}}})[0])
        self.assertEqual(bt.first_stage_ok({}), (False, []))

    def test_tight_null(self):
        def block(d_est, d_se):
            return {"price_growth": {"split": {"slope_low_minus_high": {"est": d_est, "se": d_se}},
                                     "pooled": {"slope": {"est": 1.0, "se": 0.1, "p": 0.001}}}}
        # CI 0.05 +/- 0.196 = [-0.146, 0.246], inside +/- 0.5.
        self.assertEqual(bt.tight_null(block(0.05, 0.1))["status"], "tight null")
        # CI 0.1 +/- 0.588 = [-0.488, 0.688]: crosses 0 but reaches past 0.5.
        self.assertEqual(bt.tight_null(block(0.1, 0.3))["status"], "not a tight null")
        # CI 0.8 +/- 0.196 excludes 0.
        self.assertEqual(bt.tight_null(block(0.8, 0.1))["status"], "gap is significant")
        self.assertEqual(bt.tight_null({})["status"], "not evaluable")


class TestSmoke(unittest.TestCase):
    def test_full_analysis_path_runs(self):
        rng = np.random.RandomState(1)
        rows = []
        for i in range(400):
            z = rng.normal(5, 3)
            rows.append({"fips": "%05d" % (1000 + i), "state": "%02d" % (1 + i % 12),
                         "cbsa": "c%02d" % (i % 40) if i % 5 else None, "metro": bool(i % 5),
                         "grp": i % 3, "w": 1000.0 + i, "pop10": 5000.0 + 100 * i, "bartik": z,
                         "emp_growth": z + rng.normal(), "inc_growth": 1.5 * z + rng.normal(),
                         "pop_growth": 0.5 * z + rng.normal(), "hu_growth": 0.4 * z + rng.normal(),
                         "permits_per_1000hu": 5 * z + rng.normal(), "price_growth": z + rng.normal(),
                         "hu_growth_00_10": rng.normal(10, 3), "log_density": rng.normal(4, 1)})
        mrows = []
        for i in range(90):
            z = rng.normal(5, 3)
            mrows.append({"fips": "m%03d" % i, "cbsa": "m%03d" % i, "metro": True, "grp": i % 3,
                          "w": 1.0, "pop10": 1.0, "bartik": z, "emp_growth": z + rng.normal(),
                          "pop_growth": z + rng.normal(), "hu_growth": z + rng.normal(),
                          "permits_per_1000hu": z + rng.normal(), "price_growth": z + rng.normal()})
        res, iv = bt.analyse(rows, mrows)
        hyps = bt.hypotheses(res, iv)
        self.assertEqual(len(hyps), 8)
        self.assertTrue(all(k.startswith("B%d " % (n + 1)) for n, k in enumerate(hyps)))
        self.assertTrue(all("status" in v for v in hyps.values()))
        self.assertIn("theta", iv["county_state_fe"])
        self.assertIn("theta", iv["metro"])
        self.assertIn("slopes", res["within_metro"]["price_growth"]["split"])
        self.assertNotIn("inc_growth", res["metro"])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.md")
            bt.write_md(p, {"x": 1}, res, iv, hyps, {"first_stage": bt.first_stage_ok(res["county_state_fe"]),
                                                     "tight_null": bt.tight_null(res["county_state_fe"])})
            with open(p, encoding="utf-8") as f:
                self.assertIn("Realised inverse supply slope", f.read())


if __name__ == "__main__":
    unittest.main()
