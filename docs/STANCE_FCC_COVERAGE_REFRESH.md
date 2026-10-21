# Stance FCC Coverage Refresh

This runs in the **gamblerspassion/open-operator** GitHub repository, separate from the Stance sales website.

## Run

1. Open **Actions → Stance FCC Coverage Refresh → Run workflow** on the **main** branch.
2. Enter the **FCC ArcGIS FeatureServer URL** for the desired snapshot. The prefilled URL is the existing source and **does not establish the data's vintage**.
3. Enter a comma-separated list of broadband **filing names** (up to 24), e.g. `Spectrum,Frontier,Brightspeed,Verizon,T-Mobile,altafiber`.
4. Run the workflow. When the aggregate job succeeds, download the **stance-fcc-coverage-zip-city-county-state** artifact from that run.

## Delivered files

- `coverage_zip.csv`: one row per ZCTA, filing name, and technology.
- `coverage_city.csv`: 2020 Census place (city/CDP) area-weighted estimates.
- `coverage_county.csv`: county area-weighted estimates.
- `coverage_state.csv`: state area-weighted estimates.
- `coverage_zip_raw.csv`: original provider/technology ZCTA detail.
- `zip_h3_denominators.csv`: H3-derived ZCTA serviceable-location totals.
- `manifest.json`, `methodology.json`, `run_inputs.json`: assumptions, limitations, and selected parameters.

The workflow runs a denominator job and separate provider jobs, saves distinct extraction artifacts, downloads them all **from the same workflow run**, overlays H3 cell centers onto 2020 ZCTAs, joins ZCTAs to counties and cities, and uploads the final package. **No historical Actions run ID is used.**

## Interpretation

- **Sort `estimated_coverage_pct` descending** for coverage-first agent placement. Prefer `estimated_covered_locations` if the goal is absolute market size.
- Results remain separated by **technology code**. Do **not** sum those technology rows to infer unique addresses reached by a provider.
- City, county, and state coverage is allocated using the **land area overlap** between 2020 ZCTAs and those geographies; this is a geographic estimate, not actual qualifying addresses inside city limits.
- Brand matching is a case-insensitive **contains** filter against filing names. Inspect the resulting `provider_as_filed` values for over-inclusive names. No selected-provider match is treated as a failed run, not an empty successful export.
- Data vintage is determined by the **selected source**, not by the ZIP boundary vintage or the workflow date.
- FCC broadband coverage alone cannot verify specific plan availability, commission, dealer territory or a provider's actual order eligibility.

## Errors and large runs

Failed provider jobs prevent the aggregate job from publishing incomplete coverage. More providers increase nationwide download size. GitHub-hosted runner time limits and disk space may require narrowing to fewer providers per run. Temporary artifact retention is 30 days.

The existing Stance placement application and production sheets are **not updated** by this extractor; manually import the reviewed geographic output into any sales decision system.
