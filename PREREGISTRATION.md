# Pre-registration: do supply constraints explain county house-price and quantity growth?

Written 2026-11-17, before any of the data below were downloaded or looked at by us.
By MV2 of Munim, Inc. (mv2@munimtech.com). Made with AI agents working in his name.
Licence: text CC BY 4.0, code Apache-2.0.

## Question

The standard model of local housing markets says that, given the same rise in demand, places
where housing is hard to build (low supply elasticity) see more price growth and less growth in
the number of homes. Louie, Mondragon and Wieland (2025, NBER w33576, "Supply Constraints do not
Explain House Price and Quantity Growth Across U.S. Cities") report the opposite for U.S. metro
areas, 2000-2020. In their data, income growth predicts the same growth in house prices,
housing quantity and population whatever the estimated supply elasticity. They have been
challenged by Furth (2025), who argues that total income growth is itself shaped by supply, and
by Wiebe (2025), who points to group-specific bias in their estimates. Both drew replies from the
authors. If the claim holds up, much of the case for loosening zoning to lower prices across
cities would need rethinking, so it matters a great deal for housing policy.

We run an independent, fully open test at the **county** level. It uses only public data, the
Baum-Snow and Han (2024, JPE) tract-level supply elasticities averaged up to counties, a
pre-pandemic period, and the post-2019 period that includes the remote-work demand shock.

## Data (all public, fetched by the code)

- **Prices:** FHFA annual county house price index (hpi_at_county.xlsx), as log growth.
- **Demand:** BEA CAINC1 county personal income, as log growth of total personal income
  (primary) and of per-capita personal income (robustness, as an answer to Furth's critique).
- **Quantity:**
  - Census Building Permits Survey county units permitted over the period, per 1,000 residents
    at the start.
  - BEA population, as log growth.
- **Supply elasticity:** Baum-Snow and Han (2024) tract estimates (`.dta` from the authors' page).
  - Primary measure: the housing-**units** elasticity, finite-mixture-model quadratic version if
    present. The fixed selection rule is `pick_elasticity` in sc_analysis.py: tier 1 is
    "unit" + "fmm/mixture" + "quad" in the name or label, tier 2 is "unit" + "fmm/mixture", and
    tier 3 is "unit".
  - Secondary measure: the floorspace (square-footage) elasticity, chosen by the same rule.
  - County value: the unweighted mean of the county's tracts.
  - Counties are ranked into terciles (0 = most constrained).
- Connecticut is dropped, because its counties were replaced in 2022. Counties that the sources
  define differently (for example BEA's combined Virginia areas) drop out by not matching.

## Periods

- **P1:** 2010 to 2019 (pre-pandemic).
- **P2:** 2019 to L, where L is the latest year with 1,000+ counties in both FHFA and BEA (the
  remote-work period).
- **P0:** 2000 to 2019 (long run, secondary).

## Specification (primary)

For each outcome y (price growth, permits per 1,000, population growth):

    y = sum_k a_k D_k + sum_k b_k D_k * g + e,   k = elasticity tercile, g = log income growth

- Weighted by start-year population.
- Standard errors clustered by state.
- Key contrasts:
  - the slope gap b_low - b_high;
  - the level gap at the weighted mean of g: (a_low + b_low gbar) - (a_high + b_high gbar).
- A continuous version interacts g with the county's centred elasticity percentile.

**Robustness:** unweighted; state fixed effects; per-capita income growth as g; counties with
10,000+ residents only; the secondary (floorspace) elasticity.

## Predictions (our honest probabilities, stated before seeing data)

"Supported" means the right sign and two-sided p < 0.05 (state-clustered).

| # | Prediction (standard model) | Our probability |
|---|---|---:|
| H1 | P1: price slope on income growth is larger in the most constrained tercile than in the least constrained | 0.40 |
| H2 | P1: permits slope is larger in the least constrained tercile | 0.45 |
| H3 | P2 (2019 to L): price slope larger in the most constrained tercile | 0.50 |
| H4 | P1 with per-capita income growth: price slope larger in the most constrained tercile | 0.50 |
| H5 | P1: at mean income growth, price growth is higher in the most constrained tercile (level gap) | 0.75 |

**What would be news:**
- If H1 to H3 fail with tight confidence intervals, the Louie-Mondragon-Wieland result
  replicates at a finer geography, with different data and through the post-2019 boom.
- If they hold, the claim does not generalise from metros to counties, and the debate gains a
  concrete, reproducible counter-example.
- Either outcome is reported in full.

## Deviations

The code is fixed by this commit. If a data source fails to download or the elasticity file's
variables do not match the rule, the run reports that and nothing else. A later version fixes
only the data step, and each such change is listed in the results as a deviation, with the
reason. No outcome, period, weight or test will be changed after we see results.

## Limits we already know

- County averages of tract elasticities mix very different neighbourhoods.
- The FHFA county index is built from repeat sales of conforming-loan homes.
- Permits are not completions.
- Income growth is not an exogenous demand shock. This is the same design and the same critique
  as the original paper, which is what we are testing.
- This is not investment advice.
