# E-Presso Business Intelligence

Course project for analyzing E-Presso sales and market-survey data.

The project will include:

- A Looker Studio baseline analysis
- A Python and Streamlit analytical dashboard
- Reusable analytical functions

## Data preparation

The preparation pipeline reads the original E-Presso Access, Excel, and
tab-delimited store files without modifying them. It validates table keys and
relationships before creating a flat analytical table for Looker Studio and
the later Streamlit application.

Requirements:

- Python 3.9 or newer
- `mdbtools` installed on macOS (`brew install mdbtools`)
- Python packages in `requirements.txt`

Run from the repository root:

```bash
python scripts/prepare_data.py \
  --input-dir .. \
  --output-dir data/processed
```

The command checks the expected five-year revenue control total of
`$42,174,440.00`. Raw and generated data are excluded from Git.

See `docs/data_dictionary.md` for table grain, fields, and relationships.
See `docs/pbix_migration_methods.md` for the PBIX inspection, command-line
workflow, Looker Studio migration method, validation controls, and AI-use record.
- A controlled analytical assistant
- Validation and updated-data test evidence

## Current status

Source inventory and relationship validation are in progress. Raw course datasets are kept outside this public repository.

## Data period

The supplied sales data covers January 2025 through December 2029.

## Data handling

The application will load user-supplied course files at runtime. Raw Access, Excel, Power BI, and private data files are excluded from version control.

