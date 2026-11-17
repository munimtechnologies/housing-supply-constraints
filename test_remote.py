# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Hand-checked tests for remote.py (part 3). Every expected number is worked out by hand in the
comments; none comes from running the code."""

import math
import unittest

import remote as rm

# A B08301 row whose internal sums hold (line 1 first):
# car L2 = alone 50 + carpool 10 = 60; carpool L4 = 4+2+1+1+2 = 10;
# transit L10 = 5+3+1+0+1 = 10; L16..L21 = 1,2,3,4,5,15 (sum 30);
# total L1 = 60 + 10 + 30 = 100. Worked from home (L21) = 15.
V = [100, 60, 50, 10, 4, 2, 1, 1, 2, 10, 5, 3, 1, 0, 1, 1, 2, 3, 4, 5, 15]


def seq_row(logrecno, v, pre=("7", "8", "9"), post=("3", "3")):
    # six identifier fields, then `pre` filler cells, then the table, then `post`.
    return (["ACSSF", "2019e5", "al", "000", "0027", logrecno] + list(pre)
            + [str(x) for x in v] + list(post))


class TestB08301(unittest.TestCase):
    def test_sums_hold(self):
        self.assertTrue(rm.b08301_ok(V))
        self.assertTrue(rm.b08301_ok([2 * x for x in V]))

    def test_sums_fail_when_shifted_or_changed(self):
        bad = list(V)
        bad[20] = 16  # WFH 16 -> total should be 101
        self.assertFalse(rm.b08301_ok(bad))
        self.assertFalse(rm.b08301_ok(V[1:] + [0]))

    def test_cells(self):
        row = seq_row("0000012", V)
        # identifiers are positions 1-6, filler 7-9, so the table starts at position 10.
        self.assertEqual(rm.cells(row, 10), [float(x) for x in V])
        self.assertIsNone(rm.cells(row, 20))  # runs past the end of the row (32 fields)
        row2 = list(row)
        row2[12] = "."  # a non-numeric cell inside the table
        self.assertIsNone(rm.cells(row2, 10))

    def test_find_start_documented_and_scan(self):
        rows = [seq_row("0000012", V), seq_row("0000013", [3 * x for x in V])]
        self.assertEqual(rm.find_start(rows, preferred=10), (10, 2, 2))
        # A wrong documented position (8) must be caught: at 8, "line 1" is 9, so the sums fail;
        # the scan over positions 7..12 finds 10 (at 11, L2=50 != L3+L4=10+4).
        self.assertEqual(rm.find_start(rows, preferred=8), (10, 2, 2))
        # Rows with no workers are not counted.
        rows0 = rows + [seq_row("0000014", [0] * 21)]
        self.assertEqual(rm.find_start(rows0, preferred=10), (10, 2, 2))


class TestParsers(unittest.TestCase):
    def test_parse_geo19(self):
        def geo(sumlev, comp, logrec, geoid, name):
            return ",".join(["ACSSF", "AL", sumlev, comp, logrec] + [""] * 43
                            + [geoid, '"%s"' % name, "", "", ""])
        text = "\n".join([
            geo("040", "00", "0000001", "04000US01", "Alabama"),
            geo("050", "00", "0000012", "05000US01001", "Autauga County, Alabama"),
            geo("050", "01", "0000013", "05001US01001", "Autauga County, Alabama -- Urban"),
            geo("050", "00", "0000014", "05000US01003", "Baldwin County, Alabama"),
        ])
        self.assertEqual(rm.parse_geo19(text), {"0000012": "01001", "0000014": "01003"})

    def test_parse_acs23(self):
        header = ["GEO_ID"] + ["B08301_%s%03d" % (t, i) for i in range(1, 22) for t in ("E", "M")]
        # E001 is column 1, E021 is column 1 + 2*20 = 41.
        def line(geo, total, wfh):
            vals = ["0"] * 42
            vals[0], vals[1], vals[41] = geo, str(total), str(wfh)
            return "|".join(vals) + "\n"
        lines = ["|".join(header) + "\n", line("0400000US01", 2000000, 150000),
                 line("0500000US01001", 25000, 2500), line("0500000US01003", 0, 0)]
        self.assertEqual(rm.parse_acs23(lines), {"01001": {"workers": 25000.0, "wfh": 2500.0}})

    def test_norm(self):
        self.assertEqual(rm.norm(".Doña Ana County"), "dona ana county")
        self.assertEqual(rm.norm("  New   Mexico "), "new mexico")

    def test_parse_coest(self):
        text = ("SUMLEV,REGION,DIVISION,STATE,COUNTY,STNAME,CTYNAME,ESTIMATESBASE2020,"
                "POPESTIMATE2020,POPESTIMATE2025\n"
                "040,3,6,01,000,Alabama,Alabama,5025437,5032962,5200000\n"
                "050,3,6,01,001,Alabama,Autauga County,58805,58914,61000\n"
                "050,4,8,35,013,New Mexico,Doña Ana County,219561,220000,226000\n")
        pop, names = rm.parse_coest(text)
        self.assertEqual(sorted(pop), ["01001", "35013"])
        self.assertEqual(pop["01001"], {"base": 58805.0, 2020: 58914.0, 2025: 61000.0})
        self.assertEqual(names[("dona ana county", "new mexico")], "35013")

    def test_parse_hu_xlsx(self):
        rows = [
            ("Annual Estimates of Housing Units for Counties (CO-EST2025-HU)", None, None, None, None),
            ("Geographic Area", "April 1, 2020 Estimates Base", "Housing Unit Estimate (as of July 1)", None, None),
            (None, None, 2020, 2021, "2025"),
            ("United States", 140498736, 140803000, 142153000, 147000000),
            (".Autauga County, Alabama", 25000, 25100, 25300, 25600),
            (".Doña Ana County, New Mexico", 90000.0, 90100.0, 90500.0, 91000.0),
        ]
        got = rm.parse_hu_xlsx(rows)
        self.assertEqual(got[("autauga county", "alabama")],
                         {"base": 25000.0, 2020: 25100.0, 2021: 25300.0, 2025: 25600.0})
        self.assertEqual(got[("dona ana county", "new mexico")][2025], 91000.0)
        self.assertEqual(len(got), 2)

    def test_parse_gazetteer(self):
        text = ("USPS\tGEOID\tANSICODE\tNAME\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\tINTPTLAT\tINTPTLONG   \n"
                "AL\t01001\t00161526\tAutauga County\t1539634184\t25674812\t594.456\t9.913\t32.532237\t-86.64644   \n")
        self.assertEqual(rm.parse_gazetteer(text), {"01001": 594.456})


class TestBuildRows(unittest.TestCase):
    def test_one_county(self):
        f = "01001"
        rows = rm.build_rows(
            groups={f: 2, "09001": 0},  # Connecticut is dropped
            acs19={f: {"workers": 20000.0, "wfh": 1000.0, "ok": True},
                   "09001": {"workers": 1.0, "wfh": 0.0, "ok": True}},
            acs23={f: {"workers": 25000.0, "wfh": 3000.0}},
            hpi={f: {2019: 100.0, 2023: 150.0, 2025: 160.0}},
            hu={f: {"base": 1000.0, 2025: 1100.0}}, hu_year=2025,
            pop={f: {"base": 2000.0, 2025: 2200.0}}, pop_year=2025,
            permits={2020: {f: 10}, 2021: {f: 20}}, permit_years=[2020, 2021],
            land={f: 100.0}, delin={f: {"cbsa": "33860", "metro": True}},
            price_end=2023, price_latest=2025)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        # 2015-19: 1000/20000 = 5%; 2019-23: 3000/25000 = 12%; change 7 points.
        self.assertAlmostEqual(r["w19"], 5.0)
        self.assertAlmostEqual(r["w23"], 12.0)
        self.assertAlmostEqual(r["d_wfh"], 7.0)
        self.assertAlmostEqual(r["price_19_23"], 100 * math.log(1.5))  # 40.5465...
        self.assertAlmostEqual(r["price_19_L"], 100 * math.log(1.6))
        self.assertAlmostEqual(r["hu_growth"], 100 * math.log(1.1))   # 9.5310...
        self.assertAlmostEqual(r["pop_growth"], 100 * math.log(1.1))
        self.assertAlmostEqual(r["permits_per_1000hu"], 30.0)         # 1000 * 30 / 1000
        self.assertAlmostEqual(r["log_density"], math.log(20.0))      # 2000 people / 100 sq mi
        self.assertEqual((r["cbsa"], r["metro"], r["grp"], r["w"]), ("33860", True, 2, 20000.0))

    def test_missing_pieces_are_none(self):
        f = "01003"
        rows = rm.build_rows({f: 0}, {f: {"workers": 10.0, "wfh": 1.0, "ok": True}}, {}, {}, {},
                             2025, {}, 2025, {}, [], {}, {})
        r = rows[0]
        for k in ("w23", "d_wfh", "price_19_23", "hu_growth", "permits_per_1000hu", "log_density"):
            self.assertIsNone(r[k], k)
        self.assertIsNone(r["cbsa"])
        self.assertFalse(r["metro"])


def synthetic(b=(2.0, 1.0, 0.5), with_control=False):
    """Three metros, each with counties in all three terciles and x = 1..4.
    y = metro effect + 0.3 k + b_k x (+ 0.8 * c, c = 0.1 x^2 + 1[metro A])."""
    eff = {"A": 1.0, "B": -2.0, "C": 0.5}
    rows = []
    for m, e in eff.items():
        for k in range(3):
            for x in (1, 2, 3, 4):
                c = 0.1 * x * x + (1.0 if m == "A" else 0.0)
                y = e + 0.3 * k + b[k] * x + (0.8 * c if with_control else 0.0)
                rows.append({"fips": "%s%d%d" % (m, k, x), "cbsa": m, "state": "01", "grp": k,
                             "x": float(x), "y": y, "c": c, "w": 1.0 + (x % 2)})
    return rows


class TestFit(unittest.TestCase):
    def test_split_slopes_within_fe(self):
        res = rm.fit(synthetic(), "y", xcol="x", fe="cbsa", cluster="cbsa", min_n=5)
        self.assertEqual(res["n"], 36)
        self.assertEqual(res["n_by_group"], [12, 12, 12])
        for got, want in zip(res["slopes"], (2.0, 1.0, 0.5)):
            self.assertAlmostEqual(got["est"], want, places=7)
        self.assertAlmostEqual(res["slope_low_minus_high"]["est"], 1.5, places=7)

    def test_control(self):
        # The metro-A part of c is absorbed by the metro effect; 0.1 x^2 is not collinear
        # with the tercile slopes on x, so the slopes are still recovered exactly.
        res = rm.fit(synthetic(with_control=True), "y", xcol="x", fe="cbsa", cluster="cbsa",
                     controls=("c",), min_n=5)
        for got, want in zip(res["slopes"], (2.0, 1.0, 0.5)):
            self.assertAlmostEqual(got["est"], want, places=6)

    def test_pooled(self):
        rows = synthetic(b=(1.7, 1.7, 1.7))
        res = rm.fit(rows, "y", xcol="x", fe="cbsa", cluster="cbsa", split=False, min_n=5)
        self.assertAlmostEqual(res["slope"]["est"], 1.7, places=7)
        # Without the metro effect, y = e_m + 0.3 k + 1.7 x and x is balanced within every
        # metro and tercile, so the national slope on x is still exactly 1.7.
        res2 = rm.fit(rows, "y", xcol="x", fe=None, cluster="cbsa", split=False, min_n=5)
        self.assertAlmostEqual(res2["slope"]["est"], 1.7, places=7)

    def test_singletons_and_min_n(self):
        rows = synthetic() + [{"fips": "Z", "cbsa": "Z", "state": "01", "grp": 0, "x": 9.0,
                               "y": 99.0, "c": 0.0, "w": 1.0}]
        res = rm.fit(rows, "y", xcol="x", fe="cbsa", cluster="cbsa", min_n=5)
        self.assertEqual(res["n"], 36)  # the lone county in metro Z is dropped
        self.assertAlmostEqual(res["slopes"][0]["est"], 2.0, places=7)
        self.assertIn("skipped", rm.fit(rows, "y", xcol="x", fe="cbsa", cluster="cbsa"))  # 36 < 45


class TestReadouts(unittest.TestCase):
    def block(self, d_est, d_se, pooled_est, pooled_p):
        return {"price_19_23": {"split": {"slope_low_minus_high": {"est": d_est, "se": d_se, "p": 0.5}},
                                "pooled": {"slope": {"est": pooled_est, "se": 0.1, "p": pooled_p}}}}

    def test_tight_null(self):
        # CI = 0.05 +/- 1.96*0.1 = [-0.146, 0.246]; half the pooled slope = 0.5 > 0.246.
        self.assertEqual(rm.tight_null(self.block(0.05, 0.1, 1.0, 0.001))["status"], "tight null")
        # Half the pooled slope = 0.2 < 0.246.
        self.assertEqual(rm.tight_null(self.block(0.05, 0.1, 0.4, 0.001))["status"], "not a tight null")
        # CI = 0.5 +/- 0.196 excludes zero.
        self.assertEqual(rm.tight_null(self.block(0.5, 0.1, 1.0, 0.001))["status"], "gap is significant")
        self.assertTrue(rm.tight_null(self.block(0.05, 0.1, 1.0, 0.2))["status"].startswith("not evaluable"))

    def test_ratios(self):
        def sl(a, b, c):
            return {"split": {"slopes": [{"est": a}, {"est": b}, {"est": c}]}}
        block = {"d_wfh": sl(0.5, 0.5, 0.25), "price_19_23": sl(2.0, 1.0, 0.5),
                 "hu_growth": sl(0.25, 0.5, 1.0)}
        r = rm.ratios(block)
        self.assertAlmostEqual(r[0]["iv_price"], 4.0)     # 2.0 / 0.5
        self.assertAlmostEqual(r[2]["iv_hu"], 4.0)        # 1.0 / 0.25
        self.assertAlmostEqual(r[0]["price_per_hu"], 8.0)  # 2.0 / 0.25
        self.assertAlmostEqual(r[2]["price_per_hu"], 0.5)  # 0.5 / 1.0


if __name__ == "__main__":
    unittest.main()
