# Part 3 pre-registration: one outside demand shock, compared within metro areas

Written on 2026-11-17 by AI agents working in the name of MV2 of Munim, Inc., **before any
of the data below were downloaded or seen**. It is published in this repository before the
run (job `sc-remote-v1`). Results will be added under `results/` unedited, whichever way they
come out. Any change after publication will be listed under "Deviations" with its date and
reason.

## Question

When the same outside shock raises housing demand, does it turn into higher prices in
supply-constrained counties and into more homes in elastic counties, **when the counties
compared share one metro labour market**?

## Why this, and what is new

- Louie, Mondragon and Wieland (2025, NBER w33576; FRBSF WP 2025-06) find that across U.S.
  metros, income growth predicts the same price, quantity and population growth whatever the
  supply elasticity. One objection (Furth, SSRN 5227968) is that income growth is itself an
  outcome, not an outside demand shock. LMW answer in part with the 2019-2023 shift to remote
  work (Mondragon and Wieland, NBER w30041, who use the 2015-2019 remote-work share as an
  instrument), and again find no difference by elasticity **across metros**.
- Murphy and Shaheen (2026, Dallas Fed WP 2635) say supply constraints do explain permits and
  prices. They also use metros (an annual panel with metro and year fixed effects).
- Howard, Liebersohn and Ozimek's remote-work papers use county elasticities inside a structural
  model; the Philadelphia Fed's "Great Reshuffle" (WP 25-36) finds remote-work migration moved
  demand toward elastic areas.
- As far as we found, nobody has run the reduced-form LMW test with the remote-work shock
  **within metros** (metro fixed effects), where constrained cores and elastic suburbs face the
  same jobs, rates and credit. Metro averages mix both; within-metro comparisons remove
  everything common to a metro. This is the gap.

## Data (all public; downloaded at run time)

- **Exposure:** 2015-2019 ACS 5-year, table B08301 (means of transportation to work) for every
  county: worked from home (line 21) / workers 16+ (line 1), in percent. Source: the 2019
  summary-file sequence 0027 for each state on www2.census.gov (documented start position 157,
  21 cells). The parser checks the table's own sums (total = all modes; car = alone + carpool;
  carpool = its sizes; transit = its modes) and uses the documented position only if the sums
  hold in at least 99% of counties; otherwise it scans for the position where they hold and logs
  it.
- **First stage:** the same table from the 2019-2023 ACS 5-year table-based file
  (acsdt5y2023-b08301.dat). d_wfh = 2019-23 percent minus 2015-19 percent.
- **Prices:** FHFA annual county HPI. Primary: 100 x log(2023/2019), the window LMW use for
  remote work. Secondary: 2019 to the latest year.
- **Quantity:** Census county housing-unit estimates, vintage 2025 (fallback 2024): 100 x log
  of July of the latest year over the April 1, 2020 base. Permits: Census BPS county annual
  files 2020 through the vintage year, per 1,000 April-2020 homes. Population: the matching
  vintage of co-est20xx-alldata.csv, 100 x log growth from the 2020 base.
- **Density control:** 2020 base population / 2020 Gazetteer land area (log).
- **Metros:** OMB 2023 delineation (list1); metropolitan statistical areas only.
- **Supply elasticity:** Baum-Snow and Han (2024, JPE) unit elasticity, tract means averaged
  to counties, ranked into terciles over all counties with an estimate, exactly as in parts 1
  and 2 (code from `sc_analysis.py`, commit 993d76d). Connecticut is dropped.

## Design

For county c in tercile k (0 = least elastic), with exposure x = 2015-19 work-from-home percent:

    y_c = metro FE + a_k + b_k * x_c + e_c

Weights: 2015-19 workers. Standard errors clustered by metro (CBSA). Counties alone in their
metro sample are dropped. Pooled version: one slope b instead of b_k.

Specifications (each run for d_wfh, price_19_23, price_19_L, hu_growth, permits_per_1000hu,
pop_growth):

1. **within_metro (primary)**: metro member counties, metro fixed effects.
2. within_metro_density: plus log density.
3. within_metro_unweighted.
4. within_metro_workers5k: counties with at least 5,000 workers (ACS noise).
5. cross_county_state_fe: all counties, state fixed effects, clustered by state.
6. national_no_fe: all counties, no fixed effects, clustered by state.

Also reported, descriptively: per-tercile ratios of reduced form to first stage (IV estimates
per point of new remote work), and of price to housing-unit response.

## Predictions (fixed now; "supported" means the stated sign with p < 0.05)

| id | prediction | our probability |
|---|---|---:|
| Q1 | within_metro first stage: the 2015-19 share predicts the rise in work from home (pooled slope > 0) | 0.90 |
| Q2 | within_metro: the 2015-19 share predicts 2019-23 price growth (pooled slope > 0) | 0.55 |
| Q3 | within_metro price slope, low tercile > high tercile | 0.30 |
| Q4 | within_metro housing-unit slope, high tercile > low tercile | 0.40 |
| Q5 | within_metro permits slope, high tercile > low tercile | 0.40 |
| Q6 | cross_county_state_fe price slope, low > high | 0.40 |
| Q7 | cross_county_state_fe housing-unit slope, high > low | 0.45 |

A **tight null** for Q3 means the 95% interval of the low-minus-high price slope lies inside
plus or minus half the pooled within-metro price slope (only judged when Q2 holds).

## How the results will be read (fixed now)

- **Q1 or Q2 fails:** pre-pandemic work from home is not a usable demand shock within metros at
  the county level. We report that and make **no claim** about supply elasticity from this part.
- **Q1, Q2 hold; Q3 and Q4 both supported:** within metros, the same outside shock raised prices
  more and homes less in constrained counties. That is the textbook supply story, and it would
  suggest LMW's metro-level null comes from averaging over very different counties.
- **Q1, Q2 hold; Q3 and Q4 both not supported, with a tight null on Q3:** LMW's pattern holds
  even within metros for an outside shock, which strengthens their reading.
- **Anything else** (one of Q3/Q4, or a wide null): partial or inconclusive, and we will say so.
- If Q3/Q4 hold in the primary spec but not with the density control (spec 2), we will report
  that they may reflect the pandemic "donut" (demand moving from dense cores to suburbs,
  Ramani and Bloom) rather than supply elasticity.
- If the first stage differs a lot between terciles, we will read the reduced-form gaps through
  the IV ratios, not alone.

## Known limits

- The ACS work-from-home count includes farm and other home-based self-employed workers;
  Mondragon and Wieland drop agriculture in microdata. The within-metro, 5,000-worker and
  density specifications reduce but do not remove this.
- 5-year ACS windows smooth the shock; 2019 is in both windows.
- Elasticities are Baum-Snow and Han's, estimated mostly before 2020.
- Housing-unit estimates are modelled from permits and other records, so they are not fully
  independent of permits.
- This is research on public data, not investment advice.

## Deviations

None yet.
