#!/usr/bin/env python3
# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Part 6: inequality or regulation? A direct test of the two-margin model of housing.

Louie, Mondragon, Najjar and Wieland ("Quality, Inequality and Understanding Housing Markets",
August 2026; LMNW) argue that there is no single housing supply elasticity. Rich households buy
housing quality, poor households buy units, and quality is the scarce margin. The empirical
unit-price elasticity is then (their eq. in section 2 and appendix A.1)

    u/P = [shock dependence] x (psi + 1) / (s_r theta(q_r) + (1 - s_r) theta(q_p)),

so a demand shock turns more into prices and less into units (a) where the rich hold a larger
share of the market (state dependence, s_r) and (b) when the shock falls on rich households'
incomes rather than on the number of poorer households (shock dependence). They illustrate this
only with three instruments from LMW (2025). Buchholz, Kemeny, Randolph and Storper (2026) argue
more broadly that "inequality, not regulation" drives affordability.

This module puts the two explanations side by side on public data for U.S. metro areas,
2011-2019:
- inequality: the 2011 share of adjusted gross income (AGI) reported on returns of $200,000 or
  more (IRS Statistics of Income county data), its change, and the growth of income above a
  fixed REAL threshold versus below it (Pareto interpolation inside the top class, so nominal
  bracket creep does not count as concentration);
- regulation: the Baum-Snow and Han unit supply elasticity (metro tract mean), as in parts 1-5.
Outcomes: real FHFA house prices, Census housing units, BEA population; demand: real BEA
personal income. See PREREGISTRATION-INEQ.md for the fixed plan and predictions I1-I8.
"""

import argparse
import csv
import io
import json
import math
import os
import statistics
import sys
import urllib.request

import ms
import reconcile as rc
import sc_analysis as sc

IRS_URL = "https://www.irs.gov/pub/irs-soi/%02dincyallagi.csv"
CPI_URLS = ["https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL&fq=Annual&fam=avg"]
BASE, END, LATE = 2011, 2019, 2022
TOP_STUB = 8      # IRS county AGI class 8 = "$200,000 or more"
TOP_K = 200.0     # its lower edge in $ thousands (A00100 is reported in $ thousands)
MIN_RETURNS = 20  # IRS suppresses cells with fewer than 20 returns
MIN_COVERAGE = 0.95
finite = ms.finite


# ---------------------------------------------------------------- IRS county data

def parse_irs(text):
    """IRS SOI county CSV (yyincyallagi.csv) -> {county fips: {agi_stub: (returns N1, AGI A00100
    in $ thousands)}}. Column names are matched case-insensitively. State and U.S. total rows
    (county 000 or state 00) and rows with a non-numeric N1 or A00100 are skipped."""
    out = {}
    idx = None
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if idx is None:
            h = [c.strip().lstrip(chr(0xFEFF)).strip('"').strip().lower() for c in row]
            need = ("statefips", "countyfips", "agi_stub", "n1", "a00100")
            if all(k in h for k in need):
                idx = {k: h.index(k) for k in need}
            continue
        if len(row) <= max(idx.values()):
            continue
        st = rc._code(row[idx["statefips"]].strip(), 2)
        co = rc._code(row[idx["countyfips"]].strip(), 3)
        stub = sc._num(row[idx["agi_stub"]])
        n1, a = sc._num(row[idx["n1"]]), sc._num(row[idx["a00100"]])
        if not st or not co or st == "00" or co == "000" or stub is None or n1 is None or a is None:
            continue
        out.setdefault(st + co, {})[int(stub)] = (n1, a)
    return out


def county_total(rec):
    """(returns, AGI) for the whole county: class 0 when the file has it, else the sum of the
    size classes. None if the county is absent."""
    if not rec:
        return None
    if 0 in rec:
        return rec[0]
    parts = [v for k, v in rec.items() if k != 0]
    if not parts:
        return None
    return (sum(v[0] for v in parts), sum(v[1] for v in parts))


def check_classes(rec_by_fips, stub=TOP_STUB, edge=TOP_K):
    """Confirms the class numbering before anything is estimated: among counties with at least
    MIN_RETURNS returns in a class, the share whose class-`stub` mean AGI is >= edge, and the share
    whose class-(stub-1) mean lies in [edge/2, edge) ($100,000 under $200,000)."""
    top_ok = top_n = nxt_ok = nxt_n = 0
    seen = set()
    for rec in rec_by_fips.values():
        seen |= set(rec)
        t = rec.get(stub)
        if t and t[0] >= MIN_RETURNS:
            top_n += 1
            top_ok += 1 if t[1] / t[0] >= edge else 0
        s = rec.get(stub - 1)
        if s and s[0] >= MIN_RETURNS:
            nxt_n += 1
            nxt_ok += 1 if edge / 2 <= s[1] / s[0] < edge else 0
    return {"classes_seen": sorted(seen), "counties": len(rec_by_fips),
            "top_class_ok_share": top_ok / top_n if top_n else None, "top_class_counties": top_n,
            "next_class_ok_share": nxt_ok / nxt_n if nxt_n else None, "next_class_counties": nxt_n}


def classes_ok(chk):
    a, b = chk.get("top_class_ok_share"), chk.get("next_class_ok_share")
    return a is not None and b is not None and a >= 0.99 and b >= 0.99


def metro_pair(fs, rec0, rec1, stub=TOP_STUB, min_cov=MIN_COVERAGE):
    """Sums a metro's member counties for two years. Every member must be present in both years.
    Shares and growth use only counties whose top class is reported in BOTH years; these must
    hold at least `min_cov` of the metro's AGI in each year. -> dict or None."""
    s = {"agi0": 0.0, "agi1": 0.0, "top_n0": 0.0, "top_agi0": 0.0, "top_n1": 0.0, "top_agi1": 0.0}
    all0 = all1 = 0.0
    for f in fs:
        r0, r1 = rec0.get(f), rec1.get(f)
        t0, t1 = county_total(r0), county_total(r1)
        if t0 is None or t1 is None:
            return None
        all0 += t0[1]
        all1 += t1[1]
        p0, p1 = r0.get(stub), r1.get(stub)
        if not (p0 and p1 and p0[0] > 0 and p1[0] > 0):
            continue
        s["agi0"] += t0[1]
        s["agi1"] += t1[1]
        s["top_n0"] += p0[0]
        s["top_agi0"] += p0[1]
        s["top_n1"] += p1[0]
        s["top_agi1"] += p1[1]
    if all0 <= 0 or all1 <= 0 or s["top_n0"] <= 0 or s["top_n1"] <= 0:
        return None
    s["coverage"] = min(s["agi0"] / all0, s["agi1"] / all1)
    if s["coverage"] < min_cov:
        return None
    return s


def above_real_threshold(top_n, top_agi, r, edge=TOP_K):
    """AGI and returns above edge * r (r >= 1), from the top class (returns above `edge`), under a
    Pareto tail fitted to the class mean m: alpha = m / (m - edge). Then the number above x is
    top_n (x / edge)^-alpha and the income above edge * r is top_agi * r^(1 - alpha).
    -> (agi_above, returns_above, alpha) or None."""
    if top_n <= 0 or top_agi <= 0 or r < 1:
        return None
    m = top_agi / top_n
    if m <= edge:
        return None
    alpha = m / (m - edge)
    return top_agi * r ** (1.0 - alpha), top_n * r ** (-alpha), alpha


# ---------------------------------------------------------------- metro rows

def build_rows(members, divs, msas, bea, hu, cbsa_hpi, m_elas, irs, cpi, a, b, with_units=True):
    """One row per metro with an elasticity: log changes a -> b. Y real personal income, N
    population, H housing units, P real house price (all BEA/Census/FHFA); S0 top-class share of
    AGI in a; S1_real share above the real threshold in b; dS = S1_real - S0; g_top, g_rest real
    growth of AGI above and below the real threshold; top_c = S0 g_top and rest_c = (1 - S0)
    g_rest (their sum is close to real AGI growth)."""
    rows = []
    info = {"no_income": 0, "no_irs": 0, "no_price": 0, "no_units": 0}
    if a not in cpi or b not in cpi or a not in irs or b not in irs:
        return rows, info
    r = cpi[b] / cpi[a]
    dcpi = math.log(r)
    for cb, fs in sorted(members.items()):
        if cb not in m_elas:
            continue
        inc, _ = ms.metro_income(cb, fs, msas, bea)
        if a not in inc or b not in inc:
            info["no_income"] += 1
            continue
        d = metro_pair(fs, irs[a], irs[b])
        hi = above_real_threshold(d["top_n1"], d["top_agi1"], r) if d else None
        if d is None or hi is None or d["agi0"] <= d["top_agi0"] or d["agi1"] <= hi[0]:
            info["no_irs"] += 1
            continue
        A_T1, N_T1, alpha1 = hi
        S0 = d["top_agi0"] / d["agi0"]
        g_top = math.log(A_T1 / d["top_agi0"]) - dcpi
        g_rest = math.log((d["agi1"] - A_T1) / (d["agi0"] - d["top_agi0"])) - dcpi
        row = {"m": cb, "E": m_elas[cb], "w": inc[a][1],
               "Y": math.log(inc[b][0] / inc[a][0]) - dcpi,
               "N": math.log(inc[b][1] / inc[a][1]),
               "S0": S0, "S1_nom": d["top_agi1"] / d["agi1"], "S1_real": A_T1 / d["agi1"],
               "dS": A_T1 / d["agi1"] - S0, "g_top": g_top, "g_rest": g_rest,
               "top_c": S0 * g_top, "rest_c": (1.0 - S0) * g_rest,
               "Y_irs": math.log(d["agi1"] / d["agi0"]) - dcpi,
               "alpha0": d["top_agi0"] / d["top_n0"] / (d["top_agi0"] / d["top_n0"] - TOP_K),
               "alpha1": alpha1, "coverage": d["coverage"], "H": None, "P": None}
        lh, _ = ms.metro_lhpi(cb, divs, cbsa_hpi, hu, base_year=a)
        if a in lh and b in lh:
            row["P"] = lh[b] - lh[a] - dcpi
        else:
            info["no_price"] += 1
        if with_units:
            h0 = [rc.hu_at(hu.get(f, {}), a) for f in fs]
            h1 = [rc.hu_at(hu.get(f, {}), b) for f in fs]
            if all(h0) and all(h1):
                row["H"] = math.log(sum(h1) / sum(h0))
            else:
                info["no_units"] += 1
        rows.append(row)
    return rows, info


def zscore(rows, col, out):
    vals = [r[col] for r in rows]
    if len(vals) < 2:
        return None, None
    mu, sd = statistics.mean(vals), statistics.pstdev(vals)
    for r in rows:
        r[out] = (r[col] - mu) / sd if sd > 0 else 0.0
    return mu, sd


def prepare(rows, need):
    """Common sample (every column in `need` finite), standardized S and E (z-scores within the
    sample) and the interactions YxS = Y * S, YxE = Y * E."""
    sub = [dict(r) for r in rows if all(finite(r.get(c)) for c in need)]
    zscore(sub, "S0", "S")
    zscore(sub, "E", "Ez")
    for r in sub:
        r["YxS"] = r["Y"] * r["S"]
        r["YxE"] = r["Y"] * r["Ez"]
    return sub


def corr(xs, ys):
    if len(xs) < 3:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None


# ---------------------------------------------------------------- estimation

def fit(rows, ycol, xcols, weighted=False):
    """OLS (or population-weighted LS) of y on a constant and xcols, HC1 standard errors.
    -> {"n", "coef": {name: {est, se, z, p}}, "beta", "V", "names"}"""
    sub = [r for r in rows if finite(r.get(ycol)) and all(finite(r.get(c)) for c in xcols)]
    if len(sub) < 40:
        return {"n": len(sub), "skipped": "too few metros"}
    X = [[1.0] + [r[c] for c in xcols] for r in sub]
    y = [r[ycol] for r in sub]
    w = [r["w"] if weighted else 1.0 for r in sub]
    beta, V, _ = sc.wls(y, X, w)
    names = ["const"] + list(xcols)
    out = {"n": len(sub), "coef": {}, "beta": [float(b) for b in beta], "V": V.tolist(), "names": names}
    for j, nm in enumerate(names):
        c = [0.0] * len(names)
        c[j] = 1.0
        out["coef"][nm] = sc.contrast(beta, V, c)
    return out


def diff(f, a, b):
    """Contrast coef(a) - coef(b) from a fit."""
    if "names" not in f:
        return None
    c = [0.0] * len(f["names"])
    c[f["names"].index(a)] = 1.0
    c[f["names"].index(b)] = -1.0
    import numpy as np
    return sc.contrast(np.asarray(f["beta"]), np.asarray(f["V"]), c)


SPECS = {
    "R1_price_state": ("P", ["Y", "YxS", "S"]),
    "R2_units_state": ("H", ["Y", "YxS", "S"]),
    "R2n_pop_state": ("N", ["Y", "YxS", "S"]),
    "R3_units_race": ("H", ["Y", "YxS", "S", "YxE", "Ez"]),
    "R3_price_race": ("P", ["Y", "YxS", "S", "YxE", "Ez"]),
    "R4_price_comp": ("P", ["top_c", "rest_c"]),
    "R4_units_comp": ("H", ["top_c", "rest_c"]),
    "R4_pop_comp": ("N", ["top_c", "rest_c"]),
    "R5_pop_conc": ("N", ["Y", "dS"]),
    "R5_units_conc": ("H", ["Y", "dS"]),
    "R6_units_lmw": ("H", ["Y", "YxE", "Ez"]),
    "R6_price_lmw": ("P", ["Y", "YxE", "Ez"]),
}
NEED_PRIMARY = ("Y", "N", "H", "P", "E", "S0", "dS", "top_c", "rest_c")
NEED_LATE = ("Y", "N", "P", "E", "S0", "dS", "top_c", "rest_c")


def analyse(rows, specs=SPECS, weighted=False):
    out = {k: fit(rows, y, xs, weighted) for k, (y, xs) in specs.items()}
    for k in ("R4_price_comp", "R4_units_comp", "R4_pop_comp"):
        if k in out and "names" in out[k]:
            out[k]["top_minus_rest"] = diff(out[k], "top_c", "rest_c")
    return out


def strip(res):
    """Drops beta/V/names for the JSON and markdown outputs (coefficients keep est, se, z, p)."""
    return {k: {kk: vv for kk, vv in v.items() if kk not in ("beta", "V", "names")} for k, v in res.items()}


# ---------------------------------------------------------------- hypotheses

def _c(res, spec, name):
    f = res.get(spec) or {}
    return (f.get("coef") or {}).get(name)


def signed(c, sign):
    if not c or not finite(c.get("est")) or not finite(c.get("p")):
        return {"status": "not evaluable"}
    ok = sign * c["est"] > 0 and c["p"] < 0.05
    return {"status": "supported" if ok else "not supported", "est": c["est"], "p": c["p"]}


def race(res, spec, sign_s):
    s, e = _c(res, spec, "YxS"), _c(res, spec, "YxE")
    if not s or not e or not all(finite(c.get(k)) for c in (s, e) for k in ("est", "p")):
        return {"status": "not evaluable"}
    ok = sign_s * s["est"] > 0 and s["p"] < 0.05 and e["p"] >= 0.05
    return {"status": "supported" if ok else "not supported",
            "YxS": [s["est"], s["p"]], "YxE": [e["est"], e["p"]]}


def hypotheses(res):
    h = {}
    h["I1 price: income x top share > 0 (p < 0.05)"] = signed(_c(res, "R1_price_state", "YxS"), +1)
    h["I2 units: income x top share < 0 (p < 0.05)"] = signed(_c(res, "R2_units_state", "YxS"), -1)
    h["I3 race, units: income x top share < 0 (p < 0.05) while income x elasticity has p >= 0.05"] = \
        race(res, "R3_units_race", -1)
    h["I4 race, prices: income x top share > 0 (p < 0.05) while income x elasticity has p >= 0.05"] = \
        race(res, "R3_price_race", +1)
    h["I5 prices load more on top-income growth than on the rest (top - rest > 0, p < 0.05)"] = \
        signed((res.get("R4_price_comp") or {}).get("top_minus_rest"), +1)
    h["I6 units load more on the rest than on top-income growth (top - rest < 0, p < 0.05)"] = \
        signed((res.get("R4_units_comp") or {}).get("top_minus_rest"), -1)
    h["I7 population: rising real top share < 0 given income growth (p < 0.05)"] = \
        signed(_c(res, "R5_pop_conc", "dS"), -1)
    e = _c(res, "R6_units_lmw", "YxE")
    h["I8 LMW null in 2011-2019: units on income x elasticity has p >= 0.05"] = (
        {"status": "not evaluable"} if not e or not finite(e.get("p")) else
        {"status": "supported" if e["p"] >= 0.05 else "not supported", "est": e["est"], "p": e["p"]})
    return h


def reading(res):
    """Pre-registered reading of the horse race (R3), units first, then prices."""
    def one(spec, sign_s, sign_e):
        s, e = _c(res, spec, "YxS"), _c(res, spec, "YxE")
        if not s or not e or not finite(s.get("p")) or not finite(e.get("p")):
            return "not evaluable"
        si = sign_s * s["est"] > 0 and s["p"] < 0.05
        el = sign_e * e["est"] > 0 and e["p"] < 0.05
        return {(True, False): "inequality", (False, True): "supply elasticity",
                (True, True): "both", (False, False): "neither"}[(si, el)]
    return {"units": one("R3_units_race", -1, +1), "prices": one("R3_price_race", +1, -1)}


# ---------------------------------------------------------------- output

def fmt(c):
    if not c or not finite(c.get("est")):
        return "n/a"
    return "%.3f (%.3f) p=%.3f" % (c["est"], c["se"], c["p"])


def write_md(path, meta, blocks, hyps, read):
    L = ["# Part 6 results: inequality or regulation? (sc-ineq-v1)", "",
         "Made with AI agents working in the name of MV2 of Munim, Inc. Pre-registered in "
         "PREREGISTRATION-INEQ.md before any data were seen. Log changes; Y real personal income, "
         "N population, H housing units, P real FHFA price (CPI-U). S = 2011 share of AGI on "
         "returns of $200,000 or more (z-score in the sample); Ez = Baum-Snow-Han unit elasticity "
         "(z-score). HC1 standard errors.", "", "## Inputs and checks", ""]
    for k, v in meta.items():
        L.append("- %s: %s" % (k, v if isinstance(v, str) else json.dumps(v, default=str)))
    for title, res in blocks:
        L += ["", "## " + title, "", "| model | outcome | n | coefficients |", "|---|---|---:|---|"]
        for k, (y, xs) in SPECS.items():
            f = res.get(k)
            if f is None:
                continue
            if "coef" not in f:
                L.append("| %s | %s | %s | skipped |" % (k, y, f.get("n")))
                continue
            cs = "; ".join("%s %s" % (x, fmt(f["coef"][x])) for x in xs)
            if f.get("top_minus_rest"):
                cs += "; top - rest %s" % fmt(f["top_minus_rest"])
            L.append("| %s | %s | %d | %s |" % (k, y, f["n"], cs))
    L += ["", "## Pre-registered predictions (primary: 2011-2019, unweighted)", ""]
    for k, v in hyps.items():
        L.append("- %s: %s" % (k, json.dumps(v, default=str)))
    L += ["", "## Pre-registered reading of the horse race (R3)", "", "- %s" % json.dumps(read)]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# ---------------------------------------------------------------- main

def get_irs(year, data_dir, log):
    """The IRS file for one year; a second attempt with a plain browser User-Agent if the
    project's own User-Agent is refused."""
    dest = os.path.join(data_dir, "irs_%02dincyallagi.csv" % (year % 100))
    url = IRS_URL % (year % 100)
    p = sc.get_first([url], dest, sc.is_text_table, log)
    if p:
        return p
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read()
        if data[:64].lstrip().startswith(b"<"):
            log("IRS %d: HTML instead of CSV" % year)
            return None
        with open(dest, "wb") as f:
            f.write(data)
        log("ok (second attempt) %s (%d bytes)" % (url, len(data)))
        return dest
    except Exception as e:  # network or HTTP error
        log("failed (second attempt) %s: %r" % (url, e))
        return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    data_dir = sc.writable_dir(args.data_dir, os.path.join(args.out_dir, "cache"))
    log = sc.Log(os.path.join(args.out_dir, "ineq_report.txt"))
    log("data dir: %s" % data_dir)
    j = lambda name: os.path.join(data_dir, name)  # noqa: E731

    bea_zip = sc.get_first(sc.BEA_URLS, j("CAINC1.zip"), sc.is_zip, log)
    cbsa_x = sc.get_first([rc.FHFA_CBSA_URL], j("hpi_at_cbsa.xlsx"), sc.is_zip, log)
    delin_x = sc.get_first([rc.DELIN_URL], j("list1_2023.xlsx"), sc.is_zip, log)
    hu10_p = sc.get_first([rc.HU10_URL], j("HU-EST2020_ALL.csv"), sc.is_text_table, log)
    bsh_p = sc.get_first(sc.BSH_URLS, j("bsh_elasticities.dta"), sc.is_dta, log)
    cpi_p = sc.get_first(CPI_URLS, j("fred_cpiaucsl_annual.csv"), sc.is_text_table, log)

    irs, checks = {}, {}
    for y in (BASE, END, LATE):
        p = get_irs(y, data_dir, log)
        if p:
            with open(p, "rb") as f:
                raw = f.read()
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            first = text.splitlines()[0] if text else ""
            log("IRS %d header (first 200 chars): %s" % (y, first[:200]))
            irs[y] = parse_irs(text)
            checks[y] = check_classes(irs[y])
            log("IRS %d: %d counties; class check %s" % (y, len(irs[y]), json.dumps(checks[y])))

    import zipfile
    bea, msas = {}, {}
    if bea_zip:
        with zipfile.ZipFile(bea_zip) as zf:
            pick = [n for n in zf.namelist() if "ALL_AREAS" in n and n.lower().endswith(".csv")]
            if pick:
                bea, msas, _ = rc.parse_bea_all(zf.read(pick[0]).decode("latin-1"))
    cbsa_hpi = {}
    if cbsa_x:
        cbsa_hpi = (rc.xlsx_parse(cbsa_x, rc.parse_hpi_rows)
                    or rc.xlsx_parse(cbsa_x, lambda rows: rc.parse_hpi_rows(rows, key="msa")))
    delin = rc.xlsx_parse(delin_x, rc.parse_delineation) if delin_x else {}
    hu = rc.parse_hu(open(hu10_p, encoding="latin-1").read()) if hu10_p else {}
    cpi = ms.parse_fred_annual(open(cpi_p, encoding="utf-8", errors="replace").read()) if cpi_p else {}
    log("BEA county rows %d, MSA rows %d; FHFA series %d; delineation counties %d; HU counties %d; "
        "CPI %s" % (len(bea), len(msas), len(cbsa_hpi), len(delin), len(hu),
                    {y: cpi.get(y) for y in (BASE, END, LATE)}))

    meta = {"irs_class_checks": checks, "cpi": {y: cpi.get(y) for y in (BASE, END, LATE)}}
    blocks, hyps, read = [], {}, {}
    bsh = sc.load_bsh(bsh_p, log) if bsh_p else None
    ok = (bsh and bsh.get("primary_by_county") and delin and all(y in cpi for y in (BASE, END))
          and all(y in irs and classes_ok(checks[y]) for y in (BASE, END)))
    rows_p = []
    if not ok:
        log("missing elasticity, delineation, CPI or IRS data, or the IRS class check failed: "
            "analysis skipped")
    else:
        elas = {k: v for k, v in bsh["primary_by_county"].items() if k[:2] not in sc.DROP_STATES}
        members, divs = rc.metro_units(delin)
        m_elas = rc.metro_elasticity(members, elas, bsh.get("primary_tracts", {}))
        titles = {}
        for f, d in delin.items():
            titles.setdefault(d["cbsa"], d["title"])
        raw_p, info_p = build_rows(members, divs, msas, bea, hu, cbsa_hpi, m_elas, irs, cpi, BASE, END)
        rows_p = prepare(raw_p, NEED_PRIMARY)
        res_p = analyse(rows_p)
        res_pw = analyse(rows_p, weighted=True)
        blocks += [("Primary: 2011-2019, unweighted (graded)", strip(res_p)),
                   ("Robustness: 2011-2019, weighted by 2011 population (not graded)", strip(res_pw))]
        hyps = hypotheses(res_p)
        read = reading(res_p)
        late_info = None
        if LATE in irs and classes_ok(checks[LATE]) and LATE in cpi:
            raw_l, late_info = build_rows(members, divs, msas, bea, hu, cbsa_hpi, m_elas, irs, cpi,
                                          BASE, LATE, with_units=False)
            rows_l = prepare(raw_l, NEED_LATE)
            specs_l = {k: v for k, v in SPECS.items() if v[0] != "H"}
            blocks.append(("Exploratory: 2011-2022, prices and population only (not graded)",
                           strip(analyse(rows_l, specs_l))))
            meta["late_sample_metros"] = len(rows_l)
        top = sorted(rows_p, key=lambda r: -r["S0"])[:10]
        meta.update({
            "elasticity_column": bsh["primary"], "metros_with_elasticity": len(m_elas),
            "primary_rows_built": len(raw_p), "primary_dropped": info_p, "late_dropped": late_info,
            "common_sample_metros": len(rows_p),
            "corr_S_E": corr([r["S"] for r in rows_p], [r["Ez"] for r in rows_p]),
            "S0_mean_median_min_max": ([statistics.mean([r["S0"] for r in rows_p]),
                                        statistics.median([r["S0"] for r in rows_p]),
                                        min(r["S0"] for r in rows_p), max(r["S0"] for r in rows_p)]
                                       if rows_p else None),
            "dS_mean": statistics.mean([r["dS"] for r in rows_p]) if rows_p else None,
            "alpha_2011_median": statistics.median([r["alpha0"] for r in rows_p]) if rows_p else None,
            "real_threshold_2019_dollars": TOP_K * 1000 * cpi[END] / cpi[BASE],
            "min_coverage": min((r["coverage"] for r in rows_p), default=None),
            "corr_Y_bea_vs_irs": corr([r["Y"] for r in rows_p], [r["Y_irs"] for r in rows_p]),
            "top10_S0": [[r["m"], titles.get(r["m"], ""), round(r["S0"], 4)] for r in top],
        })
        if meta["corr_S_E"] is not None and abs(meta["corr_S_E"]) > 0.7:
            meta["collinearity_flag"] = "|corr(S, E)| > 0.7: the horse race cannot separate them well"
        log("common sample %d metros; corr(S, E) %s" % (len(rows_p), meta["corr_S_E"]))
        with open(os.path.join(args.out_dir, "metro_ineq.csv"), "w", newline="") as f:
            cols = ["m", "E", "w", "Y", "N", "H", "P", "S0", "S1_nom", "S1_real", "dS", "g_top",
                    "g_rest", "top_c", "rest_c", "Y_irs", "alpha0", "alpha1", "coverage"]
            wr = csv.DictWriter(f, fieldnames=["title"] + cols, extrasaction="ignore")
            wr.writeheader()
            for r in rows_p:
                wr.writerow(dict(r, title=titles.get(r["m"], "")))
    with open(os.path.join(args.out_dir, "ineq_results.json"), "w") as f:
        json.dump(ms.jsonable({"meta": meta, "blocks": dict(blocks), "hypotheses": hyps,
                               "reading": read}), f, indent=1, default=str)
    write_md(os.path.join(args.out_dir, "ineq_results.md"), meta, blocks, hyps, read)
    log("hypotheses: %s" % json.dumps(ms.jsonable(hyps), default=str))
    log("reading: %s" % json.dumps(read))
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
