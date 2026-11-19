#!/usr/bin/env python3
# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Pipeline probe for housing-supply-constraints. It reads NO outcome data.

The seven pre-registered analysis jobs of this study (parts 1-6) have never run. Their code was
written and hand-checked without a Python interpreter. This probe checks, before they run:

1. Tests. For each part it rebuilds that job's working folder from the repository at the commit
   the job was published with (the main module, its test file and its pinned-dependency
   fetcher), runs the fetcher, then runs the part's unittest suite.
2. Data sources. For every download URL constant in those modules (names ending in _URL or
   _URLS) it records the HTTP status, content type and length, and whether the first 64 KB look
   like the format the code expects (zip/xlsx, Stata .dta, or a text table rather than HTML).
3. IRS gate (part 6). It downloads the IRS county income files for 2011, 2019 and 2022 and runs
   part 6's own pre-registered class check (class 8 = $200,000 or more), which only looks at mean
   AGI inside each income class. No price, unit, population or elasticity data are read.

Outputs in --out-dir: probe.json, probe_report.md and tests/<job>.txt.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = "munimtechnologies/housing-supply-constraints"
RAW = "https://raw.githubusercontent.com/%s/%s/%s"
HEAD = "ab1e0722ec45fcd120dddfe0a292b16c09ba9b35"
UA = "Mozilla/5.0 (compatible; MV2-housing-research/0.1; Munim, Inc.; mv2@munimtech.com)"

# job name, commit it was published with, files in its working folder, dependency fetcher,
# test module, main module
PARTS = [
    ("sc-county-v1", "60f7c3111b2ee90308ef0960d3dfae61af893703",
     ["sc_analysis.py", "test_sc_analysis.py"], None, "test_sc_analysis", "sc_analysis"),
    ("sc-reconcile-v1", "993d76ddeacf70065837faa6d6ec2d39c74b832d",
     ["sc_analysis.py", "reconcile.py", "test_reconcile.py"], None, "test_reconcile", "reconcile"),
    ("sc-remote-v1", "0e6c10dcb241ba1e9294f4ac7c0c9e6c722efe1e",
     ["remote.py", "test_remote.py", "fetch_deps.py"], "fetch_deps.py", "test_remote", "remote"),
    ("sc-bartik-v1", "fc53b0083790fb4171b493b8f7fdd6e24792ff60",
     ["bartik.py", "test_bartik.py", "fetch_deps_bartik.py"], "fetch_deps_bartik.py",
     "test_bartik", "bartik"),
    ("sc-ms-v1", "1e1d5335ec44df334d3cf846450aad1734e61f1b",
     ["ms.py", "test_ms.py", "fetch_deps_ms.py"], "fetch_deps_ms.py", "test_ms", "ms"),
    ("sc-lmw-v1", "78246a34a75518b9cc4eaf85dce188d7205c266d",
     ["lmw.py", "test_lmw.py", "fetch_deps_lmw.py"], "fetch_deps_lmw.py", "test_lmw", "lmw"),
    ("sc-ineq-v1", HEAD,
     ["ineq.py", "test_ineq.py", "fetch_deps_ineq.py"], "fetch_deps_ineq.py", "test_ineq", "ineq"),
]
IRS_YEARS = (2011, 2019, 2022)
TEMPLATE_YEAR = 2019


# ---------------------------------------------------------------- helpers (unit-tested)

def classify_head(head):
    """Format guess from the first bytes of a download."""
    if not head:
        return "empty"
    if head.startswith(b"PK"):
        return "zip"
    # Stata 13+ starts with "<stata_dta>"; older versions with a version byte 0x71-0x73 followed
    # by a byte-order byte 0x01 or 0x02 (so a text file starting with "q", "r" or "s" is text).
    if head.startswith(b"<stata_dta>") or (head[:1] in (b"\x71", b"\x72", b"\x73")
                                           and head[1:2] in (b"\x01", b"\x02")):
        return "dta"
    s = head.lstrip()
    if s.startswith(b"<"):
        return "html"
    if s.startswith(b"%PDF"):
        return "pdf"
    return "text"


def fill_template(url, year=TEMPLATE_YEAR):
    """Fills the year placeholders used in the study's URL constants: {year}, {y}, {yy} and a
    single %02d or %d (two-digit year). Other text is left alone."""
    out = url
    if "{" in out:
        out = (out.replace("{year}", str(year)).replace("{yy}", "%02d" % (year % 100))
               .replace("{y}", str(year)))
    if "%02d" in out:
        out = out.replace("%02d", "%02d" % (year % 100))
    elif "%d" in out:
        out = out.replace("%d", str(year))
    return out


def collect_urls(module):
    """{constant name: [url, ...]} for module attributes named *_URL or *_URLS. Accepts a string,
    a list of strings, or a list of (year, url) pairs."""
    found = {}
    for name in sorted(vars(module)):
        if not (name.endswith("_URL") or name.endswith("_URLS")):
            continue
        val = getattr(module, name)
        urls = []
        if isinstance(val, str):
            urls = [val]
        elif isinstance(val, (list, tuple)):
            for v in val:
                if isinstance(v, str):
                    urls.append(v)
                elif isinstance(v, (list, tuple)) and v and isinstance(v[-1], str):
                    urls.append(v[-1])
        urls = [u for u in urls if u.startswith("http")]
        if urls:
            found[name] = urls
    return found


def unittest_verdict(text):
    """'OK', 'FAILED (...)' or 'no verdict' from unittest output."""
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("OK") or line.startswith("FAILED"):
            return line
    return "no verdict"


def expected_kind(url):
    u = url.lower().split("?")[0]
    if u.endswith((".zip", ".xlsx", ".xls")):
        return "zip"
    if u.endswith(".dta") or "drive" in url.lower():
        return "dta"
    return "text"


# ---------------------------------------------------------------- network

def get(url, dest=None, limit=65536, timeout=180):
    """GET with the project's User-Agent. With dest, saves the whole body; else reads at most
    `limit` bytes. -> dict(status, type, length, head, error, bytes)."""
    rec = {"url": url}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rec["status"] = r.status
            rec["type"] = r.headers.get("Content-Type")
            rec["length"] = r.headers.get("Content-Length")
            rec["final_url"] = r.geturl()
            if dest:
                tmp = dest + ".part"
                n = 0
                head = b""
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        if len(head) < 64:
                            head += chunk[:64]
                        f.write(chunk)
                        n += len(chunk)
                os.replace(tmp, dest)
                rec["bytes"] = n
            else:
                head = r.read(limit)
                rec["bytes_read"] = len(head)
            rec["head"] = head[:64]
    except Exception as e:  # network or HTTP error
        rec["error"] = repr(e)[:300]
    return rec


def fetch_part_files(sha, files, folder, log):
    """Downloads `files` at commit `sha` (falls back to HEAD). -> commit actually used or None."""
    for ref in (sha, HEAD):
        ok = True
        for name in files:
            rec = get(RAW % (REPO, ref, name), dest=os.path.join(folder, name), timeout=120)
            if "error" in rec:
                log("  %s @ %s: %s" % (name, ref[:7], rec["error"]))
                ok = False
                break
        if ok:
            return ref
    return None


def run(cmd, cwd, timeout):
    t = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or ""), time.time() - t
    except subprocess.TimeoutExpired as e:
        return "timeout", str(e), time.time() - t


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--skip-irs", action="store_true")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    os.makedirs(os.path.join(args.out_dir, "tests"), exist_ok=True)
    os.makedirs(args.data_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="probe-work-")
    lines = []

    def log(msg):
        print(msg, flush=True)
        lines.append(msg)

    result = {"head": HEAD, "python": sys.version.split()[0], "parts": {}, "urls": {}, "irs": {}}

    # 1. tests, each part in its own rebuilt working folder
    for job, sha, files, fetcher, test_mod, main_mod in PARTS:
        folder = os.path.join(work, job)
        os.makedirs(folder)
        rec = {"commit_wanted": sha[:7]}
        ref = fetch_part_files(sha, files, folder, log)
        rec["commit_used"] = ref[:7] if ref else None
        if not ref:
            rec["verdict"] = "files not fetched"
            result["parts"][job] = rec
            log("%s: files not fetched" % job)
            continue
        out_txt = ""
        if fetcher:
            code, text, secs = run([sys.executable, fetcher], folder, 300)
            rec["deps"] = {"exit": code, "seconds": round(secs, 1), "tail": text[-400:]}
            out_txt += "== %s\n%s\n" % (fetcher, text)
        code, text, secs = run([sys.executable, "-m", "unittest", "-v", test_mod], folder, 900)
        out_txt += "== unittest %s\n%s\n" % (test_mod, text)
        rec.update({"exit": code, "seconds": round(secs, 1), "verdict": unittest_verdict(text)})
        with open(os.path.join(args.out_dir, "tests", job + ".txt"), "w", encoding="utf-8") as f:
            f.write(out_txt)
        result["parts"][job] = rec
        log("%s @ %s: tests %s (%.0fs)" % (job, rec["commit_used"], rec["verdict"], secs))

    # 2. data URLs: import each part's main module from its folder and collect the constants
    seen = {}
    for job, sha, files, fetcher, test_mod, main_mod in PARTS:
        folder = os.path.join(work, job)
        if not os.path.exists(os.path.join(folder, main_mod + ".py")):
            continue
        here = os.path.dirname(os.path.abspath(__file__))
        snippet = ("import json, sys; sys.path.insert(0, '.'); import %s as m; "
                   "sys.path.insert(0, %r); import probe as p; "
                   "print('URLS ' + json.dumps(p.collect_urls(m)))" % (main_mod, here))
        code, text, _ = run([sys.executable, "-c", snippet], folder, 120)
        try:
            line = [ln for ln in text.splitlines() if ln.startswith("URLS ")][-1]
            consts = json.loads(line[5:])
        except Exception:
            log("%s: could not import %s: %s" % (job, main_mod, text[-300:]))
            continue
        for name, urls in consts.items():
            for u in urls:
                seen.setdefault(u, set()).add("%s.%s" % (main_mod, name))
    for template in sorted(seen):
        url = fill_template(template)
        rec = get(url)
        head = rec.pop("head", b"")
        rec["kind"] = classify_head(head) if "error" not in rec else "error"
        rec["expected"] = expected_kind(url)
        rec["ok"] = rec["kind"] == rec["expected"]
        rec["used_by"] = sorted(seen[template])
        rec["template"] = template
        rec["head_hex"] = head[:16].hex()
        result["urls"][url] = rec
        log("url %s: %s %s kind=%s expected=%s%s" % (
            url, rec.get("status"), rec.get("type"), rec["kind"], rec["expected"],
            " ERROR " + rec["error"] if "error" in rec else ""))

    # 3. IRS gate for part 6 (class means only)
    if not args.skip_irs:
        folder = os.path.join(work, "sc-ineq-v1")
        sys.path.insert(0, folder)
        try:
            import ineq  # noqa: E402  (fetched above with its pinned dependencies)
            for y in IRS_YEARS:
                # part 6's own download path (project User-Agent, then a plain browser one)
                dest = ineq.get_irs(y, args.data_dir, log)
                rec = {"url": ineq.IRS_URL % (y % 100), "path": dest}
                if dest:
                    rec["bytes"] = os.path.getsize(dest)
                    with open(dest, "rb") as f:
                        rec["kind"] = classify_head(f.read(64))
                else:
                    rec["kind"] = "not downloaded"
                if rec["kind"] == "text":
                    with open(dest, "rb") as f:
                        raw = f.read()
                    try:
                        text = raw.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        text = raw.decode("latin-1")
                    rec["header"] = text.splitlines()[0][:300] if text else ""
                    parsed = ineq.parse_irs(text)
                    chk = ineq.check_classes(parsed)
                    rec["class_check"] = chk
                    rec["classes_ok"] = ineq.classes_ok(chk)
                    rec["has_class_0"] = sum(1 for v in parsed.values() if 0 in v)
                result["irs"][str(y)] = rec
                log("IRS %d: %s" % (y, json.dumps(rec, default=str)[:600]))
        except Exception as e:  # report, do not hide
            result["irs"]["error"] = repr(e)[:500]
            log("IRS gate error: %r" % e)

    with open(os.path.join(args.out_dir, "probe.json"), "w") as f:
        json.dump(result, f, indent=1, default=str)
    md = ["# housing-supply-constraints pipeline probe (sc-probe-v1)", "",
          "Made with AI agents working in the name of MV2 of Munim, Inc. No outcome data read.", "",
          "## Tests per job", "", "| job | commit | deps | tests |", "|---|---|---|---|"]
    for job, rec in result["parts"].items():
        md.append("| %s | %s | %s | %s |" % (job, rec.get("commit_used"),
                                            (rec.get("deps") or {}).get("exit", "-"),
                                            rec.get("verdict")))
    md += ["", "## Data URLs", "", "| url | status | kind | expected | used by |",
           "|---|---|---|---|---|"]
    for url, rec in result["urls"].items():
        md.append("| %s | %s | %s | %s | %s |" % (url, rec.get("status", rec.get("error", "")),
                                                 rec["kind"], rec["expected"],
                                                 ", ".join(rec["used_by"])))
    md += ["", "## IRS class gate (part 6)", ""]
    for y, rec in result["irs"].items():
        md.append("- %s: %s" % (y, json.dumps(rec, default=str)[:800]))
    md += ["", "## Log", ""] + ["    " + ln for ln in lines]
    with open(os.path.join(args.out_dir, "probe_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
