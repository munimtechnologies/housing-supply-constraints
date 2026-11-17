#!/usr/bin/env python3
# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Reconciliation layer: why do Louie-Mondragon-Wieland and Murphy-Shaheen disagree?

Louie, Mondragon and Wieland (2025, NBER w33576) find that, across U.S. metros 2000-2020,
income growth predicts the same growth in prices and housing quantity whatever the supply
elasticity (long differences). Murphy and Shaheen (2026, Dallas Fed WP 2635) say supply
constraints DO explain permits and prices, using annual metro panels with fixed effects.

On one set of public data this module runs, side by side:
  A. the LMW long-difference design at the METRO level (2000-2020, 2010-2020),
  B. the same design at the COUNTY level,
  C. an annual county PANEL with county and year fixed effects and a 3-year distributed lag.
Housing quantity comes from Census housing-unit counts (2000 and 2010 censuses, April 2020
estimate) as well as permits. See PREREGISTRATION-RECONCILE.md for the fixed plan.
"""

import argparse
import csv
import io
import json
import math
import os
import re
import sys
import zipfile

import numpy as np

import sc_analysis as sc

HU00_URL = ("https://www2.census.gov/programs-surveys/popest/datasets/2000-2010/intercensal/"
            "housing/hu-est00int-tot.csv")
HU10_URL = ("https://www2.census.gov/programs-surveys/popest/datasets/2010-2020/housing/"
            "HU-EST2020_ALL.csv")
DELIN_URL = ("https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/"
             "2023/delineation-files/list1_2023.xlsx")
FHFA_CBSA_URL = "https://www.fhfa.gov/hpi/download/annual/hpi_at_cbsa.xlsx"

AREA_MARKERS = ("(metropolitan", "(micropolitan", "(combined", "metropolitan portion",
                "nonmetropolitan", "metropolitan division")
CENSUS_POINT = {2000: "c2000", 2010: "c2010", 2020: "apr2020"}
K = 3


# ---------------------------------------------------------------- parsers

def _code(v, width):
    """Cell value -> zero-padded digit code of the given width, or ""."""
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v) or not v.is_integer():
            return ""
        v = int(v)
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if not s.isdigit() or len(s) > width:
        return ""
    return s.zfill(width)


def parse_bea_all(text):
    """BEA CAINC1 ALL_AREAS CSV -> (counties, msas, collisions).

    counties: {fips: {"pi","pop","pci": {year: value}}} for county rows only (area rows such as
    metropolitan statistical areas, divisions, CSAs and metro/nonmetro portions are excluded by
    their GeoName). msas: the same for rows named "(Metropolitan Statistical Area)", keyed by
    CBSA code. collisions: codes used both by a county row and by an area row."""
    counties, msas = {}, {}
    county_codes, area_codes = set(), set()
    header = None
    for row in csv.reader(io.StringIO(text), skipinitialspace=True):
        if not row:
            continue
        first = row[0].lstrip(chr(0xFEFF)).strip().strip('"')
        if header is None:
            if first == "GeoFIPS":
                header = [h.lstrip(chr(0xFEFF)).strip().strip('"') for h in row]
                years = [(i, int(h)) for i, h in enumerate(header) if h.isdigit()]
                if "LineCode" not in header or "GeoName" not in header:
                    return counties, msas, set()
                i_line = header.index("LineCode")
                i_name = header.index("GeoName")
            continue
        if len(row) < len(header):
            continue
        code = first.strip()
        if len(code) != 5 or not code.isdigit():
            continue
        name = row[i_name].strip().lower()
        try:
            line = int(row[i_line].strip())
        except ValueError:
            continue
        key = {1: "pi", 2: "pop", 3: "pci"}.get(line)
        if key is None:
            continue
        if any(m in name for m in AREA_MARKERS):
            area_codes.add(code)
            if "(metropolitan statistical area)" not in name:
                continue
            target = msas
        else:
            if code.endswith("000"):
                continue
            county_codes.add(code)
            target = counties
        rec = target.setdefault(code, {"pi": {}, "pop": {}, "pci": {}})
        for i, y in years:
            v = sc._num(row[i])
            if v is not None:
                rec[key][y] = v
    return counties, msas, county_codes & area_codes


_HU_YEAR = re.compile(r"HUEST_?(?:IMATE)?(\d{4})")


def parse_hu(text):
    """Census county housing-unit CSV (hu-est00int-tot.csv or HU-EST2020_ALL.csv) ->
    {fips: {"c2000"|"c2010"|"apr2020"|year: units}}. July estimates are keyed by int year."""
    out = {}
    header = None
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if header is None:
            header = [h.strip().lstrip(chr(0xFEFF)).upper() for h in row]
            idx = {h: i for i, h in enumerate(header)}
            if not {"SUMLEV", "STATE", "COUNTY"} <= set(idx):
                return out
            cols = []
            for i, h in enumerate(header):
                m = _HU_YEAR.fullmatch(h)
                if h == "HUESTBASE2000":
                    cols.append((i, "c2000"))
                elif h == "CENSUS2010HU":
                    cols.append((i, "c2010"))
                elif h == "HUESTIMATE042020":
                    cols.append((i, "apr2020"))
                elif m:
                    cols.append((i, int(m.group(1))))
            continue
        if len(row) < len(header) or row[idx["SUMLEV"]].strip() != "050":
            continue
        fips = row[idx["STATE"]].strip().zfill(2) + row[idx["COUNTY"]].strip().zfill(3)
        rec = out.setdefault(fips, {})
        for i, key in cols:
            v = sc._num(row[i])
            if v is not None and v > 0:
                rec[key] = v
    return out


def merge_hu(*dicts):
    """Later dicts override earlier ones key by key (the 2010s file wins for 2010)."""
    out = {}
    for d in dicts:
        for f, rec in d.items():
            out.setdefault(f, {}).update(rec)
    return out


def hu_at(rec, year):
    """Census-based count at 2000/2010/2020 (April) when present, else the July estimate."""
    key = CENSUS_POINT.get(year)
    if key is not None and key in rec:
        return rec[key]
    return rec.get(year)


def parse_delineation(rows):
    """OMB list1 rows -> {county fips: {"cbsa", "div", "metro", "title"}}."""
    out = {}
    idx = None
    for row in rows:
        cells = ["" if c is None else str(c).strip() for c in row]
        low = [c.lower() for c in cells]
        if idx is None:
            if "cbsa code" in low and "fips state code" in low and "fips county code" in low:
                idx = {"cbsa": low.index("cbsa code"), "st": low.index("fips state code"),
                       "co": low.index("fips county code"),
                       "div": low.index("metropolitan division code") if "metropolitan division code" in low else None,
                       "type": next((i for i, c in enumerate(low) if c.startswith("metropolitan/micropolitan")), None),
                       "title": low.index("cbsa title") if "cbsa title" in low else None}
            continue
        if len(cells) <= max(v for v in idx.values() if v is not None):
            continue
        cb = _code(row[idx["cbsa"]], 5)
        st = _code(row[idx["st"]], 2)
        co = _code(row[idx["co"]], 3)
        if not (cb and st and co):
            continue
        typ = cells[idx["type"]].lower() if idx["type"] is not None else ""
        out[st + co] = {"cbsa": cb,
                        "div": _code(row[idx["div"]], 5) if idx["div"] is not None else "",
                        "metro": "metropolitan statistical" in typ,
                        "title": cells[idx["title"]] if idx["title"] is not None else ""}
    return out


def parse_hpi_rows(rows, key="cbsa", width=5):
    """FHFA annual HPI sheet rows -> {code: {year: hpi}} using the first column whose header
    contains `key` (not a name/title column), plus "year" and "hpi"."""
    out = {}
    idx = None
    for row in rows:
        cells = ["" if c is None else str(c).strip() for c in row]
        low = [c.lower() for c in cells]
        if idx is None:
            ks = [i for i, c in enumerate(low) if key in c and "name" not in c and "title" not in c]
            if ks and "year" in low and "hpi" in low:
                idx = (ks[0], low.index("year"), low.index("hpi"))
            continue
        if len(cells) <= max(idx):
            continue
        code = _code(row[idx[0]], width)
        if not code:
            continue
        try:
            y = int(float(cells[idx[1]]))
            h = float(cells[idx[2]])
        except ValueError:
            continue
        out.setdefault(code, {})[y] = h
    return out


def xlsx_parse(path, parser):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for ws in wb.worksheets:
        out = parser(ws.iter_rows(values_only=True))
        if out:
            return out
    return {}


# ---------------------------------------------------------------- statistics

def lg(a, b):
    return math.log(b / a) if a and b and a > 0 and b > 0 else None


def demean(M, w, groupings, tol=1e-11, max_iter=2000):
    """Weighted alternating projections: sweep out the means of every grouping in turn until
    no group mean is larger than tol. Returns (demeaned matrix, iterations)."""
    M = np.array(M, dtype=float, copy=True)
    if M.ndim == 1:
        M = M[:, None]
    w = np.asarray(w, dtype=float)
    codes = []
    for g in groupings:
        _, inv = np.unique(np.asarray([str(x) for x in g]), return_inverse=True)
        codes.append((inv, np.bincount(inv, weights=w)))
    it = 0
    for it in range(1, max_iter + 1):
        delta = 0.0
        for inv, sw in codes:
            for j in range(M.shape[1]):
                means = np.bincount(inv, weights=w * M[:, j]) / sw
                M[:, j] -= means[inv]
                delta = max(delta, float(np.max(np.abs(means))))
        if delta < tol:
            break
    return M, it


def tercile_slopes(rows, ycol, gcol, weighted=True, cluster=True):
    """y = sum_k a_k D_k + sum_k b_k D_k g. Clustered by r["cl"] (CR1) or HC1."""
    X, y, w, cl = [], [], [], []
    for r in rows:
        d = [1.0 if r["grp"] == k else 0.0 for k in range(K)]
        X.append(d + [dk * r[gcol] for dk in d])
        y.append(r[ycol])
        w.append(r["w"] if weighted else 1.0)
        cl.append(r["cl"])
    beta, V_hc1, V_cl = sc.wls(y, X, w, cl if cluster else None)
    V = V_cl if (cluster and V_cl is not None) else V_hc1
    res = {"n": len(rows), "se_type": "cluster" if cluster else "HC1",
           "n_clusters": len(set(cl)), "n_by_group": [sum(1 for r in rows if r["grp"] == k) for k in range(K)],
           "slopes": [sc.contrast(beta, V, [1.0 if i == K + k else 0.0 for i in range(2 * K)]) for k in range(K)]}
    c = [0.0] * (2 * K)
    c[K], c[2 * K - 1] = 1.0, -1.0
    res["slope_low_minus_high"] = sc.contrast(beta, V, c)
    return res


def panel_fit(rows, ycol, fe="county+year", weighted=True, lags=3):
    """Annual panel: y_ct = county FE + (year or state-year) FE + sum_j sum_k b_jk D_k g_{c,t-j}.
    Reports the cumulative response sum_j b_jk by tercile, clustered by state."""
    sub = [r for r in rows if r.get(ycol) is not None and math.isfinite(r[ycol])]
    if len(sub) < 200:
        return {"n": len(sub), "skipped": "too few county-years"}
    X = []
    for r in sub:
        x = []
        for j in range(lags):
            for k in range(K):
                x.append(r["g%d" % j] if r["grp"] == k else 0.0)
        X.append(x)
    w = [r["w"] if weighted else 1.0 for r in sub]
    county = [r["fips"] for r in sub]
    second = [r["t"] for r in sub] if fe == "county+year" else ["%s-%d" % (r["fips"][:2], r["t"]) for r in sub]
    M = np.column_stack([np.asarray([r[ycol] for r in sub], float), np.asarray(X, float)])
    Md, iters = demean(M, w, [county, second])
    beta, V_hc1, V_cl = sc.wls(Md[:, 0], Md[:, 1:], w, [r["fips"][:2] for r in sub])
    p = lags * K
    cum = []
    for k in range(K):
        c = [1.0 if (i % K) == k else 0.0 for i in range(p)]
        cum.append(sc.contrast(beta, V_cl, c))
    c = [(1.0 if (i % K) == 0 else (-1.0 if (i % K) == K - 1 else 0.0)) for i in range(p)]
    return {"n": len(sub), "n_counties": len(set(county)), "n_states": len({f[:2] for f in county}),
            "years": [min(r["t"] for r in sub), max(r["t"] for r in sub)], "fe": fe, "lags": lags,
            "demean_iterations": iters,
            "n_by_group": [len({r["fips"] for r in sub if r["grp"] == k}) for k in range(K)],
            "cumulative": cum, "cumulative_low_minus_high": sc.contrast(beta, V_cl, c)}


# ---------------------------------------------------------------- assembly

def county_ld_rows(start, end, bea, hpi, hu, permits, groups):
    """Long-difference rows for counties with an elasticity group."""
    rows = []
    years = list(range(start + 1, end + 1))
    have_permits = all(y in permits for y in years)
    for f, rec in sorted(bea.items()):
        if f[:2] in sc.DROP_STATES or f not in groups:
            continue
        pi, pop, pci = rec["pi"], rec["pop"], rec["pci"]
        g, gp, pg = lg(pi.get(start), pi.get(end)), lg(pci.get(start), pci.get(end)), lg(pop.get(start), pop.get(end))
        if g is None or gp is None or pg is None:
            continue
        h = hpi.get(f, {})
        hr = hu.get(f, {})
        r = {"fips": f, "cl": f[:2], "grp": groups[f], "w": pop[start], "pop_start": pop[start],
             "g_inc": g, "g_pci": gp, "pop_growth": pg,
             "price_growth": lg(h.get(start), h.get(end)),
             "hu_growth": lg(hu_at(hr, start), hu_at(hr, end))}
        if have_permits and all(f in permits[y] for y in years):
            r["permits_per_1000"] = 1000.0 * sum(permits[y][f] for y in years) / pop[start]
        else:
            r["permits_per_1000"] = None
        rows.append(r)
    return rows


def metro_units(delin):
    """-> ({cbsa: [member county fips]}, {cbsa: {division: [fips]}}) for metropolitan
    statistical areas, leaving out any CBSA with a member in a dropped state."""
    members, divs, drop = {}, {}, set()
    for f, d in delin.items():
        if not d["metro"]:
            continue
        members.setdefault(d["cbsa"], []).append(f)
        if d["div"]:
            divs.setdefault(d["cbsa"], {}).setdefault(d["div"], []).append(f)
        if f[:2] in sc.DROP_STATES:
            drop.add(d["cbsa"])
    return ({cb: sorted(fs) for cb, fs in members.items() if cb not in drop},
            {cb: dv for cb, dv in divs.items() if cb not in drop})


def metro_elasticity(members, elas_mean, elas_n):
    """Tract-weighted mean of county tract means = mean over the metro's tracts."""
    out = {}
    for cb, fs in members.items():
        have = [f for f in fs if f in elas_mean and elas_n.get(f)]
        den = sum(elas_n[f] for f in have)
        if den > 0:
            out[cb] = sum(elas_mean[f] * elas_n[f] for f in have) / den
    return out


def metro_ld_rows(start, end, members, divs, msas, bea_cty, hu, cbsa_hpi, cty_hpi, permits, groups):
    rows = []
    years = list(range(start + 1, end + 1))
    have_permits = all(y in permits for y in years)
    for cb, fs in sorted(members.items()):
        if cb not in groups:
            continue
        src = msas.get(cb)
        if src:
            how = "bea_msa"
            pi0, pi1 = src["pi"].get(start), src["pi"].get(end)
            p0, p1 = src["pop"].get(start), src["pop"].get(end)
            c0, c1 = src["pci"].get(start), src["pci"].get(end)
        else:
            how = "county_sum"
            ok = [f for f in fs if f in bea_cty and all(
                (bea_cty[f][k].get(y) or 0) > 0 for k in ("pi", "pop") for y in (start, end))]
            if not ok or len(ok) < len(fs):
                continue
            pi0 = sum(bea_cty[f]["pi"][start] for f in ok)
            pi1 = sum(bea_cty[f]["pi"][end] for f in ok)
            p0 = sum(bea_cty[f]["pop"][start] for f in ok)
            p1 = sum(bea_cty[f]["pop"][end] for f in ok)
            c0, c1 = 1000.0 * pi0 / p0, 1000.0 * pi1 / p1
        g, gp, pg = lg(pi0, pi1), lg(c0, c1), lg(p0, p1)
        if g is None or gp is None or pg is None:
            continue
        h0 = [hu_at(hu.get(f, {}), start) for f in fs]
        h1 = [hu_at(hu.get(f, {}), end) for f in fs]
        hu_growth = lg(sum(h0), sum(h1)) if all(h0) and all(h1) else None
        h = cbsa_hpi.get(cb, {})
        price, price_src = lg(h.get(start), h.get(end)), "fhfa_cbsa"
        if price is None and cb in divs:
            parts = []
            for dv, dfs in sorted(divs[cb].items()):
                dh = cbsa_hpi.get(dv, {})
                parts.append((lg(dh.get(start), dh.get(end)),
                              sum(hu_at(hu.get(f, {}), start) or 0.0 for f in dfs)))
            tot = sum(wt for _, wt in parts)
            if parts and tot > 0 and all(x is not None for x, _ in parts):
                price, price_src = sum(x * wt for x, wt in parts) / tot, "fhfa_divisions"
        if price is None:
            price_src = None
        num = den = tot = 0.0
        for f in fs:
            wt = hu_at(hu.get(f, {}), start) or 0.0
            tot += wt
            ch = cty_hpi.get(f, {})
            x = lg(ch.get(start), ch.get(end))
            if x is not None and wt > 0:
                num += x * wt
                den += wt
        price_cty = num / den if den > 0 and den >= 0.5 * tot else None
        perm, missing = None, 0
        if have_permits:
            s = 0
            for y in years:
                for f in fs:
                    if f in permits[y]:
                        s += permits[y][f]
                    else:
                        missing += 1
            perm = 1000.0 * s / p0
        rows.append({"fips": cb, "cl": cb, "grp": groups[cb], "w": p0, "pop_start": p0,
                     "n_counties": len(fs), "income_source": how,
                     "g_inc": g, "g_pci": gp, "pop_growth": pg, "hu_growth": hu_growth,
                     "price_growth": price, "price_source": price_src, "price_growth_cty": price_cty,
                     "permits_per_1000": perm, "permit_county_years_missing": missing})
    return rows


def panel_rows(years, bea, hpi, permits, hu, groups, wbase=2000):
    rows = []
    for f, rec in sorted(bea.items()):
        if f[:2] in sc.DROP_STATES or f not in groups:
            continue
        pi, pop = rec["pi"], rec["pop"]
        if (pop.get(wbase) or 0) <= 0:
            continue
        h, hr = hpi.get(f, {}), hu.get(f, {})
        for t in years:
            gs = [lg(pi.get(t - j - 1), pi.get(t - j)) for j in range(3)]
            if any(x is None for x in gs):
                continue
            r = {"fips": f, "t": t, "grp": groups[f], "w": pop[wbase],
                 "g0": gs[0], "g1": gs[1], "g2": gs[2],
                 "dprice": lg(h.get(t - 1), h.get(t)),
                 "dhu": lg(hr.get(t - 1), hr.get(t)),
                 "dpop": lg(pop.get(t - 1), pop.get(t))}
            pr = permits.get(t)
            r["permits_rate"] = (1000.0 * pr[f] / pop[t - 1]
                                 if pr is not None and f in pr and (pop.get(t - 1) or 0) > 0 else None)
            rows.append(r)
    return rows


# ---------------------------------------------------------------- analysis

LD_OUTCOMES = ["price_growth", "hu_growth", "permits_per_1000", "pop_growth"]
PANEL_OUTCOMES = ["dprice", "permits_rate", "dhu", "dpop"]


def run_ld(rows, specs, outcomes, cluster):
    out = {}
    for name, gcol, weighted, filt, ymap in specs:
        out[name] = {}
        for y in outcomes:
            ycol = ymap.get(y, y)
            sub = [r for r in rows if filt(r) and r.get(ycol) is not None
                   and math.isfinite(r[ycol]) and math.isfinite(r[gcol])]
            if len(sub) < 45:
                out[name][y] = {"n": len(sub), "skipped": "too few units"}
                continue
            out[name][y] = tercile_slopes(sub, ycol, gcol, weighted=weighted, cluster=cluster)
    return out


def get_c(res, *path):
    try:
        for p in path:
            res = res[p]
        return res
    except (KeyError, TypeError, IndexError):
        return None


def expect_sign(c, sign):
    if c is None:
        return {"status": "not evaluable"}
    held = sign * c["est"] > 0 and c["p"] < 0.05
    return {"status": "supported" if held else "not supported", "est": c["est"], "se": c["se"], "p": c["p"]}


def expect_null(c):
    if c is None:
        return {"status": "not evaluable"}
    return {"status": "null reproduced" if c["p"] >= 0.05 else "not reproduced (p<0.05)",
            "est": c["est"], "se": c["se"], "p": c["p"]}


def fmt(c):
    return "n/a" if not c else "%.3f (%.3f)" % (c["est"], c["se"])


def ld_table(block):
    L = ["| outcome | n | slope low | slope mid | slope high | low minus high | p |",
         "|---|---:|---:|---:|---:|---:|---:|"]
    for y, r in block.items():
        if "slopes" not in r:
            L.append("| %s | %s | skipped | | | | |" % (y, r.get("n")))
            continue
        d = r["slope_low_minus_high"]
        L.append("| %s | %d | %s | %s | %s | %s | %.3g |" % (
            y, r["n"], fmt(r["slopes"][0]), fmt(r["slopes"][1]), fmt(r["slopes"][2]), fmt(d), d["p"]))
    return L


def panel_table(block):
    L = ["| outcome | county-years | counties | cum. low | cum. mid | cum. high | low minus high | p |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for y, r in block.items():
        if "cumulative" not in r:
            L.append("| %s | %s | skipped | | | | | |" % (y, r.get("n")))
            continue
        d = r["cumulative_low_minus_high"]
        L.append("| %s | %d | %d | %s | %s | %s | %s | %.3g |" % (
            y, r["n"], r["n_counties"], fmt(r["cumulative"][0]), fmt(r["cumulative"][1]),
            fmt(r["cumulative"][2]), fmt(d), d["p"]))
    return L


def write_md(path, meta, results, hyps):
    L = ["# Reconciliation layer: results (sc-reconcile-v1)", "",
         "Made with AI agents working in the name of MV2 of Munim, Inc. "
         "Pre-registered in PREREGISTRATION-RECONCILE.md before any data were seen.", "",
         "Tercile 0 = lowest Baum-Snow-Han unit supply elasticity (most constrained). Long-difference "
         "slopes are on log growth of total personal income; panel figures are cumulative 3-year "
         "responses to annual log income growth. Standard errors in brackets.", "", "## Inputs", ""]
    for k, v in meta.items():
        L.append("- %s: %s" % (k, v if isinstance(v, str) else json.dumps(v, default=str)))
    L.append("")
    for section, res in results.items():
        L += ["## %s" % section, ""]
        for spec, block in res.items():
            L += ["### %s" % spec, ""]
            L += panel_table(block) if section.startswith("panel") else ld_table(block)
            L.append("")
    L += ["## Pre-registered hypotheses", ""]
    for k, v in hyps.items():
        L.append("- %s: %s" % (k, json.dumps(v)))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def write_csv(path, rows, keys):
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow(r)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    data_dir = sc.writable_dir(args.data_dir, os.path.join(args.out_dir, "cache"))
    log = sc.Log(os.path.join(args.out_dir, "reconcile_report.txt"))
    log("data dir: %s" % data_dir)
    j = lambda name: os.path.join(data_dir, name)  # noqa: E731

    bea_zip = sc.get_first(sc.BEA_URLS, j("CAINC1.zip"), sc.is_zip, log)
    fhfa_x = sc.get_first(sc.FHFA_URLS, j("hpi_at_county.xlsx"), sc.is_zip, log)
    cbsa_x = sc.get_first([FHFA_CBSA_URL], j("hpi_at_cbsa.xlsx"), sc.is_zip, log)
    delin_x = sc.get_first([DELIN_URL], j("list1_2023.xlsx"), sc.is_zip, log)
    hu00_p = sc.get_first([HU00_URL], j("hu-est00int-tot.csv"), sc.is_text_table, log)
    hu10_p = sc.get_first([HU10_URL], j("HU-EST2020_ALL.csv"), sc.is_text_table, log)
    bsh_p = sc.get_first(sc.BSH_URLS, j("bsh_elasticities.dta"), sc.is_dta, log)

    bea, msas, collisions = {}, {}, set()
    if bea_zip:
        with zipfile.ZipFile(bea_zip) as zf:
            pick = [n for n in zf.namelist() if "ALL_AREAS" in n and n.lower().endswith(".csv")]
            if pick:
                bea, msas, collisions = parse_bea_all(zf.read(pick[0]).decode("latin-1"))
    log("BEA county rows: %d; MSA rows: %d; codes shared by a county and an area row: %s"
        % (len(bea), len(msas), sorted(collisions)))
    cty_hpi = xlsx_parse(fhfa_x, sc.parse_fhfa_rows) if fhfa_x else {}
    cbsa_hpi = {}
    if cbsa_x:
        cbsa_hpi = (xlsx_parse(cbsa_x, parse_hpi_rows)
                    or xlsx_parse(cbsa_x, lambda rows: parse_hpi_rows(rows, key="msa")))
    delin = xlsx_parse(delin_x, parse_delineation) if delin_x else {}
    hu = merge_hu(*[parse_hu(open(p, encoding="latin-1").read()) for p in (hu00_p, hu10_p) if p])
    log("FHFA county series: %d; FHFA CBSA/division series: %d; delineation counties: %d; "
        "HU counties: %d (with 2000, 2010, Apr-2020 counts: %d)" % (
            len(cty_hpi), len(cbsa_hpi), len(delin), len(hu),
            sum(1 for r in hu.values() if all(k in r for k in CENSUS_POINT.values()))))

    ly_bea = sc.latest_year({f: r["pi"] for f, r in bea.items()}) if bea else None
    ly_fhfa = sc.latest_year(cty_hpi) if cty_hpi else None
    L = min(ly_bea, ly_fhfa) if ly_bea and ly_fhfa else None
    permits = {}
    for y in range(2001, (L or 2020) + 1):
        p = sc.get_first([sc.BPS_URL.format(year=y)], j("co%da.txt" % y), sc.is_text_table, log)
        if p:
            with open(p, encoding="latin-1") as f:
                permits[y] = sc.parse_bps_county(f.read())
    log("BPS years: %s; latest common BEA/FHFA year L: %s" % (sorted(permits), L))

    bsh = sc.load_bsh(bsh_p, log) if bsh_p else None
    meta = {"latest_common_year": L, "bea_county_rows": len(bea), "bea_msa_rows": len(msas),
            "bea_code_collisions": sorted(collisions), "fhfa_county_series": len(cty_hpi),
            "fhfa_cbsa_series": len(cbsa_hpi), "delineation_counties": len(delin),
            "hu_counties": len(hu), "bps_years": sorted(permits)}
    results, hyps = {}, {}
    if not (bsh and bsh.get("primary_by_county")):
        log("no elasticity data: analysis skipped")
    else:
        elas = {k: v for k, v in bsh["primary_by_county"].items() if k[:2] not in sc.DROP_STATES}
        ntr = bsh.get("primary_tracts", {})
        groups, _ = sc.rank_groups(elas)
        members, divs = metro_units(delin)
        m_elas = metro_elasticity(members, elas, ntr)
        m_groups, _ = sc.rank_groups(m_elas) if m_elas else ({}, {})
        meta.update({"elasticity_column": bsh["primary"], "elasticity_rule_tier": bsh["tier"],
                     "counties_with_elasticity": len(elas), "metros": len(members),
                     "metros_with_elasticity": len(m_elas)})
        in_metro = {f for cb, fs in members.items() if cb in m_elas for f in fs}
        cty_specs = [
            ("primary", "g_inc", True, lambda r: True, {}),
            ("unweighted", "g_inc", False, lambda r: True, {}),
            ("per_capita_income", "g_pci", True, lambda r: True, {}),
            ("metro_member_counties", "g_inc", True, lambda r: r["fips"] in in_metro, {}),
        ]
        m_specs = [
            ("primary", "g_inc", True, lambda r: True, {}),
            ("unweighted", "g_inc", False, lambda r: True, {}),
            ("per_capita_income", "g_pci", True, lambda r: True, {}),
            ("county_aggregated_price", "g_inc", True, lambda r: True, {"price_growth": "price_growth_cty"}),
        ]
        m_out, c_out = [], []
        for s, e in ((2000, 2020), (2010, 2020)):
            mrows = metro_ld_rows(s, e, members, divs, msas, bea, hu, cbsa_hpi, cty_hpi, permits, m_groups)
            crows = county_ld_rows(s, e, bea, cty_hpi, hu, permits, groups)
            log("LD %d-%d: %d metros (price sources %s), %d counties" % (
                s, e, len(mrows), json.dumps({k: sum(1 for r in mrows if r["price_source"] == k)
                                             for k in ("fhfa_cbsa", "fhfa_divisions", None)}), len(crows)))
            results["metro_LD_%d_%d" % (s, e)] = run_ld(mrows, m_specs, LD_OUTCOMES, cluster=False)
            results["county_LD_%d_%d" % (s, e)] = run_ld(crows, cty_specs, LD_OUTCOMES, cluster=True)
            m_out += [dict(r, period="%d-%d" % (s, e), elasticity=m_elas[r["fips"]]) for r in mrows]
            c_out += [dict(r, period="%d-%d" % (s, e), elasticity=elas[r["fips"]]) for r in crows]
        pre = list(range(2001, 2020))
        full = list(range(2001, (L or 2019) + 1))
        prow = panel_rows(full, bea, cty_hpi, permits, hu, groups)
        log("panel rows: %d county-years" % len(prow))
        pre_rows = [r for r in prow if r["t"] in pre]
        specs = [("primary", pre_rows, "county+year", True, 3),
                 ("state_year_fe", pre_rows, "county+state-year", True, 3),
                 ("unweighted", pre_rows, "county+year", False, 3),
                 ("contemporaneous_only", pre_rows, "county+year", True, 1),
                 ("through_latest_year", prow, "county+year", True, 3)]
        panel = {}
        for name, rws, fe, wtd, lags in specs:
            panel[name] = {y: panel_fit(rws, y, fe=fe, weighted=wtd, lags=lags) for y in PANEL_OUTCOMES}
        results["panel_annual"] = panel

        def ldc(section, y):
            return get_c(results, section, "primary", y, "slope_low_minus_high")
        hyps = {
            "R1 metro 2000-2020 price slope gap is null (LMW reproduced)": expect_null(ldc("metro_LD_2000_2020", "price_growth")),
            "R2 metro 2000-2020 housing-unit slope gap is null (LMW reproduced)": expect_null(ldc("metro_LD_2000_2020", "hu_growth")),
            "R3 county 2000-2020 price slope low>high": expect_sign(ldc("county_LD_2000_2020", "price_growth"), +1),
            "R4 county 2000-2020 housing-unit slope high>low": expect_sign(ldc("county_LD_2000_2020", "hu_growth"), -1),
            "R5 panel permits cumulative response high>low": expect_sign(get_c(panel, "primary", "permits_rate", "cumulative_low_minus_high"), -1),
            "R6 panel price cumulative response low>high": expect_sign(get_c(panel, "primary", "dprice", "cumulative_low_minus_high"), +1),
            "R7 panel housing-unit cumulative response high>low": expect_sign(get_c(panel, "primary", "dhu", "cumulative_low_minus_high"), -1),
        }
        write_csv(os.path.join(args.out_dir, "metro_ld.csv"), m_out,
                  ["period", "fips", "grp", "elasticity", "n_counties", "income_source", "pop_start",
                   "g_inc", "g_pci", "pop_growth", "hu_growth", "price_growth", "price_source",
                   "price_growth_cty", "permits_per_1000", "permit_county_years_missing"])
        write_csv(os.path.join(args.out_dir, "county_ld.csv"), c_out,
                  ["period", "fips", "grp", "elasticity", "pop_start", "g_inc", "g_pci",
                   "pop_growth", "hu_growth", "price_growth", "permits_per_1000"])
    with open(os.path.join(args.out_dir, "reconcile_results.json"), "w") as f:
        json.dump({"meta": meta, "results": results, "hypotheses": hyps}, f, indent=1, default=str)
    write_md(os.path.join(args.out_dir, "reconcile_results.md"), meta, results, hyps)
    log("hypotheses: %s" % json.dumps(hyps))
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
