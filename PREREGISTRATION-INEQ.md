# Pre-registration, part 6: inequality or regulation? (sc-ineq-v1)

Written 2026-11-19, before any of the data below were downloaded or seen by anyone working on
this project. Made with AI agents working in the name of MV2 of Munim, Inc. Code: `ineq.py`;
hand-checked tests: `test_ineq.py`. Licence: code Apache-2.0, text CC BY 4.0.

## The question

Why do some U.S. metros turn income growth into higher house prices and others into more homes?

- **The supply view** (Saiz 2010; Glaeser and Gyourko 2018; Baum-Snow and Han 2024): it depends on
  how hard it is to build. Where supply is inelastic, demand becomes prices; where it is elastic,
  it becomes homes.
- **The two-margin view** (Louie, Mondragon, Najjar and Wieland, "Quality, Inequality and
  Understanding Housing Markets", August 2026, "LMNW"): there is no single supply elasticity. Rich
  households buy housing *quality*, which is scarce; poorer households buy *units*, which are easy
  to add. Their model (section 2 and appendix A.1) gives the empirical unit-price elasticity as
  a "shock dependence" term times (psi + 1) / (s_r theta(q_r) + (1 - s_r) theta(q_p)). Two
  testable consequences follow:
  - **state dependence:** where the rich hold a larger share of the market (s_r), the same demand
    shock produces more price growth and less unit growth;
  - **shock dependence:** income growth that accrues to the rich shows up in prices, while growth
    in the number and incomes of everyone else shows up in units. With migration (their A.3),
    rich-income growth can even push poorer households out, so that prices rise while population
    and units fall.
- Buchholz, Kemeny, Randolph and Storper (2026, LSE III WP 159) argue, mainly by simulation, that
  "inequality, not regulation" drives the affordability crisis.

**What is new here.** LMNW support their model only with three instruments for one supply curve
(per-capita income, population and total income; LMW 2025 Section A5). Their argument rests on the
income *distribution*, but they do not measure it. As far as we could find (searches on
2026-11-19), no study has put a measure of the local income distribution directly against a
measured supply elasticity, on the same metros and the same years, as rival explanations of
whether demand turned into prices or into homes. Classic work links top incomes to house prices
(Gyourko, Mayer and Sinai 2013, "Superstar Cities"; Matlack and Vigdor 2008), but it does not
run this race against measured elasticities. If the inequality interaction wins, that is direct
evidence for the two-margin view. If the elasticity interaction wins, the supply view survives a
test built on its rival's own terms. If neither wins, that is informative too.

## Data (all public)

- **IRS Statistics of Income county data**, tax years 2011, 2019 and 2022
  (`https://www.irs.gov/pub/irs-soi/YYincyallagi.csv`): returns (N1) and adjusted gross income
  (A00100, in $ thousands) by county and AGI size class. Class 8 is "$200,000 or more". 2011 is
  the first year published as a single all-county CSV.
- BEA CAINC1: personal income and population by metro (BEA's own metro rows, else the sum of
  member counties).
- FHFA annual house price index by CBSA (metropolitan divisions combined, weighted by 2011
  housing units, where the CBSA itself is not published).
- Census county housing-unit estimates, July 2011 and July 2019 (HU-EST2020_ALL).
- Baum-Snow and Han (2024) unit supply elasticities, averaged over each metro's tracts (as in parts
  2, 5 and 5b).
- CPI-U annual averages (FRED CPIAUCSL), used as the deflator, as in LMW.
- OMB 2023 metro delineation. Metros with a Connecticut county are dropped (Connecticut replaced
  its counties in 2022), as in every earlier part.

## Variables (metro m, log changes from 2011 to 2019 unless stated)

- Y: real personal income growth. N: population growth. H: housing-unit growth. P: real
  house-price growth.
- **S0**, the inequality state: the share of the metro's AGI on returns of $200,000 or more in
  2011. S is its z-score in the estimation sample.
- E: the Baum-Snow-Han elasticity. Ez is its z-score in the sample.
- **Real-threshold top income.** A fixed nominal $200,000 line would count inflation as
  concentration ("bracket creep"). Instead, the 2019 top income is income above $200,000 x
  CPI(2019)/CPI(2011), about $227,000 in 2019 dollars. It is interpolated inside the top class
  with a Pareto tail fitted to that class's own mean m: alpha = m / (m - 200) in $ thousands.
  Income above r x $200k is then A_top x r^(1 - alpha).
- dS = (2019 share above the real threshold) - S0.
- g_top and g_rest: the real growth of AGI above and below the real threshold.
- top_c = S0 x g_top and rest_c = (1 - S0) x g_rest. These are the contributions of top and other
  incomes to real AGI growth; their sum is approximately real AGI growth.

## Data rules fixed now

- **Class check.** Analysis runs only if, in both 2011 and 2019, at least 99% of counties with 20
  or more returns in class 8 have a class-8 mean AGI of at least $200,000, and at least 99% of
  those with 20 or more returns in class 7 have a mean of $100,000 to under $200,000. Otherwise
  every prediction is "not evaluable", and a -v2 may fix only the class mapping (logged as a
  deviation).
- **Members and coverage.** Every member county must appear in both IRS years. Shares and growth
  use only member counties whose class 8 is reported in both years, and those counties must hold
  at least 95% of the metro's AGI in each year.
- County total: class 0 if the file has it, else the sum of the classes.
- Common sample: metros with Y, N, H, P, E, S0, dS, top_c and rest_c all present.

## Models (OLS, unweighted as in LMW, HC1 standard errors; constant in all)

| id | outcome | regressors |
|---|---|---|
| R1 | P | Y, Y x S, S |
| R2 | H | Y, Y x S, S |
| R2n | N | Y, Y x S, S |
| R3 (horse race) | H and P | Y, Y x S, S, Y x Ez, Ez |
| R4 (shock composition) | P, H, N | top_c, rest_c (test: top_c - rest_c) |
| R5 (concentration) | N and H | Y, dS |
| R6 (LMW in this window) | H and P | Y, Y x Ez, Ez |

Reported but not graded:

- the same models weighted by 2011 population;
- an exploratory 2011-2022 window for prices and population. Unit estimates are not used for
  2022 because the 2020s housing-unit series is on a new census base.

## Predictions (primary: 2011-2019, unweighted; "p" is the two-sided HC1 p-value)

| id | prediction | our probability |
|---|---|---:|
| I1 | R1: Y x S > 0, p < 0.05 (more unequal metros turn income into more price growth) | 0.55 |
| I2 | R2: Y x S < 0, p < 0.05 (and into less unit growth) | 0.50 |
| I3 | R3 units: Y x S < 0 with p < 0.05 **and** Y x Ez has p >= 0.05 | 0.35 |
| I4 | R3 prices: Y x S > 0 with p < 0.05 **and** Y x Ez has p >= 0.05 | 0.35 |
| I5 | R4 prices: top_c - rest_c > 0, p < 0.05 | 0.55 |
| I6 | R4 units: top_c - rest_c < 0, p < 0.05 | 0.55 |
| I7 | R5 population: dS < 0, p < 0.05 (concentration at the top displaces people, given income growth) | 0.40 |
| I8 | R6 units: Y x Ez has p >= 0.05 (LMW's null holds in 2011-2019) | 0.50 |

These are our honest guesses, not hopes. We expect top shares and elasticities to be correlated
(the coastal metros are both unequal and hard to build in). We therefore think a clean win for
either side (I3, I4) is less likely than not.

## How the results will be read (fixed now)

- **Horse race (R3), units and prices read separately:**
  - "inequality": Y x S has LMNW's sign (units -, prices +) with p < 0.05, and Y x Ez does not
    have the supply view's sign (units +, prices -) with p < 0.05.
  - "supply elasticity": the reverse.
  - "both": both hold.
  - "neither": neither holds.
  `ineq.py` computes this mechanically.
- If |corr(S, Ez)| > 0.7 in the sample, the race is still graded as written, but the results will
  say it cannot separate the two well.
- I5 and I6 together are the direct test of LMNW's shock dependence. Holding up together, they
  are evidence that *who* gains income decides prices versus homes. One holding alone is partial.
- A null on I1-I7 is a real negative result for the two-margin view at this scale and horizon.
  It will be reported as one.
- Nothing here identifies causal effects. Income growth is not an outside shock (the objection to
  LMW that parts 3 and 4 address). These are the equilibrium associations both theories make
  predictions about, measured the same way for both.

## Limits known in advance

- AGI is income of tax filers, by residence. It includes realized capital gains, which swing with
  markets (2011 and 2019 were both ordinary years). It misses non-filers.
- The real threshold relies on a Pareto tail inside the top class.
- The 2011 top share uses a nominal line in one year. Across metros this is a measure of the
  local rich share, but it partly reflects local price levels, which is part of LMNW's mechanism.
- Metro geography is the 2023 delineation applied to all years. A few county changes since 2011
  (for example Bedford city, VA, merged into Bedford County in 2013) slightly mis-assign income in
  a handful of metros.
- One run. Any departure from this plan will be logged under "Deviations" below, with its date.

## Deviations

None to the plan. One dated note follows.

### Note added 2026-11-19 (later the same day), before any data were seen: prior work we missed

The job sc-ineq-v1 had not run when this note was written, so nobody working on this project had
seen any of its data. This note changes **no** data rule, model, prediction, probability or
reading rule above. It corrects the "What is new here" paragraph, which missed one closely
related empirical paper:

- **Liu, Lou and Xiang, "Income Inequality, Housing Supply, and House Prices"** (working paper;
  earlier version "Income Inequality, House Prices, and Housing Regulations", SSRN 4787863, April
  2024, revised April 2025; current version on Chao Liu's website,
  https://chaoliu-cuhk.github.io/). On U.S. counties from 1990 to 2017, with a Bartik-type
  instrument for the Gini coefficient built from 90 occupation-income groups, they report that a
  one standard deviation higher Gini raises house prices by about 30% and cuts building permits by
  44% over the next ten years. They report that the effects are stronger where supply is less
  elastic. Their mechanism is on the **supply side**: inequality brings tighter land-use regulation
  and more resistance to pro-supply reforms. (Figures are from the authors' own summaries; we have
  not yet read the full paper.)

So the claim "no study has put a measure of the local income distribution against a measured
supply elasticity" is too strong as written: Liu, Lou and Xiang do study inequality together with
supply elasticity, though as a moderator of inequality's effect rather than as a rival
explanation. What part 6 still adds, as far as we know:

1. It asks the LMNW question, how the **same income growth** splits into prices and units
   depending on the income distribution (Y x S), not how inequality affects price levels.
2. It conditions that interaction on the measured elasticity's own interaction (Y x Ez), the
   horse race R3.
3. It splits income growth by **who** received it, above and below a fixed real threshold (R4),
   which is LMNW's "shock dependence".

The two explanations of an inequality effect make different predictions in R3, which helps read
the results (again, this changes no reading rule). If inequality works only through regulation
(Liu, Lou and Xiang's channel), and the Baum-Snow-Han elasticity captures that regulation, then Y x S
should shrink once Y x Ez is in the model. If the inequality interaction survives that control, it
points to LMNW's demand-side channel, or to regulation the elasticity does not capture. Both
readings will be stated with the results.
