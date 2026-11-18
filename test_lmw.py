# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Hand-checked tests for lmw.py (part 5b). Every expected number is worked out by hand in the
comments or follows from an exact synthetic model (zero residual, so the fit must recover it);
none comes from running the code."""

import math
import unittest

import lmw


class TestUnits(unittest.TestCase):
    def test_annualize(self):
        # 20 years of 1% a year: log change 20 ln 1.01 -> 100 (1.01 - 1) = 1.0.
        self.assertAlmostEqual(lmw.ann(20 * math.log(1.01)), 1.0, places=10)
        self.assertEqual(lmw.ann(0.0), 0.0)

    def test_lmw_units(self):
        rows = [{"m": "a", "E": 0.3, "g_real": 20 * math.log(1.03), "pop_growth": 20 * math.log(1.01),
                 "hu_growth": 20 * math.log(1.02), "price_growth": None},
                {"m": "b", "E": 0.4, "g_real": 0.1, "pop_growth": None, "hu_growth": 0.1, "price_growth": 0.1}]
        out = lmw.lmw_units(rows)
        self.assertEqual(len(out), 1)  # row b has no population: dropped
        r = out[0]
        self.assertAlmostEqual(r["Y"], 3.0, places=10)
        self.assertAlmostEqual(r["N"], 1.0, places=10)
        # per-capita: exp((20 ln 1.03 - 20 ln 1.01) / 20) = 1.03 / 1.01
        self.assertAlmostEqual(r["y_pc"], 100 * (1.03 / 1.01 - 1), places=10)
        self.assertAlmostEqual(r["H"], 2.0, places=10)
        self.assertIsNone(r["P"])
        self.assertEqual(lmw.common_sample(out), [])  # no price: not in the common sample

    def test_ms_units_keep_logs(self):
        r = lmw.ms_units([{"E": 0.2, "g_real": 0.5, "pop_growth": 0.2, "hu_growth": 0.3, "price_growth": 0.1}])[0]
        self.assertEqual((r["Y"], r["N"], r["H"], r["P"]), (0.5, 0.2, 0.3, 0.1))
        self.assertAlmostEqual(r["y_pc"], 0.3, places=12)

    def test_median_split(self):
        # median of 0.1, 0.2, 0.3, 0.4 is 0.25: D = 0, 0, 1, 1 (strictly above).
        rows = [{"E": e} for e in (0.1, 0.2, 0.3, 0.4)]
        lmw.set_split(rows, 0.25, "Dmed")
        self.assertEqual([r["Dmed"] for r in rows], [0.0, 0.0, 1.0, 1.0])
        # a value equal to the threshold is not "above"
        rows = [{"E": e} for e in (0.1, 0.2, 0.3)]
        lmw.set_split(rows, 0.2, "Dmed")
        self.assertEqual([r["Dmed"] for r in rows], [0.0, 0.0, 1.0])


def synth(n=50):
    rows = []
    for i in range(n):
        Y = 1.0 + ((i * 7) % 11) / 5.0
        N = 0.5 + ((i * 3) % 7) / 10.0
        D = 1.0 if i >= 25 else 0.0
        P = 0.5 * Y + 0.3 * N + 0.02 * ((i * 5) % 9)  # depends on N, so N is a relevant instrument
        rows.append({"m": str(i), "E": 0.1 + 0.01 * i, "Y": Y, "N": N, "y_pc": Y - N, "P": P,
                     "Dmed": D, "Dmean": 1.0 if i >= 20 else 0.0,
                     # exact model: H = 0.2 + 0.6 Y + 0.1 D - 0.05 Y D
                     "H": 0.2 + 0.6 * Y + 0.1 * D - 0.05 * Y * D,
                     # exact supply curve for the IV test
                     "H2": 0.3 + 1.5 * P})
    return rows


class TestFits(unittest.TestCase):
    def test_lmw_cell_recovers_exact_model(self):
        res = lmw.analyse(synth(), synth())
        c = res["lmw_exact"]["L1_units_on_income"]
        self.assertEqual(c["n"], 50)
        self.assertAlmostEqual(c["income"]["est"], 0.6, places=8)
        self.assertAlmostEqual(c["interaction"]["est"], -0.05, places=8)
        self.assertAlmostEqual(c["main"]["est"], 0.1, places=8)
        self.assertIn("less_minus_more", res["lmw_exact"]["L7_2sls"])
        self.assertEqual(len(res["bridge"]), 4)
        # same rows in both unit systems and the same Dmed: identical bridge cells
        a = res["bridge"]["lmw_units_cpi_annualized|above_median"]["interaction"]["est"]
        b = res["bridge"]["ms_units_pce_log|above_median"]["interaction"]["est"]
        self.assertAlmostEqual(a, b, places=12)

    def test_iv_single_exact(self):
        # H2 = 0.3 + 1.5 P exactly: 2SLS with a constant and any relevant instrument gives 1.5.
        r = lmw.iv_single(synth(), "H2", "P", "y_pc")
        self.assertAlmostEqual(r["elasticity"]["est"], 1.5, places=8)
        r = lmw.iv_single(synth(), "H2", "P", "N")
        self.assertAlmostEqual(r["elasticity"]["est"], 1.5, places=8)
        self.assertIn("skipped", lmw.iv_single(synth(10), "H2", "P", "N"))


class TestBridgeAndHypotheses(unittest.TestCase):
    def bridge(self):
        def c(z):
            return {"n": 300, "interaction": {"est": z / 10, "se": 0.1, "z": z, "p": 0.5}}
        return {"lmw_units_cpi_annualized|above_mean": c(2.0), "lmw_units_cpi_annualized|above_median": c(1.4),
                "ms_units_pce_log|above_mean": c(2.5), "ms_units_pce_log|above_median": c(1.7)}

    def test_bridge_effects_by_hand(self):
        # threshold: (|2.0 - 1.4| + |2.5 - 1.7|) / 2 = (0.6 + 0.8) / 2 = 0.7
        # units:     (|2.0 - 2.5| + |1.4 - 1.7|) / 2 = (0.5 + 0.3) / 2 = 0.4
        e = lmw.bridge_effects(self.bridge())
        self.assertAlmostEqual(e["threshold"], 0.7, places=12)
        self.assertAlmostEqual(e["units"], 0.4, places=12)

    def test_hypotheses_by_hand(self):
        res = {"lmw_exact": {
            "L1_units_on_income": {"income": {"est": 0.62, "se": 0.03, "z": 20.7, "p": 0.0},
                                   "interaction": {"est": -0.2, "se": 0.05, "z": -4.0, "p": 0.0001}},
            "L2_price_on_income": {"interaction": {"est": 0.05, "se": 0.1, "z": 0.5, "p": 0.62}},
            "L7_2sls": {"interaction": {"est": -0.1, "se": 0.2, "z": -0.5, "p": 0.62}},
            "L8_iv_by_instrument": {"per_capita_income": {"elasticity": {"est": 0.2}},
                                    "population": {"elasticity": {"est": 1.0}}}},
            "bridge": self.bridge()}
        h = lmw.hypotheses(res)
        self.assertEqual(len(h), 7)
        st = {k[:2]: v["status"] for k, v in h.items()}
        self.assertEqual(st["Q1"], "not supported")  # p = 0.0001 < 0.05
        self.assertEqual(st["Q2"], "supported")      # p = 0.62
        self.assertEqual(st["Q3"], "not supported")  # -0.2 is outside [-0.115, 0.085]
        self.assertEqual(st["Q4"], "supported")      # 0.62 in [0.50, 0.80]
        self.assertEqual(st["Q5"], "supported")
        self.assertEqual(st["Q6"], "supported")      # 1.0 - 0.2 = 0.8 > 0.5
        self.assertEqual(st["Q7"], "supported")      # 0.7 < 1.0

    def test_published_numbers_complete(self):
        for key, _, _ in lmw.CELLS:
            p = lmw.LMW_PUBLISHED[key]
            for f in ("income", "interaction", "main"):
                self.assertEqual(len(p[f]), 2)


if __name__ == "__main__":
    unittest.main()
