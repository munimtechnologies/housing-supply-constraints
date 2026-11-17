#!/usr/bin/env python3
# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Do supply constraints explain county house-price and quantity growth?

An open, pre-registered county-level test of the claim in Louie, Mondragon and Wieland
(2025, NBER w33576) that local income growth predicts the same growth in house prices
and housing quantity whatever the local housing supply elasticity.

Public inputs only (downloaded at run time, nothing private):
  - FHFA annual county house price indexes (hpi_at_county.xlsx)
  - BEA CAINC1 county personal income, population and per-capita income
  - Census Building Permits Survey annual county files (co<year>a.txt)
  - Baum-Snow and Han (2024, JPE) tract-level housing supply elasticities (.dta)

See PREREGISTRATION.md for the fixed specification and predictions.
"""

import argparse
import csv
import io
import json
import math
import os
import sys
import urllib.request
import zipfile

import numpy as np

UA = "Mozilla/5.0 (compatible; MV2-housing-research/0.1; Munim, Inc.; mv2@munimtech.com)"

BPS_URL = "https://www2.census.gov/econ/bps/County/co{year}a.txt"
FHFA_URLS = [
    "https://www.fhfa.gov/hpi/download/annual/hpi_at_county.xlsx",
    "https://www.fhfa.gov/hpi/download/annually/hpi_at_bdl_county.xlsx",
]
BEA_URLS = ["https://apps.bea.gov/regional/zip/CAINC1.zip"]
BSH_ID = "1Qn3PZ0u8PO2IbyyPETCrca3rGmPyTVL7"
BSH_URLS = [
    "https://drive.usercontent.google.com/download?id=%s&export=download&confirm=t" % BSH_ID,
    "https://drive.google.com/uc?export=download&id=%s" % BSH_ID,
]
# Connecticut's counties were replaced by planning regions in 2022, so its series break.
DROP_STATES = {"09"}

STATE_KEYS = ("statefp", "state", "stfips", "statefips", "st", "fips_state", "state_fips")
COUNTY_KEYS = ("countyfp", "county", "cntyfips", "cofips", "countyfips", "cty",
               "fips_county", "county_fips", "cnty")


# ---------------------------------------------------------------- downloads

def fetch(url, dest, timeout=180):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    return dest


def get_first(urls, dest, check, log):
    for url in urls:
        try:
            fetch(url, dest)
            with open(dest, "rb") as f:
                head = f.read(64)
            if check(head):
                log("ok %s -> %s (%d bytes)" % (url, os.path.basename(dest), os.path.getsize(dest)))
                return dest
            log("bad content from %s: %r" % (url, head[:40]))
            os.remove(dest)
        except Exception as e:  # network or HTTP error: try the next URL
            log("failed %s: %r" % (url, e))
            if os.path.exists(dest):
                os.remove(dest)
    return None


def is_zip(head):
    return head.startswith(b"PK")


def is_dta(head):
    return head.startswith(b"<stata_dta>") or head[:1] in (b"\x71", b"\x72", b"\x73")


def is_text_table(head):
    return not head.lstrip().startswith(b"<")


def writable_dir(preferred, fallback):
    for d in (preferred, fallback):
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".probe")
            with open(probe, "w") as f:
                f.write("x")
            os.remove(probe)
            return d
        except OSError:
            continue
    raise SystemExit("no writable data directory")


# ---------------------------------------------------------------- parsers

def _num(s):
    s = (s or "").strip().strip('"').replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_bps_county(text):
    """BPS annual county file -> {5-digit FIPS: total units permitted (estimates)}.
    Columns: survey date, state FIPS, county FIPS, region, division, name, then
    buildings/units/value for 1, 2, 3-4 and 5+ unit structures."""
    out = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 18 or not parts[0].isdigit() or len(parts[0]) not in (4, 6):
            continue
        try:
            nums = [int(float(p or 0)) for p in parts[6:18]]
        except ValueError:
            continue
        fips = parts[1].zfill(2) + parts[2].zfill(3)
        out[fips] = nums[1] + nums[4] + nums[7] + nums[10]
    return out


def parse_bea_cainc1(text):
    """BEA CAINC1 CSV -> {fips: {"pi": {year: thousands of $}, "pop": {...}, "pci": {...}}}.
    LineCode 1 = personal income, 2 = population, 3 = per-capita personal income."""
    out = {}
    header = years = None
    i_line = None
    for row in csv.reader(io.StringIO(text), skipinitialspace=True):
        if not row:
            continue
        first = row[0].lstrip(chr(0xFEFF)).strip().strip('"')
        if header is None:
            if first == "GeoFIPS":
                header = [h.lstrip(chr(0xFEFF)).strip().strip('"') for h in row]
                years = [(i, int(h)) for i, h in enumerate(header) if h.isdigit()]
                if "LineCode" not in header:
                    return out
                i_line = header.index("LineCode")
            continue
        if len(row) < len(header):
            continue
        fips = first.strip()
        if len(fips) != 5 or not fips.isdigit() or fips.endswith("000"):
            continue
        try:
            line = int(row[i_line].strip())
        except ValueError:
            continue
        key = {1: "pi", 2: "pop", 3: "pci"}.get(line)
        if key is None:
            continue
        rec = out.setdefault(fips, {"pi": {}, "pop": {}, "pci": {}})
        for i, y in years:
            v = _num(row[i])
            if v is not None:
                rec[key][y] = v
    return out


def parse_fhfa_rows(rows):
    """FHFA county HPI sheet rows -> {fips: {year: hpi}}. Finds the header row itself."""
    out = {}
    idx = None
    for row in rows:
        cells = ["" if c is None else str(c).strip() for c in row]
        low = [c.lower() for c in cells]
        if idx is None:
            if any("fips" in c for c in low) and "year" in low and any(c.startswith("hpi") for c in low):
                i_f = next(i for i, c in enumerate(low) if "fips" in c)
                i_h = low.index("hpi") if "hpi" in low else next(i for i, c in enumerate(low) if c.startswith("hpi"))
                idx = (i_f, low.index("year"), i_h)
            continue
        i_f, i_y, i_h = idx
        if len(cells) <= max(idx):
            continue
        f = cells[i_f]
        if f.endswith(".0"):
            f = f[:-2]
        if not f.isdigit():
            continue
        try:
            y = int(float(cells[i_y]))
            h = float(cells[i_h])
        except ValueError:
            continue
        out.setdefault(f.zfill(5), {})[y] = h
    return out


def _digits(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        if v.is_integer():
            v = int(v)
    s = str(v).strip()
    return s if s.isdigit() else ""


def county_codes(columns):
    """columns: {name: list of values} -> (list of 5-digit county FIPS or "", how)."""
    low = {name.lower(): name for name in columns}
    st = next((low[k] for k in STATE_KEYS if k in low), None)
    co = next((low[k] for k in COUNTY_KEYS if k in low), None)
    if st and co:
        out = []
        for a, b in zip(columns[st], columns[co]):
            a, b = _digits(a), _digits(b)
            if len(b) == 5:
                out.append(b)
            elif a and b and len(a) <= 2 and len(b) <= 3:
                out.append(a.zfill(2) + b.zfill(3))
            else:
                out.append("")
        if out and sum(1 for c in out if c) >= 0.5 * len(out):
            return out, "state=%s county=%s" % (st, co)
    named = ("tract", "geoid", "fips", "ctid", "gisjoin")
    tract_cols = []
    for name, vals in columns.items():
        codes = [_digits(v) for v in vals]
        good = sum(1 for c in codes if len(c) in (10, 11))
        if vals and good >= 0.95 * len(vals):
            tract_cols.append((not any(k in name.lower() for k in named), name, codes))
    if tract_cols:
        tract_cols.sort(key=lambda t: t[0])
        _, name, codes = tract_cols[0]
        return [c.zfill(11)[:5] if len(c) in (10, 11) else "" for c in codes], "tract=%s" % name
    for name, vals in columns.items():
        if not any(k in name.lower() for k in ("county", "cnty", "fips")):
            continue
        codes = [_digits(v) for v in vals]
        if vals and sum(1 for c in codes if len(c) in (4, 5)) >= 0.95 * len(vals):
            return [c.zfill(5) if len(c) in (4, 5) else "" for c in codes], "county5=%s" % name
    return None, "no county or tract identifier found"


def _is_err(name, label):
    n, t = name.lower(), (label or "").lower()
    return (n.endswith("_se") or "_se_" in n or n.startswith("se_") or "stderr" in n
            or any(k in t for k in ("std. err", "stderr", "standard error", "s.e.", "std err")))


PRIMARY_TIERS = [
    lambda t: "unit" in t and ("fmm" in t or "mixture" in t) and "quad" in t,
    lambda t: "unit" in t and ("fmm" in t or "mixture" in t),
    lambda t: "unit" in t,
]


def _sq(t):
    return any(k in t for k in ("sqft", "square", "sq ft", "footage", "space", "servic"))


SECONDARY_TIERS = [
    lambda t: _sq(t) and ("fmm" in t or "mixture" in t) and "quad" in t,
    lambda t: _sq(t) and ("fmm" in t or "mixture" in t),
    lambda t: _sq(t),
]


def pick_elasticity(names, labels, numeric):
    """Pre-registered rule. Returns (primary, primary_tier, secondary, candidates)."""
    def text(n):
        return (n + " " + (labels.get(n) or "")).lower()
    cands = [n for n in names if n in numeric and not _is_err(n, labels.get(n))
             and any(k in text(n) for k in ("elast", "gamma", "fmm"))]
    flag = ""
    if not cands:
        cands = [n for n in names if n in numeric]
        flag = "fallback-all-numeric"
    primary, tier = None, None
    for ti, rule in enumerate(PRIMARY_TIERS):
        hit = [n for n in cands if rule(text(n))]
        if hit:
            primary, tier = hit[0], "units-tier-%d" % (ti + 1)
            break
    if primary is None and cands:
        primary, tier = cands[0], "fallback-first-candidate"
    secondary = None
    for rule in SECONDARY_TIERS:
        hit = [n for n in cands if rule(text(n)) and n != primary]
        if hit:
            secondary = hit[0]
            break
    return primary, (tier + (" " + flag if flag else "")) if tier else flag, secondary, cands


# ---------------------------------------------------------------- statistics

def wls(y, X, w=None, groups=None):
    """Weighted least squares with HC1 and cluster-robust (CR1) covariance."""
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    n, k = X.shape
    sw = np.ones(n) if w is None else np.sqrt(np.asarray(w, float))
    Xs = X * sw[:, None]
    ys = y * sw
    XtX_inv = np.linalg.pinv(Xs.T @ Xs)
    beta = XtX_inv @ (Xs.T @ ys)
    u = ys - Xs @ beta
    Xu = Xs * u[:, None]
    V_hc1 = XtX_inv @ (Xu.T @ Xu) @ XtX_inv * (n / (n - k))
    V_cl = None
    if groups is not None:
        sums = {}
        for i, g in enumerate(groups):
            sums[g] = sums.get(g, 0) + Xu[i]
        S = np.stack(list(sums.values()))
        G = S.shape[0]
        V_cl = XtX_inv @ (S.T @ S) @ XtX_inv * (G / (G - 1)) * ((n - 1) / (n - k))
    return beta, V_hc1, V_cl


def rank_groups(values, K=3):
    """{key: value} -> ({key: group 0..K-1 by rank, 0 = lowest}, {key: centred percentile})."""
    order = sorted(values, key=lambda k: (values[k], k))
    n = len(order)
    groups, pct = {}, {}
    for r, key in enumerate(order):
        groups[key] = (K * r) // n
        pct[key] = (r + 0.5) / n - 0.5
    return groups, pct


def pval(z):
    return math.erfc(abs(z) / math.sqrt(2))


def contrast(beta, V, c):
    c = np.asarray(c, float)
    est = float(c @ beta)
    se = float(math.sqrt(max(c @ V @ c, 0.0)))
    z = est / se if se > 0 else float("nan")
    return {"est": est, "se": se, "z": z, "p": pval(z) if se > 0 else float("nan")}


def group_slopes(rows, ycol, gcol, K=3, weighted=True, state_fe=False):
    """y = sum_k a_k D_k + sum_k b_k D_k g (+ state dummies). Clustered by state."""
    states = sorted({r["fips"][:2] for r in rows})
    X, y, w, cl = [], [], [], []
    for r in rows:
        d = [1.0 if r["grp"] == k else 0.0 for k in range(K)]
        x = d + [dk * r[gcol] for dk in d]
        if state_fe:
            x += [1.0 if r["fips"][:2] == s else 0.0 for s in states[1:]]
        X.append(x)
        y.append(r[ycol])
        w.append(r["w"] if weighted else 1.0)
        cl.append(r["fips"][:2])
    beta, V_hc1, V_cl = wls(y, X, w, cl)
    V = V_cl if V_cl is not None else V_hc1
    p = len(X[0])
    gbar = sum(r[gcol] * (r["w"] if weighted else 1.0) for r in rows) / sum(r["w"] if weighted else 1.0 for r in rows)

    def e(i):
        v = [0.0] * p
        v[i] = 1.0
        return v
    res = {"n": len(rows), "n_states": len(states), "gbar": gbar, "slopes": [], "slopes_hc1_se": []}
    for k in range(K):
        res["slopes"].append(contrast(beta, V, e(K + k)))
        res["slopes_hc1_se"].append(contrast(beta, V_hc1, e(K + k))["se"])
        res.setdefault("n_by_group", []).append(sum(1 for r in rows if r["grp"] == k))
    c = [0.0] * p
    c[K] = 1.0
    c[K + K - 1] = -1.0
    res["slope_low_minus_high"] = contrast(beta, V, c)
    res["slope_low_minus_high_hc1"] = contrast(beta, V_hc1, c)
    if not state_fe:
        c2 = [0.0] * p
        c2[0], c2[K - 1] = 1.0, -1.0
        c2[K], c2[2 * K - 1] = gbar, -gbar
        res["level_low_minus_high_at_gbar"] = contrast(beta, V, c2)
    return res


def continuous(rows, ycol, gcol, weighted=True):
    """y = a + b g + c z + d g z, z = centred elasticity percentile (-0.5 .. 0.5)."""
    X = [[1.0, r[gcol], r["z"], r[gcol] * r["z"]] for r in rows]
    y = [r[ycol] for r in rows]
    w = [r["w"] if weighted else 1.0 for r in rows]
    cl = [r["fips"][:2] for r in rows]
    beta, V_hc1, V_cl = wls(y, X, w, cl)
    return {"n": len(rows), "b_income": contrast(beta, V_cl, [0, 1, 0, 0]),
            "c_elasticity": contrast(beta, V_cl, [0, 0, 1, 0]),
            "d_interaction": contrast(beta, V_cl, [0, 0, 0, 1])}


# ---------------------------------------------------------------- assembly

def build_rows(start, end, bea, fhfa, permits, groups, pct):
    rows = []
    years = list(range(start + 1, end + 1))
    have_permits = all(y in permits for y in years)
    for fips, rec in bea.items():
        if fips[:2] in DROP_STATES or fips not in groups:
            continue
        pi, pop, pci = rec["pi"], rec["pop"], rec["pci"]
        try:
            if min(pi[start], pi[end], pop[start], pop[end], pci[start], pci[end]) <= 0:
                continue
        except KeyError:
            continue
        r = {"fips": fips, "grp": groups[fips], "z": pct[fips], "w": pop[start],
             "pop_start": pop[start],
             "g_inc": math.log(pi[end] / pi[start]),
             "g_pci": math.log(pci[end] / pci[start]),
             "pop_growth": math.log(pop[end] / pop[start])}
        h = fhfa.get(fips, {})
        r["price_growth"] = (math.log(h[end] / h[start])
                             if h.get(start, 0) > 0 and h.get(end, 0) > 0 else None)
        if have_permits and all(fips in permits[y] for y in years):
            r["permits_per_1000"] = 1000.0 * sum(permits[y][fips] for y in years) / pop[start]
        else:
            r["permits_per_1000"] = None
        rows.append(r)
    return rows


def latest_year(series_by_fips, min_count=1000):
    counts = {}
    for d in series_by_fips.values():
        for y in d:
            counts[y] = counts.get(y, 0) + 1
    ok = [y for y, c in counts.items() if c >= min_count]
    return max(ok) if ok else None


OUTCOMES = ["price_growth", "permits_per_1000", "pop_growth"]
SPECS = [
    ("primary", "g_inc", True, False, 0),
    ("unweighted", "g_inc", False, False, 0),
    ("state_fe", "g_inc", True, True, 0),
    ("per_capita_income", "g_pci", True, False, 0),
    ("pop_10k_plus", "g_inc", True, False, 10000),
]


def analyse(rows):
    out = {}
    for name, gcol, weighted, fe, min_pop in SPECS:
        out[name] = {}
        for y in OUTCOMES:
            sub = [r for r in rows if r[y] is not None and r["pop_start"] >= min_pop
                   and math.isfinite(r[y]) and math.isfinite(r[gcol])]
            if len(sub) < 60:
                out[name][y] = {"n": len(sub), "skipped": "too few counties"}
                continue
            res = group_slopes(sub, y, gcol, weighted=weighted, state_fe=fe)
            if name == "primary":
                res["continuous"] = continuous(sub, y, gcol, weighted=weighted)
            out[name][y] = res
    return out


def verdict(res, period, spec, outcome, key, sign):
    try:
        c = res[period][spec][outcome][key]
    except (KeyError, TypeError):
        return {"status": "not evaluable"}
    est = sign * c["est"]
    held = est > 0 and c["p"] < 0.05
    return {"status": "supported" if held else "not supported", "est": c["est"], "se": c["se"], "p": c["p"]}


def fmt(c):
    if c is None:
        return "n/a"
    return "%.3f (%.3f)" % (c["est"], c["se"])


def write_markdown(path, meta, results, hyps):
    L = ["# Supply constraints and county growth: results (sc-county-v1)", "",
         "Made with AI agents working in the name of MV2 of Munim, Inc. Pre-registered in PREREGISTRATION.md.", "",
         "## Inputs", ""]
    for k, v in meta.items():
        L.append("- %s: %s" % (k, json.dumps(v) if not isinstance(v, str) else v))
    L += ["", "Tercile 0 = lowest Baum-Snow-Han supply elasticity (most constrained), 2 = highest.",
          "Slopes are on log growth of total personal income (or per-capita income where named). "
          "Standard errors (in brackets) are clustered by state.", ""]
    for period, res in results.items():
        L += ["## %s" % period, ""]
        for spec, block in res.items():
            L += ["### %s" % spec, "",
                  "| outcome | n | slope low | slope mid | slope high | low minus high (p) | level gap at mean growth (p) |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
            for y, r in block.items():
                if "slopes" not in r:
                    L.append("| %s | %s | skipped | | | | |" % (y, r.get("n")))
                    continue
                d = r["slope_low_minus_high"]
                lv = r.get("level_low_minus_high_at_gbar")
                L.append("| %s | %d | %s | %s | %s | %s p=%.3g | %s |" % (
                    y, r["n"], fmt(r["slopes"][0]), fmt(r["slopes"][1]), fmt(r["slopes"][2]),
                    fmt(d), d["p"], (fmt(lv) + " p=%.3g" % lv["p"]) if lv else "n/a"))
            L.append("")
            if spec == "primary":
                for y, r in block.items():
                    if "continuous" in r:
                        c = r["continuous"]["d_interaction"]
                        L.append("- %s: income x elasticity-percentile interaction %s p=%.3g" % (y, fmt(c), c["p"]))
                L.append("")
    L += ["## Pre-registered hypotheses", ""]
    for k, v in hyps.items():
        L.append("- %s: %s" % (k, json.dumps(v)))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


class Log:
    def __init__(self, path):
        self.path = path
        open(path, "w").close()

    def __call__(self, msg):
        print(msg, flush=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(str(msg) + "\n")


def load_bsh(path, log):
    import pandas as pd
    with pd.read_stata(path, iterator=True, convert_categoricals=False) as rdr:
        df = rdr.read()
        labels = rdr.variable_labels()
    log("BSH file: %d rows x %d columns" % df.shape)
    for c in df.columns:
        log("  column %-28s %-10s %s" % (c, str(df[c].dtype), labels.get(c, "")))
    log("BSH head:\n" + df.head(5).to_string())
    numeric = {c for c in df.columns if str(df[c].dtype).startswith(("float", "int"))}
    columns = {c: df[c].tolist() for c in df.columns}
    codes, how = county_codes(columns)
    log("county id: %s" % how)
    if codes is None:
        return None
    id_like = set()
    for c in df.columns:
        lc = c.lower()
        if (any(k in lc for k in ("tract", "geoid", "fips", "cbsa", "gisjoin"))
                or lc in STATE_KEYS or lc in COUNTY_KEYS or lc in ("year", "id", "msa", "cz")):
            id_like.add(c)
    primary, tier, secondary, cands = pick_elasticity(list(df.columns), labels, numeric - id_like)
    log("elasticity candidates: %s" % cands)
    log("primary: %s [%s]; secondary: %s" % (primary, tier, secondary))
    result = {"how": how, "primary": primary, "tier": tier, "secondary": secondary,
              "candidates": cands, "labels": {c: labels.get(c, "") for c in cands}}
    for role, col in (("primary", primary), ("secondary", secondary)):
        if col is None:
            continue
        acc = {}
        for code, v in zip(codes, columns[col]):
            if code and v is not None and isinstance(v, (int, float)) and math.isfinite(v):
                acc.setdefault(code, []).append(float(v))
        result[role + "_by_county"] = {k: sum(v) / len(v) for k, v in acc.items()}
        result[role + "_tracts"] = {k: len(v) for k, v in acc.items()}
        vals = sorted(result[role + "_by_county"].values())
        if vals:
            log("%s county means: n=%d min=%.4g median=%.4g max=%.4g" % (
                role, len(vals), vals[0], vals[len(vals) // 2], vals[-1]))
    # correlations among candidates at county level, for the record
    return result


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    data_dir = writable_dir(args.data_dir, os.path.join(args.out_dir, "cache"))
    log = Log(os.path.join(args.out_dir, "data_report.txt"))
    log("data dir: %s" % data_dir)

    bea_zip = get_first(BEA_URLS, os.path.join(data_dir, "CAINC1.zip"), is_zip, log)
    fhfa_x = get_first(FHFA_URLS, os.path.join(data_dir, "hpi_at_county.xlsx"), is_zip, log)
    bsh_p = get_first(BSH_URLS, os.path.join(data_dir, "bsh_elasticities.dta"), is_dta, log)

    bea = {}
    if bea_zip:
        with zipfile.ZipFile(bea_zip) as zf:
            names = zf.namelist()
            log("CAINC1 zip members: %s" % names[:12])
            pick = [n for n in names if "ALL_AREAS" in n and n.lower().endswith(".csv")]
            if pick:
                bea = parse_bea_cainc1(zf.read(pick[0]).decode("latin-1"))
    log("BEA counties: %d; latest year with 1000+ counties: %s" % (
        len(bea), latest_year({f: r["pi"] for f, r in bea.items()})))

    fhfa = {}
    if fhfa_x:
        import openpyxl
        wb = openpyxl.load_workbook(fhfa_x, read_only=True, data_only=True)
        for ws in wb.worksheets:
            fhfa = parse_fhfa_rows(ws.iter_rows(values_only=True))
            if fhfa:
                break
    log("FHFA counties: %d; latest year with 1000+ counties: %s" % (len(fhfa), latest_year(fhfa)))

    bsh = load_bsh(bsh_p, log) if bsh_p else None

    L = None
    ly_bea = latest_year({f: r["pi"] for f, r in bea.items()}) if bea else None
    ly_fhfa = latest_year(fhfa) if fhfa else None
    if ly_bea and ly_fhfa:
        L = min(ly_bea, ly_fhfa)
    periods = [("P1_2010_2019", 2010, 2019)]
    if L and L >= 2022:
        periods.append(("P2_2019_%d" % L, 2019, L))
    periods.append(("P0_2000_2019", 2000, 2019))

    permits = {}
    years_needed = sorted({y for _, s, e in periods for y in range(s + 1, e + 1)})
    for y in years_needed:
        p = get_first([BPS_URL.format(year=y)], os.path.join(data_dir, "co%da.txt" % y), is_text_table, log)
        if p:
            with open(p, encoding="latin-1") as f:
                permits[y] = parse_bps_county(f.read())
    log("BPS years loaded: %s" % sorted(permits))

    meta = {"latest_common_year": L, "bea_counties": len(bea), "fhfa_counties": len(fhfa),
            "bps_years": sorted(permits)}
    results, panel = {}, []
    if bsh and bsh.get("primary_by_county"):
        elas = {k: v for k, v in bsh["primary_by_county"].items() if k[:2] not in DROP_STATES}
        groups, pct = rank_groups(elas)
        cut = sorted(elas.values())
        n = len(cut)
        meta.update({"elasticity_column": bsh["primary"], "elasticity_rule_tier": bsh["tier"],
                     "elasticity_label": bsh["labels"].get(bsh["primary"], ""),
                     "secondary_column": bsh["secondary"], "county_id": bsh["how"],
                     "counties_with_elasticity": n,
                     "tercile_cutoffs": [cut[n // 3], cut[(2 * n) // 3]] if n >= 3 else None})
        for name, s, e in periods:
            rows = build_rows(s, e, bea, fhfa, permits, groups, pct)
            log("%s: %d counties with income and elasticity" % (name, len(rows)))
            results[name] = analyse(rows)
            for r in rows:
                panel.append(dict(r, period=name, elasticity=elas[r["fips"]]))
        if bsh.get("secondary_by_county"):
            elas2 = {k: v for k, v in bsh["secondary_by_county"].items() if k[:2] not in DROP_STATES}
            g2, p2 = rank_groups(elas2)
            for name, s, e in periods[:2]:
                rows = build_rows(s, e, bea, fhfa, permits, g2, p2)
                results[name + "_secondary_elasticity"] = {"primary": analyse(rows)["primary"]}
    else:
        log("no elasticity data: analysis skipped")

    P2 = periods[1][0] if len(periods) > 2 else None
    hyps = {
        "H1 P1 price slope low>high": verdict(results, "P1_2010_2019", "primary", "price_growth", "slope_low_minus_high", +1),
        "H2 P1 permits slope high>low": verdict(results, "P1_2010_2019", "primary", "permits_per_1000", "slope_low_minus_high", -1),
        "H3 P2 price slope low>high": verdict(results, P2, "primary", "price_growth", "slope_low_minus_high", +1) if P2 else {"status": "not evaluable"},
        "H4 P1 per-capita price slope low>high": verdict(results, "P1_2010_2019", "per_capita_income", "price_growth", "slope_low_minus_high", +1),
        "H5 P1 price level low>high at mean income growth": verdict(results, "P1_2010_2019", "primary", "price_growth", "level_low_minus_high_at_gbar", +1),
    }
    with open(os.path.join(args.out_dir, "results.json"), "w") as f:
        json.dump({"meta": meta, "results": results, "hypotheses": hyps}, f, indent=1, default=str)
    write_markdown(os.path.join(args.out_dir, "results.md"), meta, results, hyps)
    if panel:
        keys = ["period", "fips", "grp", "elasticity", "z", "pop_start", "g_inc", "g_pci",
                "price_growth", "permits_per_1000", "pop_growth"]
        with open(os.path.join(args.out_dir, "county_panel.csv"), "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            wr.writeheader()
            for r in panel:
                wr.writerow(r)
    log("hypotheses: %s" % json.dumps(hyps))
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
