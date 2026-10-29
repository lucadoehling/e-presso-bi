# E-Presso Business Intelligence

Course project analyzing five years of E-Presso sales and market-survey data.
The original Power BI prerequisite has been reproduced in Looker Studio, with
Python used to prepare and validate the source data on macOS.

## Live Looker Studio report

[Open the E-Presso Looker Studio report](https://datastudio.google.com/reporting/8d641dde-a08f-4db8-bf05-8e6a3a089f44)

The baseline report covers revenue by sales channel, annual and monthly
patterns, product-category filtering, store geography, and the association
between customer satisfaction and revenue.

## Analytical methodology

### 1. Source inventory and table grain

The analysis begins with the original course sources:

- Access database: Categories, Products, and Sales
- Excel workbook: annual Survey Results
- Tab-delimited store file: store type, market, and geography
- PBIX report: model and visualization reference

Each table was profiled before calculating metrics. The Sales table contains
25,200 rows at a store-month-product grain. It covers January 2025 through
December 2029. Identifier uniqueness, missing values, data types, duplicates,
and date coverage were checked before joining tables.

### 2. Reproducible preparation

`scripts/prepare_data.py` reads the original files without modifying them. On
macOS, it uses the read-only `mdb-export` command from `mdbtools` to extract
Access tables. pandas and openpyxl read and clean the text and Excel sources.

Important preparation decisions include:

- Preserve identifiers and postal codes as text.
- Convert `Date` to a date and `Revenue` to a numeric field.
- Keep missing website survey scores as null rather than replacing them with
  zero.
- Remove Phone and Manager because they are not needed for the analysis.
- Keep raw and generated data outside the public Git repository.

### 3. Relationship validation

The flat analytical table is created with four many-to-one left joins:

| Sales key | Lookup key | Purpose |
|---|---|---|
| `Category ID` | `Categories[Category ID]` | Add category name |
| `Product ID` | `Products[Product ID]` | Add product name |
| `Store ID` | `Stores[ID]` | Add store type and geography |
| `StoreYear` | `Survey Results[Survey ID]` | Add annual survey values |

`StoreYear` must join to `Survey ID`; joining `Store ID` directly to
`Survey ID` produces no matches. Product joins use `Product ID` because product
names are not unique.

Every join is checked for many-to-one cardinality, unmatched keys, changed row
counts, and changed revenue. The final table remains at 25,200 rows, and the
five-year revenue control total remains `$42,174,440`.

### 4. Metric definitions

- **Total revenue:** sum of the stored `Revenue` field for the selected scope.
- **Channel revenue:** total revenue grouped by Website or Brick & Mortar.
- **Annual trend:** total revenue grouped by calendar year.
- **Monthly pattern:** total revenue grouped by calendar month across the
  five-year period.
- **Average satisfaction:** mean of non-null annual Satisfaction scores for the
  selected store or store-year scope.

Revenue is not profit because the source data does not include costs. Missing
survey values are excluded from averages, not treated as zero.

### 5. Looker Studio analysis

The prepared `sales_enriched.csv` table supplies the Looker Studio baseline.
The report reproduces the intent of the Power BI walkthrough through:

- Five-year revenue scorecard
- Website versus brick-and-mortar comparison
- Annual revenue trend
- Monthly revenue pattern
- Product-category and store-type controls
- Store Type, Market, and City drill hierarchy
- Revenue-versus-satisfaction scatterplot
- Store revenue and satisfaction table

Interactive filters recalculate the applicable metrics and charts. The
satisfaction scatterplot describes association only; it does not establish
that satisfaction caused revenue changes.

### 6. Validation and documentation

The preparation script independently checks the expected revenue total, source
row counts, key uniqueness, missing values, join coverage, and revenue
preservation. It writes a column-level data-quality report and a JSON validation
summary for later reconciliation with Streamlit.

Detailed documentation:

- [Data dictionary](docs/data_dictionary.md)
- [PBIX migration, command-line methods, and AI-use report](docs/pbix_migration_methods.md)

## Run the preparation pipeline

Requirements:

- Python 3.9 or newer
- `mdbtools` on macOS (`brew install mdbtools`)
- Python packages in `requirements.txt`

From the repository root:

```bash
python scripts/prepare_data.py \
  --input-dir .. \
  --output-dir data/processed
```

Raw source files and generated analytical outputs are excluded from Git.

## Project status

Completed:

- Source inventory and data profiling
- Relationship and revenue validation
- Reproducible Python preparation pipeline
- Looker Studio prerequisite report
- PBIX migration and AI-use documentation

Planned in later course checkpoints:

- Streamlit analytical dashboard
- Reusable analytical functions
- Controlled analytical assistant
- Updated-data and assistant validation evidence

