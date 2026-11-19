# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Fetch the modules part 6 builds on from this repository at pinned commits, so it uses exactly
the published code: ms.py from the part-5 commit (1e1d533), and sc_analysis.py and reconcile.py
from the part-3 commit (0e6c10d) that part 5 itself pins. Skips files that already exist."""

import os
import sys
import urllib.request

REPO = "https://raw.githubusercontent.com/munimtechnologies/housing-supply-constraints/%s/%s"
PART5 = "1e1d5335ec44df334d3cf846450aad1734e61f1b"
PART3 = "0e6c10dcb241ba1e9294f4ac7c0c9e6c722efe1e"
NEEDED = [("ms.py", PART5, "def metro_lhpi"),
          ("sc_analysis.py", PART3, "def load_bsh"),
          ("reconcile.py", PART3, "def parse_delineation")]


def main():
    for name, commit, marker in NEEDED:
        if os.path.exists(name):
            print("have", name)
            continue
        with urllib.request.urlopen(REPO % (commit, name), timeout=120) as r:
            data = r.read()
        if marker.encode() not in data:
            print("unexpected content for", name)
            return 1
        with open(name, "wb") as f:
            f.write(data)
        print("fetched", name, "@", commit[:7], len(data), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
