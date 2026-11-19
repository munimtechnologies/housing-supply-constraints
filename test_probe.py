# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Hand-checked tests for the pure helpers in probe.py (no network)."""

import types
import unittest

import probe


class TestClassify(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(probe.classify_head(b"PK\x03\x04rest"), "zip")
        self.assertEqual(probe.classify_head(b"<stata_dta><header>"), "dta")
        self.assertEqual(probe.classify_head(b"\x72\x02\x01\x00"), "dta")
        self.assertEqual(probe.classify_head(b"  <!DOCTYPE html><html>"), "html")
        self.assertEqual(probe.classify_head(b"%PDF-1.7"), "pdf")
        self.assertEqual(probe.classify_head(b"STATEFIPS,STATE,COUNTYFIPS"), "text")
        self.assertEqual(probe.classify_head(b"statefips,state,countyfips"), "text")
        self.assertEqual(probe.classify_head(b""), "empty")


class TestTemplates(unittest.TestCase):
    def test_fill(self):
        self.assertEqual(probe.fill_template("https://x/co{year}a.txt"), "https://x/co2019a.txt")
        self.assertEqual(probe.fill_template("https://x/{y}/cbp{yy}co.zip"),
                         "https://x/2019/cbp19co.zip")
        self.assertEqual(probe.fill_template("https://x/%02dincyallagi.csv"),
                         "https://x/19incyallagi.csv")
        self.assertEqual(probe.fill_template("https://x/%02dincyallagi.csv", 2011),
                         "https://x/11incyallagi.csv")
        self.assertEqual(probe.fill_template("https://x/plain.csv"), "https://x/plain.csv")

    def test_expected(self):
        self.assertEqual(probe.expected_kind("https://a/b.xlsx"), "zip")
        self.assertEqual(probe.expected_kind("https://a/CAINC1.zip"), "zip")
        self.assertEqual(probe.expected_kind("https://drive.google.com/uc?export=download&id=1"),
                         "dta")
        self.assertEqual(probe.expected_kind("https://fred/graph.csv?id=CPI"), "text")


class TestCollect(unittest.TestCase):
    def test_collect(self):
        m = types.ModuleType("fake")
        m.A_URL = "https://a/x.csv"
        m.B_URLS = ["https://b/1.zip", "https://b/2.zip"]
        m.HU_URLS = [(2025, "https://c/hu.xlsx"), (2020, "https://c/hu20.xlsx")]
        m.NOT_A_URL_LIST = ["https://ignored"]
        m.WWW2 = "https://www2/"
        m.BAD_URL = "ftp://nope"
        got = probe.collect_urls(m)
        self.assertEqual(got, {"A_URL": ["https://a/x.csv"],
                               "B_URLS": ["https://b/1.zip", "https://b/2.zip"],
                               "HU_URLS": ["https://c/hu.xlsx", "https://c/hu20.xlsx"]})


class TestVerdict(unittest.TestCase):
    def test_verdict(self):
        self.assertEqual(probe.unittest_verdict("...\nRan 3 tests in 0.1s\n\nOK\n"), "OK")
        self.assertEqual(probe.unittest_verdict("x\nFAILED (failures=2)\n"), "FAILED (failures=2)")
        self.assertEqual(probe.unittest_verdict("Traceback ...\nImportError: x\n"), "no verdict")


class TestParts(unittest.TestCase):
    def test_parts_shape(self):
        names = [p[0] for p in probe.PARTS]
        self.assertEqual(len(names), 7)
        self.assertEqual(len(set(names)), 7)
        for job, sha, files, fetcher, test_mod, main_mod in probe.PARTS:
            self.assertEqual(len(sha), 40)
            self.assertIn(test_mod + ".py", files)
            self.assertIn(main_mod + ".py", files)
            if fetcher:
                self.assertIn(fetcher, files)


if __name__ == "__main__":
    unittest.main()
