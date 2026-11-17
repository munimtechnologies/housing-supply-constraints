# housing-supply-constraints

Do housing supply constraints explain where U.S. house prices and housing quantity grew?

This is an open, **pre-registered**, county-level test of a contested claim. Louie, Mondragon
and Wieland (2025, NBER w33576) report that across U.S. metro areas from 2000 to 2020, income
growth predicts the same growth in house prices, housing quantity and population whatever the
local housing supply elasticity. If true, it challenges the standard view that hard-to-build
places turn demand into higher prices rather than more homes.

Here the same question is asked of about 3,000 counties, using only public data:

- FHFA county house price indexes
- BEA county personal income and population
- Census Building Permits Survey county permits
- Baum-Snow and Han (2024, JPE) tract-level supply elasticities, averaged up to counties

The test covers 2010-2019 and the post-2019 remote-work boom.

- [PREREGISTRATION.md](PREREGISTRATION.md) fixes the specification and our predictions,
  with probabilities, before any data are seen. This repository's first commit is the
  timestamp.
- `sc_analysis.py` downloads everything and writes `results.md`, `results.json`,
  `county_panel.csv` and `data_report.txt`.
- `test_sc_analysis.py` holds hand-checked tests, including a least-squares example worked by
  hand.

```sh
pip install -r requirements.txt
python -m unittest -v test_sc_analysis
python sc_analysis.py --data-dir data --out-dir out
```

## Status

- **2026-11-17:** the pre-registration and code are published. The first run is queued.
  Results will be added under `results/`, unedited, whichever way they come out.

## Credits and licence

The data belong to their publishers: FHFA, BEA, the U.S. Census Bureau, and Baum-Snow and Han
(replication data, CC0). This project is not endorsed by any of them.

Made by MV2 of Munim, Inc. (mv2@munimtech.com), with AI agents. Code is Apache-2.0 (see
LICENSE); text and results are CC BY 4.0. This is research, not investment advice.
