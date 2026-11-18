# Pre-registration, part 5: which choice makes the two Fed papers disagree?

Written 2026-11-17, before any data below were downloaded or looked at by us, and before parts
1-4 of this project have produced any result. By MV2 of Munim, Inc. (mv2@munimtech.com).
Made with AI agents working in his name. Licence: text CC BY 4.0, code Apache-2.0.

## Why this part

- **Louie, Mondragon and Wieland** (2025, NBER w33576, "LMW"): across U.S. metros, 2000-2020,
  income growth predicts the same growth in housing units and prices whatever the supply
  elasticity.
- **Murphy and Shaheen** (2026, Dallas Fed WP 2635, "M-S"): on the same question, they find that
  supply elasticity does matter. In their reading, the long-difference gap "stem[s] from our use
  of regressions weighted by MSA population size and, to a lesser extent, our use of the
  continuous supply elasticity / constraint measures rather than dummy variables". For their
  structural (2SLS) long difference they write that they cannot account for the difference ("a
  puzzling no"). They prefer an annual panel: log permits on log real per-capita income and its
  interaction with elasticity, with metro and year fixed effects.

We read the M-S paper in full. Two further differences between the designs are visible in the
equations and tables M-S print (pp. 13-14; Tables 6, 7, 10, 11 and A2):

1. **The elasticity main effect.** M-S's long-difference equations are
   `y = pi0 + pi1 g + pi2 (g x E) + v` and the 2SLS analogue, with **no E term on its own**. LMW
   include it ("Less Constrained" is a row in their Tables II-IV). Income growth g is positive in
   almost every metro, so g x E behaves much like a rescaled E. If elastic metros grew faster for
   reasons other than their response to income, that level difference can load on the
   interaction. A symptom: without the main effect, the interaction estimate changes when income
   is deflated differently (real instead of nominal), which cannot happen once E is included
   (this is proved on a worked example in `test_ms.py`).
2. **The national cycle in the annual panel.** Year fixed effects are common to all metros. They
   do not absorb E x (national income path). So the annual interaction can be identified by
   elastic metros riding the 2000s boom and bust, or the post-2012 recovery, differently, rather
   than by their response to their own local income. Adding elasticity-by-year effects (E x year
   dummies) removes exactly that channel.

We cannot see M-S's code. If their code included E but their printed equations omit it, then
point 1 is a fact about the data but not about their paper. We will say so.

## Data (all public)

- Metros: OMB 2023 metropolitan statistical areas (list1_2023). Any CBSA with a Connecticut
  member is dropped.
- Elasticity E: the Baum-Snow and Han tract **unit** elasticity, picked as in part 1. A metro's
  value is the mean over its tracts. M-S use the Gorback-Keys (2026) metro mapping, which is not
  open. We report our unweighted and population-weighted means next to theirs (0.340 and 0.234,
  n = 318). D = 1 if E is above the unweighted mean over the analysed metros (LMW's "relative
  to the mean").
- Income: BEA CAINC1 metro rows (or the member-county sum if BEA has none). The panel uses per
  capita income and the long difference total income, as M-S do. Deflator: the PCE price index
  (FRED PCEPI, annual average), as M-S use.
- House prices: FHFA annual CBSA index (M-S use Cotality/CoreLogic, which is not open). For
  CBSAs that FHFA reports only by metropolitan division, we use the 2000-housing-unit-weighted
  mean of the division log indexes. Prices are deflated by PCE.
- Housing units: Census counts for 2000 and the April 2020 estimate, summed over member counties.
- Permits: Census BPS annual county totals, summed over member counties. Missing member-years
  count as 0 and are reported. Years with zero permits drop out of log permits; we report how
  many.
- Weights: the 2010 BEA metro population. M-S report "2010 Population Weighted" statistics.

## Designs

**Long differences, 2000-2020 (HC1 standard errors).** The outcomes are the change in log
housing units and the change in log real price. g is the change in log real total personal
income.

- **Reduced form:** `y = a + b g + c (g x M) [+ d M]`. We fit all 8 cells of three switches:
  - weights: 2010 population, or none;
  - measure M: continuous E, or above-mean D;
  - main effect d M: left out (M-S), or included (LMW).
  - We also fit the weighted, continuous cells with **nominal** income, with and without the
    main effect.
- **Structural (2SLS):** `dlog H = a + b1 dlogP + b2 (dlogP x M) [+ d M]`, with instruments g
  and g x M. Fitted weighted, for M = E or D, without and with the main effect, with first-stage
  F statistics.
- **Switch effects:** for the housing-unit interaction, the mean absolute change in its
  z-statistic when one switch is flipped, averaged over the 4 settings of the other two.

**Annual panel**, from 2000 to T, where T is the last year present in BEA, FHFA CBSA, BPS and
PCE. All fits have metro and year fixed effects, absorbed by weighted alternating projections.
Driscoll-Kraay standard errors with a Bartlett kernel and 1 lag (as M-S), plus metro-clustered
errors for reference. Weights are the 2010 population unless stated.

| id | specification |
|---|---|
| A1 | M-S reduced form: ln permits on ln y and ln y x E |
| A2 | A1 plus E x year dummies |
| A3 | ln y split into the national path n_t (the weighted mean over the panel's metro-years) and the local deviation u = ln y - n_t: regressors u, u x E, n_t x E |
| A4 | A1 for 2000-2011 and for 2012-T |
| A5 | A1 unweighted |
| A6 | A1 with D instead of E, and with D x year dummies |
| A7 | M-S structural: ln permits on ln real price and ln price x E, instruments ln y and ln y x E |
| A8 | A7 plus E x year dummies |
| A9 | ln real price on ln y and ln y x E, without and with E x year dummies |

## Predictions (our probabilities, before seeing data)

"Supported" means the predicted sign with two-sided p < 0.05 (Driscoll-Kraay for the panel).

| # | Prediction | Our probability |
|---|---|---:|
| P1 | Long difference, M-S cell (weighted, continuous, no main effect): housing-unit interaction > 0 | 0.70 |
| P2 | Long difference, LMW cell (unweighted, above-mean, with main effect): housing-unit interaction null (p >= 0.05) | 0.65 |
| P3 | If P1 holds: adding the main effect (weighted, continuous) at least halves the housing-unit interaction and leaves p >= 0.05 | 0.45 |
| P4 | Of the three switches, the main effect moves the housing-unit interaction z the most | 0.50 |
| P5 | Price, weighted, continuous, with main effect: interaction < 0 | 0.35 |
| P6 | A1: ln y x E > 0 for ln permits | 0.50 |
| P7 | A2 (with E x year): ln y x E > 0 | 0.30 |
| P8 | A3: national path x E > 0 | 0.50 |
| P9 | Long-difference 2SLS, weighted, continuous, with main effect: price x E > 0 | 0.35 |

## How we will read the results (fixed now)

- **P1 fails:** our open data do not reproduce M-S's long-difference result. We say so and make
  no claim about why their paper differs from LMW.
- **P1 and P3 hold:** on open data, the M-S long-difference result depends on leaving out the
  elasticity's own term. If P4 also holds, that matters more than weighting or the measure.
  - Including E is the standard way to write an interaction model.
  - This would also explain M-S's "puzzling" structural result if P9 fails.
- **P1 holds and P3 fails:** M-S's result survives the main effect on our data, and the gap
  lies where they say: in weighting and the measure.
- **P6 holds and P7 fails:** M-S's annual result is identified by how elastic metros moved with
  the national cycle, not by their response to their own income. P8 holding would confirm this.
- **P6 and P7 hold:** elastic metros build more when their own income rises, even net of any
  elasticity-specific national cycle. That would be strong support for M-S beyond what they
  showed.
- **P6 fails:** we do not reproduce the annual M-S result with FHFA, BEA and BPS data. We report
  it, along with the input differences (CoreLogic, Haver, and the Gorback-Keys mapping).
- Every table is published whatever it shows. This part does not change parts 1-4.

## Deviations

The code is fixed by this commit. A later version may fix only the data step: a failed
download, or a changed file layout. Each such fix is listed here, with the reason. No outcome,
period, weight, sample rule or test will change after we see results.

## Limits we already know

- **One elasticity measure.** We use only Baum-Snow and Han. M-S also use Saiz, WRLURI, Davis et
  al., Lutz-Sand and Guren et al.; LMW use the first four of those.
- **Different metro mapping and prices.** Our metro BSH values and FHFA prices are not M-S's
  Gorback-Keys mapping and CoreLogic indexes.
- **Not causal.** Income is not an exogenous demand shock in any of these designs. Parts 3 and 4
  use outside shocks.
- **Deflator.** The PCE deflator only matters for the specifications without a main effect; that
  dependence is itself one of the things we report.
- **Housing units in 2020.** The 2020 figure is the vintage-2020 April estimate, not the census
  count.
- This is research, not investment advice.

## Notes added before any result (2026-11-18)

These notes do not change the design, the code or any prediction above. They correct how one
cell is described. They were written before sc-ms-v1 had run and before any data were looked at.

- **LMW split at the median, not the mean.** After filing this part we read the February 2026
  revision of LMW in full (FRBSF Working Paper 2025-06, doi:10.24148/wp2025-06). Their
  "Less Constrained" indicator is an **above-median** split (pp. 19, 22 eq. 8, 25; notes to
  Tables II-IV). The phrase "relative to the mean" above was ours, not theirs. They also deflate
  by the CPI (p. 17), use annualized percent growth (p. 17), and mention no weighting.
- **What this means for P2.** P2 still tests the cell exactly as written (above-mean, PCE, log
  changes), and it will be scored that way. It is close to LMW's cell but not identical.
  LMW's exact cell is run separately, with its own predictions, in part 5b
  (PREREGISTRATION-LMW.md, job sc-lmw-v1). Part 5b also reports a 2 x 2 bridge that shows how
  much switching from the mean to the median, and from part 5's units to LMW's, moves the
  housing-unit interaction. When we report P2 we will put part 5b's L1 cell next to it.
