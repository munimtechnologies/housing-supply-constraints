# Pre-registration, part 2: why do the metro studies disagree?

Written 2026-11-17, before any data below were downloaded or looked at by us, and before the
first part (PREREGISTRATION.md, job sc-county-v1) has produced any result.
By MV2 of Munim, Inc. (mv2@munimtech.com). Made with AI agents working in his name.
Licence: text CC BY 4.0, code Apache-2.0.

## The disagreement

- **Louie, Mondragon and Wieland** (2025, NBER w33576; FRBSF WP 2025-06; "LMW"):
  - Data: U.S. metros, 2000-2020, long differences.
  - Finding: income growth predicts the same growth in prices, housing quantity and population
    in elastic and inelastic metros alike.
  - Conclusion: supply constraints do not explain where prices rose.
- **Murphy and Shaheen** (2026, Federal Reserve Bank of Dallas WP 2635, "Supply Constraints
  Do Explain House Price and Quantity Growth Across U.S. Cities"):
  - Data: annual metro data with year and metro fixed effects, with permits as new supply.
  - Finding: LMW's result "does not hold up"; constraints do explain permits and prices.

Both teams use metros. They differ mainly in **horizon and specification**: one long
difference versus annual changes with fixed effects. Part 1 of this project adds a third
dimension, **geography** (counties instead of metros).

This part runs all three designs on one set of open data, with one elasticity measure. That
shows which choice moves the answer.

## Designs

The elasticity is the same as in part 1: the Baum-Snow and Han tract **unit** elasticity, picked
by `pick_elasticity`. A county's value is the mean over its tracts. A metro's value is the mean
over all of its tracts (the county means weighted by tract counts). Units are ranked into
terciles within each sample, where 0 is the most constrained.

**A. Metro long difference, LMW-style.**
- Metros: OMB 2023 metropolitan statistical areas (list1_2023). Micropolitan areas are
  excluded, and so is any CBSA with a Connecticut member.
- Periods: 2000-2020 (primary) and 2010-2020.
- Income and population: BEA's own MSA rows in CAINC1. If BEA has no MSA rows, the member
  counties are summed instead, and only metros with every member present are kept.
- Price:
  - FHFA annual CBSA index.
  - For CBSAs that FHFA reports only by metropolitan division: the divisions' log growth,
    weighted by 2000 (or start-year) housing units.
  - Robustness: the housing-unit-weighted mean of member-county FHFA growth, kept only where
    it covers at least half the units.
- Housing units: the sum over member counties of the census-based counts (Census 2000 base,
  Census 2010, and the April 1, 2020 estimate from vintage 2020).
- Permits: BPS units over the period per 1,000 start-year residents. A member county missing
  from a year's file counts as 0, and the count of such cases is reported.
- Model: y = sum_k a_k D_k + sum_k b_k D_k g, with g = log growth of total personal income.
  Weighted by start population, with HC1 standard errors.
- Robustness: unweighted; per-capita income growth; county-aggregated price.

**B. County long difference.** The same model, periods and outcomes for counties, clustered by
state.
- Robustness: unweighted; per-capita income growth; only counties that belong to a metro in
  sample A.

**C. Annual county panel** (a Murphy-Shaheen-style design, not a replication of their paper).
- Model: y_ct = county FE + year FE + sum_{j=0..2} sum_k b_jk D_k g_{c,t-j}.
- g_ct is the annual log growth of BEA total personal income. The reported quantity is the
  3-year cumulative response sum_j b_jk for each tercile.
- Outcomes:
  - annual log change of the FHFA county index;
  - BPS permits in year t per 1,000 residents in t-1;
  - annual log change of July housing-unit estimates (2001-2020 only);
  - annual log change of BEA population.
- Primary sample: 2001-2019. Weighted by 2000 population, clustered by state.
- Fixed effects are absorbed by weighted alternating projections.
- Robustness: county + state-by-year FE; unweighted; contemporaneous income growth only; and
  2001 through the latest common BEA/FHFA year.

## Predictions (our probabilities, before seeing data)

"Supported" means the predicted sign with two-sided p < 0.05. "Null reproduced" means p >= 0.05
for the gap. That is a failure to reject, not proof of equality, so confidence intervals are
reported too.

| # | Prediction | Our probability |
|---|---|---:|
| R1 | A, 2000-2020: price slope gap (low minus high) is null, so LMW's metro result is reproduced on our data | 0.55 |
| R2 | A, 2000-2020: housing-unit slope gap is null (LMW reproduced) | 0.55 |
| R3 | B, 2000-2020: price slope larger in the most constrained tercile | 0.40 |
| R4 | B, 2000-2020: housing-unit slope larger in the least constrained tercile | 0.50 |
| R5 | C: cumulative permits response larger in the least constrained tercile | 0.55 |
| R6 | C: cumulative price response larger in the most constrained tercile | 0.45 |
| R7 | C: cumulative housing-unit response larger in the least constrained tercile | 0.45 |

## How we will read the results (fixed now)

- **R1 and R2 fail:** our data do not reproduce LMW at the metro level. We report that, and we
  do not use the county results to make claims about their paper.
- **R1 and R2 hold, and R3 to R7 all fail:** the LMW null survives finer geography and an
  annual panel. That is strong support for LMW.
- **R1 and R2 hold, and R3 or R4 hold:** finer geography reveals constraint effects that metro
  averaging hides.
- **R1 and R2 hold, R5 to R7 hold, and R3 and R4 fail:** the horizon or specification (annual
  fixed-effects panel versus long difference) explains the disagreement between the two papers.
- Every table is published whatever it shows.

## Deviations

The code is fixed by this commit. A later version may fix only the data step: a failed
download, or a changed file layout. Each such fix is listed here, with the reason. No outcome,
period, weight, sample rule or test will change after we see results.

## Limits we already know

- Income growth is not an exogenous demand shock. This is the same design and the same critique
  (Furth 2025) as LMW. The answer will need a separate instrument; a remote-work shock is
  planned as part 3.
- The April 2020 housing-unit figure is the vintage-2020 estimate, not the 2020 census count,
  because the Census API now needs a key.
- The BSH elasticities cover urban tracts only, so rural counties drop out.
- BEA combines some Virginia independent cities with their counties, so those codes do not
  match in the county samples.
- Murphy and Shaheen's exact specification was not available to us in text form. Design C is
  our own panel analogue, not a replication of their paper.
- This is research, not investment advice.
