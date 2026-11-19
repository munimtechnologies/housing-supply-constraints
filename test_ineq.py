# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Hand-checked tests for ineq.py (part 6). Every expected number is worked out by hand in the
comments or follows from an exact synthetic model (zero residual, so the fit must recover it);
none comes from running the code."""

import math
import unittest

import ineq


class TestIRS(unittest.TestCase):
    def test_parse_irs(self):
        text = (chr(0xFEFF) + "STATEFIPS,STATE,COUNTYFIPS,COUNTYNAME,AGI_STUB,N1,A00100\n"
                "00,US,000,United States,0,100,1000\n"          # U.S. total: skipped
                "01,AL,000,Alabama,0,50,500\n"                  # state total: skipped
                "01,AL,001,Autauga County,0,30,3000\n"
                "01,AL,001,Autauga County,8,2,600\n"
                "1,AL,3,Baldwin County,8,d,5\n")                # suppressed N1: skipped
        out = ineq.parse_irs(text)
        self.assertEqual(out, {"01001": {0: (30.0, 3000.0), 8: (2.0, 600.0)}})

    def test_parse_irs_lowercase_and_unpadded(self):
        text = "statefips,state,countyfips,countyname,agi_stub,N1,mars1,A00100\n6,CA,75,SF,8,1000,0,900000\n"
        self.assertEqual(ineq.parse_irs(text), {"06075": {8: (1000.0, 900000.0)}})

    def test_county_total(self):
        self.assertEqual(ineq.county_total({1: (10, 50), 8: (2, 500)}), (12, 550))
        self.assertEqual(ineq.county_total({0: (99, 999), 8: (2, 500)}), (99, 999))
        self.assertIsNone(ineq.county_total(None))
        self.assertIsNone(ineq.county_total({}))

    def test_check_classes(self):
        recs = {"a": {7: (30, 4500.0), 8: (25, 10000.0)},   # means 150 and 400: both fine
                "b": {7: (40, 4000.0), 8: (10, 100.0)}}     # 7: mean 100 (= edge/2, fine); 8: < 20 returns
        c = ineq.check_classes(recs)
        self.assertEqual(c["top_class_counties"], 1)
        self.assertEqual(c["top_class_ok_share"], 1.0)
        self.assertEqual(c["next_class_counties"], 2)
        self.assertEqual(c["next_class_ok_share"], 1.0)
        self.assertTrue(ineq.classes_ok(c))
        recs["c"] = {8: (30, 3000.0)}                       # mean 100 < 200: wrong class
        c = ineq.check_classes(recs)
        self.assertEqual(c["top_class_ok_share"], 0.5)
        self.assertFalse(ineq.classes_ok(c))

    def test_above_real_threshold(self):
        # 10 returns, $4,000k: mean 400, alpha = 400 / (400 - 200) = 2.
        # income above 1.21 x 200: 4000 x 1.21^(1-2) = 3305.785..; returns 10 x 1.21^-2 = 6.8301..
        a, n, alpha = ineq.above_real_threshold(10, 4000.0, 1.21)
        self.assertAlmostEqual(alpha, 2.0, places=12)
        self.assertAlmostEqual(a, 4000.0 / 1.21, places=9)
        self.assertAlmostEqual(n, 10.0 / 1.4641, places=9)
        self.assertEqual(ineq.above_real_threshold(10, 4000.0, 1.0), (4000.0, 10.0, 2.0))
        self.assertIsNone(ineq.above_real_threshold(10, 4000.0, 0.9))
        self.assertIsNone(ineq.above_real_threshold(10, 2000.0, 1.1))  # mean 200 = edge

    def test_metro_pair(self):
        rec0 = {"f1": {0: (100, 10000.0), 8: (5, 2500.0)}, "f2": {0: (50, 3000.0), 8: (2, 600.0)}}
        rec1 = {"f1": {0: (110, 13000.0), 8: (8, 4000.0)}, "f2": {0: (55, 3300.0)}}
        # f2 has no top class in year 1: only f1 counts. Coverage min(10000/13000, 13000/16300)
        # = 0.769.. < 0.95 -> None; with min_cov 0.5 the sums are f1's.
        self.assertIsNone(ineq.metro_pair(["f1", "f2"], rec0, rec1))
        s = ineq.metro_pair(["f1", "f2"], rec0, rec1, min_cov=0.5)
        self.assertEqual((s["agi0"], s["agi1"], s["top_n0"], s["top_agi0"], s["top_n1"], s["top_agi1"]),
                         (10000.0, 13000.0, 5.0, 2500.0, 8.0, 4000.0))
        self.assertAlmostEqual(s["coverage"], 10000.0 / 13000.0, places=12)
        self.assertIsNone(ineq.metro_pair(["f1", "f3"], rec0, rec1, min_cov=0.5))  # f3 absent


class TestRows(unittest.TestCase):
    def test_build_rows_by_hand(self):
        members = {"10000": ["01001"]}
        msas = {"10000": {"pi": {2011: 1000.0, 2019: 1500.0}, "pop": {2011: 100.0, 2019: 110.0},
                          "pci": {2011: 10.0, 2019: 1500.0 / 110.0}}}
        hu = {"01001": {2011: 40.0, 2019: 44.0}}
        hpi = {"10000": {2011: 100.0, 2019: 150.0}}
        irs = {2011: {"01001": {0: (100.0, 10000.0), 8: (5.0, 2000.0)}},
               2019: {"01001": {0: (110.0, 14400.0), 8: (10.0, 4000.0)}}}
        cpi = {2011: 100.0, 2019: 121.0}
        rows, info = ineq.build_rows(members, {}, msas, {}, hu, hpi, {"10000": 0.3}, irs, cpi, 2011, 2019)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        l121 = math.log(1.21)
        self.assertAlmostEqual(r["Y"], math.log(1.5) - l121, places=12)
        self.assertAlmostEqual(r["N"], math.log(1.1), places=12)
        self.assertAlmostEqual(r["H"], math.log(1.1), places=12)
        self.assertAlmostEqual(r["P"], math.log(1.5) - l121, places=12)
        self.assertAlmostEqual(r["S0"], 0.2, places=12)                 # 2000 / 10000
        self.assertAlmostEqual(r["S1_nom"], 4000.0 / 14400.0, places=12)
        a_t = 4000.0 / 1.21                                              # alpha 2 in 2019 (mean 400)
        self.assertAlmostEqual(r["S1_real"], a_t / 14400.0, places=12)
        self.assertAlmostEqual(r["dS"], a_t / 14400.0 - 0.2, places=12)
        # g_top = ln(3305.79 / 2000) - ln 1.21 = ln 2 - 2 ln 1.21
        self.assertAlmostEqual(r["g_top"], math.log(2.0) - 2 * l121, places=12)
        self.assertAlmostEqual(r["g_rest"], math.log((14400.0 - a_t) / 8000.0) - l121, places=12)
        self.assertAlmostEqual(r["top_c"], 0.2 * r["g_top"], places=12)
        self.assertAlmostEqual(r["rest_c"], 0.8 * r["g_rest"], places=12)
        self.assertAlmostEqual(r["alpha0"], 2.0, places=12)              # 2011 mean 400 as well
        self.assertAlmostEqual(r["Y_irs"], math.log(1.44) - l121, places=12)
        self.assertEqual(r["w"], 100.0)
        self.assertEqual(info, {"no_income": 0, "no_irs": 0, "no_price": 0, "no_units": 0})
        # without the elasticity the metro is not built; without units H stays None
        self.assertEqual(ineq.build_rows(members, {}, msas, {}, hu, hpi, {}, irs, cpi, 2011, 2019)[0], [])
        r2 = ineq.build_rows(members, {}, msas, {}, hu, hpi, {"10000": 0.3}, irs, cpi, 2011, 2019,
                             with_units=False)[0][0]
        self.assertIsNone(r2["H"])

    def test_prepare_zscores(self):
        # S0 0.1, 0.2, 0.3: mean 0.2, population sd sqrt(0.02 / 3) = 0.081650
        rows = [{"Y": 1.0, "E": e, "S0": s} for s, e in ((0.1, 1.0), (0.2, 2.0), (0.3, 3.0))]
        rows.append({"Y": 1.0, "E": None, "S0": 0.5})                     # dropped: no E
        p = ineq.prepare(rows, ("Y", "E", "S0"))
        self.assertEqual(len(p), 3)
        k = 0.1 / math.sqrt(0.02 / 3)
        self.assertAlmostEqual(p[0]["S"], -k, places=10)
        self.assertAlmostEqual(p[1]["S"], 0.0, places=10)
        self.assertAlmostEqual(p[2]["Ez"], k, places=10)                  # E 1,2,3: same z pattern
        self.assertAlmostEqual(p[2]["YxS"], k, places=10)
        self.assertNotIn("S", rows[0])                                     # inputs not modified

    def test_corr(self):
        self.assertAlmostEqual(ineq.corr([1, 2, 3], [2, 4, 6]), 1.0, places=12)
        self.assertAlmostEqual(ineq.corr([1, 2, 3], [3, 2, 1]), -1.0, places=12)
        self.assertIsNone(ineq.corr([1, 1, 1], [1, 2, 3]))


def synth(n=60):
    raw = []
    for i in range(n):
        raw.append({"m": str(i), "w": 1.0 + i, "Y": 0.1 + (i % 7) / 20.0, "S0": ((i * 3) % 11) / 50.0,
                    "E": ((i * 5) % 13) / 40.0, "N": 0.02 * ((i * 2) % 5), "dS": ((i * 7) % 9) / 100.0,
                    "top_c": ((i * 4) % 9) / 50.0, "rest_c": ((i * 5) % 7) / 30.0, "H": 0.0, "P": 0.0})
    rows = ineq.prepare(raw, ("Y", "E", "S0"))
    for r in rows:
        # exact models
        r["P"] = 0.1 + 0.5 * r["Y"] + 0.2 * r["YxS"] - 0.1 * r["S"]
        r["H"] = 0.05 + 0.3 * r["top_c"] + 0.1 * r["rest_c"]
    return rows


class TestFits(unittest.TestCase):
    def test_exact_recovery(self):
        res = ineq.analyse(synth(), {"R1_price_state": ("P", ["Y", "YxS", "S"]),
                                     "R4_units_comp": ("H", ["top_c", "rest_c"])})
        c = res["R1_price_state"]["coef"]
        self.assertEqual(res["R1_price_state"]["n"], 60)
        self.assertAlmostEqual(c["const"]["est"], 0.1, places=8)
        self.assertAlmostEqual(c["Y"]["est"], 0.5, places=8)
        self.assertAlmostEqual(c["YxS"]["est"], 0.2, places=8)
        self.assertAlmostEqual(c["S"]["est"], -0.1, places=8)
        # top - rest = 0.3 - 0.1 = 0.2
        self.assertAlmostEqual(res["R4_units_comp"]["top_minus_rest"]["est"], 0.2, places=8)
        # weighting cannot change an exact fit
        w = ineq.analyse(synth(), {"R1_price_state": ("P", ["Y", "YxS", "S"])}, weighted=True)
        self.assertAlmostEqual(w["R1_price_state"]["coef"]["YxS"]["est"], 0.2, places=8)
        self.assertIn("skipped", ineq.fit(synth()[:30], "P", ["Y"]))
        s = ineq.strip(res)
        self.assertNotIn("V", s["R1_price_state"])
        self.assertIn("coef", s["R1_price_state"])


def cf(est, p):
    return {"est": est, "se": 0.1, "z": est / 0.1, "p": p}


class TestHypotheses(unittest.TestCase):
    def res(self):
        return {
            "R1_price_state": {"coef": {"YxS": cf(0.3, 0.01)}},
            "R2_units_state": {"coef": {"YxS": cf(-0.1, 0.20)}},
            "R3_units_race": {"coef": {"YxS": cf(-0.2, 0.01), "YxE": cf(0.05, 0.40)}},
            "R3_price_race": {"coef": {"YxS": cf(0.1, 0.30), "YxE": cf(-0.2, 0.001)}},
            "R4_price_comp": {"top_minus_rest": cf(0.4, 0.001)},
            "R4_units_comp": {"top_minus_rest": cf(0.2, 0.01)},
            "R5_pop_conc": {"coef": {"dS": cf(-1.0, 0.04)}},
            "R6_units_lmw": {"coef": {"YxE": cf(0.1, 0.03)}},
        }

    def test_by_hand(self):
        h = ineq.hypotheses(self.res())
        self.assertEqual(len(h), 8)
        st = {k[:2]: v["status"] for k, v in h.items()}
        self.assertEqual(st["I1"], "supported")       # +0.3, p 0.01
        self.assertEqual(st["I2"], "not supported")   # right sign, p 0.20
        self.assertEqual(st["I3"], "supported")       # YxS -0.2 p 0.01; YxE p 0.40
        self.assertEqual(st["I4"], "not supported")   # YxS p 0.30
        self.assertEqual(st["I5"], "supported")
        self.assertEqual(st["I6"], "not supported")   # wrong sign (+0.2)
        self.assertEqual(st["I7"], "supported")       # -1.0, p 0.04
        self.assertEqual(st["I8"], "not supported")   # p 0.03 < 0.05

    def test_reading(self):
        r = ineq.reading(self.res())
        self.assertEqual(r["units"], "inequality")           # S right sign and sig.; E not sig.
        self.assertEqual(r["prices"], "supply elasticity")   # E -0.2 sig. (right sign for prices)
        self.assertEqual(ineq.reading({})["units"], "not evaluable")

    def test_missing_is_not_evaluable(self):
        h = ineq.hypotheses({})
        self.assertTrue(all(v["status"] == "not evaluable" for v in h.values()))


if __name__ == "__main__":
    unittest.main()
