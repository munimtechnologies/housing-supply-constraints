#!/usr/bin/env python3
# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Part 5: which specification choice makes Murphy-Shaheen and Louie-Mondragon-Wieland disagree?

Murphy and Shaheen (2026, Dallas Fed WP 2635, "M-S") answer Louie, Mondragon and Wieland (2025,
NBER w33576, "LMW"). On the same question (do supply elasticities change how income growth turns
into homes and prices across U.S. metros?) M-S find yes and LMW find no. M-S attribute the
long-difference gap to population weighting and to continuous instead of above-mean measures.

Two further differences can be read off the equations M-S print (pp. 13-14 and Tables 6, 10, A2):

1. Long differences: M-S regress growth on income growth and income growth x elasticity with NO
   elasticity main effect; LMW include it. Because income growth is positive almost everywhere,
   g*E is close to a rescaled E, so any direct association between elasticity and growth (for
   example Sun Belt growth for other reasons) can load on the interaction. Without the main
   effect, the interaction coefficient even changes with the choice of price deflator; with it,
   it cannot (shown in test_ms.py).
2. Annual panel: ln permits on ln real per-capita income and its interaction with elasticity,
   with metro and year fixed effects. Year effects common to all metros do not absorb
   E x (national income path), so the interaction can be identified from elastic metros riding
   the national boom-bust cycle differently rather than from their response to LOCAL income.
   Adding elasticity-by-year effects removes that channel.

This module runs the full grid on public data (FHFA metro HPI, BEA income, Census permits and
housing units, Baum-Snow and Han elasticities, FRED PCE price index). See PREREGISTRATION-MS.md.
"""

import argparse
import csv
import json
import math
import os
import sys
import zipfile

import numpy as np

import reconcile as rc
import sc_analysis as sc

PCE_URLS = ["https://fred.stlouisfed.org/graph/fredgraph.csv?id=PCEPI&fq=Annual&fam=avg"]
FIRST_YEAR = 2000
SPLIT_YEAR = 2012  # second sub-period starts here


def finite(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


# ---------------------------------------------------------------- parsers

def parse_fred_annual(text):
    """FRED fredgraph CSV ("observation_date,SERIES" then "YYYY-MM-DD,value") -> {year: value}.
    Missing values (".") and malformed lines are skipped."""
    out = {}
    for line in text.splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) < 2 or len(parts[0]) < 4 or not parts[0][:4].isdigit():
            continue
        try:
            out[int(parts[0][:4])] = float(parts[1])
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------- estimation

def tsls(y, endog, exog, instr=None, w=None, time=None, cluster=None, lag=1):
    """Weighted two-stage least squares; OLS when instr is None (endog then treated as exogenous).

    X = [endog, exog], Z = [instr, exog]. Returns beta (endog first, then exog) and three
    covariances: HC1, Driscoll-Kraay (Bartlett kernel, `lag` periods, scores summed by `time`,
    scaled by (n-1)/(n-k)) and CR1 by `cluster`. Fixed effects must be absorbed beforehand."""
    y = np.asarray(y, float)
    n = y.shape[0]

    def mat(a):
        if a is None:
            return np.zeros((n, 0))
        a = np.asarray(a, float)
        return a.reshape(n, -1) if a.size else np.zeros((n, 0))

    En, Ex = mat(endog), mat(exog)
    X = np.hstack([En, Ex])
    Z = X if instr is None else np.hstack([mat(instr), Ex])
    k = X.shape[1]
    sw = np.ones(n) if w is None else np.sqrt(np.asarray(w, float))
    Xs, Zs, ys = X * sw[:, None], Z * sw[:, None], y * sw
    Xh = Zs @ (np.linalg.pinv(Zs.T @ Zs) @ (Zs.T @ Xs))
    B = np.linalg.pinv(Xh.T @ Xh)
    beta = B @ (Xh.T @ ys)
    e = ys - Xs @ beta
    H = Xh * e[:, None]
    out = {"beta": beta, "n": n, "k": k,
           "V_hc1": B @ (H.T @ H) @ B * (n / (n - k)) if n > k else None, "V_dk": None, "V_cl": None}
    if time is not None:
        sums = {}
        for i, t in enumerate(time):
            sums[t] = sums.get(t, 0) + H[i]
        S = np.zeros((k, k))
        for t, h in sums.items():
            S += np.outer(h, h)
        for l in range(1, lag + 1):
            wt = 1.0 - l / (lag + 1.0)
            for t, h in sums.items():
                if t - l in sums:
                    g = sums[t - l]
                    S += wt * (np.outer(h, g) + np.outer(g, h))
        out["V_dk"] = B @ S @ B * ((n - 1) / (n - k)) if n > k else None
    if cluster is not None:
        sums = {}
        for i, c in enumerate(cluster):
            sums[c] = sums.get(c, 0) + H[i]
        S = np.stack(list(sums.values()))
        G = S.shape[0]
        if G > 1 and n > k:
            out["V_cl"] = B @ (S.T @ S) @ B * (G / (G - 1)) * ((n - 1) / (n - k))
    return out


def coef(fit, j, V="V_hc1"):
    c = [0.0] * fit["k"]
    c[j] = 1.0
    Vm = fit.get(V)
    if Vm is None:
        return None
    return sc.contrast(fit["beta"], Vm, c)


def first_stage_F(endog, exog, instr, w=None, time=None):
    """For each endogenous column: Wald F of the excluded instruments in its first stage
    (Driscoll-Kraay covariance if `time` is given, else HC1)."""
    endog = np.asarray(endog, float)
    endog = endog.reshape(endog.shape[0], -1)
    instr = np.asarray(instr, float).reshape(endog.shape[0], -1)
    q = instr.shape[1]
    out = []
    for j in range(endog.shape[1]):
        f = tsls(endog[:, j], instr, exog, None, w=w, time=time)
        V = f["V_dk"] if time is not None else f["V_hc1"]
        b = f["beta"][:q]
        Vq = V[:q, :q]
        try:
            out.append(float(b @ np.linalg.solve(Vq, b)) / q)
        except np.linalg.LinAlgError:
            out.append(float("nan"))
    return out


# ---------------------------------------------------------------- long differences

def ld_fit(rows, ycol, gcol, mcol, weighted=True, main=False):
    """y = a + b g + c g*M (+ d M). HC1 standard errors. Returns income, interaction, main."""
    sub = [r for r in rows if finite(r.get(ycol)) and finite(r.get(gcol)) and finite(r.get(mcol))]
    if len(sub) < 40:
        return {"n": len(sub), "skipped": "too few metros"}
    X = [[1.0, r[gcol], r[gcol] * r[mcol]] + ([r[mcol]] if main else []) for r in sub]
    y = [r[ycol] for r in sub]
    w = [r["w"] if weighted else 1.0 for r in sub]
    beta, V, _ = sc.wls(y, X, w)
    k = len(X[0])

    def c(j):
        v = [0.0] * k
        v[j] = 1.0
        return sc.contrast(beta, V, v)
    res = {"n": len(sub), "income": c(1), "interaction": c(2)}
    if main:
        res["main"] = c(3)
    return res


def ld_structural(rows, ycol, pcol, gcol, mcol, weighted=True, main=False):
    """2SLS: y = a + b1 p + b2 p*M (+ d M), instruments g and g*M. HC1 standard errors."""
    sub = [r for r in rows if all(finite(r.get(c)) for c in (ycol, pcol, gcol, mcol))]
    if len(sub) < 40:
        return {"n": len(sub), "skipped": "too few metros"}
    en = [[r[pcol], r[pcol] * r[mcol]] for r in sub]
    ex = [[1.0] + ([r[mcol]] if main else []) for r in sub]
    iv = [[r[gcol], r[gcol] * r[mcol]] for r in sub]
    w = [r["w"] if weighted else 1.0 for r in sub]
    f = tsls([r[ycol] for r in sub], en, ex, iv, w=w)
    res = {"n": len(sub), "price": coef(f, 0), "interaction": coef(f, 1),
           "first_stage_F": first_stage_F(en, ex, iv, w=w)}
    if main:
        res["main"] = coef(f, 3)
    return res


LD_OUTCOMES = ["hu_growth", "price_growth"]


def analyse_ld(rows):
    """The 2 x 2 x 2 grid (weights x measure x main effect) for both outcomes, the nominal-income
    variants of the weighted continuous cells, and the structural (2SLS) supply curve."""
    grid = {}
    for y in LD_OUTCOMES:
        grid[y] = {}
        for weighted in (True, False):
            for mcol in ("E", "D"):
                for main in (False, True):
                    key = "%s|%s|%s" % ("weighted" if weighted else "unweighted",
                                        "continuous" if mcol == "E" else "above_mean",
                                        "with_main" if main else "no_main")
                    grid[y][key] = ld_fit(rows, y, "g_real", mcol, weighted, main)
        for main in (False, True):
            grid[y]["weighted|continuous|%s|nominal_income" % ("with_main" if main else "no_main")] = \
                ld_fit(rows, y, "g_nom", "E", True, main)
    structural = {}
    for main in (False, True):
        for mcol in ("E", "D"):
            structural["weighted|%s|%s" % ("continuous" if mcol == "E" else "above_mean",
                                           "with_main" if main else "no_main")] = \
                ld_structural(rows, "hu_growth", "price_growth", "g_real", mcol, True, main)
    return {"reduced_form": grid, "structural": structural}


def switch_effects(grid_y):
    """Mean absolute change in the interaction z-statistic when one switch is flipped, averaged
    over the four settings of the other two. Keys 'weights', 'measure', 'main_effect'."""
    opts = {"weights": ("weighted", "unweighted"), "measure": ("continuous", "above_mean"),
            "main_effect": ("no_main", "with_main")}
    names = list(opts)
    out = {}
    for s in names:
        others = [o for o in names if o != s]
        diffs = []
        for a in opts[others[0]]:
            for b in opts[others[1]]:
                zs = []
                for v in opts[s]:
                    setting = {s: v, others[0]: a, others[1]: b}
                    key = "|".join(setting[n] for n in names)
                    r = grid_y.get(key, {})
                    zs.append(r["interaction"]["z"] if "interaction" in r else None)
                if None not in zs and all(math.isfinite(z) for z in zs):
                    diffs.append(abs(zs[0] - zs[1]))
        out[s] = sum(diffs) / len(diffs) if len(diffs) == 4 else None
    return out


# ---------------------------------------------------------------- annual panel

def national_path(rows, col="lny", weighted=True):
    """{year: weighted mean of col over the rows of that year}."""
    num, den = {}, {}
    for r in rows:
        w = r["w"] if weighted else 1.0
        num[r["t"]] = num.get(r["t"], 0.0) + w * r[col]
        den[r["t"]] = den.get(r["t"], 0.0) + w
    return {t: num[t] / den[t] for t in num if den[t] > 0}


def panel_fit(rows, ycol, exog, endog=None, instr=None, elas_by_year=None, weighted=True, lag=1):
    """Metro + year fixed effects (absorbed by weighted alternating projections), optional
    elasticity-by-year effects (column `elas_by_year` x year dummies, first year omitted), then
    OLS or 2SLS. exog/endog/instr are lists of (name, function(row) -> float)."""
    endog = endog or []
    instr = instr or []
    fns = [f for _, f in exog + endog + instr]
    sub = []
    for r in rows:
        if not finite(r.get(ycol)):
            continue
        try:
            vals = [f(r) for f in fns]
        except (TypeError, KeyError):  # a needed value is missing (None) in this metro-year
            continue
        if all(finite(v) for v in vals):
            sub.append(r)
    if len(sub) < 200:
        return {"n": len(sub), "skipped": "too few metro-years"}
    years = sorted({r["t"] for r in sub})
    ex = list(exog)
    if elas_by_year:
        for yr in years[1:]:
            ex.append(("%s_x_%d" % (elas_by_year, yr),
                       (lambda r, yr=yr: r[elas_by_year] if r["t"] == yr else 0.0)))
    M = np.array([[r[ycol]] + [f(r) for _, f in endog] + [f(r) for _, f in ex] +
                  [f(r) for _, f in instr] for r in sub], dtype=float)
    w = np.array([r["w"] if weighted else 1.0 for r in sub], float)
    Md, iters = rc.demean(M, w, [[r["m"] for r in sub], [r["t"] for r in sub]])
    ne, nx, ni = len(endog), len(ex), len(instr)
    yd = Md[:, 0]
    En = Md[:, 1:1 + ne]
    Ex = Md[:, 1 + ne:1 + ne + nx]
    Iv = Md[:, 1 + ne + nx:]
    times = [r["t"] for r in sub]
    f = tsls(yd, En if ne else None, Ex, Iv if ni else None, w=w, time=times,
             cluster=[r["m"] for r in sub], lag=lag)
    names = [n for n, _ in endog] + [n for n, _ in ex]
    out = {"n": len(sub), "n_metros": len({r["m"] for r in sub}), "years": [years[0], years[-1]],
           "weighted": weighted, "elasticity_by_year": bool(elas_by_year),
           "demean_iterations": iters, "coef": {}}
    shown = [n for n, _ in endog] + [n for n, _ in exog]
    for j, name in enumerate(names):
        if name not in shown:
            continue
        dk, cl = coef(f, j, "V_dk"), coef(f, j, "V_cl")
        out["coef"][name] = {"est": dk["est"] if dk else None,
                             "se_dk": dk["se"] if dk else None, "p_dk": dk["p"] if dk else None,
                             "se_cl": cl["se"] if cl else None, "p_cl": cl["p"] if cl else None}
    if ni:
        out["first_stage_F_dk"] = first_stage_F(En, Ex, Iv, w=w, time=times)
    return out


def analyse_panel(rows, split_year=SPLIT_YEAR):
    """The annual specifications A1-A9 (see PREREGISTRATION-MS.md)."""
    base = [r for r in rows if finite(r.get("lny"))]
    nat = national_path(base)
    for r in base:
        r["nat"] = nat[r["t"]]
        r["loc"] = r["lny"] - nat[r["t"]]
    lny = ("lny", lambda r: r["lny"])
    lnyE = ("lny_x_E", lambda r: r["lny"] * r["E"])
    lnyD = ("lny_x_D", lambda r: r["lny"] * r["D"])
    hp = ("lnhp", lambda r: r["lnhp"])
    hpE = ("lnhp_x_E", lambda r: r["lnhp"] * r["E"])
    loc = ("local", lambda r: r["loc"])
    locE = ("local_x_E", lambda r: r["loc"] * r["E"])
    natE = ("national_x_E", lambda r: r["nat"] * r["E"])
    early = [r for r in base if r["t"] < split_year]
    late = [r for r in base if r["t"] >= split_year]
    P = "lnpermits"
    return {
        "A1_ms_reduced_form": panel_fit(base, P, [lny, lnyE]),
        "A2_plus_elasticity_by_year": panel_fit(base, P, [lny, lnyE], elas_by_year="E"),
        "A3_local_vs_national": panel_fit(base, P, [loc, locE, natE]),
        "A4a_early": panel_fit(early, P, [lny, lnyE]),
        "A4b_late": panel_fit(late, P, [lny, lnyE]),
        "A5_unweighted": panel_fit(base, P, [lny, lnyE], weighted=False),
        "A6_above_mean": panel_fit(base, P, [lny, lnyD]),
        "A6b_above_mean_plus_by_year": panel_fit(base, P, [lny, lnyD], elas_by_year="D"),
        "A7_structural": panel_fit(base, P, [], endog=[hp, hpE], instr=[lny, lnyE]),
        "A8_structural_plus_by_year": panel_fit(base, P, [], endog=[hp, hpE], instr=[lny, lnyE],
                                                elas_by_year="E"),
        "A9_price_reduced_form": panel_fit(base, "lnhp", [lny, lnyE]),
        "A9b_price_plus_by_year": panel_fit(base, "lnhp", [lny, lnyE], elas_by_year="E"),
    }


# ---------------------------------------------------------------- metro assembly

def metro_income(cb, fs, msas, bea):
    """{year: (personal income, population, per-capita income)} from BEA's own MSA row, else
    the sum of member counties for years where every member is present."""
    src = msas.get(cb)
    out = {}
    if src:
        for y, pi in src["pi"].items():
            pop, pci = src["pop"].get(y), src["pci"].get(y)
            if finite(pi) and finite(pop) and pop > 0 and pi > 0:
                out[y] = (pi, pop, pci if finite(pci) and pci > 0 else 1000.0 * pi / pop)
        return out, "bea_msa"
    years = set()
    for f in fs:
        if f not in bea:
            return {}, "county_sum"
        years |= set(bea[f]["pi"])
    for y in sorted(years):
        pis = [bea[f]["pi"].get(y) for f in fs]
        pops = [bea[f]["pop"].get(y) for f in fs]
        if all(finite(v) and v > 0 for v in pis + pops):
            pi, pop = sum(pis), sum(pops)
            out[y] = (pi, pop, 1000.0 * pi / pop)
    return out, "county_sum"


def metro_lhpi(cb, divs, cbsa_hpi, hu, base_year=FIRST_YEAR):
    """{year: log FHFA index} for the CBSA, or for CBSAs reported only by metropolitan division
    the base-year-housing-unit-weighted mean of division log indexes (years with every division)."""
    h = cbsa_hpi.get(cb)
    if h:
        return {y: math.log(v) for y, v in h.items() if finite(v) and v > 0}, "fhfa_cbsa"
    if cb not in divs:
        return {}, None
    parts = []
    for dv, dfs in sorted(divs[cb].items()):
        wt = sum(rc.hu_at(hu.get(f, {}), base_year) or 0.0 for f in dfs)
        parts.append((cbsa_hpi.get(dv, {}), wt))
    tot = sum(wt for _, wt in parts)
    if tot <= 0 or any(not s for s, _ in parts):
        return {}, None
    years = set.intersection(*[set(s) for s, _ in parts])
    out = {}
    for y in years:
        vals = [s[y] for s, _ in parts]
        if all(finite(v) and v > 0 for v in vals):
            out[y] = sum(math.log(v) * wt for v, (_, wt) in zip(vals, parts)) / tot
    return out, "fhfa_divisions"


def build_metros(members, divs, msas, bea, hu, cbsa_hpi, permits, m_elas, lpce, years, w_year=2010):
    """-> (long-difference rows 2000-2020, annual panel rows, info)."""
    ld, panel = [], []
    info = {"income_source": {}, "price_source": {}, "permit_member_years_missing": 0,
            "zero_permit_metro_years": 0}
    for cb, fs in sorted(members.items()):
        if cb not in m_elas:
            continue
        inc, how = metro_income(cb, fs, msas, bea)
        if w_year not in inc:
            continue
        lh, psrc = metro_lhpi(cb, divs, cbsa_hpi, hu)
        info["income_source"][how] = info["income_source"].get(how, 0) + 1
        info["price_source"][str(psrc)] = info["price_source"].get(str(psrc), 0) + 1
        E, w = m_elas[cb], inc[w_year][1]
        r = {"m": cb, "E": E, "w": w, "n_counties": len(fs), "income_source": how, "price_source": psrc}
        a, b = 2000, 2020
        if a in inc and b in inc and a in lpce and b in lpce:
            dp = lpce[b] - lpce[a]
            r["g_nom"] = math.log(inc[b][0] / inc[a][0])
            r["g_real"] = r["g_nom"] - dp
            r["pop_growth"] = math.log(inc[b][1] / inc[a][1])
            h0 = [rc.hu_at(hu.get(f, {}), a) for f in fs]
            h1 = [rc.hu_at(hu.get(f, {}), b) for f in fs]
            r["hu_growth"] = math.log(sum(h1) / sum(h0)) if all(h0) and all(h1) else None
            r["price_growth"] = (lh[b] - lh[a] - dp) if a in lh and b in lh else None
            ld.append(r)
        for t in years:
            if t not in inc or t not in lpce:
                continue
            s, miss = 0, 0
            pt = permits.get(t)
            if pt is None:
                lnp = None
            else:
                for f in fs:
                    if f in pt:
                        s += pt[f]
                    else:
                        miss += 1
                info["permit_member_years_missing"] += miss
                if s <= 0:
                    info["zero_permit_metro_years"] += 1
                lnp = math.log(s) if s > 0 else None
            panel.append({"m": cb, "t": t, "E": E, "w": w,
                          "lnpermits": lnp, "permits": s if pt is not None else None,
                          "lny": math.log(inc[t][2]) - lpce[t],
                          "lnhp": (lh[t] - lpce[t]) if t in lh else None})
    return ld, panel, info


def set_dummy(rows_list, threshold):
    for rows in rows_list:
        for r in rows:
            r["D"] = 1.0 if r["E"] > threshold else 0.0


# ---------------------------------------------------------------- hypotheses

def h_sign(c, sign, p_key="p"):
    if not c or not finite(c.get("est")) or not finite(c.get(p_key)):
        return {"status": "not evaluable"}
    held = sign * c["est"] > 0 and c[p_key] < 0.05
    return {"status": "supported" if held else "not supported", "est": c["est"], "p": c[p_key]}


def hypotheses(ld, panel):
    rf = ld["reduced_form"]
    hu = rf.get("hu_growth", {})
    pr = rf.get("price_growth", {})

    def inter(block, key):
        return (block.get(key) or {}).get("interaction")

    h = {}
    h["P1 M-S long-difference cell (weighted, continuous, no main effect): housing-unit interaction > 0"] = \
        h_sign(inter(hu, "weighted|continuous|no_main"), +1)
    c = inter(hu, "unweighted|above_mean|with_main")
    h["P2 LMW long-difference cell (unweighted, above-mean, with main effect): housing-unit interaction null"] = (
        {"status": "not evaluable"} if not c else
        {"status": "supported" if c["p"] >= 0.05 else "not supported", "est": c["est"], "p": c["p"]})
    c0, c1 = inter(hu, "weighted|continuous|no_main"), inter(hu, "weighted|continuous|with_main")
    if not c0 or not c1 or not (c0["est"] > 0 and c0["p"] < 0.05):
        h["P3 adding the main effect halves the M-S housing-unit interaction and makes it insignificant"] = {
            "status": "not evaluable (P1 not supported)"}
    else:
        held = c1["est"] <= 0.5 * c0["est"] and c1["p"] >= 0.05
        h["P3 adding the main effect halves the M-S housing-unit interaction and makes it insignificant"] = {
            "status": "supported" if held else "not supported", "without": c0["est"], "with": c1["est"],
            "p_with": c1["p"]}
    sw = switch_effects(hu)
    if None in sw.values():
        h["P4 the main-effect switch moves the housing-unit interaction z most"] = {"status": "not evaluable", "effects": sw}
    else:
        top = max(sw, key=sw.get)
        h["P4 the main-effect switch moves the housing-unit interaction z most"] = {
            "status": "supported" if top == "main_effect" else "not supported", "effects": sw}
    h["P5 price, weighted continuous WITH main effect: interaction < 0"] = \
        h_sign(inter(pr, "weighted|continuous|with_main"), -1)

    def pc(spec, name):
        c = ((panel.get(spec) or {}).get("coef") or {}).get(name)
        return None if not c else {"est": c["est"], "p": c["p_dk"]}
    h["P6 annual M-S reduced form (A1): ln income x E on ln permits > 0"] = h_sign(pc("A1_ms_reduced_form", "lny_x_E"), +1)
    h["P7 with elasticity-by-year effects (A2): ln income x E > 0"] = h_sign(pc("A2_plus_elasticity_by_year", "lny_x_E"), +1)
    h["P8 national income path x E (A3) > 0"] = h_sign(pc("A3_local_vs_national", "national_x_E"), +1)
    s = (ld.get("structural") or {}).get("weighted|continuous|with_main") or {}
    h["P9 long-difference 2SLS with main effect: price x E on housing units > 0"] = h_sign(s.get("interaction"), +1)
    return h


# ---------------------------------------------------------------- output

def fmt(c, p="p"):
    if not c or not finite(c.get("est")):
        return "n/a"
    se = c.get("se", c.get("se_dk"))
    return "%.3f (%.3f) p=%.3g" % (c["est"], se if finite(se) else float("nan"), c.get(p, float("nan")))


def write_md(path, meta, ld, panel, hyps):
    L = ["# Part 5 results: the Murphy-Shaheen specification on open data (sc-ms-v1)", "",
         "Made with AI agents working in the name of MV2 of Munim, Inc. Pre-registered in "
         "PREREGISTRATION-MS.md before any data were seen. E = Baum-Snow-Han unit supply elasticity "
         "(metro tract mean); D = 1 if E is above the sample mean. Standard errors in brackets: HC1 "
         "for long differences, Driscoll-Kraay (lag 1) for the annual panel.", "", "## Inputs", ""]
    for k, v in meta.items():
        L.append("- %s: %s" % (k, v if isinstance(v, str) else json.dumps(v, default=str)))
    L += ["", "## Long differences 2000-2020 (reduced form)", ""]
    for y, block in ld["reduced_form"].items():
        L += ["### %s" % y, "", "| cell | n | income | income x M | M (main) |", "|---|---:|---:|---:|---:|"]
        for key, r in block.items():
            if "interaction" not in r:
                L.append("| %s | %s | skipped | | |" % (key, r.get("n")))
                continue
            L.append("| %s | %d | %s | %s | %s |" % (key, r["n"], fmt(r["income"]), fmt(r["interaction"]),
                                                    fmt(r.get("main"))))
        L += ["", "Mean |change in interaction z| per switch: %s" % json.dumps(switch_effects(block)), ""]
    L += ["## Long differences 2000-2020 (2SLS supply curve, housing units on price)", "",
          "| cell | n | price | price x M | first-stage F |", "|---|---:|---:|---:|---|"]
    for key, r in ld["structural"].items():
        if "interaction" not in r:
            L.append("| %s | %s | skipped | | |" % (key, r.get("n")))
            continue
        L.append("| %s | %d | %s | %s | %s |" % (key, r["n"], fmt(r["price"]), fmt(r["interaction"]),
                                                ", ".join("%.1f" % x for x in r["first_stage_F"])))
    L += ["", "## Annual panel (metro and year fixed effects)", "",
          "| spec | metro-years | metros | years | coefficients (Driscoll-Kraay SE, p) | first-stage F |",
          "|---|---:|---:|---|---|---|"]
    for key, r in panel.items():
        if "coef" not in r:
            L.append("| %s | %s | skipped | | | |" % (key, r.get("n")))
            continue
        cs = "; ".join("%s %s" % (n, fmt(c, "p_dk")) for n, c in r["coef"].items())
        L.append("| %s | %d | %d | %d-%d | %s | %s |" % (
            key, r["n"], r["n_metros"], r["years"][0], r["years"][1], cs,
            ", ".join("%.1f" % x for x in r.get("first_stage_F_dk", [])) or ""))
    L += ["", "## Pre-registered predictions", ""]
    for k, v in hyps.items():
        L.append("- %s: %s" % (k, json.dumps(v, default=str)))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def write_csv(path, rows, keys):
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow(r)


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    data_dir = sc.writable_dir(args.data_dir, os.path.join(args.out_dir, "cache"))
    log = sc.Log(os.path.join(args.out_dir, "ms_report.txt"))
    log("data dir: %s" % data_dir)
    j = lambda name: os.path.join(data_dir, name)  # noqa: E731

    bea_zip = sc.get_first(sc.BEA_URLS, j("CAINC1.zip"), sc.is_zip, log)
    cbsa_x = sc.get_first([rc.FHFA_CBSA_URL], j("hpi_at_cbsa.xlsx"), sc.is_zip, log)
    delin_x = sc.get_first([rc.DELIN_URL], j("list1_2023.xlsx"), sc.is_zip, log)
    hu00_p = sc.get_first([rc.HU00_URL], j("hu-est00int-tot.csv"), sc.is_text_table, log)
    hu10_p = sc.get_first([rc.HU10_URL], j("HU-EST2020_ALL.csv"), sc.is_text_table, log)
    bsh_p = sc.get_first(sc.BSH_URLS, j("bsh_elasticities.dta"), sc.is_dta, log)
    pce_p = sc.get_first(PCE_URLS, j("fred_pcepi_annual.csv"), sc.is_text_table, log)

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
    pce = parse_fred_annual(open(pce_p, encoding="utf-8", errors="replace").read()) if pce_p else {}
    deflator = "FRED PCEPI annual average" if pce else "none (nominal; PCE download failed)"
    log("BEA county rows %d, MSA rows %d; FHFA CBSA/division series %d; delineation counties %d; "
        "HU counties %d; PCE years %d" % (len(bea), len(msas), len(cbsa_hpi), len(delin), len(hu), len(pce)))

    ly_bea = sc.latest_year({f: r["pi"] for f, r in bea.items()}) if bea else None
    ly_hpi = sc.latest_year(cbsa_hpi, min_count=200) if cbsa_hpi else None
    T = min(x for x in (ly_bea, ly_hpi, max(pce) if pce else ly_bea) if x) if (ly_bea and ly_hpi) else None
    permits = {}
    for y in range(FIRST_YEAR, (T or 2020) + 1):
        p = sc.get_first([sc.BPS_URL.format(year=y)], j("co%da.txt" % y), sc.is_text_table, log)
        if p:
            with open(p, encoding="latin-1") as f:
                permits[y] = sc.parse_bps_county(f.read())
    years = [y for y in range(FIRST_YEAR, (T or 2020) + 1) if y in permits]
    lpce = ({y: math.log(v / 100.0) for y, v in pce.items()} if pce
            else {y: 0.0 for y in range(1990, 2031)})
    log("latest BEA year %s, latest FHFA CBSA year %s, panel end T=%s; BPS years %s"
        % (ly_bea, ly_hpi, T, sorted(permits)))

    meta = {"deflator": deflator, "panel_last_year": T, "bea_msa_rows": len(msas),
            "bea_code_collisions": sorted(collisions), "fhfa_cbsa_series": len(cbsa_hpi),
            "bps_years": sorted(permits)}
    ld, panel, hyps = {"reduced_form": {}, "structural": {}}, {}, {}
    bsh = sc.load_bsh(bsh_p, log) if bsh_p else None
    if not (bsh and bsh.get("primary_by_county")) or not delin:
        log("no elasticity or delineation data: analysis skipped")
    else:
        elas = {k: v for k, v in bsh["primary_by_county"].items() if k[:2] not in sc.DROP_STATES}
        members, divs = rc.metro_units(delin)
        m_elas = rc.metro_elasticity(members, elas, bsh.get("primary_tracts", {}))
        ld_rows, p_rows, info = build_metros(members, divs, msas, bea, hu, cbsa_hpi, permits,
                                             m_elas, lpce, years)
        universe = sorted({r["m"] for r in p_rows} | {r["m"] for r in ld_rows})
        threshold = sum(m_elas[m] for m in universe) / len(universe) if universe else float("nan")
        set_dummy([ld_rows, p_rows], threshold)
        ws = {r["m"]: r["w"] for r in p_rows}
        wsum = sum(ws.values())
        meta.update({"elasticity_column": bsh["primary"], "metros": len(members),
                     "metros_with_elasticity": len(m_elas), "analysis_metros": len(universe),
                     "E_mean_unweighted": threshold,
                     "E_mean_pop2010_weighted": (sum(m_elas[m] * ws[m] for m in ws) / wsum) if wsum else None,
                     "ms_table2_bsh_for_comparison": "unweighted 0.340, 2010-pop-weighted 0.234 (n=318)",
                     "ld_metros": len(ld_rows), "panel_metro_years": len(p_rows)})
        meta.update(info)
        log("metros: %d with elasticity, %d analysed; LD rows %d; panel rows %d; info %s"
            % (len(m_elas), len(universe), len(ld_rows), len(p_rows), json.dumps(info)))
        ld = analyse_ld(ld_rows)
        panel = analyse_panel(p_rows)
        hyps = hypotheses(ld, panel)
        write_csv(os.path.join(args.out_dir, "metro_ms_ld.csv"), ld_rows,
                  ["m", "E", "D", "w", "n_counties", "income_source", "price_source", "g_nom", "g_real",
                   "pop_growth", "hu_growth", "price_growth"])
        write_csv(os.path.join(args.out_dir, "metro_ms_panel.csv"), p_rows,
                  ["m", "t", "E", "D", "w", "permits", "lnpermits", "lny", "lnhp"])
    with open(os.path.join(args.out_dir, "ms_results.json"), "w") as f:
        json.dump(jsonable({"meta": meta, "long_difference": ld, "panel": panel, "hypotheses": hyps}),
                  f, indent=1, default=str)
    write_md(os.path.join(args.out_dir, "ms_results.md"), meta, ld, panel, hyps)
    log("hypotheses: %s" % json.dumps(jsonable(hyps), default=str))
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
