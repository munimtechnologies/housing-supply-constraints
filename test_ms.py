# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Hand-checked tests for ms.py (part 5). Every expected number is worked out by hand in the
comments or follows exactly from how the synthetic data are built (a model that fits the data
with zero residual must be recovered exactly); none comes from running the code."""

import math
import unittest

import numpy as np

import ms


class TestFred(unittest.TestCase):
    def test_parse(self):
        text = "observation_date,PCEPI\n1999-01-01,72.0\n2000-01-01,73.822\n2001-01-01,.\nbad\n"
        self.assertEqual(ms.parse_fred_annual(text), {1999: 72.0, 2000: 73.822})


class TestTsls(unittest.TestCase):
    def test_ols_hc1_dk_cluster_by_hand(self):
        # One regressor equal to 1 (no other columns): beta = mean(y) = (1+3+2+6)/4 = 3.
        # Residuals e = (-2, 0, -1, 3). B = (X'X)^-1 = 1/4.
        # HC1: sum e^2 = 14, V = (1/4)(14)(1/4) * n/(n-k) = 14/16 * 4/3 = 7/6.
        # Driscoll-Kraay, periods (1,1,2,2): h1 = -2, h2 = 2.
        #   S = h1^2 + h2^2 + (1 - 1/2)(h2 h1 + h1 h2) = 8 - 4 = 4; V = 4/16 * (n-1)/(n-k) = 0.25.
        # Cluster (a,a,b,b): same sums, S = 8, V = 8/16 * G/(G-1) = 0.5 * 2 = 1.0.
        y = [1.0, 3.0, 2.0, 6.0]
        f = ms.tsls(y, None, [[1.0]] * 4, None, time=[1, 1, 2, 2], cluster=["a", "a", "b", "b"])
        self.assertAlmostEqual(f["beta"][0], 3.0, places=12)
        self.assertAlmostEqual(f["V_hc1"][0, 0], 7.0 / 6.0, places=12)
        self.assertAlmostEqual(f["V_dk"][0, 0], 0.25, places=12)
        self.assertAlmostEqual(f["V_cl"][0, 0], 1.0, places=12)

    def test_iv_exact_with_constant(self):
        # y = 2 + 3x exactly, so 2SLS with any relevant instrument returns (3, 2).
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        z = [1.0, 3.0, 2.0, 5.0, 4.0]
        y = [2 + 3 * v for v in x]
        f = ms.tsls(y, [[v] for v in x], [[1.0]] * 5, [[v] for v in z])
        self.assertAlmostEqual(f["beta"][0], 3.0, places=10)
        self.assertAlmostEqual(f["beta"][1], 2.0, places=10)

    def test_iv_differs_from_ols_by_hand(self):
        # No constant. IV: sum(z y) / sum(z x) = (3 - 1 + 0 - 2) / (2 - 0 + 1 - 1) = 0 / 2 = 0.
        # OLS: sum(x y) / sum(x^2) = (6 + 0 + 0 + 2) / (4 + 0 + 1 + 1) = 8/6.
        z = [[1.0], [-1.0], [1.0], [-1.0]]
        x = [[2.0], [0.0], [1.0], [1.0]]
        y = [3.0, 1.0, 0.0, 2.0]
        self.assertAlmostEqual(ms.tsls(y, x, None, z)["beta"][0], 0.0, places=12)
        self.assertAlmostEqual(ms.tsls(y, None, x, None)["beta"][0], 8.0 / 6.0, places=12)


def ld_rows(n=40):
    rows = []
    for i in range(n):
        E = 0.1 + 0.01 * i
        g = 0.3 + 0.2 * ((i * 7) % 11) / 10.0
        rows.append({"m": str(i), "E": E, "D": 1.0 if E > 0.295 else 0.0, "w": 1.0 + (i % 5),
                     "g_real": g, "g_nom": g + 0.3,
                     # a pure level effect of E and NO interaction:
                     "hu_growth": 0.5 * g + 1.0 * E,
                     "price_growth": 0.9 * g - 0.5 * g * E + 0.05 * ((i * 3) % 7)})
    return rows


class TestLongDifference(unittest.TestCase):
    def test_main_effect_mechanism(self):
        # hu_growth = 0.5 g + 1.0 E exactly. With the E main effect the model fits exactly, so
        # the interaction is 0 and stays 0 when income is shifted by a constant (g_nom = g + 0.3:
        # y = 0.5 g_nom - 0.15 + E, again exact). Without it, E is not in the span of
        # [1, g, gE], so part of E's level effect loads on gE (nonzero), and that loading changes
        # with the shift, i.e. with the deflator.
        rows = ld_rows()
        for gcol in ("g_real", "g_nom"):
            r = ms.ld_fit(rows, "hu_growth", gcol, "E", weighted=True, main=True)
            self.assertAlmostEqual(r["interaction"]["est"], 0.0, places=8)
            self.assertAlmostEqual(r["income"]["est"], 0.5, places=8)
            self.assertAlmostEqual(r["main"]["est"], 1.0, places=8)
        a = ms.ld_fit(rows, "hu_growth", "g_real", "E", weighted=True, main=False)
        b = ms.ld_fit(rows, "hu_growth", "g_nom", "E", weighted=True, main=False)
        self.assertGreater(abs(a["interaction"]["est"]), 1e-4)
        self.assertGreater(abs(a["interaction"]["est"] - b["interaction"]["est"]), 1e-6)

    def test_switch_effects_by_hand(self):
        # z = 4 - 3[with_main] - 0.5[unweighted] - 1[above_mean]: each switch changes z by a
        # constant, so the mean absolute changes are main 3, weights 0.5, measure 1.
        grid = {}
        for wv in ("weighted", "unweighted"):
            for mv in ("continuous", "above_mean"):
                for ev in ("no_main", "with_main"):
                    z = 4 - 3 * (ev == "with_main") - 0.5 * (wv == "unweighted") - 1 * (mv == "above_mean")
                    grid["%s|%s|%s" % (wv, mv, ev)] = {"interaction": {"z": z}}
        sw = ms.switch_effects(grid)
        self.assertAlmostEqual(sw["main_effect"], 3.0)
        self.assertAlmostEqual(sw["weights"], 0.5)
        self.assertAlmostEqual(sw["measure"], 1.0)

    def test_analyse_ld_runs(self):
        out = ms.analyse_ld(ld_rows())
        self.assertIn("weighted|continuous|no_main", out["reduced_form"]["hu_growth"])
        self.assertIn("weighted|continuous|with_main|nominal_income", out["reduced_form"]["price_growth"])
        s = out["structural"]["weighted|continuous|with_main"]
        self.assertEqual(s["n"], 40)
        self.assertEqual(len(s["first_stage_F"]), 2)


def panel_rows(n_m=20, years=range(2000, 2014)):
    """Balanced panel. lny has a metro x year pattern that is not additive, E varies by metro."""
    rows = []
    gamma = {t: 0.3 * math.sin(t) for t in years}  # elasticity-specific year effects
    for m in range(n_m):
        E = 0.1 + 0.02 * m
        for k, t in enumerate(years):
            lny = 10 + 0.02 * m + 0.015 * k + 0.01 * ((m * k) % 5) + 0.004 * ((m * m + k) % 3)
            rows.append({"m": "M%d" % m, "t": t, "E": E, "D": 1.0 if m >= 10 else 0.0,
                         "w": 1.0 + m, "lny": lny, "a": 0.1 * m, "b": 0.05 * k, "gamma": gamma[t],
                         "lnhp": 0.4 * lny + 0.01 * ((m + 2 * k) % 4)})
    return rows


class TestPanel(unittest.TestCase):
    def test_elasticity_by_year_recovers_truth(self):
        # lnpermits = a_m + b_t + 0.8 lny + gamma_t E, with NO lny x E effect. With metro, year
        # and E x year effects the model fits exactly: lny = 0.8, lny x E = 0.
        rows = panel_rows()
        for r in rows:
            r["lnpermits"] = r["a"] + r["b"] + 0.8 * r["lny"] + r["gamma"] * r["E"]
        lny = ("lny", lambda r: r["lny"])
        lnyE = ("lny_x_E", lambda r: r["lny"] * r["E"])
        f = ms.panel_fit(rows, "lnpermits", [lny, lnyE], elas_by_year="E")
        self.assertEqual(f["n"], 280)
        self.assertAlmostEqual(f["coef"]["lny"]["est"], 0.8, places=6)
        self.assertAlmostEqual(f["coef"]["lny_x_E"]["est"], 0.0, places=6)

    def test_local_vs_national_and_full_run(self):
        # lnpermits = a_m + b_t + 0.5 local + 1.2 national x E, where national is the weighted
        # year mean of lny and local = lny - national. A3 fits exactly: (0.5, 0, 1.2).
        rows = panel_rows()
        nat = ms.national_path(rows)
        for r in rows:
            r["lnpermits"] = r["a"] + r["b"] + 0.5 * (r["lny"] - nat[r["t"]]) + 1.2 * nat[r["t"]] * r["E"]
        out = ms.analyse_panel(rows)
        c = out["A3_local_vs_national"]["coef"]
        self.assertAlmostEqual(c["local"]["est"], 0.5, places=6)
        self.assertAlmostEqual(c["local_x_E"]["est"], 0.0, places=6)
        self.assertAlmostEqual(c["national_x_E"]["est"], 1.2, places=6)
        # years 2012-2013 only: 40 metro-years, below the 200 minimum
        self.assertIn("skipped", out["A4b_late"])
        self.assertIn("lnhp_x_E", out["A7_structural"]["coef"])
        self.assertEqual(len(out["A7_structural"]["first_stage_F_dk"]), 2)
        h = ms.hypotheses(ms.analyse_ld(ld_rows()), out)
        self.assertEqual(len(h), 9)


class TestHypotheses(unittest.TestCase):
    def test_p3_logic(self):
        def cell(est, p):
            return {"interaction": {"est": est, "se": 0.1, "z": est / 0.1, "p": p}}
        hu = {"weighted|continuous|no_main": cell(0.5, 0.01), "weighted|continuous|with_main": cell(0.1, 0.4)}
        ld = {"reduced_form": {"hu_growth": hu, "price_growth": {}}, "structural": {}}
        h = ms.hypotheses(ld, {})
        p3 = [v for k, v in h.items() if k.startswith("P3")][0]
        self.assertEqual(p3["status"], "supported")
        hu["weighted|continuous|with_main"] = cell(0.3, 0.4)  # 0.3 > half of 0.5
        p3 = [v for k, v in ms.hypotheses(ld, {}).items() if k.startswith("P3")][0]
        self.assertEqual(p3["status"], "not supported")


if __name__ == "__main__":
    unittest.main()
