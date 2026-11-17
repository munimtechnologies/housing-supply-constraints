# Part 4 pre-registration: do measured supply elasticities predict the response to a later job shock?

Written on 2026-11-17 by AI agents working in the name of MV2 of Munim, Inc., **before any of
the data below were downloaded or seen** (no part of this project has produced results yet). It
is published in this repository before the run (job `sc-bartik-v1`). Results will be added under
`results/` unedited, whichever way they come out. Any change after publication will be listed
under "Deviations" with its date and reason.

## Question

Baum-Snow and Han (2024, JPE, "The Microgeography of Housing Supply") measured how elastic
housing supply is in every U.S. neighbourhood. Their measures are the ones used on both sides of
the current debate. **When an outside job shock arrived after those measures were made, did the
counties they call least elastic actually turn it into higher prices rather than more homes?**
In other words, do the measured elasticities predict the realised supply curve out of sample?

## Why this, and what is new

- Louie, Mondragon and Wieland (2025, NBER w33576; FRBSF WP 2025-06; "LMW") find that across
  U.S. metros, demand growth turns into the same price and quantity growth whatever the measured
  elasticity (Baum-Snow-Han, Saiz or Wharton). They check this with a metro Bartik labour-demand
  instrument, climate instruments and the remote-work shock, and conclude that measured
  constraints do not explain where prices rose.
- Murphy and Shaheen (2026, Dallas Fed WP 2635) answer that supply constraints do explain permits
  and prices, from an annual metro panel with metro and year fixed effects.
- Baum-Snow and Han identify their elasticities from labour-demand shocks to commuting
  destinations; their replication package (Harvard Dataverse, doi:10.7910/DVN/LFGAAW) builds
  those from 1990 and 2000 commuting data (CTPP). So a 2010-2019 shock comes **after** the data
  the elasticities were estimated from.
- As far as we found, nobody has asked whether these elasticities predict the price/quantity
  split of a **later** shift-share shock at the **county** level, or estimated the realised
  inverse supply slope (price response per unit of quantity response to the same shock) by
  measured-elasticity group. LMW use metros and the same decades the measures come from. This is
  the gap. The answer bears directly on whether the elasticity measures behind zoning-reform
  arguments carry real information.

## Data (all public; downloaded at run time)

- **Shock:** Census County Business Patterns (CBP) county files for 2010 and 2019
  (`cbp10co.zip`, `cbp19co.zip`). Employment by 3-digit NAICS industry (rows coded `NNN///`;
  sector 99 left out). Cells withheld in 2010 (EMP 0 with an EMPFLAG letter) get the midpoint of
  their size class (A 10, B 60, C 175, E 375, F 750, G 1,750, H 3,750, I 7,500, J 17,500,
  K 37,500, L 75,000, M 100,000). Shock for county c, in percent:

      B_c = sum_i s_ci * 100 * ln[(N2019_i - e2019_ci) / (N2010_i - e2010_ci)]

  with s_ci = c's 2010 share of its 3-digit employment in industry i and N the national sum over
  counties (leave-one-out). Industries without positive leave-one-out employment in both years
  are dropped and the shares rescaled (the kept share is logged).
- **First stage:** CBP all-industry employment, 100 x log(2019/2010).
- **Outcomes, 2010 to 2019:** FHFA annual county HPI (100 x log); Census housing units, April
  2010 census count to the July 2019 estimate (`HU-EST2020_ALL.csv`, 100 x log); Census BPS
  permits 2011-2019 per 1,000 homes of 2010; BEA CAINC1 personal income and population
  (100 x log).
- **Controls for robustness:** housing-unit growth 2000-2010 (censuses), log 2010 population
  density (2020 Gazetteer land area).
- **Metros:** OMB 2023 delineation (list1), metropolitan statistical areas.
- **Supply elasticity:** Baum-Snow and Han unit elasticity, tract means averaged to counties and
  ranked into terciles over all counties with an estimate, exactly as in parts 1-3 (code from
  `sc_analysis.py`, commit 0e6c10d). Metro elasticity = mean over the metro's tracts. Connecticut
  is dropped.

## Design

For county c in tercile k (0 = least elastic):

    y_c = state FE + a_k + b_k * B_c + e_c          (reduced form, one per outcome)
    price_c = state FE + a_k + theta_k * hu_c + e_c (2SLS; D_k * hu instrumented by D_k * B)

Weights: 2010 population (BEA). Standard errors clustered by state. theta_k is the realised
inverse supply slope: percent price growth per percent growth in homes caused by the shock.
Supply theory says theta should be largest in the least elastic tercile.

Specifications (each run for emp_growth, inc_growth, pop_growth, hu_growth, permits_per_1000hu,
price_growth, plus the 2SLS):

1. **county_state_fe (primary)**: all counties, state fixed effects.
2. county_state_fe_unweighted.
3. county_state_fe_pop10k: counties with 10,000+ people in 2010 (CBP imputation noise).
4. county_state_fe_lagged_growth: plus 2000-2010 housing-unit growth (persistence).
5. county_no_fe.
6. within_metro: metro member counties, metro (CBSA) fixed effects, clustered by metro.
7. within_metro_density: plus log density.
8. metro: metro aggregates (LMW's unit), no fixed effects, robust standard errors. The metro
   shock is the 2010-employment-weighted mean of its counties' shocks; every member county must
   have one.

## Predictions (fixed now; "supported" means the stated sign with p < 0.05)

| id | prediction (primary spec unless named) | our probability |
|---|---|---:|
| B1 | first stage: the shock predicts county employment growth (pooled slope > 0) | 0.90 |
| B2 | the shock predicts housing-unit growth (pooled slope > 0) | 0.75 |
| B3 | price response: low tercile > high tercile | 0.40 |
| B4 | housing-unit response: high tercile > low tercile | 0.45 |
| B5 | permits response: high tercile > low tercile | 0.45 |
| B6 | realised inverse supply slope (2SLS): low tercile > high tercile | 0.35 |
| B7 | within_metro price response: low > high | 0.25 |
| B8 | metro level (LMW's unit) price response: low > high | 0.30 |

B6 is judged only if the housing-unit reduced form (the 2SLS first stage) is positive with
t >= 3.16 (F >= 10) in both the lowest and the highest tercile; otherwise it is reported as "not
evaluable (weak first stage)". A **tight null** for B3 means the 95% interval of the
low-minus-high price slope lies inside plus or minus half the pooled price slope (judged only
when the pooled price slope is positive with p < 0.05).

## How the results will be read (fixed now)

- **B1 or B2 fails:** the shift-share shock is not a usable county demand shock here. We report
  that and make **no claim** about supply elasticities from this part.
- **B3 and B4 supported (and B6 supported if judged):** the elasticity measures predict, out of
  sample, where a later outside shock became prices and where it became homes. Measured
  constraints carry real information, and any metro-level null (B8 here, R1/R2 in part 2) would
  point to aggregation or design rather than to elasticities that do not matter.
- **B3 and B4 not supported, B3 a tight null, and B6 not supported:** the measures do not
  predict the realised supply response to a later outside shock at county level. That is the
  strongest county-level support for LMW's reading so far, and we will say so.
- **B3/B4 hold but not with the 2000-2010 growth control (spec 4):** the gaps may reflect growth
  persistence rather than elasticity.
- **B3/B4 hold across counties but B7 does not:** the elasticity signal is between metros or
  regions, not between neighbouring counties (or commuting spillovers inside metros wash it out).
- **Anything else:** partial or inconclusive, and we will say so.

## Known limits

- CBP leaves out the self-employed, most government and farm employment; 2010 withheld cells are
  imputed at class midpoints. NAICS changed between 2007 (used in 2010) and 2017 (used in 2019);
  3-digit codes that do not match drop out of the shock (logged).
- Shift-share validity rests on the 2010 industry shares being unrelated to other drivers of
  housing growth (Goldsmith-Pinkham, Sorkin and Swift 2020; Borusyak, Hull and Jaravel 2022).
  The lagged-growth and density specifications check this only in part.
- Jobs in one county raise housing demand in its neighbours (commuting), which weakens county
  contrasts, most of all within metros. Baum-Snow and Han handle this with commuting market
  access; we do not.
- That the elasticities are estimated from 1990s-2000s data is taken from their replication
  package's file list; if the paper's own window turns out to reach past 2010, the
  "out of sample" wording will be corrected as a dated deviation.
- Housing-unit estimates after 2010 are modelled partly from permits.
- This is research on public data, not investment advice.

## Deviations

None yet.
