# Was Liberation a Delusion?

BSc Economics thesis, University of Amsterdam  
Çağan Oflazoğlu

This repository contains the thesis PDF, the replication pipeline, the processed public panels, the regression outputs, and the figures behind one question: when the United States called April 2, 2025 a day of economic liberation, did the customs record show that American buyers were actually made better off, or did it show that the country mostly paid higher tariffs while changing which foreign suppliers it used?

The reason the project is built around realized effective tariff rates is that the policy cannot be read only from the legal rate that was announced. A tariff written into a statement is not automatically the tariff collected at the border, because exemptions, carve-outs, grace periods, product composition, and shipment timing all stand between the announcement and the customs counter. So the repository separates the headline tariff from the tariff burden that was actually collected, and only after that asks whether trade fell, whether the fall was large, and whether the missing imports from China were replaced by production in the United States or by imports from other foreign suppliers.

[Read the thesis](thesis/finalized_main.pdf)

## What To Open First

| If you want to see | Open |
|---|---|
| Thesis | [`thesis/finalized_main.pdf`](thesis/finalized_main.pdf) |
| Data construction and regressions | [`pipeline.py`](pipeline.py) |
| Figure generation | [`figures_v2.py`](figures_v2.py) |
| Processed panels used by the paper | [`data/processed/`](data/processed/) |
| Tables and model outputs | [`outputs/`](outputs/) |
| Exported figures | [`figures/`](figures/) |

## The Evidence At A Glance

| Policy timing | Announced rate versus what customs collected |
|---|---|
| ![Policy timeline for the 2025 tariff shock](figures/fig01_policy_timeline.png) | ![Announced and realized effective tariff rates in 2025](figures/fig02_announced_vs_realized.png) |

| Trade diversion | Market-share reshuffling |
|---|---|
| ![Trade diversion quadrant by partner](figures/fig06_diversion_quadrant.png) | ![Top gainers and losers in US import market share](figures/fig07_market_share_mirror.png) |

| Reallocation over time | Product exposure |
|---|---|
| ![Monthly reallocation index around the tariff shock](figures/fig08_reallocation_timeseries.png) | ![Product exposure to China-dominated HS6 goods](figures/figE_product_exposure.png) |

| Regression scale | Independent customs-value check |
|---|---|
| ![PPML coefficient plotted against tariff elasticity benchmarks](figures/figC_coef_plot.png) | ![Census and USITC customs-value validation](figures/figF_usitc_validation.png) |

## What The Paper Finds

The paper does not argue that the policy had no effect. The tariff burden rose, the trade data moved, and the reshuffle is visible even before waiting for a long-run equilibrium. The problem for the liberation story is where the movement seems to go. In the first ten months, the evidence looks less like a return of production to the United States and more like a tax on US firms and consumers combined with rerouting through third countries.

The average realized US import tariff rises from 1.39 percent in the 2020 to 2024 baseline to 5.68 percent in 2025. At the same time, the announced China rate reaches 145 percent, while the realized country-month rate collected at customs never goes above 70.4 percent. That gap is not a footnote, because using the announced number would make the empirical design pretend that firms faced a border rate that many goods did not actually pay.

When the realized tariff burden is used in a PPML gravity model, the main estimate is negative and statistically significant, with a coefficient of `-1.68` on `ln(1 + ETR)` in the top-40 partner specification. The market-share evidence then shows why the result should be read carefully. China loses the most US import share, while the main gains go to the next group of large third-country suppliers, including Taiwan, Vietnam, Mexico, Thailand, India, and Malaysia. In other words, part of the trade did not disappear into American production. It moved around the map.

## Repository Shape

```text
.
|-- README.md
|-- pipeline.py
|-- figures_v2.py
|-- pyproject.toml
|-- requirements.lock
|-- thesis/
|   `-- finalized_main.pdf
|-- data/
|   |-- raw/
|   |   `-- imf_weo_apr2025.csv
|   `-- processed/
|-- outputs/
`-- figures/
```

The repository is intentionally narrower than the private working folder. It publishes the thesis, the code, the figures, the public processed panels, one small public WEO cache needed for Appendix Figure B, and the output tables needed to inspect the results, while larger raw archives, private drafts, access keys, literature PDFs, and restricted-data products are left out.

## Reproduce My Work

The pipeline is written for Python 3.12, with dependencies pinned in `requirements.lock`. A first full run can take a while because the script downloads public data, waits between rate-limited requests, builds the panels, runs the regressions, and exports the figures. Later runs are faster because raw downloads are cached locally.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock

python pipeline.py run
python pipeline.py regress
python pipeline.py figures
```

The last command is the pipeline wrapper around `figures_v2.py`, so running `python figures_v2.py` directly gives the same figure-generation path.

The public replication route uses IMF, US Census, Yale Budget Lab, CEPII, IMF WEO, OECD, and USITC sources. Some HS6 product-detail calls may work better with a free Census API key stored locally, but no key is included in this repository. The Teti Global Tariff Database is treated separately because its access conditions are not the same as the public sources. If you have access, place the archives manually in `data/raw/` and the optional Teti checks can be regenerated; if you do not, the main Census realized-ETR results still run without those files.

## Data Availability

| Source | Role in the paper | Public release treatment |
|---|---|---|
| IMF Direction of Trade Statistics | Monthly bilateral trade flows | Rebuilt by the pipeline from public SDMX endpoints |
| US Census Bureau | Imports, customs duties, and product detail | Rebuilt by the pipeline from public API calls |
| Yale Budget Lab Tariff Tracker | Announced tariff-rate path | Rebuilt by the pipeline from the public tracker file |
| CEPII Gravity and GeoDist | Gravity controls | Rebuilt by the pipeline from public CEPII files |
| IMF World Economic Outlook | GDP controls | A small public CSV cache is included for Appendix Figure B and can also be rebuilt by the pipeline |
| OECD Quarterly National Accounts | Macro extension data | Rebuilt by the pipeline from public OECD endpoints |
| USITC DataWeb | Independent customs-value validation | Public validation output is included |
| Teti Global Tariff Database | Optional product-weighted applied-tariff checks | Raw files and derived restricted-data tables are not redistributed |

The processed files included here are the public-side panels and tables used to explain the thesis result. Most raw data are deliberately not committed, partly because they are re-downloadable and partly because not every source carries the same redistribution permission. The exception is the small public WEO CSV used to regenerate Appendix Figure B from a fresh clone. That is also why the Teti archives, direct access links, and Teti-derived CSV outputs are outside the public release.

## Main Files

| Path | What it contains |
|---|---|
| [`pipeline.py`](pipeline.py) | Download, cleaning, panel construction, regressions, and report commands |
| [`figures_v2.py`](figures_v2.py) | Matplotlib figure factory for all thesis figures |
| [`data/raw/imf_weo_apr2025.csv`](data/raw/imf_weo_apr2025.csv) | Public WEO cache used by Appendix Figure B |
| [`data/processed/gravity_event_study_panel.csv`](data/processed/gravity_event_study_panel.csv) | Main country-month gravity panel |
| [`data/processed/realized_etr_by_country_month.csv`](data/processed/realized_etr_by_country_month.csv) | Census realized tariff burden by partner and month |
| [`data/processed/trade_diversion_indicators.csv`](data/processed/trade_diversion_indicators.csv) | Partner-level diversion and overlap measures |
| [`outputs/regression_coefficients.csv`](outputs/regression_coefficients.csv) | Main coefficient table in machine-readable form |
| [`outputs/regression_results.txt`](outputs/regression_results.txt) | Main PPML regression output |
| [`outputs/usitc_census_discrepancy.csv`](outputs/usitc_census_discrepancy.csv) | Census versus USITC validation comparison |

## Limits

The post-shock window is short, so the results should not be read as the final long-run welfare answer. Country-month realized tariff rates also average across products, which means sector-level differences are partly hidden, and the diversion evidence observes customs origin and product overlap rather than the physical journey of every shipment. Still, those limits do not erase the main pattern. The available evidence can show that realized tariffs rose, that imports fell more where the collected tariff burden was higher, and that the first visible reshuffle mostly favored other foreign suppliers rather than domestic production.

## Citation

Oflazoğlu, Ç. (2026). *Was Liberation a Delusion? Liberation Day Tariff Shocks, Bilateral Trade Flows, and Trade Diversion in 2025.* BSc thesis, University of Amsterdam, Faculty of Economics and Business.

## Contact

Çağan Oflazoğlu  
University of Amsterdam, Faculty of Economics and Business  
cagan.oflazoglu@student.uva.nl

## Bibliography

<details>
<summary>Click to show or hide the bibliography</summary>

- Anderson, J. E. (2011). The gravity model. *Annual Review of Economics, 3*(1), 133-160. https://doi.org/10.1146/annurev-economics-111809-125114

- Anderson, J. E., & van Wincoop, E. (2003). Gravity with gravitas: A solution to the border puzzle. *American Economic Review, 93*(1), 170-192. https://doi.org/10.1257/000282803321455214

- Baldwin, R., & Taglioni, D. (2006). *Gravity for dummies and dummies for gravity equations* (NBER Working Paper No. 12516). National Bureau of Economic Research. https://doi.org/10.3386/w12516

- Berlin, I. (1958). *Two concepts of liberty*. Inaugural lecture delivered before the University of Oxford, 31 October 1958. Clarendon Press.

- Boehm, C. E., Levchenko, A. A., & Pandalai-Nayar, N. (2022). The long and short (run) of trade elasticities. *American Economic Review, 113*(4), 861-905. https://doi.org/10.1257/aer.20210519

- Carrere, C., Mrazova, M., & Neary, J. P. (2020). Gravity without apology: The science of elasticities, distance, and trade. *Economic Journal, 130*(630), 1609-1946. https://doi.org/10.1093/ej/ueaa039

- CEPII. (2011). *GeoDist: Bilateral distances and geographic characteristics* [Data set]. cepii.fr.

- CEPII. (2022). *Gravity dataset, version V202211* [Data set]. cepii.fr.

- Costinot, A., & Rodríguez-Clare, A. (2018). The U.S. gains from trade: Valuation using the demand for foreign factor services. In *Handbook of International Economics* (Vol. 4, pp. 1-40). Elsevier.

- Cox, J. (2025). Dow plunges 2,200 points as tariff tumult rocks markets. *CNN Business*. https://cnn.com/2025/04/04/investing/stock-market-dow-tariffs

- Cutler, W., Reinsch, W. A., Benson, E., & Goodman, M. P. (2025). *"Liberation Day" tariffs explained*. Center for Strategic and International Studies. https://csis.org/analysis/liberation-day-tariffs-explained

- Duncan, O. D., & Duncan, B. (1955). A methodological analysis of segregation indexes. *American Sociological Review, 20*(2), 210-217. https://doi.org/10.2307/2088328

- Eaton, J., & Kortum, S. (2002). Technology, geography, and trade. *Econometrica, 70*(5), 1741-1779. https://doi.org/10.1111/1468-0262.00352

- Executive Office of the President. (2025). *Regulating imports with a reciprocal tariff to rectify trade practices that contribute to large and persistent annual United States goods trade deficits* (Executive Order No. 14257). https://www.presidency.ucsb.edu/documents/executive-order-14257

- Fajgelbaum, P. D., & Khandelwal, A. K. (2022). The economic impacts of the U.S.-China trade war. *Annual Review of Economics, 14*, 415-443. https://doi.org/10.1146/annurev-economics-051420-110410

- Fajgelbaum, P. D., & Khandelwal, A. K. (2026). Tariffs in 2025: Short-run impacts on the U.S. economy. *Brookings Papers on Economic Activity*. https://doi.org/10.3386/w35064

- Fally, T. (2015). Structural gravity and fixed effects. *Journal of International Economics, 97*(1), 76-85. https://doi.org/10.1016/j.jinteco.2015.05.005

- Furceri, D., Ostry, J. D., Papageorgiou, C., & Wibaux, P. (2021). Retaliatory temporary trade barriers: New facts and patterns. *Journal of Policy Modeling, 43*(4), 873-891. https://doi.org/10.1016/j.jpolmod.2021.02.011

- Goodman-Bacon, A. (2021). Difference-in-differences with variation in treatment timing. *Journal of Econometrics, 225*(2), 254-277. https://doi.org/10.1016/j.jeconom.2021.03.014

- Grubel, H. G., & Lloyd, P. J. (1971). The empirical measurement of intra-industry trade. *Economic Record, 47*(4), 494-517. https://doi.org/10.1111/j.1475-4932.1971.tb00772.x

- Handley, K., & Limão, N. (2015). Trade and investment under policy uncertainty: Theory and firm evidence. *American Economic Review, 105*(10), 3116-3148. https://doi.org/10.1257/aer.20141419

- International Monetary Fund. (2025). *Direction of Trade Statistics (IMTS): Bilateral monthly merchandise trade* [Data set]. SDMX 2.1 REST API.

- International Monetary Fund. (2025). *World Economic Outlook, April 2025* [Data set]. imf.org.

- Larch, M. (2026). *Regional trade agreements database* [Data set]. University of Bayreuth.

- McCallum, J. (1995). National borders matter: Canada-U.S. regional trade patterns. *American Economic Review, 85*(3), 615-623.

- National Taxpayers Union Foundation. (2025). *"Liberation Day" tariff timeline*. https://ntu.org/publications/detail/liberation-day-tariff-timeline

- OECD. (2025). *Quarterly National Accounts* [Data set]. sdmx.oecd.org.

- Office of the Federal Register. (2025a). *Executive Order 14257 of April 2, 2025: Regulating imports with a reciprocal tariff*. *Federal Register, 90*, 15625. https://www.federalregister.gov

- Office of the Federal Register. (2025b). *Executive Order 14326: Further modifying the reciprocal tariff rates*. *Federal Register*. https://www.federalregister.gov/documents/2025/08/06/2025-15010

- Oflazoğlu, Ç. (2026). *pipeline.py: Data collection and processing pipeline for Liberation Day gravity analysis* [Computer software]. University of Amsterdam.

- Pattararangrong, J., & Suwanprasert, W. (2025). *Fast and furious: Daily export responses to the Liberation Day tariff shock* (PIER Discussion Paper No. 244). SSRN.

- Pillsbury Winthrop Shaw Pittman LLP. (2025). *U.S. tariffs on non-USMCA-compliant products take effect*. https://pillsburylaw.com/en/news-and-insights/tariffs-usmca-compliant.html

- Santos Silva, J. M. C., & Tenreyro, S. (2006). The log of gravity. *Review of Economics and Statistics, 88*(4), 641-658. https://doi.org/10.1162/rest.88.4.641

- Teti, F. (2025). *Global Tariff Database: Product-level tariff changes at the HS6 and HTS10 level, 2018-2025* [Data set]. ifo Institute.

- Tinbergen, J. (1962). *Shaping the world economy: Suggestions for an international economic policy*. Twentieth Century Fund.

- U.S. Census Bureau. (2025). *USA Trade Online: Monthly merchandise imports and calculated duties* [Data set]. https://api.census.gov/data/timeseries/intltrade/imports/hs

- U.S. Customs and Border Protection. (2025). *Guidance on technology-sector exclusions from reciprocal tariffs*. CBP CSMS guidance.

- Yale Budget Lab. (2025a). *State of U.S. tariffs: September 4, 2025*. https://budgetlab.yale.edu/research/state-us-tariffs-september-4-2025

- Yale Budget Lab. (2025b). *Tariff Rate Tracker* [Data set]. budgetlab.yale.edu.

- York, E., Durante, A., & Watson, G. (2026). *Tariff Tracker: 2026 Trump tariffs and trade war by the numbers*. Tax Foundation. https://taxfoundation.org/research/all/federal/trump-tariffs-trade-war/

- Yotov, Y. V., Piermartini, R., Monteiro, J.-A., & Larch, M. (2016). *An advanced guide to trade policy analysis: The structural gravity model*. World Trade Organization and United Nations Conference on Trade and Development.

</details>
