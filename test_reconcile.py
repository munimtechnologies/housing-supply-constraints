# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Hand-checked fixtures for reconcile.py (made with AI agents for MV2 of Munim, Inc.).
import math
import unittest

import numpy as np

import reconcile as rc


def bea_row(code, name, line, a, b):
    return '"%s","%s","","CAINC1",%d,"...","desc","unit",%s,%s\n' % (code, name, line, a, b)


class TestBEA(unittest.TestCase):
    def test_counties_msas_and_collisions(self):
        text = ('"GeoFIPS","GeoName","Region","TableName","LineCode","IndustryClassification",'
                '"Description","Unit","2000","2020"\n'
                + bea_row("00000", "United States", 1, 1, 2)
                + bea_row("00998", "United States (Metropolitan Portion)", 1, 5, 6)
                + bea_row("24510", "Baltimore City, MD", 1, 100, 200)
                + bea_row("24510", "Baltimore City, MD", 2, 10, '"(NA)"')
                + bea_row("12580", "Baltimore-Columbia-Towson, MD (Metropolitan Statistical Area)", 1, 1000, 3000)
                + bea_row("29510", "St. Louis City, MO", 1, 7, 8)
                + bea_row("29510", "Fake, XX (Metropolitan Statistical Area) *", 1, 70, 80)
                + bea_row("35614", "New York-Jersey City-White Plains, NY-NJ (Metropolitan Division)", 1, 9, 9)
                + '"Note: footnote"\n')
        counties, msas, coll = rc.parse_bea_all(text)
        self.assertEqual(sorted(counties), ["24510", "29510"])
        self.assertEqual(counties["24510"]["pi"], {2000: 100.0, 2020: 200.0})
        self.assertEqual(counties["24510"]["pop"], {2000: 10.0})
        self.assertEqual(counties["29510"]["pi"][2000], 7.0)
        self.assertEqual(sorted(msas), ["12580", "29510"])
        self.assertEqual(msas["29510"]["pi"][2020], 80.0)
        self.assertEqual(coll, {"29510"})


class TestHousingUnits(unittest.TestCase):
    def test_both_layouts_and_merge(self):
        t00 = ("SUMLEV,STATE,COUNTY,CTYNAME,HUESTBASE2000,HUEST_2000,HUEST_2001,CENSUS2010HU,HUEST_2010\n"
               "040,01,,Alabama,1,1,1,1,1\n"
               "050,01,001,Autauga County,17733,17845,18344,22135,22155\n")
        t10 = ("SUMLEV,REGION,STATE,COUNTY,REGNAME,STNAME,CTYNAME,CENSUS2010HU,HUESTIMATESBASE2010,"
               "HUESTIMATE2010,HUESTIMATE2019,HUESTIMATE042020,HUESTIMATE2020\n"
               "050,3,01,001,South Region,Alabama,Autauga County,22135,22136,22160,24000,24100,24150\n")
        a, b = rc.parse_hu(t00), rc.parse_hu(t10)
        self.assertEqual(a, {"01001": {"c2000": 17733.0, 2000: 17845.0, 2001: 18344.0,
                                       "c2010": 22135.0, 2010: 22155.0}})
        self.assertEqual(b, {"01001": {"c2010": 22135.0, 2010: 22160.0, 2019: 24000.0,
                                       "apr2020": 24100.0, 2020: 24150.0}})
        m = rc.merge_hu(a, b)["01001"]
        self.assertEqual(m[2010], 22160.0)  # the 2010s file wins
        self.assertEqual(rc.hu_at(m, 2000), 17733.0)  # census 2000 base, not July
        self.assertEqual(rc.hu_at(m, 2010), 22135.0)
        self.assertEqual(rc.hu_at(m, 2020), 24100.0)  # April 2020, not July
        self.assertEqual(rc.hu_at(m, 2001), 18344.0)
        self.assertIsNone(rc.hu_at(m, 2005))


class TestDelineationAndHPI(unittest.TestCase):
    def test_delineation(self):
        rows = [("List 1. CORE BASED STATISTICAL AREAS",), (None,),
                ("CBSA Code", "Metropolitan Division Code", "CSA Code", "CBSA Title",
                 "Metropolitan/Micropolitan Statistical Area", "Metropolitan Division Title", "CSA Title",
                 "County/County Equivalent", "State Name", "FIPS State Code", "FIPS County Code",
                 "Central/Outlying County"),
                ("35620", "35614", "408", "New York-Newark-Jersey City, NY-NJ", "Metropolitan Statistical Area",
                 "New York-Jersey City-White Plains, NY-NJ", "New York-Newark, NY-NJ-CT-PA", "Bronx County",
                 "New York", "36", "005", "Central"),
                ("10100", None, None, "Aberdeen, SD", "Micropolitan Statistical Area", None, None,
                 "Brown County", "South Dakota", 46, 13, "Central"),
                ("Note: source OMB",)]
        out = rc.parse_delineation(rows)
        self.assertEqual(out, {
            "36005": {"cbsa": "35620", "div": "35614", "metro": True, "title": "New York-Newark-Jersey City, NY-NJ"},
            "46013": {"cbsa": "10100", "div": "", "metro": False, "title": "Aberdeen, SD"}})

    def test_cbsa_hpi(self):
        rows = [("FHFA CBSA HPI",),
                ("CBSA", "Name", "Year", "Annual Change (%)", "HPI", "HPI with 1990 base"),
                (10180, "Abilene, TX", 2000, ".", 100.0, 120.0),
                ("10180", "Abilene, TX", 2020, "5", 180.0, "."),
                ("35614", "NY division", 2000, ".", ".", ".")]
        self.assertEqual(rc.parse_hpi_rows(rows), {"10180": {2000: 100.0, 2020: 180.0}})


class TestDemean(unittest.TestCase):
    def test_two_way_balanced_by_hand(self):
        # y_it - ybar_i - ybar_t + ybar: means a=1.5, b=4.5, t1=2, t2=4, all=3.
        M, it = rc.demean([1.0, 2.0, 3.0, 6.0], [1, 1, 1, 1], [["a", "a", "b", "b"], [1, 2, 1, 2]])
        self.assertTrue(np.allclose(M[:, 0], [0.5, -0.5, -0.5, 0.5]))

    def test_one_way_weighted(self):
        # weighted mean (1*1 + 3*3)/4 = 2.5
        M, _ = rc.demean([[1.0], [3.0]], [1, 3], [["g", "g"]])
        self.assertTrue(np.allclose(M[:, 0], [-1.5, 0.5]))


def synthetic_panel():
    b = [[0.5, 0.3, 0.2], [0.2, 0.1, 0.0], [0.1, 0.0, -0.05]]  # cumulative 1.0, 0.3, 0.05
    rows = []
    for i in range(12):
        k = i // 4
        for t in range(2001, 2021):
            g = [0.05 * math.sin(1.3 * i + 0.7 * t + 2.1 * j) + 0.02 * math.cos(0.37 * i * t + j)
                 for j in range(3)]
            y = 0.1 * i - 0.01 * (t - 2000) + 0.003 * (t % 3) + sum(b[k][j] * g[j] for j in range(3))
            rows.append({"fips": "%02d%03d" % (i % 4 + 1, i), "t": t, "grp": k, "w": 1.0 + i,
                         "g0": g[0], "g1": g[1], "g2": g[2], "y": y})
    return rows


class TestPanel(unittest.TestCase):
    def test_recovers_cumulative_responses(self):
        rows = synthetic_panel()
        for fe in ("county+year", "county+state-year"):
            res = rc.panel_fit(rows, "y", fe=fe)
            self.assertEqual(res["n"], 240)
            self.assertEqual(res["n_counties"], 12)
            self.assertAlmostEqual(res["cumulative"][0]["est"], 1.0, places=6)
            self.assertAlmostEqual(res["cumulative"][1]["est"], 0.3, places=6)
            self.assertAlmostEqual(res["cumulative"][2]["est"], 0.05, places=6)
            self.assertAlmostEqual(res["cumulative_low_minus_high"]["est"], 0.95, places=6)

    def test_too_few_rows_skipped(self):
        self.assertIn("skipped", rc.panel_fit(synthetic_panel()[:150], "y"))

    def test_panel_rows(self):
        bea = {"01001": {"pi": {1997: 100.0, 1998: 110.0, 1999: 121.0, 2000: 133.1, 2001: 146.41},
                         "pop": {2000: 1000.0, 2001: 1010.0}, "pci": {}},
               "09001": {"pi": {y: 1.0 for y in range(1990, 2003)}, "pop": {2000: 1.0, 2001: 1.0}, "pci": {}}}
        rows = rc.panel_rows([2001, 2002], bea, {"01001": {2000: 100.0, 2001: 110.0}},
                             {2001: {"01001": 20}}, {"01001": {2000: 500.0, 2001: 505.0}},
                             {"01001": 1, "09001": 0})
        self.assertEqual(len(rows), 1)  # 2002 has no income; Connecticut dropped
        r = rows[0]
        for key in ("g0", "g1", "g2", "dprice"):
            self.assertAlmostEqual(r[key], math.log(1.1))
        self.assertAlmostEqual(r["permits_rate"], 20.0)
        self.assertAlmostEqual(r["dhu"], math.log(1.01))
        self.assertAlmostEqual(r["dpop"], math.log(1.01))
        self.assertEqual(r["w"], 1000.0)


class TestLongDifference(unittest.TestCase):
    def test_tercile_slopes_hc1(self):
        rows = []
        i = 0
        for k in range(3):
            for g in (0.1, 0.2, 0.4, 0.5):
                i += 1
                rows.append({"cl": "m%d" % i, "grp": k, "w": 1.0, "g": g,
                             "y": (k + 1) * g + 0.0001 * ((i % 3) - 1)})
        res = rc.tercile_slopes(rows, "y", "g", cluster=False)
        self.assertEqual(res["se_type"], "HC1")
        self.assertAlmostEqual(res["slopes"][0]["est"], 1.0, places=2)
        self.assertAlmostEqual(res["slope_low_minus_high"]["est"], -2.0, places=2)

    def test_county_rows(self):
        bea = {"01001": {"pi": {2000: 100.0, 2020: 150.0}, "pop": {2000: 1000.0, 2020: 1100.0},
                         "pci": {2000: 100.0, 2020: 136.0}},
               "09001": {"pi": {2000: 1.0, 2020: 2.0}, "pop": {2000: 1.0, 2020: 1.0},
                         "pci": {2000: 1.0, 2020: 2.0}}}
        rows = rc.county_ld_rows(2000, 2020, bea, {"01001": {2000: 100.0, 2020: 200.0}},
                                 {"01001": {"c2000": 400.0, "apr2020": 500.0, 2020: 9999.0}},
                                 {y: {"01001": 10} for y in range(2001, 2021)}, {"01001": 2, "09001": 0})
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["cl"], "01")
        self.assertAlmostEqual(r["hu_growth"], math.log(1.25))
        self.assertAlmostEqual(r["price_growth"], math.log(2))
        self.assertAlmostEqual(r["g_pci"], math.log(1.36))
        self.assertAlmostEqual(r["permits_per_1000"], 200.0)

    def test_metro_units_elasticity_and_rows(self):
        delin = {"36005": {"cbsa": "35620", "div": "35614", "metro": True, "title": ""},
                 "34003": {"cbsa": "35620", "div": "35084", "metro": True, "title": ""},
                 "46013": {"cbsa": "10100", "div": "", "metro": False, "title": ""},
                 "09001": {"cbsa": "14860", "div": "", "metro": True, "title": ""}}
        members, divs = rc.metro_units(delin)
        self.assertEqual(members, {"35620": ["34003", "36005"]})
        self.assertEqual(divs, {"35620": {"35614": ["36005"], "35084": ["34003"]}})
        el = rc.metro_elasticity(members, {"36005": 0.2, "34003": 0.5}, {"36005": 1, "34003": 3})
        self.assertAlmostEqual(el["35620"], 0.425)  # (0.2*1 + 0.5*3) / 4
        msas = {"35620": {"pi": {2000: 100.0, 2020: 200.0}, "pop": {2000: 10.0, 2020: 12.0},
                          "pci": {2000: 10.0, 2020: 16.0}}}
        hu = {"36005": {"c2000": 100.0, "apr2020": 110.0}, "34003": {"c2000": 300.0, "apr2020": 390.0}}
        cbsa_hpi = {"35614": {2000: 100.0, 2020: 200.0}, "35084": {2000: 100.0, 2020: 150.0}}
        permits = {y: {"36005": 1, "34003": 2} for y in range(2001, 2021)}
        del permits[2005]["34003"]
        rows = rc.metro_ld_rows(2000, 2020, members, divs, msas, {}, hu, cbsa_hpi,
                                {"36005": {2000: 50.0, 2020: 100.0}}, permits, {"35620": 0})
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["income_source"], "bea_msa")
        self.assertAlmostEqual(r["g_inc"], math.log(2))
        self.assertAlmostEqual(r["g_pci"], math.log(1.6))
        self.assertAlmostEqual(r["pop_growth"], math.log(1.2))
        self.assertAlmostEqual(r["hu_growth"], math.log(1.25))  # 400 -> 500
        self.assertEqual(r["price_source"], "fhfa_divisions")
        self.assertAlmostEqual(r["price_growth"], (100 * math.log(2) + 300 * math.log(1.5)) / 400)
        self.assertIsNone(r["price_growth_cty"])  # county HPI covers 100 of 400 units (< half)
        self.assertAlmostEqual(r["permits_per_1000"], 5800.0)  # 1000 * (20*1 + 19*2) / 10
        self.assertEqual(r["permit_county_years_missing"], 1)


class TestVerdicts(unittest.TestCase):
    def test_null_and_sign(self):
        c = {"est": 0.3, "se": 0.1, "p": 0.003}
        self.assertEqual(rc.expect_null(c)["status"], "not reproduced (p<0.05)")
        self.assertEqual(rc.expect_null(dict(c, p=0.2))["status"], "null reproduced")
        self.assertEqual(rc.expect_sign(c, +1)["status"], "supported")
        self.assertEqual(rc.expect_sign(c, -1)["status"], "not supported")
        self.assertEqual(rc.expect_sign(None, 1)["status"], "not evaluable")


if __name__ == "__main__":
    unittest.main()
