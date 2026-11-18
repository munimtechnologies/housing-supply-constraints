# Pre-registration, part 5b: LMW's own cell, on open data

Written 2026-11-18, before any data below were downloaded or looked at by us, and before parts
1-5 of this project have produced any result. By MV2 of Munim, Inc. (mv2@munimtech.com).
Made with AI agents working in his name. Licence: text CC BY 4.0, code Apache-2.0.

## Why this part

Part 5 (PREREGISTRATION-MS.md) asks which specification choice makes Murphy and Shaheen (2026,
Dallas Fed WP 2635) and Louie, Mondragon and Wieland ("LMW") disagree. Its prediction P2 tests an
"LMW cell": unweighted, with the elasticity main effect, and a dummy for an elasticity **above the
mean**, in log changes deflated by PCE.

After filing part 5 we read the February 2026 revision of LMW in full (Federal Reserve Bank of
San Francisco Working Paper 2025-06, doi:10.24148/wp2025-06). LMW's own cell differs from part 5's
in three ways:

| choice | LMW (Feb 2026) | where in LMW | part 5's "LMW cell" |
|---|---|---|---|
| split | above the **median** of each measure | pp. 19, 22 (eq. 8), 25; notes to Tables II-IV | above the mean |
| deflator | CPI | p. 17 | PCE |
| units | annualized percent growth, 2000-2020 | p. 17 | 20-year log change |
| weights | none mentioned anywhere | (whole paper) | none |
| main effect | included ("Less Constrained" row) | eq. 8, Tables II-IV | included |

The deflator and units cannot change the interaction much once the main effect is in, but the
split can: it decides which metros count as "less constrained". So part 5's P2 is not, strictly,
a test of LMW's cell. This part runs LMW's cell exactly, as far as open data allow, and a small
bridge that shows how much the split and the units each move the result. Part 5 is not changed.

## Data (all public; same downloads as part 5)

- Metros: OMB 2023 metropolitan statistical areas, as in part 5 (LMW use Saiz's 1999 MSA
  definitions, which we cannot rebuild exactly).
- Elasticity E: the Baum-Snow and Han tract unit elasticity, metro value = mean over its tracts,
  as in part 5 (LMW aggregate with BSH's equation 21 and housing quantities; not reproducible from
  the open file without their quantity weights).
- Income and population: BEA CAINC1, 2000 and 2020. Housing units: Census 2000 and the April 2020
  estimate. Prices: FHFA annual CBSA index (LMW use CoreLogic December values).
- Deflator: CPI-U, all items, annual average (FRED CPIAUCSL, checked 2026-11-18: 172.192 in 2000,
  258.856 in 2020). PCE (FRED PCEPI) for the bridge only.
- Growth: annualized percent, `100 (exp(dlog / 20) - 1)`. Y = real total income, N = population,
  y_pc = real per-capita income, H = housing units, P = real price.
- Sample: metros with Y, H, P and E all present ("common sample"). Dmed = 1 if E is strictly above
  the median of E over the common sample; Dmean = 1 if strictly above its mean.

## Designs (all unweighted, HC1 standard errors)

LMW-exact cells, `outcome = a + b x + c (x Dmed) + d Dmed`, compared with LMW's Baum-Snow-Han
column:

| id | outcome | x | LMW comparison (col. 2) |
|---|---|---|---|
| L1 | H | Y | Table III A: x 0.635 (0.030), interaction -0.015 (0.048), n 310 |
| L2 | P | Y | Table II A: 0.589 (0.078), 0.052 (0.111), n 308 |
| L3 | N | Y | Table III B: 0.717 (0.034), 0.001 (0.051) |
| L4 | P | y_pc | Table II B: 1.284 (0.187), -0.162 (0.248) |
| L5 | H | y_pc | Table VII A: 0.309 (0.148), -0.030 (0.193) |
| L6 | H | N | Table VIII A: 0.876 (0.019), -0.019 (0.024) |
| L7 | 2SLS: H on P, P x Dmed, Dmed; instruments Y, Y x Dmed | | Table IV A: more 1.078, less 0.965, p(equal) 0.60 |
| L8 | 2SLS: H on P with one instrument, y_pc or N | | Table IX: 0.215 (0.081) and 1.506 (0.178), n 321 |

**Bridge:** L1 in a 2 x 2 of units (LMW: annualized, CPI; part 5: log, PCE) x split (mean,
median). We report the mean absolute change in the interaction's z when each switch is flipped.

## Predictions (our probabilities, before seeing data)

| # | Prediction | Our probability |
|---|---|---:|
| Q1 | L1 housing-unit interaction null (p >= 0.05) | 0.70 |
| Q2 | L2 price interaction null (p >= 0.05) | 0.65 |
| Q3 | L1 interaction within 0.10 of LMW's -0.015, i.e. in [-0.115, 0.085] | 0.55 |
| Q4 | L1 income coefficient in [0.50, 0.80] (LMW 0.635) | 0.60 |
| Q5 | L7: less and more constrained elasticities not different (p >= 0.05) | 0.70 |
| Q6 | L8: elasticity with population as instrument exceeds that with per-capita income by more than 0.5 | 0.65 |
| Q7 | Bridge: switching mean to median moves the L1 interaction z by less than 1.0 | 0.65 |

## How we will read the results (fixed now)

- **Q1 and Q2 hold:** LMW's null for the Baum-Snow-Han elasticity reproduces in their own cell on
  open data. Any disagreement found in part 5 then comes from weights, the continuous measure or
  the main effect, not from the split or the units.
- **Q1 fails** (a significant housing-unit interaction): open data contradict LMW's Baum-Snow-Han
  result in their own cell. We report it with the input differences listed above and claim nothing
  about LMW's data.
- **Q6 holds:** LMW's evidence for two margins (per-capita income moves prices, population moves
  housing units) reproduces on open data. **Q6 fails:** it does not, on our inputs.
- **Q7 fails:** part 5's P2 must be read together with L1; we will say so next to P2.
- Every table is published whatever it shows.

## Deviations

The code is fixed by this commit. A later version may fix only the data step: a failed download
or a changed file layout. Each such fix is listed here, with the reason. No outcome, sample rule,
split, weight or test will change after we see results.

## Limits we already know

- One elasticity measure (Baum-Snow and Han), different metro definitions, a different price
  index and a different BSH aggregation from LMW's. A match is reassuring; a mismatch can come from
  any of these.
- LMW do not state their standard errors; we use HC1.
- Not causal; income is not an exogenous demand shock. Parts 3 and 4 use outside shocks.
- This is research, not investment advice.
