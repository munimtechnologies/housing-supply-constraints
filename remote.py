#!/usr/bin/env python3
# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Part 3: does the same outside demand shock turn into prices in constrained counties and into
homes in elastic ones, comparing counties WITHIN the same metro area?

Furth's critique of Louie, Mondragon and Wieland (2025, NBER w33576) is that local income growth
is not an outside demand shock. LMW answer with the 2019-2023 shift to remote work (Mondragon and
Wieland, NBER w30041), measured across METRO areas, and find no difference by supply elasticity.
Murphy and Shaheen (2026, Dallas Fed WP 2635) dispute LMW, also with metros. Neither looks inside
metros, where constrained cores and elastic suburbs face one labour market.

Exposure: the share of a county's resident workers who worked from home in 2015-2019 (ACS 5-year
table B08301, line 21 / line 1), the pre-pandemic remote-work share that Mondragon and Wieland use
as their instrument. Outcomes: FHFA county price growth 2019-2023 (and to the latest year), Census
housing-unit growth April 2020 - July 2025, permits 2020-2025 per 1,000 homes, population growth,
and the first stage (the change in the work-from-home share, 2015-19 to 2019-23).
Elasticity: Baum-Snow and Han unit supply elasticity, county terciles (as in parts 1 and 2).
See PREREGISTRATION-REMOTE.md for the fixed plan. Reuses sc_analysis.py and reconcile.py
(commit 993d76d of this repository).
"""

import argparse
import csv
import io
import json
import math
import os
import re
import sys
import unicodedata
import zipfile
from collections import Counter

import numpy as np

import reconcile as rc
import sc_analysis as sc

K = 3
WWW2 = "https://www2.census.gov/"
ACS19_URL = (WWW2 + "programs-surveys/acs/summary_file/2019/data/5_year_seq_by_state/"
             "{folder}/All_Geographies_Not_Tracts_Block_Groups/{file}")
ACS23_URL = (WWW2 + "programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/"
             "acsdt5y2023-b08301.dat")
HU_URLS = [(2025, WWW2 + "programs-surveys/popest/tables/2020-2025/housing/totals/CO-EST2025-HU.xlsx"),
           (2024, WWW2 + "programs-surveys/popest/tables/2020-2024/housing/totals/CO-EST2024-HU.xlsx")]
POP_URLS = [(2025, WWW2 + "programs-surveys/popest/datasets/2020-2025/counties/totals/co-est2025-alldata.csv"),
            (2024, WWW2 + "programs-surveys/popest/datasets/2020-2024/counties/totals/co-est2024-alldata.csv")]
GAZ_URL = WWW2 + "geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_Gaz_counties_national.zip"

# B08301 (Means of transportation to work) in the 2019 ACS 5-year sequence files: sequence 0027,
# start position 157 (1-based, counting the six identifier fields), 21 cells
# (ACS_5yr_Seq_Table_Number_Lookup.txt). Line 1 = total workers, line 21 = worked from home.
B08301_SEQ = "0027"
B08301_START = 157
NCELL = 21

# 2019 state folders on www2 and their file abbreviations. Connecticut is left out because its
# counties were replaced by planning regions in 2022 (dropped in parts 1 and 2 as well).
STATES = [
    ("Alabama", "al"), ("Alaska", "ak"), ("Arizona", "az"), ("Arkansas", "ar"),
    ("California", "ca"), ("Colorado", "co"), ("Delaware", "de"),
    ("DistrictOfColumbia", "dc"), ("Florida", "fl"), ("Georgia", "ga"), ("Hawaii", "hi"),
    ("Idaho", "id"), ("Illinois", "il"), ("Indiana", "in"), ("Iowa", "ia"), ("Kansas", "ks"),
    ("Kentucky", "ky"), ("Louisiana", "la"), ("Maine", "me"), ("Maryland", "md"),
    ("Massachusetts", "ma"), ("Michigan", "mi"), ("Minnesota", "mn"), ("Mississippi", "ms"),
    ("Missouri", "mo"), ("Montana", "mt"), ("Nebraska", "ne"), ("Nevada", "nv"),
    ("NewHampshire", "nh"), ("NewJersey", "nj"), ("NewMexico", "nm"), ("NewYork", "ny"),
    ("NorthCarolina", "nc"), ("NorthDakota", "nd"), ("Ohio", "oh"), ("Oklahoma", "ok"),
    ("Oregon", "or"), ("Pennsylvania", "pa"), ("RhodeIsland", "ri"), ("SouthCarolina", "sc"),
    ("SouthDakota", "sd"), ("Tennessee", "tn"), ("Texas", "tx"), ("Utah", "ut"),
    ("Vermont", "vt"), ("Virginia", "va"), ("Washington", "wa"), ("WestVirginia", "wv"),
    ("Wisconsin", "wi"), ("Wyoming", "wy"),
]


# ---------------------------------------------------------------- small helpers

def decode(raw):
    """Bytes -> text: UTF-8 if it decodes cleanly, else Latin-1."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def read_text(path):
    with open(path, "rb") as f:
        return decode(f.read())


def norm(s):
    """Place name -> ASCII, lower case, single spaces, no leading dots ("Doña" -> "dona")."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s.strip().lstrip(".").strip().lower())


def lg100(a, b):
    v = rc.lg(a, b)
    return None if v is None else 100.0 * v


# ---------------------------------------------------------------- 2015-2019 ACS (sequence files)

_GEO050 = re.compile(r"^05000US(\d{5})$")


def parse_geo19(text):
    """2019 ACS state geography CSV (no header) -> {LOGRECNO: county fips}. Keeps summary level
    050 (county), geographic component 00 (whole county). LOGRECNO is field 4; the GEOID field
    (05000USsscc) is found by its form rather than by position."""
    out = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 6 or row[2].strip() != "050" or row[3].strip() != "00":
            continue
        fips = next((m.group(1) for m in (_GEO050.match(c.strip()) for c in row) if m), None)
        if fips:
            out[row[4].strip()] = fips
    return out


def cells(row, start, n=NCELL):
    """n numeric cells from a sequence-file row starting at 1-based position `start`, or None."""
    part = row[start - 1:start - 1 + n]
    if len(part) < n:
        return None
    out = []
    for c in part:
        v = sc._num(c)
        if v is None:
            return None
        out.append(v)
    return out


def b08301_ok(v):
    """Internal sums of table B08301 hold: total = car + transit + taxi + motorcycle + bicycle +
    walked + other + worked from home; car = alone + carpool; carpool = its five sizes;
    transit = its five modes. (v[0] is line 1.)"""
    L = lambda i: v[i - 1]  # noqa: E731
    return (abs(L(1) - (L(2) + L(10) + sum(L(i) for i in range(16, 22)))) < 0.5
            and abs(L(2) - (L(3) + L(4))) < 0.5
            and abs(L(4) - sum(L(i) for i in range(5, 10))) < 0.5
            and abs(L(10) - sum(L(i) for i in range(11, 16))) < 0.5)


def find_start(rows, preferred=B08301_START, min_share=0.99):
    """-> (start, good, total). Uses the documented start position when B08301's sums hold for at
    least 99% of rows with workers; otherwise scans every position and takes the one where they
    hold for the most rows (still at least 99%), or (None, good, total)."""
    def score(s):
        good = tot = 0
        for row in rows:
            v = cells(row, s)
            if v is None or v[0] <= 0:
                continue
            tot += 1
            good += 1 if b08301_ok(v) else 0
        return good, tot
    g, t = score(preferred)
    if t and g >= min_share * t:
        return preferred, g, t
    width = max((len(r) for r in rows), default=0)
    best = None
    for s in range(7, width - NCELL + 2):
        g2, t2 = score(s)
        if t2 and g2 >= min_share * t2 and (best is None or g2 > best[1]):
            best = (s, g2, t2)
    return best if best else (None, g, t)


def load_acs19(data_dir, log):
    county_rows = []
    missing = []
    for folder, ab in STATES:
        zname, gname = "20195%s%s000.zip" % (ab, B08301_SEQ), "g20195%s.csv" % ab
        z = sc.get_first([ACS19_URL.format(folder=folder, file=zname)],
                         os.path.join(data_dir, "acs19_" + zname), sc.is_zip, log)
        g = sc.get_first([ACS19_URL.format(folder=folder, file=gname)],
                         os.path.join(data_dir, "acs19_" + gname), sc.is_text_table, log)
        if not (z and g):
            missing.append(ab)
            continue
        geo = parse_geo19(read_text(g))
        with zipfile.ZipFile(z) as zf:
            names = [n for n in zf.namelist()
                     if os.path.basename(n).lower().startswith("e") and n.lower().endswith(".txt")]
            if not names:
                log("no estimate file in %s: %s" % (zname, zf.namelist()))
                missing.append(ab)
                continue
            text = zf.read(names[0]).decode("latin-1")
        n0 = len(county_rows)
        for row in csv.reader(io.StringIO(text)):
            if len(row) > 6 and row[5].strip() in geo:
                county_rows.append((geo[row[5].strip()], row))
        log("ACS 2019 %s: %d county geographies, %d county rows" % (ab, len(geo), len(county_rows) - n0))
    start, good, tot = find_start([r for _, r in county_rows])
    info = {"start_position": start, "documented_start": B08301_START, "rows_checked": tot,
            "rows_with_sums_holding": good, "states_missing": missing}
    log("B08301 start position: %s (documented %d); sums hold in %d of %d county rows"
        % (start, B08301_START, good, tot))
    out = {}
    if start is None:
        return out, info
    for fips, row in county_rows:
        v = cells(row, start)
        if v is None or v[0] <= 0:
            continue
        out[fips] = {"workers": v[0], "wfh": v[NCELL - 1], "ok": b08301_ok(v)}
    return out, info


# ---------------------------------------------------------------- 2019-2023 ACS (table-based)

def parse_acs23(lines):
    """acsdt5y2023-b08301.dat (pipe-delimited, header first) -> {fips: {"workers", "wfh"}}."""
    it = iter(lines)
    try:
        header = next(it).rstrip("\r\n").lstrip(chr(0xFEFF)).split("|")
    except StopIteration:
        return {}
    if "B08301_E001" not in header or "B08301_E021" not in header:
        return {}
    i1, i21 = header.index("B08301_E001"), header.index("B08301_E021")
    out = {}
    for line in it:
        if not line.startswith("0500000US"):
            continue
        parts = line.rstrip("\r\n").split("|")
        if len(parts) <= max(i1, i21):
            continue
        w, h = sc._num(parts[i1]), sc._num(parts[i21])
        if w is not None and h is not None and w > 0:
            out[parts[0][-5:]] = {"workers": w, "wfh": h}
    return out


# ---------------------------------------------------------------- Census population estimates

def parse_coest(text):
    """co-est20xx-alldata.csv -> ({fips: {"base": ESTIMATESBASE2020, year: POPESTIMATEyear}},
    {(county name, state name): fips})."""
    pop, names = {}, {}
    rdr = csv.reader(io.StringIO(text))
    header = None
    for row in rdr:
        if header is None:
            header = [h.strip().lstrip(chr(0xFEFF)).upper() for h in row]
            idx = {h: i for i, h in enumerate(header)}
            need = {"SUMLEV", "STATE", "COUNTY", "STNAME", "CTYNAME"}
            if not need <= set(idx):
                return pop, names
            years = [(i, int(h[11:])) for i, h in enumerate(header)
                     if h.startswith("POPESTIMATE") and h[11:].isdigit()]
            continue
        if len(row) < len(header) or row[idx["SUMLEV"]].strip() != "050":
            continue
        fips = row[idx["STATE"]].strip().zfill(2) + row[idx["COUNTY"]].strip().zfill(3)
        rec = {}
        if "ESTIMATESBASE2020" in idx:
            v = sc._num(row[idx["ESTIMATESBASE2020"]])
            if v:
                rec["base"] = v
        for i, y in years:
            v = sc._num(row[i])
            if v:
                rec[y] = v
        pop[fips] = rec
        names[(norm(row[idx["CTYNAME"]]), norm(row[idx["STNAME"]]))] = fips
    return pop, names


def _year(c):
    if isinstance(c, bool):
        return None
    if isinstance(c, (int, float)) and not (isinstance(c, float) and math.isnan(c)):
        y = int(c)
        return y if y == c and 2000 <= y <= 2035 else None
    s = str(c or "").strip()
    return int(s) if s.isdigit() and len(s) == 4 and 2000 <= int(s) <= 2035 else None


def parse_hu_xlsx(rows):
    """CO-EST20xx-HU.xlsx rows -> {(county name, state name): {"base": April 2020, year: July}}.
    The year header is the first row with three or more year cells; the base column is the one
    whose header text mentions "base". County rows look like ".Autauga County, Alabama"."""
    out = {}
    ycols, base_i = None, None
    for row in rows:
        cells_ = list(row)
        if ycols is None:
            for i, c in enumerate(cells_):
                if isinstance(c, str) and "base" in c.lower():
                    base_i = i
            yc = {i: _year(c) for i, c in enumerate(cells_) if _year(c)}
            if len(yc) >= 3:
                ycols = yc
            continue
        if not cells_ or not isinstance(cells_[0], str):
            continue
        name = cells_[0].strip()
        if not name.startswith(".") or ", " not in name:
            continue
        county, state = name.lstrip(".").rsplit(", ", 1)
        rec = {}
        if base_i is not None and base_i < len(cells_):
            v = sc._num(str(cells_[base_i]))
            if v:
                rec["base"] = v
        for i, y in ycols.items():
            if i < len(cells_):
                v = sc._num(str(cells_[i]))
                if v:
                    rec[y] = v
        out[(norm(county), norm(state))] = rec
    return out


def parse_gazetteer(text):
    """2020 Gazetteer counties file (tab-delimited) -> {fips: land area in square miles}."""
    out = {}
    lines = text.splitlines()
    if not lines:
        return out
    header = [h.strip() for h in lines[0].split("\t")]
    if "GEOID" not in header or "ALAND_SQMI" not in header:
        return out
    ig, ia = header.index("GEOID"), header.index("ALAND_SQMI")
    for line in lines[1:]:
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) <= max(ig, ia):
            continue
        v = sc._num(parts[ia])
        if parts[ig].isdigit() and len(parts[ig]) == 5 and v and v > 0:
            out[parts[ig]] = v
    return out


# ---------------------------------------------------------------- assembly

def build_rows(groups, acs19, acs23, hpi, hu, hu_year, pop, pop_year, permits, permit_years,
               land, delin, price_end=2023, price_latest=None):
    """One row per county with an elasticity group and 2015-19 commuting data."""
    rows = []
    for f in sorted(groups):
        if f[:2] in sc.DROP_STATES or f not in acs19:
            continue
        a = acs19[f]
        if a["workers"] <= 0:
            continue
        d = delin.get(f, {})
        w19 = 100.0 * a["wfh"] / a["workers"]
        b = acs23.get(f)
        h = hpi.get(f, {})
        u = hu.get(f, {})
        p = pop.get(f, {})
        r = {"fips": f, "state": f[:2], "cbsa": d.get("cbsa") or None, "metro": bool(d.get("metro")),
             "grp": groups[f], "w": a["workers"], "workers19": a["workers"], "b08301_sums_ok": a.get("ok"),
             "w19": w19,
             "w23": 100.0 * b["wfh"] / b["workers"] if b else None,
             "price_19_23": lg100(h.get(2019), h.get(price_end)),
             "price_19_L": lg100(h.get(2019), h.get(price_latest)) if price_latest else None,
             "hu_growth": lg100(u.get("base"), u.get(hu_year)),
             "pop_growth": lg100(p.get("base"), p.get(pop_year))}
        r["d_wfh"] = r["w23"] - w19 if r["w23"] is not None else None
        if permit_years and u.get("base") and all(f in permits.get(y, {}) for y in permit_years):
            r["permits_per_1000hu"] = 1000.0 * sum(permits[y][f] for y in permit_years) / u["base"]
        else:
            r["permits_per_1000hu"] = None
        r["log_density"] = (math.log(p["base"] / land[f])
                            if p.get("base") and land.get(f) else None)
        rows.append(r)
    return rows


# ---------------------------------------------------------------- statistics

def fit(rows, ycol, xcol="w19", fe=None, cluster="state", weighted=True, controls=(),
        split=True, min_n=45):
    """y = [tercile intercepts] + sum_k b_k D_k x (split) or b x (pooled) + controls, with the
    fixed effect `fe` absorbed by weighted demeaning (one tercile dummy dropped when there is a
    fixed effect). Units alone in their fixed-effect group are dropped. Clustered (CR1)."""
    need = (ycol, xcol) + tuple(controls)
    sub = [r for r in rows if all(r.get(c) is not None and math.isfinite(r[c]) for c in need)]
    if fe:
        sub = [r for r in sub if r.get(fe)]
        cnt = Counter(r[fe] for r in sub)
        sub = [r for r in sub if cnt[r[fe]] >= 2]
    if len(sub) < min_n:
        return {"n": len(sub), "skipped": "too few counties"}
    n = len(sub)
    cols = []
    if split:
        dk = [[1.0 if r["grp"] == k else 0.0 for r in sub] for k in range(K)]
        cols += dk[1:] if fe else dk
        first = len(cols)
        cols += [[dk[k][i] * sub[i][xcol] for i in range(n)] for k in range(K)]
        slope_idx = list(range(first, first + K))
    else:
        if not fe:
            cols.append([1.0] * n)
        slope_idx = [len(cols)]
        cols.append([r[xcol] for r in sub])
    for c in controls:
        cols.append([r[c] for r in sub])
    X = np.column_stack(cols)
    y = np.asarray([r[ycol] for r in sub], float)
    w = np.asarray([r["w"] if weighted else 1.0 for r in sub], float)
    iters = 0
    if fe:
        Md, iters = rc.demean(np.column_stack([y, X]), w, [[r[fe] for r in sub]])
        y, X = Md[:, 0], Md[:, 1:]
    cl = [r[cluster] for r in sub]
    beta, V_hc1, V_cl = sc.wls(y, X, w, cl)
    p = X.shape[1]

    def e(*pairs):
        v = [0.0] * p
        for i, s in pairs:
            v[i] = s
        return v
    res = {"n": n, "n_clusters": len(set(cl)), "fe": fe, "cluster": cluster, "weighted": weighted,
           "controls": list(controls), "demean_iterations": iters,
           "n_fe_groups": len({r[fe] for r in sub}) if fe else None}
    if split:
        res["n_by_group"] = [sum(1 for r in sub if r["grp"] == k) for k in range(K)]
        res["slopes"] = [sc.contrast(beta, V_cl, e((i, 1.0))) for i in slope_idx]
        res["slope_low_minus_high"] = sc.contrast(beta, V_cl, e((slope_idx[0], 1.0), (slope_idx[-1], -1.0)))
    else:
        res["slope"] = sc.contrast(beta, V_cl, e((slope_idx[0], 1.0)))
    return res


OUTCOMES = ["d_wfh", "price_19_23", "price_19_L", "hu_growth", "permits_per_1000hu", "pop_growth"]


def specs():
    metro = lambda r: r["metro"]  # noqa: E731
    return [
        ("within_metro", metro, dict(fe="cbsa", cluster="cbsa")),
        ("within_metro_density", metro, dict(fe="cbsa", cluster="cbsa", controls=("log_density",))),
        ("within_metro_unweighted", metro, dict(fe="cbsa", cluster="cbsa", weighted=False)),
        ("within_metro_workers5k", lambda r: r["metro"] and r["workers19"] >= 5000,
         dict(fe="cbsa", cluster="cbsa")),
        ("cross_county_state_fe", lambda r: True, dict(fe="state", cluster="state")),
        ("national_no_fe", lambda r: True, dict(fe=None, cluster="state")),
    ]


def analyse(rows, min_n=45):
    out = {}
    for name, filt, kw in specs():
        sub = [r for r in rows if filt(r)]
        out[name] = {}
        for y in OUTCOMES:
            out[name][y] = {"split": fit(sub, y, split=True, min_n=min_n, **kw),
                            "pooled": fit(sub, y, split=False, min_n=min_n, **kw)}
    return out


def ratios(block):
    """Descriptive per-tercile ratios from the primary spec: reduced form / first stage (an IV
    estimate per percentage point of new remote work) and price / housing-unit response."""
    def sl(y, k):
        try:
            return block[y]["split"]["slopes"][k]["est"]
        except (KeyError, TypeError, IndexError):
            return None
    out = []
    for k in range(K):
        fs, pr, hu = sl("d_wfh", k), sl("price_19_23", k), sl("hu_growth", k)
        out.append({"tercile": k, "first_stage": fs,
                    "iv_price": pr / fs if pr is not None and fs else None,
                    "iv_hu": hu / fs if hu is not None and fs else None,
                    "price_per_hu": pr / hu if pr is not None and hu else None})
    return out


def tight_null(block):
    """Is the 95% interval of the low-minus-high price slope inside +/- half the pooled slope?"""
    try:
        d = block["price_19_23"]["split"]["slope_low_minus_high"]
        pooled = block["price_19_23"]["pooled"]["slope"]
    except (KeyError, TypeError):
        return {"status": "not evaluable"}
    if not (pooled["est"] > 0 and pooled["p"] < 0.05) or not math.isfinite(d["se"]):
        return {"status": "not evaluable (pooled price slope not positive and significant)"}
    lo, hi = d["est"] - 1.96 * d["se"], d["est"] + 1.96 * d["se"]
    tight = max(abs(lo), abs(hi)) < 0.5 * pooled["est"]
    return {"status": "tight null" if tight and lo < 0 < hi else ("not a tight null" if lo < 0 < hi else "gap is significant"),
            "ci": [lo, hi], "half_pooled": 0.5 * pooled["est"]}


def hypotheses(res):
    g = rc.get_c
    S, X = "within_metro", "cross_county_state_fe"
    return {
        "Q1 within-metro first stage: 2015-19 WFH share predicts the rise in WFH": rc.expect_sign(g(res, S, "d_wfh", "pooled", "slope"), +1),
        "Q2 within-metro: 2015-19 WFH share predicts 2019-23 price growth": rc.expect_sign(g(res, S, "price_19_23", "pooled", "slope"), +1),
        "Q3 within-metro price slope low>high": rc.expect_sign(g(res, S, "price_19_23", "split", "slope_low_minus_high"), +1),
        "Q4 within-metro housing-unit slope high>low": rc.expect_sign(g(res, S, "hu_growth", "split", "slope_low_minus_high"), -1),
        "Q5 within-metro permits slope high>low": rc.expect_sign(g(res, S, "permits_per_1000hu", "split", "slope_low_minus_high"), -1),
        "Q6 cross-county (state FE) price slope low>high": rc.expect_sign(g(res, X, "price_19_23", "split", "slope_low_minus_high"), +1),
        "Q7 cross-county (state FE) housing-unit slope high>low": rc.expect_sign(g(res, X, "hu_growth", "split", "slope_low_minus_high"), -1),
    }


# ---------------------------------------------------------------- output

def fmt(c):
    if not c:
        return "n/a"
    return "%.3f (%.3f)" % (c["est"], c["se"])


def write_md(path, meta, res, hyps, extra):
    L = ["# Part 3: remote-work demand shock, within metros (sc-remote-v1)", "",
         "Made with AI agents working in the name of MV2 of Munim, Inc. Pre-registered in "
         "PREREGISTRATION-REMOTE.md before any data were seen.", "",
         "Exposure: percent of resident workers who worked from home in 2015-2019. Outcomes are "
         "100 x log growth (percent), permits per 1,000 April-2020 homes, or (d_wfh) the change in "
         "the work-from-home percent. Tercile 0 = lowest Baum-Snow-Han unit supply elasticity "
         "(most constrained). Slopes are per percentage point of 2015-19 work from home. Standard "
         "errors in brackets, clustered as shown.", "", "## Inputs", ""]
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
        L.append("")
    L += ["## Descriptive ratios (within_metro)", ""]
    for r in extra.get("ratios", []):
        L.append("- %s" % json.dumps(r))
    L += ["", "## Tight-null check (within_metro price)", "", "- %s" % json.dumps(extra.get("tight_null")),
          "", "## Pre-registered hypotheses", ""]
    for k, v in hyps.items():
        L.append("- %s: %s" % (k, json.dumps(v)))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def first_ok(cands, data_dir, check, log):
    for year, url in cands:
        p = sc.get_first([url], os.path.join(data_dir, os.path.basename(url)), check, log)
        if p:
            return year, p
    return None, None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    data_dir = sc.writable_dir(args.data_dir, os.path.join(args.out_dir, "cache"))
    log = sc.Log(os.path.join(args.out_dir, "remote_report.txt"))
    j = lambda name: os.path.join(data_dir, name)  # noqa: E731
    log("data dir: %s" % data_dir)

    acs19, acs19_info = load_acs19(data_dir, log)
    acs23 = {}
    p23 = sc.get_first([ACS23_URL], j("acsdt5y2023-b08301.dat"), sc.is_text_table, log)
    if p23:
        with open(p23, encoding="utf-8", errors="replace") as f:
            acs23 = parse_acs23(f)
    hu_year, hu_p = first_ok(HU_URLS, data_dir, sc.is_zip, log)
    pop_year, pop_p = first_ok(POP_URLS, data_dir, sc.is_text_table, log)
    pop, names = parse_coest(read_text(pop_p)) if pop_p else ({}, {})
    hu_named = rc.xlsx_parse(hu_p, parse_hu_xlsx) if hu_p else {}
    hu = {names[k]: v for k, v in hu_named.items() if k in names}
    unmatched = sorted("%s, %s" % k for k in hu_named if k not in names)
    gz = sc.get_first([GAZ_URL], j("2020_Gaz_counties_national.zip"), sc.is_zip, log)
    land = {}
    if gz:
        with zipfile.ZipFile(gz) as zf:
            txt = [n for n in zf.namelist() if n.lower().endswith(".txt")]
            if txt:
                land = parse_gazetteer(decode(zf.read(txt[0])))
    fhfa_x = sc.get_first(sc.FHFA_URLS, j("hpi_at_county.xlsx"), sc.is_zip, log)
    hpi = rc.xlsx_parse(fhfa_x, sc.parse_fhfa_rows) if fhfa_x else {}
    delin_x = sc.get_first([rc.DELIN_URL], j("list1_2023.xlsx"), sc.is_zip, log)
    delin = rc.xlsx_parse(delin_x, rc.parse_delineation) if delin_x else {}
    permits = {}
    for y in range(2020, (hu_year or 2025) + 1):
        p = sc.get_first([sc.BPS_URL.format(year=y)], j("co%da.txt" % y), sc.is_text_table, log)
        if p:
            with open(p, encoding="latin-1") as f:
                permits[y] = sc.parse_bps_county(f.read())
    permit_years = []
    for y in range(2020, (hu_year or 2025) + 1):
        if y not in permits:
            break
        permit_years.append(y)
    ly_hpi = sc.latest_year(hpi) if hpi else None
    bsh_p = sc.get_first(sc.BSH_URLS, j("bsh_elasticities.dta"), sc.is_dta, log)
    bsh = sc.load_bsh(bsh_p, log) if bsh_p else None

    meta = {"acs2019": acs19_info, "acs2019_counties": len(acs19),
            "acs2019_counties_sums_failing": sum(1 for v in acs19.values() if not v["ok"]),
            "acs2023_counties": len(acs23), "hu_vintage": hu_year, "hu_counties_matched": len(hu),
            "hu_names_unmatched": unmatched[:40], "hu_names_unmatched_count": len(unmatched),
            "pop_vintage": pop_year, "pop_counties": len(pop), "gazetteer_counties": len(land),
            "fhfa_counties": len(hpi), "fhfa_latest_year": ly_hpi,
            "delineation_counties": len(delin), "permit_years": permit_years}
    log("meta: %s" % json.dumps(meta, default=str))
    res, hyps, extra = {}, {}, {}
    if not (bsh and bsh.get("primary_by_county")) or not acs19:
        log("missing elasticity or 2015-19 commuting data: analysis skipped")
    else:
        elas = {k: v for k, v in bsh["primary_by_county"].items() if k[:2] not in sc.DROP_STATES}
        groups, _ = sc.rank_groups(elas)
        meta.update({"elasticity_column": bsh["primary"], "elasticity_rule_tier": bsh["tier"],
                     "counties_with_elasticity": len(elas)})
        rows = build_rows(groups, acs19, acs23, hpi, hu, hu_year, pop, pop_year, permits,
                          permit_years, land, delin, price_end=2023,
                          price_latest=ly_hpi if ly_hpi and ly_hpi >= 2024 else None)
        meta.update({"rows": len(rows), "metro_rows": sum(1 for r in rows if r["metro"]),
                     "rows_by_tercile": [sum(1 for r in rows if r["grp"] == k) for k in range(K)]})
        ws = sorted(r["w19"] for r in rows)
        if ws:
            meta["w19_quartiles"] = [ws[len(ws) // 4], ws[len(ws) // 2], ws[(3 * len(ws)) // 4]]
        log("rows: %d (metro %d)" % (meta["rows"], meta["metro_rows"]))
        res = analyse(rows)
        hyps = hypotheses(res)
        extra = {"ratios": ratios(res["within_metro"]), "tight_null": tight_null(res["within_metro"])}
        rc.write_csv(os.path.join(args.out_dir, "county_remote.csv"), rows,
                     ["fips", "state", "cbsa", "metro", "grp", "workers19", "b08301_sums_ok", "w19",
                      "w23", "d_wfh", "price_19_23", "price_19_L", "hu_growth", "permits_per_1000hu",
                      "pop_growth", "log_density"])
    with open(os.path.join(args.out_dir, "remote_results.json"), "w") as f:
        json.dump({"meta": meta, "results": res, "hypotheses": hyps, "extra": extra}, f,
                  indent=1, default=str)
    write_md(os.path.join(args.out_dir, "remote_results.md"), meta, res, hyps, extra)
    log("hypotheses: %s" % json.dumps(hyps))
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
