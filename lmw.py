#!/usr/bin/env python3
# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Part 5b: Louie, Mondragon and Wieland's own long-difference cell, on open data.

Part 5 (ms.py, PREREGISTRATION-MS.md) calls its "LMW cell" the unweighted, above-MEAN, with-main-
effect regression in log changes deflated by PCE. Reading the February 2026 revision of LMW (FRBSF
Working Paper 2025-06) in full afterwards showed that LMW's own cell differs in three ways:

- the split is at the MEDIAN of each measure (pp. 19, 22, 25; notes to Tables II-IV),
- income and prices are deflated by the CPI (p. 17),
- all growth rates are annualized percentages over 2000-2020 (p. 17).

No weighting is mentioned anywhere in the paper, so its regressions are read as unweighted.

This module runs LMW's exact cell with the Baum-Snow and Han unit elasticity, their Table IV
two-stage least squares, their Table IX supply-elasticity contrast (per-capita income vs
population as the instrument), and a 2 x 2 bridge (units: part 5 vs LMW; threshold: mean vs
median) that shows how much each of the two differences moves the result. Every published LMW
number it is compared with is quoted with its table. See PREREGISTRATION-LMW.md.
"""

import argparse
import csv
import json
import math
import os
import statistics
import sys

import ms
import reconcile as rc
import sc_analysis as sc

CPI_URLS = ["https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL&fq=Annual&fam=avg"]
A, B = 2000, 2020
YEARS = B - A
finite = ms.finite

# LMW (FRBSF WP 2025-06, Feb 2026), Baum-Snow-Han column (column 2) of each table:
# (estimate, standard error). Quoted from the paper; used only for the comparison table.
LMW_PUBLISHED = {
    "L1_units_on_income": {"source": "Table III, panel A, col. 2", "n": 310,
                           "income": (0.635, 0.030), "interaction": (-0.015, 0.048), "main": (-0.001, 0.090)},
    "L2_price_on_income": {"source": "Table II, panel A, col. 2", "n": 308,
                           "income": (0.589, 0.078), "interaction": (0.052, 0.111), "main": (-0.438, 0.237)},
    "L3_population_on_income": {"source": "Table III, panel B, col. 2", "n": 310,
                                "income": (0.717, 0.034), "interaction": (0.001, 0.051), "main": (-0.088, 0.098)},
    "L4_price_on_pci": {"source": "Table II, panel B, col. 2", "n": 308,
                        "income": (1.284, 0.187), "interaction": (-0.162, 0.248), "main": (-0.263, 0.328)},
    "L5_units_on_pci": {"source": "Table VII, panel A, col. 2", "n": 310,
                        "income": (0.309, 0.148), "interaction": (-0.030, 0.193), "main": (-0.084, 0.244)},
    "L6_units_on_population": {"source": "Table VIII, panel A, col. 2", "n": 310,
                               "income": (0.876, 0.019), "interaction": (-0.019, 0.024), "main": (0.057, 0.022)},
    "L7_2sls": {"source": "Table IV, panel A, col. 2", "n": 308,
                "more_constrained": (1.078, 0.168), "less_constrained": (0.965, 0.133), "p_equal": 0.60},
    "L8_iv_by_instrument": {"source": "Table IX", "n": 321,
                            "per_capita_income": (0.215, 0.081), "population": (1.506, 0.178)},
}

# (row key, outcome column, regressor column)
CELLS = [
    ("L1_units_on_income", "H", "Y"),
    ("L2_price_on_income", "P", "Y"),
    ("L3_population_on_income", "N", "Y"),
    ("L4_price_on_pci", "P", "y_pc"),
    ("L5_units_on_pci", "H", "y_pc"),
    ("L6_units_on_population", "H", "N"),
]


def ann(x, years=YEARS):
    """Log change over `years` years -> annualized percent growth: 100 (exp(x / years) - 1)."""
    return 100.0 * (math.exp(x / years) - 1.0)


def lmw_units(rows):
    """Rows from ms.build_metros (log changes 2000-2020, built with a log deflator) -> rows with
    LMW's annualized percent columns: Y total income, N population, y_pc per-capita income,
    H housing units, P price (Y, y_pc and P real). Rows without income or population are dropped."""
    out = []
    for r in rows:
        if not (finite(r.get("g_real")) and finite(r.get("pop_growth"))):
            continue
        q = dict(r)
        q["Y"] = ann(r["g_real"])
        q["N"] = ann(r["pop_growth"])
        q["y_pc"] = ann(r["g_real"] - r["pop_growth"])
        q["H"] = ann(r["hu_growth"]) if finite(r.get("hu_growth")) else None
        q["P"] = ann(r["price_growth"]) if finite(r.get("price_growth")) else None
        out.append(q)
    return out


def ms_units(rows):
    """Part 5's units (log changes) under the same column names, for the bridge."""
    out = []
    for r in rows:
        if not (finite(r.get("g_real")) and finite(r.get("pop_growth"))):
            continue
        q = dict(r)
        q["Y"], q["N"] = r["g_real"], r["pop_growth"]
        q["y_pc"] = r["g_real"] - r["pop_growth"]
        q["H"] = r["hu_growth"] if finite(r.get("hu_growth")) else None
        q["P"] = r["price_growth"] if finite(r.get("price_growth")) else None
        out.append(q)
    return out


def common_sample(rows):
    """Rows with income, units and price all present: the sample the split is computed on."""
    return [r for r in rows if all(finite(r.get(c)) for c in ("Y", "H", "P", "E"))]


def set_split(rows, threshold, col):
    """col = 1 if E is strictly above the threshold (less constrained), else 0."""
    for r in rows:
        r[col] = 1.0 if r["E"] > threshold else 0.0


def iv_single(rows, ycol, xcol, zcol):
    """2SLS of y on x with a constant, one instrument z. HC1 standard errors."""
    sub = [r for r in rows if all(finite(r.get(c)) for c in (ycol, xcol, zcol))]
    if len(sub) < 40:
        return {"n": len(sub), "skipped": "too few metros"}
    en = [[r[xcol]] for r in sub]
    ex = [[1.0] for _ in sub]
    iv = [[r[zcol]] for r in sub]
    f = ms.tsls([r[ycol] for r in sub], en, ex, iv)
    return {"n": len(sub), "elasticity": ms.coef(f, 0), "first_stage_F": ms.first_stage_F(en, ex, iv)}


def analyse(rows_lmw, rows_ms):
    """rows_*: common-sample rows carrying Dmed and Dmean. Returns all cells."""
    out = {"lmw_exact": {}, "bridge": {}}
    for key, y, g in CELLS:
        out["lmw_exact"][key] = ms.ld_fit(rows_lmw, y, g, "Dmed", weighted=False, main=True)
    s = ms.ld_structural(rows_lmw, "H", "P", "Y", "Dmed", weighted=False, main=True)
    if "price" in s:
        # regressors: P, P x D, D. P = elasticity of the more constrained group (D = 0);
        # P x D = less minus more; its test is LMW's chi-squared test of equality.
        s["more_constrained"] = s["price"]
        s["less_minus_more"] = s["interaction"]
    out["lmw_exact"]["L7_2sls"] = s
    out["lmw_exact"]["L8_iv_by_instrument"] = {
        "per_capita_income": iv_single(rows_lmw, "H", "P", "y_pc"),
        "population": iv_single(rows_lmw, "H", "P", "N"),
    }
    for unit_name, rows in (("lmw_units_cpi_annualized", rows_lmw), ("ms_units_pce_log", rows_ms)):
        for split in ("Dmean", "Dmed"):
            out["bridge"]["%s|%s" % (unit_name, "above_mean" if split == "Dmean" else "above_median")] = \
                ms.ld_fit(rows, "H", "Y", split, weighted=False, main=True)
    return out


def less_constrained_elasticity(s):
    """From the L7 fit: the less constrained group's elasticity = price + interaction. ms.ld_structural
    does not return the full covariance, so only the point estimate is reported."""
    if not s.get("price") or not s.get("interaction"):
        return None
    return s["price"]["est"] + s["interaction"]["est"]


def bridge_effects(bridge):
    """Mean absolute change in the housing-unit interaction z when the threshold is switched
    (mean -> median, averaged over both unit systems) and when the units are switched (part 5 ->
    LMW, averaged over both thresholds)."""
    def z(k):
        r = bridge.get(k) or {}
        c = r.get("interaction")
        return c["z"] if c and finite(c.get("z")) else None
    U = ("lmw_units_cpi_annualized", "ms_units_pce_log")
    T = ("above_mean", "above_median")
    thr, uni = [], []
    for u in U:
        a, b = z("%s|%s" % (u, T[0])), z("%s|%s" % (u, T[1]))
        if a is not None and b is not None:
            thr.append(abs(a - b))
    for t in T:
        a, b = z("%s|%s" % (U[0], t)), z("%s|%s" % (U[1], t))
        if a is not None and b is not None:
            uni.append(abs(a - b))
    return {"threshold": sum(thr) / 2 if len(thr) == 2 else None,
            "units": sum(uni) / 2 if len(uni) == 2 else None}


def hypotheses(res):
    ex = res["lmw_exact"]

    def inter(key):
        return (ex.get(key) or {}).get("interaction")

    def null(c):
        if not c or not finite(c.get("p")):
            return {"status": "not evaluable"}
        return {"status": "supported" if c["p"] >= 0.05 else "not supported", "est": c["est"], "p": c["p"]}

    h = {}
    h["Q1 LMW-exact cell: housing-unit interaction null (p >= 0.05)"] = null(inter("L1_units_on_income"))
    h["Q2 LMW-exact cell: price interaction null (p >= 0.05)"] = null(inter("L2_price_on_income"))
    c = inter("L1_units_on_income")
    h["Q3 housing-unit interaction within 0.10 of LMW's -0.015, i.e. in [-0.115, 0.085]"] = (
        {"status": "not evaluable"} if not c or not finite(c.get("est")) else
        {"status": "supported" if -0.115 <= c["est"] <= 0.085 else "not supported", "est": c["est"]})
    inc = (ex.get("L1_units_on_income") or {}).get("income")
    h["Q4 housing-unit income coefficient in [0.50, 0.80] (LMW 0.635)"] = (
        {"status": "not evaluable"} if not inc or not finite(inc.get("est")) else
        {"status": "supported" if 0.50 <= inc["est"] <= 0.80 else "not supported", "est": inc["est"]})
    h["Q5 2SLS: elasticities of less and more constrained metros not different (p >= 0.05)"] = \
        null((ex.get("L7_2sls") or {}).get("interaction"))
    iv = ex.get("L8_iv_by_instrument") or {}
    a = (iv.get("per_capita_income") or {}).get("elasticity")
    b = (iv.get("population") or {}).get("elasticity")
    h["Q6 IV elasticity with population as instrument exceeds that with per-capita income by > 0.5"] = (
        {"status": "not evaluable"} if not a or not b or not finite(a.get("est")) or not finite(b.get("est")) else
        {"status": "supported" if b["est"] - a["est"] > 0.5 else "not supported",
         "per_capita_income": a["est"], "population": b["est"]})
    be = bridge_effects(res["bridge"])
    h["Q7 switching the split from mean to median moves the housing-unit interaction z by < 1.0"] = (
        {"status": "not evaluable", "effects": be} if be["threshold"] is None else
        {"status": "supported" if be["threshold"] < 1.0 else "not supported", "effects": be})
    return h


# ---------------------------------------------------------------- output

def fmt_pub(t):
    return "%.3f (%.3f)" % t


def write_md(path, meta, res, hyps):
    L = ["# Part 5b results: LMW's own cell on open data (sc-lmw-v1)", "",
         "Made with AI agents working in the name of MV2 of Munim, Inc. Pre-registered in "
         "PREREGISTRATION-LMW.md before any data were seen. E = Baum-Snow-Han unit supply elasticity "
         "(metro tract mean). Dmed = 1 if E is above the median of the common sample (LMW's split); "
         "Dmean = 1 if above its mean (part 5's split). LMW cells: unweighted, annualized percent "
         "growth 2000-2020, CPI-deflated, with the split's main effect, HC1 standard errors.", "",
         "## Inputs", ""]
    for k, v in meta.items():
        L.append("- %s: %s" % (k, v if isinstance(v, str) else json.dumps(v, default=str)))
    L += ["", "## LMW-exact cells next to LMW's published Baum-Snow-Han column", "",
          "| cell | n (LMW) | income (ours) | income (LMW) | income x Dmed (ours) | (LMW) | Dmed (ours) | (LMW) | LMW source |",
          "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for key, _, _ in CELLS:
        r = res["lmw_exact"].get(key) or {}
        p = LMW_PUBLISHED[key]
        if "interaction" not in r:
            L.append("| %s | %s (%d) | skipped | | | | | | %s |" % (key, r.get("n"), p["n"], p["source"]))
            continue
        L.append("| %s | %d (%d) | %s | %s | %s | %s | %s | %s | %s |" % (
            key, r["n"], p["n"], ms.fmt(r["income"]), fmt_pub(p["income"]), ms.fmt(r["interaction"]),
            fmt_pub(p["interaction"]), ms.fmt(r.get("main")), fmt_pub(p["main"]), p["source"]))
    s = res["lmw_exact"].get("L7_2sls") or {}
    p = LMW_PUBLISHED["L7_2sls"]
    L += ["", "## 2SLS supply elasticities (LMW Table IV analogue: housing units on price, instruments income and income x Dmed)", ""]
    if "interaction" in s:
        L += ["- ours: more constrained %s; less minus more %s (p is the test of equality); less constrained "
              "point estimate %.3f; first-stage F %s; n %d" % (
                  ms.fmt(s["price"]), ms.fmt(s["interaction"]), less_constrained_elasticity(s) or float("nan"),
                  ", ".join("%.1f" % x for x in s["first_stage_F"]), s["n"]),
              "- LMW: more constrained %s, less constrained %s, p(equal) %.2f, n %d (%s)" % (
                  fmt_pub(p["more_constrained"]), fmt_pub(p["less_constrained"]), p["p_equal"], p["n"], p["source"])]
    else:
        L.append("- skipped (n %s)" % s.get("n"))
    iv = res["lmw_exact"].get("L8_iv_by_instrument") or {}
    p = LMW_PUBLISHED["L8_iv_by_instrument"]
    L += ["", "## One supply curve, two instruments (LMW Table IX analogue)", "",
          "| instrument | n | elasticity (ours) | first-stage F | elasticity (LMW) |", "|---|---:|---:|---:|---:|"]
    for k in ("per_capita_income", "population"):
        r = iv.get(k) or {}
        if "elasticity" not in r:
            L.append("| %s | %s | skipped | | %s |" % (k, r.get("n"), fmt_pub(p[k])))
            continue
        L.append("| %s | %d | %s | %.1f | %s |" % (k, r["n"], ms.fmt(r["elasticity"]), r["first_stage_F"][0], fmt_pub(p[k])))
    L += ["", "## Bridge: housing-unit interaction by units and split (unweighted, with main effect)", "",
          "| units / split | n | income x D | z |", "|---|---:|---:|---:|"]
    for k, r in res["bridge"].items():
        if "interaction" not in r:
            L.append("| %s | %s | skipped | |" % (k, r.get("n")))
            continue
        L.append("| %s | %d | %s | %.2f |" % (k, r["n"], ms.fmt(r["interaction"]), r["interaction"]["z"]))
    L += ["", "Mean |change in z|: %s" % json.dumps(bridge_effects(res["bridge"])), "",
          "## Pre-registered predictions", ""]
    for k, v in hyps.items():
        L.append("- %s: %s" % (k, json.dumps(v, default=str)))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# ---------------------------------------------------------------- main

def log_deflator(series):
    return {y: math.log(v / 100.0) for y, v in series.items() if finite(v) and v > 0}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    data_dir = sc.writable_dir(args.data_dir, os.path.join(args.out_dir, "cache"))
    log = sc.Log(os.path.join(args.out_dir, "lmw_report.txt"))
    log("data dir: %s" % data_dir)
    j = lambda name: os.path.join(data_dir, name)  # noqa: E731

    bea_zip = sc.get_first(sc.BEA_URLS, j("CAINC1.zip"), sc.is_zip, log)
    cbsa_x = sc.get_first([rc.FHFA_CBSA_URL], j("hpi_at_cbsa.xlsx"), sc.is_zip, log)
    delin_x = sc.get_first([rc.DELIN_URL], j("list1_2023.xlsx"), sc.is_zip, log)
    hu00_p = sc.get_first([rc.HU00_URL], j("hu-est00int-tot.csv"), sc.is_text_table, log)
    hu10_p = sc.get_first([rc.HU10_URL], j("HU-EST2020_ALL.csv"), sc.is_text_table, log)
    bsh_p = sc.get_first(sc.BSH_URLS, j("bsh_elasticities.dta"), sc.is_dta, log)
    pce_p = sc.get_first(ms.PCE_URLS, j("fred_pcepi_annual.csv"), sc.is_text_table, log)
    cpi_p = sc.get_first(CPI_URLS, j("fred_cpiaucsl_annual.csv"), sc.is_text_table, log)

    import zipfile
    bea, msas, collisions = {}, {}, set()
    if bea_zip:
        with zipfile.ZipFile(bea_zip) as zf:
            pick = [n for n in zf.namelist() if "ALL_AREAS" in n and n.lower().endswith(".csv")]
            if pick:
                bea, msas, collisions = rc.parse_bea_all(zf.read(pick[0]).decode("latin-1"))
    cbsa_hpi = {}
    if cbsa_x:
        cbsa_hpi = (rc.xlsx_parse(cbsa_x, rc.parse_hpi_rows)
                    or rc.xlsx_parse(cbsa_x, lambda rows: rc.parse_hpi_rows(rows, key="msa")))
    delin = rc.xlsx_parse(delin_x, rc.parse_delineation) if delin_x else {}
    hu = rc.merge_hu(*[rc.parse_hu(open(p, encoding="latin-1").read()) for p in (hu00_p, hu10_p) if p])
    read = lambda p: ms.parse_fred_annual(open(p, encoding="utf-8", errors="replace").read()) if p else {}  # noqa: E731
    pce, cpi = read(pce_p), read(cpi_p)
    log("BEA county rows %d, MSA rows %d; FHFA series %d; delineation counties %d; HU counties %d; "
        "PCE years %d; CPI years %d" % (len(bea), len(msas), len(cbsa_hpi), len(delin), len(hu), len(pce), len(cpi)))

    meta = {"cpi_2000_2020": [cpi.get(A), cpi.get(B)], "pce_2000_2020": [pce.get(A), pce.get(B)],
            "bea_msa_rows": len(msas), "bea_code_collisions": sorted(collisions),
            "fhfa_cbsa_series": len(cbsa_hpi)}
    res, hyps = {"lmw_exact": {}, "bridge": {}}, {}
    bsh = sc.load_bsh(bsh_p, log) if bsh_p else None
    if not (bsh and bsh.get("primary_by_county")) or not delin or A not in cpi or B not in cpi \
            or A not in pce or B not in pce:
        log("missing elasticity, delineation, CPI or PCE data: analysis skipped")
    else:
        elas = {k: v for k, v in bsh["primary_by_county"].items() if k[:2] not in sc.DROP_STATES}
        members, divs = rc.metro_units(delin)
        m_elas = rc.metro_elasticity(members, elas, bsh.get("primary_tracts", {}))
        ld_cpi, _, info = ms.build_metros(members, divs, msas, bea, hu, cbsa_hpi, {}, m_elas,
                                          log_deflator(cpi), [])
        ld_pce, _, _ = ms.build_metros(members, divs, msas, bea, hu, cbsa_hpi, {}, m_elas,
                                       log_deflator(pce), [])
        rows_lmw = common_sample(lmw_units(ld_cpi))
        rows_ms = common_sample(ms_units(ld_pce))
        Es = [r["E"] for r in rows_lmw]
        med = statistics.median(Es) if Es else float("nan")
        mean = sum(Es) / len(Es) if Es else float("nan")
        for rows in (rows_lmw, rows_ms):
            set_split(rows, med, "Dmed")
            set_split(rows, mean, "Dmean")
        meta.update({"elasticity_column": bsh["primary"], "metros_with_elasticity": len(m_elas),
                     "common_sample_metros": len(rows_lmw), "common_sample_metros_pce": len(rows_ms),
                     "E_median": med, "E_mean": mean,
                     "n_Dmed_1": int(sum(r["Dmed"] for r in rows_lmw)),
                     "n_Dmean_1": int(sum(r["Dmean"] for r in rows_lmw)),
                     "price_source": info.get("price_source"), "income_source": info.get("income_source"),
                     "means_annualized_pct": {c: (sum(r[c] for r in rows_lmw) / len(rows_lmw)) if rows_lmw else None
                                              for c in ("Y", "N", "y_pc", "H", "P")},
                     "lmw_table1_means_for_comparison":
                         "real total income 2.06, population 0.81, housing units 1.01, real house price 1.23 (n 321-323, CPI)"})
        log("common sample %d metros; median E %.4f, mean E %.4f" % (len(rows_lmw), med, mean))
        res = analyse(rows_lmw, rows_ms)
        hyps = hypotheses(res)
        with open(os.path.join(args.out_dir, "metro_lmw_ld.csv"), "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=["m", "E", "Dmed", "Dmean", "Y", "N", "y_pc", "H", "P",
                                               "price_source", "income_source"], extrasaction="ignore")
            wr.writeheader()
            for r in rows_lmw:
                wr.writerow(r)
    with open(os.path.join(args.out_dir, "lmw_results.json"), "w") as f:
        json.dump(ms.jsonable({"meta": meta, "results": res, "hypotheses": hyps,
                               "lmw_published": LMW_PUBLISHED}), f, indent=1, default=str)
    write_md(os.path.join(args.out_dir, "lmw_results.md"), meta, res, hyps)
    log("hypotheses: %s" % json.dumps(ms.jsonable(hyps), default=str))
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
