# housing-supply-constraints

Do housing supply constraints explain where U.S. house prices and housing quantity grew?

This is an open, **pre-registered**, county-level test of a contested claim. Louie, Mondragon
and Wieland (2025, NBER w33576; revised as FRBSF Working Paper 2025-06, February 2026) report that
across U.S. metro areas from 2000 to 2020, income growth predicts the same growth in house prices,
housing quantity and population whatever the local housing supply elasticity. If true, it
challenges the standard view that hard-to-build places turn demand into higher prices rather than
more homes. In October 2026, Murphy and Shaheen (Dallas Fed WP 2635) answered that supply
constraints *do* explain permits and prices, using annual metro data with fixed effects.

All inputs are public:

- FHFA county and metro house price indexes
- BEA county and metro personal income and population
- Census Building Permits Survey county permits
- Census County Business Patterns county employment by industry (2010, 2019)
- Census county housing-unit counts (2000, 2010, 2020) and estimates (2010-2025)
- Census American Community Survey commuting table B08301 (2015-2019 and 2019-2023)
- IRS Statistics of Income county data: returns and adjusted gross income by income class (2011,
  2019, 2022)
- OMB 2023 metro delineations and the 2020 Census Gazetteer
- Baum-Snow and Han (2024, JPE) tract-level supply elasticities
- The PCE price index (BEA, via FRED) and the CPI-U (BLS, via FRED)

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

## Part 5: which specification choice makes the two Fed papers disagree? (sc-ms-v1)

We read Murphy and Shaheen's paper in full. They say their long-difference results differ from
LMW's mainly because they weight by population and use continuous measures. Two other
differences can be read off their printed equations:

1. **The elasticity's own term.** Their long-difference equations leave out the elasticity's
   own term. LMW's include it. Income growth is positive almost everywhere, so "income growth
   x elasticity" behaves much like the elasticity itself. Without that term, it can pick up any
   reason elastic metros grew faster. One symptom: the estimate then even depends on the price
   deflator.
2. **The national cycle.** In their annual panel, year effects do not absorb elasticity x the
   national income path. The result could therefore come from elastic metros riding the
   national boom and bust differently, not from their response to their own income.

Part 5 fits the full 2 x 2 x 2 grid on open data: weights, measure, and main effect left out or
included. It also fits M-S's annual design with and without elasticity-by-year effects, and
splits income into its national and local parts.

- [PREREGISTRATION-MS.md](PREREGISTRATION-MS.md) has the design, the predictions P1-P9 with
  probabilities, and how each pattern will be read.
- `ms.py` runs it. `fetch_deps_ms.py` gets `sc_analysis.py` and `reconcile.py` at commit
  0e6c10d. `test_ms.py` holds hand-checked tests, including the deflator symptom on a worked
  example and Driscoll-Kraay standard errors computed by hand.

## Part 5b: LMW's own cell, exactly (sc-lmw-v1)

After filing part 5 we read LMW's February 2026 revision in full. Part 5's "LMW cell" splits
metros at the **mean** elasticity. LMW split at the **median** (pp. 19, 22, 25 and the notes to
their Tables II-IV), deflate by the CPI and use annualized percent growth (p. 17). Part 5b runs
LMW's exact cell for the Baum-Snow-Han elasticity on open data and sets each estimate next to the
number LMW publish. It also re-runs two of their supply-curve estimates:

- Table IV: the 2SLS elasticity in less and more constrained metros.
- Table IX: one supply curve estimated twice, once with per-capita income and once with
  population as the instrument (0.2 and 1.5 in LMW). This gap is their evidence that housing
  has two margins, quality and quantity.

A 2 x 2 bridge (split x units) shows how much each difference moves part 5's P2.

- [PREREGISTRATION-LMW.md](PREREGISTRATION-LMW.md) has the comparison table, the predictions
  Q1-Q7 with probabilities, and how each result will be read.
- `lmw.py` runs it. `fetch_deps_lmw.py` gets `ms.py` at commit 1e1d533 and `sc_analysis.py` and
  `reconcile.py` at 0e6c10d. `test_lmw.py` holds hand-checked tests.

## Part 6: inequality or regulation? (sc-ineq-v1)

In August 2026 Louie, Mondragon, Najjar and Wieland ("Quality, Inequality and Understanding
Housing Markets") argued that there is no single housing supply elasticity:

- Rich households buy housing *quality*, which is scarce.
- Poorer households buy *units*, which are easy to add.
- So whether demand becomes prices or homes depends on **who** holds and gains the income, and
  not only on how hard it is to build.

They support this only indirectly. Part 6 tests it head on: for U.S. metros from 2011 to 2019, it
races a measure of the local income distribution against the measured supply elasticity.

- **Inequality measure:** the share of income on tax returns of $200,000 or more (IRS county
  data), with top-income growth measured above a fixed *real* threshold so that inflation does
  not count as concentration.
- **Supply measure:** the Baum-Snow-Han elasticity.
- **Question:** which one predicts whether income growth turned into prices or into homes?

If inequality wins, that is direct evidence for the two-margin view in a debate that until now has
been argued mostly in theory and simulation.

- [PREREGISTRATION-INEQ.md](PREREGISTRATION-INEQ.md) has the design, the predictions I1-I8 with
  probabilities, and how each result will be read.
- `ineq.py` runs it. `fetch_deps_ineq.py` gets `ms.py` at commit 1e1d533 and `sc_analysis.py` and
  `reconcile.py` at 0e6c10d. `test_ineq.py` holds hand-checked tests, including the Pareto
  real-threshold step worked by hand.

```sh
pip install -r requirements.txt
python -m unittest -v test_sc_analysis test_reconcile test_remote test_bartik test_ms test_lmw test_ineq
python sc_analysis.py --data-dir data --out-dir out
python reconcile.py --data-dir data --out-dir out
python remote.py --data-dir data --out-dir out
python bartik.py --data-dir data --out-dir out
python ms.py --data-dir data --out-dir out
python lmw.py --data-dir data --out-dir out
python ineq.py --data-dir data --out-dir out
```

## Status

- **2026-11-17:** the pre-registrations and code for parts 1-5 were published. Each run is
  queued.
- **2026-11-18:** part 5b was pre-registered and published. A dated note was added to
  PREREGISTRATION-MS.md about LMW's median split.
- **2026-11-19:** part 6 was pre-registered and published. No part has produced a result yet.
- Results from all parts will be added under `results/`, unedited, whichever way they come out.

## Credits and licence

The data belong to their publishers: FHFA, BEA, BLS, the U.S. Census Bureau, the IRS Statistics
of Income Division, OMB, the Federal Reserve Bank of St. Louis (FRED), and Baum-Snow and Han
(replication data, CC0). This project is not endorsed by any of them, or by the authors whose
papers it tests.

Made by MV2 of Munim, Inc. (mv2@munimtech.com), with AI agents. Code is Apache-2.0 (see
LICENSE); text and results are CC BY 4.0. This is research, not investment advice.
