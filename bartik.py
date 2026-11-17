#!/usr/bin/env python3
# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Part 4: do measured supply elasticities predict how housing supply answered a LATER, outside
job shock?

Baum-Snow and Han (2024, JPE) estimate housing supply elasticities for every U.S. tract from
labour-demand shocks to commuting destinations, built from 1990 and 2000 commuting data and the
decade changes that follow. Louie, Mondragon and Wieland (2025, NBER w33576) argue that measured
elasticities do not separate where demand became prices and where it became homes; Murphy and
Shaheen (2026, Dallas Fed WP 2635) dispute that. Both compare metros.

This part takes a demand shock that comes after the elasticities were estimated: a county
shift-share ("Bartik") labour-demand shock for 2010-2019, from County Business Patterns 3-digit
industry employment in 2010 and leave-one-out national industry growth to 2019. For each
elasticity tercile it measures the reduced-form response of employment, income, population,
housing units, permits and prices, and the realised inverse supply slope: percent price growth
per percent housing-unit growth caused by the shock (2SLS, the shock as instrument). The test is
whether the counties measured as least elastic really showed the steepest supply curve.

See PREREGISTRATION-BARTIK.md for the fixed plan. Reuses sc_analysis.py, reconcile.py and
remote.py from commit 0e6c10d of this repository.
"""

import argparse
import csv
import io
import json
import math
import os
import sys
import zipfile
from collections import Counter

import numpy as np

import reconcile as rc
import remote as rm
import sc_analysis as sc

K = 3
BASE, END = 2010, 2019
CBP_URL = "https://www2.census.gov/programs-surveys/cbp/datasets/{y}/cbp{yy}co.zip"
# Midpoints of the CBP employment-size classes used when a cell is withheld (EMP is then 0 and
# EMPFLAG holds the class letter; there is no letter D). M (100,000 or more) gets its lower bound.
FLAG_MID = {"A": 10.0, "B": 60.0, "C": 175.0, "E": 375.0, "F": 750.0, "G": 1750.0,
            "H": 3750.0, "I": 7500.0, "J": 17500.0, "K": 37500.0, "L": 75000.0, "M": 100000.0}
WEAK_T = 3.16  # first-stage t below this (F < 10) in tercile 0 or 2 -> the 2SLS test is not judged


# ---------------------------------------------------------------- County Business Patterns

def _cell(row, i):
    return row[i].strip().strip('"') if i is not None and i < len(row) else ""


def parse_cbp(lines):
    """CBP county file (CSV with header) -> (industry, total, info).

    industry: {fips: {3-digit NAICS: employment}} from rows coded like "236///".
    total: {fips: employment} from the all-industry row "------".
    Withheld cells (EMP 0 with an EMPFLAG letter) get the midpoint of their size class.
    Statewide rows (county 999) and sector 99 (not classified) are left out."""
    ind, tot = {}, {}
    info = {"rows_kept": 0, "imputed_cells": 0, "imputed_employment": 0.0}
    header = None
    for row in csv.reader(lines):
        if header is None:
            header = [h.strip().strip('"').lstrip(chr(0xFEFF)).lower() for h in row]
            idx = {h: i for i, h in enumerate(header)}
            if not {"fipstate", "fipscty", "naics", "emp"} <= set(idx):
                info["error"] = "unexpected header: %s" % header[:12]
                return ind, tot, info
            i_s, i_c, i_n, i_e = idx["fipstate"], idx["fipscty"], idx["naics"], idx["emp"]
            i_f = idx.get("empflag")
            continue
        st, co, naics = _cell(row, i_s), _cell(row, i_c), _cell(row, i_n)
        if not (st.isdigit() and co.isdigit()) or co.zfill(3) == "999":
            continue
        is_total = naics == "------"
        is_3 = len(naics) == 6 and naics[:3].isdigit() and naics[3:] == "///" and not naics.startswith("99")
        if not (is_total or is_3):
            continue
        emp = sc._num(_cell(row, i_e)) or 0.0
        flag = _cell(row, i_f).upper()
        if emp <= 0 and flag in FLAG_MID:
            emp = FLAG_MID[flag]
            info["imputed_cells"] += 1
            info["imputed_employment"] += emp
        fips = st.zfill(2) + co.zfill(3)
        info["rows_kept"] += 1
        if is_total:
            tot[fips] = emp
        else:
            ind.setdefault(fips, {})[naics[:3]] = emp
    return ind, tot, info


def bartik(ind0, ind1):
    """Leave-one-out shift-share shock, in percent:

        B_c = sum_i s_ci * 100 * ln[(N1_i - e1_ci) / (N0_i - e0_ci)]

    s_ci = county c's base-year share of its 3-digit employment in industry i; N = the sum over
    all counties. Industries whose leave-one-out employment is not positive in both years are
    left out and the remaining shares rescaled; `covered` is the share kept."""
    N0, N1 = Counter(), Counter()
    for d in ind0.values():
        for i, e in d.items():
            N0[i] += e
    for d in ind1.values():
        for i, e in d.items():
            N1[i] += e
    out = {}
    for f, d in ind0.items():
        total = sum(d.values())
        if total <= 0:
            continue
        e1 = ind1.get(f, {})
        num = cov = 0.0
        for i, e in d.items():
            a = N0[i] - e
            b = N1.get(i, 0.0) - e1.get(i, 0.0)
            if e > 0 and a > 0 and b > 0:
                num += e * 100.0 * math.log(b / a)
                cov += e
        if cov > 0:
            out[f] = {"bartik": num / cov, "covered": cov / total}
    return out


# ---------------------------------------------------------------- assembly

def build_rows(groups, bk, tot0, tot1, bea, hpi, hu, permits, land, delin, s=BASE, e=END):
    """One row per county with an elasticity group, a shift-share shock and base population."""
    rows = []
    years = list(range(s + 1, e + 1))
    for f in sorted(groups):
        if f[:2] in sc.DROP_STATES or f not in bk:
            continue
        b = bea.get(f)
        if not b:
            continue
        p0 = b["pop"].get(s)
        if not p0 or p0 <= 0:
            continue
        d = delin.get(f, {})
        h = hpi.get(f, {})
        u = hu.get(f, {})
        hu0 = rc.hu_at(u, s)
        r = {"fips": f, "state": f[:2], "cbsa": d.get("cbsa") or None, "metro": bool(d.get("metro")),
             "grp": groups[f], "w": p0, "pop10": p0,
             "bartik": bk[f]["bartik"], "covered": bk[f]["covered"],
             "emp_growth": rm.lg100(tot0.get(f), tot1.get(f)),
             "inc_growth": rm.lg100(b["pi"].get(s), b["pi"].get(e)),
             "pop_growth": rm.lg100(p0, b["pop"].get(e)),
             "hu_growth": rm.lg100(hu0, rc.hu_at(u, e)),
             "price_growth": rm.lg100(h.get(s), h.get(e)),
             "hu_growth_00_10": rm.lg100(rc.hu_at(u, 2000), hu0),
             "log_density": math.log(p0 / land[f]) if land.get(f) else None}
        if hu0 and all(f in permits.get(y, {}) for y in years):
            r["permits_per_1000hu"] = 1000.0 * sum(permits[y][f] for y in years) / hu0
        else:
            r["permits_per_1000hu"] = None
        rows.append(r)
    return rows


def metro_rows(members, divs, m_groups, bk, tot0, tot1, bea, hu, permits, cbsa_hpi, s=BASE, e=END):
    """Metro aggregates (the LMW unit). The metro shock is the base-employment-weighted mean of
    its counties' shocks; every member county must have a shock and base employment."""
    rows = []
    years = list(range(s + 1, e + 1))
    for cb, fs in sorted(members.items()):
        if cb not in m_groups:
            continue
        if not all(f in bk and (tot0.get(f) or 0) > 0 for f in fs):
            continue
        E0 = sum(tot0[f] for f in fs)
        E1 = sum(tot1.get(f) or 0.0 for f in fs)
        B = sum(tot0[f] * bk[f]["bartik"] for f in fs) / E0

        def total(get):
            vals = [get(f) for f in fs]
            return sum(vals) if all(v for v in vals) else None
        p0 = total(lambda f: bea.get(f, {}).get("pop", {}).get(s))
        p1 = total(lambda f: bea.get(f, {}).get("pop", {}).get(e))
        h0 = total(lambda f: rc.hu_at(hu.get(f, {}), s))
        h1 = total(lambda f: rc.hu_at(hu.get(f, {}), e))
        if not p0:
            continue
        hp = cbsa_hpi.get(cb, {})
        price, src = rm.lg100(hp.get(s), hp.get(e)), "fhfa_cbsa"
        if price is None:
            src = None
            if cb in divs:
                parts = []
                for dv, dfs in sorted(divs[cb].items()):
                    dh = cbsa_hpi.get(dv, {})
                    wt = sum(rc.hu_at(hu.get(f, {}), s) or 0.0 for f in dfs)
                    parts.append((rm.lg100(dh.get(s), dh.get(e)), wt))
                tw = sum(wt for _, wt in parts)
                if parts and tw > 0 and all(x is not None for x, _ in parts):
                    price, src = sum(x * wt for x, wt in parts) / tw, "fhfa_divisions"
        perm = None
        if h0 and all(f in permits.get(y, {}) for y in years for f in fs):
            perm = 1000.0 * sum(permits[y][f] for y in years for f in fs) / h0
        rows.append({"fips": cb, "cbsa": cb, "metro": True, "grp": m_groups[cb], "w": p0,
                     "pop10": p0, "n_counties": len(fs), "bartik": B,
                     "emp_growth": rm.lg100(E0, E1) if E1 > 0 else None,
                     "pop_growth": rm.lg100(p0, p1), "hu_growth": rm.lg100(h0, h1),
                     "price_growth": price, "price_source": src, "permits_per_1000hu": perm})
    return rows


# ---------------------------------------------------------------- statistics

def _sample(rows, need, fe):
    sub = [r for r in rows if all(r.get(c) is not None and math.isfinite(r[c]) for c in need)]
    if fe:
        sub = [r for r in sub if r.get(fe)]
        cnt = Counter(r[fe] for r in sub)
        sub = [r for r in sub if cnt[r[fe]] >= 2]
    return sub


def iv_by_tercile(rows, ycol="price_growth", xcol="hu_growth", zcol="bartik", fe="state",
                  cluster="state", weighted=True, controls=(), min_n=45):
    """Realised inverse supply slope by tercile (just-identified 2SLS):

        y = FE + a_k + sum_k theta_k D_k x (+ controls),  D_k x instrumented by D_k z.

    theta_k = percent price growth per percent housing-unit growth caused by the shock.
    Weighted; cluster-robust (CR1) by `cluster`."""
    sub = _sample(rows, (ycol, xcol, zcol) + tuple(controls), fe)
    if len(sub) < min_n:
        return {"n": len(sub), "skipped": "too few units"}
    n = len(sub)
    D = [[1.0 if r["grp"] == k else 0.0 for r in sub] for k in range(K)]
    W = (D[1:] if fe else D) + [[r[c] for r in sub] for c in controls]
    Wm = np.column_stack(W)
    Xm = np.column_stack([[D[k][i] * sub[i][xcol] for i in range(n)] for k in range(K)])
    Zm = np.column_stack([[D[k][i] * sub[i][zcol] for i in range(n)] for k in range(K)])
    y = np.asarray([r[ycol] for r in sub], float)
    w = np.asarray([r["w"] if weighted else 1.0 for r in sub], float)
    if fe:
        nw = Wm.shape[1]
        Md, _ = rc.demean(np.column_stack([y, Wm, Xm, Zm]), w, [[r[fe] for r in sub]])
        y, Wm, Xm, Zm = Md[:, 0], Md[:, 1:1 + nw], Md[:, 1 + nw:1 + nw + K], Md[:, 1 + nw + K:]
    R = np.column_stack([Wm, Xm])
    Z = np.column_stack([Wm, Zm])
    sw = np.sqrt(w)
    Rs, Zs, ys = R * sw[:, None], Z * sw[:, None], y * sw
    A = np.linalg.pinv(Zs.T @ Rs)
    beta = A @ (Zs.T @ ys)
    u = ys - Rs @ beta
    Zu = Zs * u[:, None]
    sums = {}
    for i, r in enumerate(sub):
        sums[r[cluster]] = sums.get(r[cluster], 0) + Zu[i]
    S = np.stack(list(sums.values()))
    G, p = S.shape[0], R.shape[1]
    V = A @ (S.T @ S) @ A.T * (G / (G - 1)) * ((n - 1) / (n - p))
    off = Wm.shape[1]

    def e(*pairs):
        v = [0.0] * p
        for i, s in pairs:
            v[i] = s
        return v
    return {"n": n, "n_clusters": G, "fe": fe, "cluster": cluster, "weighted": weighted,
            "controls": list(controls),
            "n_by_group": [sum(1 for r in sub if r["grp"] == k) for k in range(K)],
            "theta": [sc.contrast(beta, V, e((off + k, 1.0))) for k in range(K)],
            "theta_low_minus_high": sc.contrast(beta, V, e((off, 1.0), (off + K - 1, -1.0)))}


def first_stage_ok(block):
    """The housing-unit reduced form (the 2SLS first stage) must be positive with t >= 3.16 in
    the lowest and the highest tercile for the 2SLS contrast to be judged."""
    try:
        sl = block["hu_growth"]["split"]["slopes"]
    except (KeyError, TypeError):
        return False, []
    ts = [c["est"] / c["se"] if c["se"] > 0 else float("nan") for c in sl]
    ok = all(math.isfinite(ts[k]) and ts[k] >= WEAK_T for k in (0, K - 1))
    return ok, ts


OUTCOMES = ["emp_growth", "inc_growth", "pop_growth", "hu_growth", "permits_per_1000hu", "price_growth"]


def specs():
    allc = lambda r: True  # noqa: E731
    metro = lambda r: r["metro"]  # noqa: E731
    return [
        ("county_state_fe", allc, dict(fe="state", cluster="state")),
        ("county_state_fe_unweighted", allc, dict(fe="state", cluster="state", weighted=False)),
        ("county_state_fe_pop10k", lambda r: r["pop10"] >= 10000, dict(fe="state", cluster="state")),
        ("county_state_fe_lagged_growth", allc,
         dict(fe="state", cluster="state", controls=("hu_growth_00_10",))),
        ("county_no_fe", allc, dict(fe=None, cluster="state")),
        ("within_metro", metro, dict(fe="cbsa", cluster="cbsa")),
        ("within_metro_density", metro, dict(fe="cbsa", cluster="cbsa", controls=("log_density",))),
    ]


def analyse(rows, mrows, min_n=45):
    res, iv = {}, {}
    for name, filt, kw in specs():
        sub = [r for r in rows if filt(r)]
        res[name] = {y: {"split": rm.fit(sub, y, xcol="bartik", split=True, min_n=min_n, **kw),
                         "pooled": rm.fit(sub, y, xcol="bartik", split=False, min_n=min_n, **kw)}
                     for y in OUTCOMES}
        iv[name] = iv_by_tercile(sub, min_n=min_n, **kw)
    mk = dict(fe=None, cluster="fips")
    res["metro"] = {y: {"split": rm.fit(mrows, y, xcol="bartik", split=True, min_n=min_n, **mk),
                        "pooled": rm.fit(mrows, y, xcol="bartik", split=False, min_n=min_n, **mk)}
                    for y in OUTCOMES if y != "inc_growth"}
    iv["metro"] = iv_by_tercile(mrows, min_n=min_n, **mk)
    return res, iv


def tight_null(block):
    """Is the 95% interval of the low-minus-high price slope inside +/- half the pooled slope?"""
    try:
        d = block["price_growth"]["split"]["slope_low_minus_high"]
        pooled = block["price_growth"]["pooled"]["slope"]
    except (KeyError, TypeError):
        return {"status": "not evaluable"}
    if not (pooled["est"] > 0 and pooled["p"] < 0.05) or not math.isfinite(d["se"]):
        return {"status": "not evaluable (pooled price slope not positive and significant)"}
    lo, hi = d["est"] - 1.96 * d["se"], d["est"] + 1.96 * d["se"]
    if not lo < 0 < hi:
        return {"status": "gap is significant", "ci": [lo, hi]}
    tight = max(abs(lo), abs(hi)) < 0.5 * pooled["est"]
    return {"status": "tight null" if tight else "not a tight null", "ci": [lo, hi],
            "half_pooled": 0.5 * pooled["est"]}


def hypotheses(res, iv):
    g = rc.get_c
    P, M = "county_state_fe", "within_metro"
    ok, ts = first_stage_ok(res.get(P, {}))
    b6 = (rc.expect_sign(g(iv, P, "theta_low_minus_high"), +1) if ok else
          {"status": "not evaluable (weak first stage)", "first_stage_t": ts})
    return {
        "B1 first stage: the shock predicts county employment growth (pooled > 0)": rc.expect_sign(g(res, P, "emp_growth", "pooled", "slope"), +1),
        "B2 the shock predicts housing-unit growth (pooled > 0)": rc.expect_sign(g(res, P, "hu_growth", "pooled", "slope"), +1),
        "B3 price response low tercile > high tercile": rc.expect_sign(g(res, P, "price_growth", "split", "slope_low_minus_high"), +1),
        "B4 housing-unit response high tercile > low tercile": rc.expect_sign(g(res, P, "hu_growth", "split", "slope_low_minus_high"), -1),
        "B5 permits response high tercile > low tercile": rc.expect_sign(g(res, P, "permits_per_1000hu", "split", "slope_low_minus_high"), -1),
        "B6 realised inverse supply slope (2SLS) low tercile > high tercile": b6,
        "B7 within metros: price response low > high": rc.expect_sign(g(res, M, "price_growth", "split", "slope_low_minus_high"), +1),
        "B8 metro level (LMW unit): price response low > high": rc.expect_sign(g(res, "metro", "price_growth", "split", "slope_low_minus_high"), +1),
    }


# ---------------------------------------------------------------- output

def fmt(c):
    return "n/a" if not c else "%.3f (%.3f)" % (c["est"], c["se"])


def write_md(path, meta, res, iv, hyps, extra):
    L = ["# Part 4: a later job shock and the realised supply curve (sc-bartik-v1)", "",
         "Made with AI agents working in the name of MV2 of Munim, Inc. Pre-registered in "
         "PREREGISTRATION-BARTIK.md before any data were seen.", "",
         "Shock: 2010-2019 leave-one-out shift-share employment growth, percent. Outcomes are "
         "100 x log growth 2010-2019 (percent), or permits 2011-2019 per 1,000 2010 homes. "
         "Tercile 0 = lowest Baum-Snow-Han unit supply elasticity (most constrained). Slopes are "
         "per percentage point of shock. Standard errors in brackets.", "", "## Inputs", ""]
    for k, v in meta.items():
        L.append("- %s: %s" % (k, v if isinstance(v, str) else json.dumps(v, default=str)))
    L.append("")
    for spec, block in res.items():
        L += ["## %s" % spec, "",
              "| outcome | n | pooled slope | slope low | slope mid | slope high | low minus high | p |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for y, b in block.items():
            s, pl = b["split"], b["pooled"]
            if "slopes" not in s:
                L.append("| %s | %s | skipped | | | | | |" % (y, s.get("n")))
                continue
            d = s["slope_low_minus_high"]
            L.append("| %s | %d | %s | %s | %s | %s | %s | %.3g |" % (
                y, s["n"], fmt(pl.get("slope")), fmt(s["slopes"][0]), fmt(s["slopes"][1]),
                fmt(s["slopes"][2]), fmt(d), d["p"]))
        t = iv.get(spec, {})
        if "theta" in t:
            d = t["theta_low_minus_high"]
            L += ["", "Realised inverse supply slope (2SLS, %% price per %% homes): low %s, mid %s, "
                  "high %s; low minus high %s, p=%.3g (n=%d)" % (
                      fmt(t["theta"][0]), fmt(t["theta"][1]), fmt(t["theta"][2]), fmt(d), d["p"], t["n"])]
        L.append("")
    L += ["## First-stage strength and tight-null check (county_state_fe)", "",
          "- %s" % json.dumps(extra.get("first_stage")), "- %s" % json.dumps(extra.get("tight_null")),
          "", "## Pre-registered hypotheses", ""]
    for k, v in hyps.items():
        L.append("- %s: %s" % (k, json.dumps(v)))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def load_cbp(year, data_dir, log):
    yy = "%02d" % (year % 100)
    p = sc.get_first([CBP_URL.format(y=year, yy=yy)], os.path.join(data_dir, "cbp%sco.zip" % yy),
                     sc.is_zip, log)
    if not p:
        return {}, {}, {"error": "download failed"}
    with zipfile.ZipFile(p) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith((".txt", ".csv"))]
        if not names:
            return {}, {}, {"error": "no text member: %s" % zf.namelist()}
        with zf.open(names[0]) as fh:
            ind, tot, info = parse_cbp(io.TextIOWrapper(fh, encoding="latin-1", newline=""))
    info.update({"member": names[0], "counties_with_industries": len(ind),
                 "counties_with_total": len(tot),
                 "industries": len({i for d in ind.values() for i in d})})
    log("CBP %d: %s" % (year, json.dumps(info)))
    return ind, tot, info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    data_dir = sc.writable_dir(args.data_dir, os.path.join(args.out_dir, "cache"))
    log = sc.Log(os.path.join(args.out_dir, "bartik_report.txt"))
    j = lambda name: os.path.join(data_dir, name)  # noqa: E731
    log("data dir: %s" % data_dir)

    ind0, tot0, cbp0 = load_cbp(BASE, data_dir, log)
    ind1, tot1, cbp1 = load_cbp(END, data_dir, log)
    bk = bartik(ind0, ind1)
    bea_zip = sc.get_first(sc.BEA_URLS, j("CAINC1.zip"), sc.is_zip, log)
    bea = {}
    if bea_zip:
        with zipfile.ZipFile(bea_zip) as zf:
            pick = [n for n in zf.namelist() if "ALL_AREAS" in n and n.lower().endswith(".csv")]
            if pick:
                bea, _, _ = rc.parse_bea_all(zf.read(pick[0]).decode("latin-1"))
    fhfa_x = sc.get_first(sc.FHFA_URLS, j("hpi_at_county.xlsx"), sc.is_zip, log)
    hpi = rc.xlsx_parse(fhfa_x, sc.parse_fhfa_rows) if fhfa_x else {}
    cbsa_x = sc.get_first([rc.FHFA_CBSA_URL], j("hpi_at_cbsa.xlsx"), sc.is_zip, log)
    cbsa_hpi = {}
    if cbsa_x:
        cbsa_hpi = (rc.xlsx_parse(cbsa_x, rc.parse_hpi_rows)
                    or rc.xlsx_parse(cbsa_x, lambda rows: rc.parse_hpi_rows(rows, key="msa")))
    delin_x = sc.get_first([rc.DELIN_URL], j("list1_2023.xlsx"), sc.is_zip, log)
    delin = rc.xlsx_parse(delin_x, rc.parse_delineation) if delin_x else {}
    hu00_p = sc.get_first([rc.HU00_URL], j("hu-est00int-tot.csv"), sc.is_text_table, log)
    hu10_p = sc.get_first([rc.HU10_URL], j("HU-EST2020_ALL.csv"), sc.is_text_table, log)
    hu = rc.merge_hu(*[rc.parse_hu(rm.read_text(p)) for p in (hu00_p, hu10_p) if p])
    permits = {}
    for y in range(BASE + 1, END + 1):
        p = sc.get_first([sc.BPS_URL.format(year=y)], j("co%da.txt" % y), sc.is_text_table, log)
        if p:
            with open(p, encoding="latin-1") as f:
                permits[y] = sc.parse_bps_county(f.read())
    gz = sc.get_first([rm.GAZ_URL], j("2020_Gaz_counties_national.zip"), sc.is_zip, log)
    land = {}
    if gz:
        with zipfile.ZipFile(gz) as zf:
            txt = [n for n in zf.namelist() if n.lower().endswith(".txt")]
            if txt:
                land = rm.parse_gazetteer(rm.decode(zf.read(txt[0])))
    bsh_p = sc.get_first(sc.BSH_URLS, j("bsh_elasticities.dta"), sc.is_dta, log)
    bsh = sc.load_bsh(bsh_p, log) if bsh_p else None

    bvals = sorted(v["bartik"] for v in bk.values())
    meta = {"cbp_2010": cbp0, "cbp_2019": cbp1, "counties_with_shock": len(bk),
            "shock_quartiles": ([bvals[len(bvals) // 4], bvals[len(bvals) // 2], bvals[(3 * len(bvals)) // 4]]
                                if bvals else None),
            "shock_min_covered": min((v["covered"] for v in bk.values()), default=None),
            "bea_counties": len(bea), "fhfa_counties": len(hpi), "fhfa_cbsa_series": len(cbsa_hpi),
            "delineation_counties": len(delin), "hu_counties": len(hu),
            "hu_counties_2010_and_2019": sum(1 for r in hu.values() if "c2010" in r and 2019 in r),
            "permit_years": sorted(permits), "gazetteer_counties": len(land)}
    log("meta: %s" % json.dumps(meta, default=str))
    res, iv, hyps, extra = {}, {}, {}, {}
    if not (bsh and bsh.get("primary_by_county")) or not bk:
        log("missing elasticity or shift-share data: analysis skipped")
    else:
        elas = {k: v for k, v in bsh["primary_by_county"].items() if k[:2] not in sc.DROP_STATES}
        groups, _ = sc.rank_groups(elas)
        members, divs = rc.metro_units(delin)
        m_elas = rc.metro_elasticity(members, elas, bsh.get("primary_tracts", {}))
        m_groups, _ = sc.rank_groups(m_elas) if m_elas else ({}, {})
        rows = build_rows(groups, bk, tot0, tot1, bea, hpi, hu, permits, land, delin)
        mrows = metro_rows(members, divs, m_groups, bk, tot0, tot1, bea, hu, permits, cbsa_hpi)
        meta.update({"elasticity_column": bsh["primary"], "elasticity_rule_tier": bsh["tier"],
                     "counties_with_elasticity": len(elas), "rows": len(rows),
                     "metro_member_rows": sum(1 for r in rows if r["metro"]), "metro_rows": len(mrows),
                     "metro_price_sources": dict(Counter(r["price_source"] for r in mrows)),
                     "rows_by_tercile": [sum(1 for r in rows if r["grp"] == k) for k in range(K)]})
        log("rows: %d counties, %d metros" % (len(rows), len(mrows)))
        res, iv = analyse(rows, mrows)
        hyps = hypotheses(res, iv)
        ok, ts = first_stage_ok(res["county_state_fe"])
        extra = {"first_stage": {"judged": ok, "hu_t_by_tercile": ts},
                 "tight_null": tight_null(res["county_state_fe"])}
        rc.write_csv(os.path.join(args.out_dir, "county_bartik.csv"), rows,
                     ["fips", "state", "cbsa", "metro", "grp", "pop10", "bartik", "covered",
                      "emp_growth", "inc_growth", "pop_growth", "hu_growth", "permits_per_1000hu",
                      "price_growth", "hu_growth_00_10", "log_density"])
        rc.write_csv(os.path.join(args.out_dir, "metro_bartik.csv"), mrows,
                     ["fips", "grp", "pop10", "n_counties", "bartik", "emp_growth", "pop_growth",
                      "hu_growth", "permits_per_1000hu", "price_growth", "price_source"])
    with open(os.path.join(args.out_dir, "bartik_results.json"), "w") as f:
        json.dump({"meta": meta, "results": res, "iv": iv, "hypotheses": hyps, "extra": extra},
                  f, indent=1, default=str)
    write_md(os.path.join(args.out_dir, "bartik_results.md"), meta, res, iv, hyps, extra)
    log("hypotheses: %s" % json.dumps(hyps))
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
