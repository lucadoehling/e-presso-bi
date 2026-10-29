# E-Presso PBIX inspection and Looker Studio migration methods

## Purpose

This report documents how AI-assisted command-line tools were used to inspect
the supplied Power BI report, recover its analytical definitions, prepare the
original source data on macOS, and create a validated table for Looker Studio.

The PBIX file was **not directly converted into a Looker Studio report**. A PBIX
contains a Power BI-specific semantic model, report layout, and visual
configuration that Looker Studio cannot import. Instead, the migration used the
PBIX as evidence of the existing model and visuals, then rebuilt the analysis
from the original Access, Excel, and tab-delimited source files.

## Files examined

- `POWER BI-MOS.pbix`: existing Power BI model and report
- `Support_EX_B_Sales.accdb`: Categories, Products, and Sales tables
- `Support_EX_B_Survey.xlsx`: annual survey results
- `Support_EX_B_Stores.csv`: tab-delimited store information
- Power BI assignment walkthrough PDF: required model and visual instructions

Original files were treated as read-only. Generated data was written to the
Git-ignored `data/processed` directory.

## Software and command-line tools

### Built-in file inspection

The macOS `file` command identified each file format before processing:

```bash
file POWER\ BI-MOS.pbix
file Support_EX_B_Sales.accdb
file Support_EX_B_Survey.xlsx
file Support_EX_B_Stores.csv
```

This confirmed that the PBIX was a ZIP-based package, the sales source was a
Microsoft Access database, and the survey source was an Excel workbook.

### PBIX package inspection with `unzip`

The PBIX package contents were listed without modifying the report:

```bash
unzip -l POWER\ BI-MOS.pbix
```

Important package entries included:

- `DataModel`: compressed Power BI semantic model
- `Report/definition/pages/...`: report-page definitions
- `Report/definition/pages/.../visuals/.../visual.json`: visual definitions
- `Metadata` and `Settings`: report metadata

Individual report definitions were read from standard output rather than
extracted over the original file:

```bash
unzip -p POWER\ BI-MOS.pbix Report/definition/report.json
unzip -p POWER\ BI-MOS.pbix Report/definition/pages/pages.json
```

The visual JSON files established that the report contained:

- Revenue by store type
- Annual revenue trend
- Monthly revenue percentage
- Category slicer
- Revenue-versus-satisfaction scatterplot

### Semantic-model inspection with PBIXRay

PBIXRay was installed in a temporary Python environment. A temporary environment
kept the inspection dependency separate from the final application:

```bash
python3 -m venv /tmp/epresso-pbix-venv
/tmp/epresso-pbix-venv/bin/pip install pbixray pandas
```

The model was then inspected with Python:

```python
from pbixray import PBIXRay

model = PBIXRay("POWER BI-MOS.pbix")
print(model.tables)
print(model.schema)
print(model.relationships)
print(model.power_query)
sales = model.get_table("Sales")
model.close()
```

This recovered table names, columns, embedded rows, Power Query expressions,
and reported relationships. It also showed the original Windows file paths used
by Power Query. Those paths could not be reused on macOS or in Looker Studio.

The PBIX relationship metadata initially appeared to connect the wrong sales
field to the survey table. The original assignment walkthrough and independent
key testing confirmed the intended relationship:

```text
Sales[StoreYear] many-to-one Survey Results[Survey ID]
```

For example, `SH01_25` matches `SH01_25`. `Sales[Store ID]` contains values such
as `SH01`, which do not match store-year Survey IDs.

## Reading the Access database on macOS

Microsoft Access is not available natively on macOS. The open-source `mdbtools`
package provided a read-only extraction route:

```bash
brew install mdbtools
mdb-tables -1 Support_EX_B_Sales.accdb
mdb-schema Support_EX_B_Sales.accdb access
mdb-export Support_EX_B_Sales.accdb Sales
```

The database contained:

| Table | Rows | Grain |
|---|---:|---|
| Categories | 5 | One row per category ID |
| Products | 20 | One row per product ID |
| Sales | 25,200 | One store-month-product revenue record |

The production preparation script calls `mdb-export` through Python's
`subprocess` module and reads the returned CSV text into pandas. It does not
write to the Access database.

## Reading the Excel and store sources

The survey workbook was read with pandas and openpyxl. The actual field names
are on the third worksheet row, after a report title and blank row:

```python
survey = pandas.read_excel(
    survey_file,
    sheet_name="Survey Results",
    header=2,
    dtype=str,
)
```

The store file has a `.csv` extension but uses tab delimiters:

```python
stores = pandas.read_csv(stores_file, sep="\t", dtype=str)
```

`Phone` and `Manager` were removed because the assignment does not require
those fields. Postal codes and all identifiers were preserved as text.

## Reproducible Python preparation

The repository contains `scripts/prepare_data.py`. It performs these steps:

1. Locates one Access, survey, and store source file.
2. Exports Categories, Products, and Sales from Access.
3. Reads and cleans the Excel and tab-delimited sources.
4. Converts sales dates and revenue to analytical data types.
5. Tests primary-key completeness and uniqueness.
6. Performs four validated many-to-one left joins.
7. Confirms joins do not change the sales row count or revenue total.
8. Writes normalized tables, a flat analytical table, and quality reports.

The script is run from the repository root with:

```bash
python scripts/prepare_data.py \
  --input-dir .. \
  --output-dir data/processed
```

The four joins are:

| Left key | Right key | Added information |
|---|---|---|
| `Sales[Category ID]` | `Categories[Category ID]` | Category name |
| `Sales[Product ID]` | `Products[Product ID]` | Product name |
| `Sales[Store ID]` | `Stores[ID]` | Store type and geography |
| `Sales[StoreYear]` | `Survey Results[Survey ID]` | Annual survey values |

Each pandas merge uses `validate="many_to_one"`. After each merge, the script
checks row count, unmatched keys, and total revenue. This prevents duplicate
dimension keys from multiplying sales rows.

## Validation results

The final `sales_enriched.csv` contains 25,200 rows and 19 columns. The joins
preserved the original sales grain and produced these controls:

| Control | Result |
|---|---:|
| Five-year revenue | $42,174,440 |
| Website revenue | $27,218,880 |
| Brick-and-mortar revenue | $14,955,560 |
| Date coverage | January 2025-December 2029 |
| Duplicate Sales IDs | 0 |
| Unmatched relationship keys | 0 |
| Missing Satisfaction values | 5 store-year records |
| Missing Interest values | 5 store-year records |

The five missing survey records belong to the website and remain null. They
were not replaced with zero.

## Migration into Looker Studio

The prepared table is uploaded to Google Sheets and connected to Looker Studio.
The Power BI visuals are recreated manually because report-layout definitions
and Power BI interactions cannot be imported into Looker Studio.

The Looker Studio report reproduces the assignment's analytical intent:

- Five-year revenue total
- Website versus brick-and-mortar revenue
- Annual revenue trend
- Monthly revenue pattern
- Category filtering
- Store Type, Market, and City drill hierarchy
- Revenue-versus-satisfaction scatterplot
- Store revenue and satisfaction table

The report uses the term **revenue**, not profit, because the supplied data does
not contain costs. The satisfaction scatterplot is presented as an association,
not proof of causation.

## How AI was used

AI served as a development and analytical assistant. It helped:

- Identify Mac-compatible tools for Access and PBIX inspection
- Generate and explain command-line commands
- Read PBIX metadata and visual JSON
- Compare candidate relationship keys using actual values
- Write the reproducible Python preparation script
- Add validation controls and explanatory comments
- Document assumptions, limitations, and results

Human judgment remained necessary to choose Looker Studio, approve software
installation, provide the course files, confirm that the assignment walkthrough
controlled the model design, and review the analytical interpretation. AI did
not invent missing data, modify the original source files, publish raw data, or
claim that revenue measured profitability.

## Limitations

- Looker Studio cannot directly import a PBIX report.
- Power BI visual formatting and interactions must be rebuilt manually.
- Original Power Query paths referenced a Windows Downloads folder and were not
  portable to macOS.
- The website lacks satisfaction and interest survey values.
- A trend line shows association only; it does not establish causation.
- Revenue cannot answer profitability questions without cost data.

