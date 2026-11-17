# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Fetch the three shared modules from this repository at a pinned commit (0e6c10d, part 3), so
the part-4 run uses exactly the published part-1/2/3 code. Skips files that already exist."""

import os
import sys
import urllib.request

COMMIT = "0e6c10dcb241ba1e9294f4ac7c0c9e6c722efe1e"
BASE = "https://raw.githubusercontent.com/munimtechnologies/housing-supply-constraints/%s/" % COMMIT
NEEDED = {"sc_analysis.py": "def load_bsh", "reconcile.py": "def parse_delineation",
          "remote.py": "def parse_acs23"}


def main():
    for name, marker in NEEDED.items():
        if os.path.exists(name):
            print("have", name)
            continue
        with urllib.request.urlopen(BASE + name, timeout=120) as r:
            data = r.read()
        if marker.encode() not in data:
            print("unexpected content for", name)
            return 1
        with open(name, "wb") as f:
            f.write(data)
        print("fetched", name, len(data), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
