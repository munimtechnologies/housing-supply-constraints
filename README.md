# housing-supply-constraints

Do housing supply constraints explain where U.S. house prices and housing quantity grew?

This is an open, **pre-registered**, county-level test of a contested claim. Louie, Mondragon
and Wieland (2025, NBER w33576) report that across U.S. metro areas from 2000 to 2020, income
growth predicts the same growth in house prices, housing quantity and population whatever the
local housing supply elasticity. If true, it challenges the standard view that hard-to-build
places turn demand into higher prices rather than more homes. In October 2026, Murphy and
Shaheen (Dallas Fed WP 2635) answered that supply constraints *do* explain permits and prices,
using annual metro data with fixed effects.

All inputs are public:

- FHFA county and metro house price indexes
- BEA county and metro personal income and population
- Census Building Permits Survey county permits
- Census County Business Patterns county employment by industry (2010, 2019)
- Census county housing-unit counts (2000, 2010, 2020) and estimates (2010-2025)
- Census American Community Survey commuting table B08301 (2015-2019 and 2019-2023)
- OMB 2023 metro delineations and the 2020 Census Gazetteer
- Baum-Snow and Han (2024, JPE) tract-level supply elasticities

## Part 1: counties (sc-county-v1)

The same question is asked of about 3,000 counties, for 2010-2019 and through the post-2019
remote-work boom.

- [PREREGISTRATION.md](PREREGISTRATION.md) fixes the specification and the predictions (with
  probabilities) before any data are seen.
- `sc_analysis.py` runs it. `test_sc_analysis.py` holds hand-checked tests.

## Part 2: why do the metro studies disagree? (sc-reconcile-v1)

One set of open data runs three designs side by side:

- **A.** LMW's long difference on metros (2000-2020)
- **B.** The same on counties
- **C.** An annual county panel with county and year fixed effects

This separates the effect of geography from that of horizon and specification.

- [PREREGISTRATION-RECONCILE.md](PREREGISTRATION-RECONCILE.md) has the fixed plan, the
  predictions R1-R7 with probabilities, and how each pattern of results will be read.
- `reconcile.py` runs it and reuses `sc_analysis.py`. `test_reconcile.py` holds hand-checked
  tests, including a two-way fixed-effects example worked by hand.

## Part 3: one outside demand shock, compared within metros (sc-remote-v1)

Income growth is not an outside shock, which is the main objection to LMW. Part 3 uses the
shift to remote work instead: each county's 2015-2019 work-from-home share (the instrument in
Mondragon and Wieland's remote-work paper). It asks whether this shock turned into prices in
constrained counties and into new homes in elastic ones, **comparing counties within the same
metro area** (metro fixed effects). Both earlier papers compare whole metros, which mixes
constrained cores with elastic suburbs.

- [PREREGISTRATION-REMOTE.md](PREREGISTRATION-REMOTE.md) has the design, the predictions Q1-Q7
  with probabilities, and how each pattern will be read.
- `remote.py` runs it. `fetch_deps.py` gets `sc_analysis.py` and `reconcile.py` at commit
  993d76d, and `test_remote.py` holds hand-checked tests.

## Part 4: do measured elasticities predict the response to a later job shock? (sc-bartik-v1)

Baum-Snow and Han's elasticities are built from 1990 and 2000 commuting data. Part 4 takes a
job shock that came afterwards: a county shift-share ("Bartik") shock for 2010-2019, from each
county's 2010 industry mix and the national growth of each industry outside that county. It
asks whether the counties measured as least elastic turned the shock into higher prices rather
than more homes. It also estimates the **realised supply curve** for each elasticity group: the
percent price growth per percent growth in homes caused by the same shock (two-stage least
squares). Supply theory says it should be steepest where supply is measured as least elastic.
The same test is run on metros (LMW's unit) and within metros.

- [PREREGISTRATION-BARTIK.md](PREREGISTRATION-BARTIK.md) has the design, the predictions B1-B8
  with probabilities, and how each pattern will be read.
- `bartik.py` runs it. `fetch_deps_bartik.py` gets `sc_analysis.py`, `reconcile.py` and
  `remote.py` at commit 0e6c10d, and `test_bartik.py` holds hand-checked tests (including a 2SLS
  that must recover known slopes exactly).

```sh
pip install -r requirements.txt
python -m unittest -v test_sc_analysis test_reconcile test_remote test_bartik
python sc_analysis.py --data-dir data --out-dir out
python reconcile.py --data-dir data --out-dir out
python remote.py --data-dir data --out-dir out
python bartik.py --data-dir data --out-dir out
```

## Status

- **2026-11-17:** part 1's pre-registration and code are published, and its run is queued.
- **2026-11-17 (later):** part 2's pre-registration and code are published, and its run is
  queued.
- **2026-11-17 (later):** part 3's pre-registration and code are published, and its run is
  queued.
- **2026-11-17 (later):** part 4's pre-registration and code are published, and its run is
  queued.
- Results from all four will be added under `results/`, unedited, whichever way they come out.

## Credits and licence

The data belong to their publishers: FHFA, BEA, the U.S. Census Bureau, OMB, and Baum-Snow and
Han (replication data, CC0). This project is not endorsed by any of them, or by the authors whose
papers it tests.

Made by MV2 of Munim, Inc. (mv2@munimtech.com), with AI agents. Code is Apache-2.0 (see
LICENSE); text and results are CC BY 4.0. This is research, not investment advice.
