# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Hand-checked fixtures for sc_analysis.py (made with AI agents for MV2 of Munim, Inc.).
import math
import unittest

import numpy as np

import sc_analysis as sc


class TestWLS(unittest.TestCase):
    def test_hc1_by_hand(self):
        # x = 0,1,2 ; y = 0,2,1 -> slope 0.5, intercept 0.5, residuals -0.5, 1, -0.5.
        # HC0 slope variance = sum (x-xbar)^2 u^2 / Sxx^2 = (0.25+0.25)/4 = 0.125; HC1 x 3/1.
        X = [[1, 0], [1, 1], [1, 2]]
        beta, V, _ = sc.wls([0, 2, 1], X)
        self.assertAlmostEqual(beta[0], 0.5)
        self.assertAlmostEqual(beta[1], 0.5)
        self.assertAlmostEqual(V[1, 1], 0.375)
        self.assertAlmostEqual(V[0, 0], 0.875)

    def test_singleton_clusters_equal_hc1(self):
        X = [[1, 0], [1, 1], [1, 2], [1, 4]]
        y = [0, 2, 1, 5]
        _, V, Vc = sc.wls(y, X, groups=["a", "b", "c", "d"])
        self.assertTrue(np.allclose(V, Vc))

    def test_weight_two_equals_duplicate(self):
        b1, _, _ = sc.wls([0, 2, 1], [[1, 0], [1, 1], [1, 2]], w=[1, 2, 1])
        b2, _, _ = sc.wls([0, 2, 2, 1], [[1, 0], [1, 1], [1, 1], [1, 2]])
        self.assertTrue(np.allclose(b1, b2))


class TestGroups(unittest.TestCase):
    def test_rank_groups(self):
        vals = {"a": 5.0, "b": 1.0, "c": 3.0, "d": 2.0, "e": 6.0, "f": 4.0}
        g, p = sc.rank_groups(vals)
        self.assertEqual(g, {"b": 0, "d": 0, "c": 1, "f": 1, "a": 2, "e": 2})
        self.assertAlmostEqual(p["b"], 0.5 / 6 - 0.5)
        self.assertAlmostEqual(p["e"], 5.5 / 6 - 0.5)

    def test_group_slopes_recovers_known_slopes(self):
        # Exact data: group k has slope k+1 and intercept 0, so low minus high = 1 - 3 = -2.
        rows = []
        i = 0
        for k in range(3):
            for st in ("01", "02", "04", "05"):
                for g in (0.1, 0.2, 0.4):
                    i += 1
                    noise = 0.0001 * ((i % 3) - 1)
                    rows.append({"fips": st + "%03d" % i, "grp": k, "z": k - 1.0, "w": 1.0,
                                 "g": g, "y": (k + 1) * g + noise})
        res = sc.group_slopes(rows, "y", "g")
        self.assertAlmostEqual(res["slopes"][0]["est"], 1.0, places=2)
        self.assertAlmostEqual(res["slopes"][2]["est"], 3.0, places=2)
        self.assertAlmostEqual(res["slope_low_minus_high"]["est"], -2.0, places=2)
        self.assertEqual(res["n_by_group"], [12, 12, 12])
        fe = sc.group_slopes(rows, "y", "g", state_fe=True)
        self.assertAlmostEqual(fe["slope_low_minus_high"]["est"], -2.0, places=2)


class TestParsers(unittest.TestCase):
    def test_bps(self):
        text = ("Survey,FIPS,FIPS,Region,Division,County,,1-unit,,,2-units\n"
                "Date,State,County,Code,Code,Name,Bldgs,Units,Value\n"
                "\n"
                "2019,01,001,3,6,Autauga County ,100,100,20000,2,4,500,1,3,400,2,30,3000,"
                "0,0,0,0,0,0,0,0,0,0,0,0\n")
        out = sc.parse_bps_county(text)
        self.assertEqual(out, {"01001": 137})

    def test_bea(self):
        text = ('"GeoFIPS","GeoName","Region","TableName","LineCode","IndustryClassification",'
                '"Description","Unit","2010","2019"\n'
                '" 00000","United States","","CAINC1",1,"...","Personal income","Thousands of dollars",1,2\n'
                '" 01001","Autauga, AL",5,"CAINC1",1,"...","Personal income (thousands of dollars)",'
                '"Thousands of dollars",1500000,2000000\n'
                '" 01001","Autauga, AL",5,"CAINC1",2,"...","Population (persons) 1/","Number of persons",'
                '54000,"(NA)"\n'
                '" 01001","Autauga, AL",5,"CAINC1",3,"...","Per capita personal income","Dollars",27778,36000\n'
                '"Note: footnote line"\n')
        out = sc.parse_bea_cainc1(text)
        self.assertEqual(list(out), ["01001"])
        self.assertEqual(out["01001"]["pi"], {2010: 1500000.0, 2019: 2000000.0})
        self.assertEqual(out["01001"]["pop"], {2010: 54000.0})
        self.assertEqual(out["01001"]["pci"][2019], 36000.0)

    def test_fhfa(self):
        rows = [("County Developmental HPI", None, None, None, None, None),
                ("State", "County", "FIPS code", "Year", "Annual Change (%)", "HPI"),
                ("AL", "Autauga", 1001, 2010, ".", 150.5),
                ("AL", "Autauga", "01001", 2019, 3.1, 180.0),
                ("AL", "Autauga", 1001, 2020, ".", "."),
                ("Source: FHFA", None, None, None, None, None)]
        out = sc.parse_fhfa_rows(rows)
        self.assertEqual(out, {"01001": {2010: 150.5, 2019: 180.0}})

    def test_county_codes_from_tract(self):
        cols = {"tract_id": [1001020100.0, "06037101110", float("nan")], "gamma_units": [0.1, 0.2, 0.3]}
        codes, how = sc.county_codes(cols)
        self.assertIsNone(codes)  # only 2 of 3 look like tracts (< 95%)
        cols["tract_id"][2] = 48201100000
        codes, how = sc.county_codes(cols)
        self.assertEqual(codes, ["01001", "06037", "48201"])
        self.assertEqual(how, "tract=tract_id")

    def test_county_codes_from_state_county(self):
        cols = {"state": [1, 6], "county": [1, 37], "e": [0.1, 0.2]}
        codes, how = sc.county_codes(cols)
        self.assertEqual(codes, ["01001", "06037"])

    def test_pick_elasticity(self):
        names = ["gamma_sqft_fmm_quad", "gamma_units_fmm_lin", "gamma_units_fmm_quad",
                 "gamma_units_fmm_quad_se", "pop2000"]
        labels = {"pop2000": "population"}
        numeric = set(names)
        prim, tier, sec, cands = sc.pick_elasticity(names, labels, numeric)
        self.assertEqual(prim, "gamma_units_fmm_quad")
        self.assertEqual(tier, "units-tier-1")
        self.assertEqual(sec, "gamma_sqft_fmm_quad")
        self.assertNotIn("gamma_units_fmm_quad_se", cands)
        self.assertNotIn("pop2000", cands)

    def test_build_rows(self):
        bea = {"01001": {"pi": {2010: 100.0, 2019: 150.0}, "pop": {2010: 1000.0, 2019: 1100.0},
                         "pci": {2010: 0.1, 2019: 0.13636}},
               "09001": {"pi": {2010: 1.0, 2019: 2.0}, "pop": {2010: 1.0, 2019: 1.0},
                         "pci": {2010: 1.0, 2019: 2.0}}}
        fhfa = {"01001": {2010: 100.0, 2019: 200.0}}
        permits = {y: {"01001": 10} for y in range(2011, 2020)}
        rows = sc.build_rows(2010, 2019, bea, fhfa, permits, {"01001": 0, "09001": 1},
                             {"01001": -0.25, "09001": 0.25})
        self.assertEqual(len(rows), 1)  # Connecticut dropped
        r = rows[0]
        self.assertAlmostEqual(r["price_growth"], math.log(2))
        self.assertAlmostEqual(r["g_inc"], math.log(1.5))
        self.assertAlmostEqual(r["permits_per_1000"], 90.0)


if __name__ == "__main__":
    unittest.main()
