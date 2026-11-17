# Copyright 2026 Munim, Inc. Licensed under the Apache License, Version 2.0 (Apache-2.0).
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Fetch the two shared modules from this repository at a pinned commit (993d76d), so the
part-3 run uses exactly the published part-1/part-2 code. Skips files that already exist."""

import os
import sys
import urllib.request

COMMIT = "993d76ddeacf70065837faa6d6ec2d39c74b832d"
BASE = "https://raw.githubusercontent.com/munimtechnologies/housing-supply-constraints/%s/" % COMMIT
NEEDED = {"sc_analysis.py": "def load_bsh", "reconcile.py": "def parse_delineation"}


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
