#!/usr/bin/env python3
"""Prepare and validate E-Presso data for Looker Studio and Streamlit."""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd


# Known total from the independently inspected source data. The script stops if a
# future run produces a different amount, which helps catch accidental data loss
# or revenue duplication.
EXPECTED_REVENUE = 42_174_440.00


def find_one(folder: Path, pattern: str) -> Path:
    """Find one required source file and reject missing or ambiguous matches."""

    # Excel creates temporary files beginning with "~$" while a workbook is open.
    # Those files are not valid inputs, so exclude them from the match.
    matches = sorted(path for path in folder.glob(pattern) if not path.name.startswith("~$"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected exactly one file matching {pattern!r} in {folder}; found {len(matches)}."
        )
    return matches[0]


def read_access_table(database: Path, table: str) -> pd.DataFrame:
    """Export one Access table with mdbtools and load the CSV text into pandas."""

    # pandas cannot reliably read an .accdb file directly on macOS. mdb-export is
    # the read-only, Mac-compatible bridge used for this project.
    if shutil.which("mdb-export") is None:
        raise RuntimeError("mdb-export was not found. On macOS, run: brew install mdbtools")
    result = subprocess.run(
        ["mdb-export", str(database), table],
        check=True,
        capture_output=True,
        text=True,
    )
    return pd.read_csv(io.StringIO(result.stdout), dtype=str, quoting=csv.QUOTE_MINIMAL)


def require_unique(df: pd.DataFrame, column: str, table: str) -> None:
    """Confirm that a column is safe to use as the one-side of a relationship."""

    if df[column].isna().any() or df[column].duplicated().any():
        raise ValueError(f"{table}[{column}] must be complete and unique.")


def validated_join(
    sales: pd.DataFrame,
    dimension: pd.DataFrame,
    *,
    left_on: str,
    right_on: str,
    label: str,
) -> pd.DataFrame:
    """Perform a many-to-one join without changing sales rows or revenue."""

    # Save control values before each join. If the dimension has duplicate keys,
    # pandas' validate option fails; the explicit checks also catch lost rows,
    # unmatched keys, and revenue inflation.
    before_rows = len(sales)
    before_revenue = sales["Revenue"].sum()
    joined = sales.merge(
        dimension,
        how="left",
        left_on=left_on,
        right_on=right_on,
        validate="many_to_one",
    )
    if len(joined) != before_rows:
        raise ValueError(f"{label} join changed row count from {before_rows} to {len(joined)}.")
    if joined["Revenue"].sum() != before_revenue:
        raise ValueError(f"{label} join changed the revenue total.")
    if joined[right_on].isna().any():
        raise ValueError(f"{label} join contains unmatched keys.")
    return joined


def quality_rows(tables: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    """Build column-level profiling rows for the data-quality report."""

    rows: list[dict[str, object]] = []
    for table_name, df in tables.items():
        for column in df.columns:
            rows.append(
                {
                    "table": table_name,
                    "column": column,
                    "rows": len(df),
                    "missing": int(df[column].isna().sum()),
                    "distinct_non_null": int(df[column].nunique(dropna=True)),
                    "dtype": str(df[column].dtype),
                }
            )
    return rows


def prepare(input_dir: Path, output_dir: Path) -> dict[str, object]:
    """Run the complete source-to-validated-output preparation workflow."""

    # Stage 1: locate the three original source files. Their filenames may have
    # suffixes such as " (1)", so the patterns allow text before the extension.
    access_file = find_one(input_dir, "Support_EX_B_Sales*.accdb")
    survey_file = find_one(input_dir, "Support_EX_B_Survey*.xlsx")
    stores_file = find_one(input_dir, "Support_EX_B_Stores*.csv")

    # Stage 2: load the three Access tables without modifying the database.
    categories = read_access_table(access_file, "Categories")
    products = read_access_table(access_file, "Products")
    sales = read_access_table(access_file, "Sales")

    # The stores source uses tabs even though its extension is .csv. Phone and
    # Manager are removed because the assignment does not use those fields.
    stores = pd.read_csv(stores_file, sep="\t", dtype=str)
    stores = stores.drop(columns=["Phone", "Manager"])

    # Row 3 contains the actual field names; the first two rows are a report title
    # and a blank row, as described in the assignment walkthrough.
    survey = pd.read_excel(survey_file, sheet_name="Survey Results", header=2, dtype=str)
    survey = survey.dropna(how="all")

    # Stage 3: convert analytical fields from source text into dates and numbers.
    # Invalid sales dates or revenue raise an error; missing survey scores are
    # expected for the website and remain null rather than becoming zero.
    sales["Date"] = pd.to_datetime(sales["Date"], format="%m/%d/%y %H:%M:%S")
    sales["Revenue"] = pd.to_numeric(sales["Revenue"], errors="raise")
    survey["Satisfaction"] = pd.to_numeric(survey["Satisfaction"], errors="coerce")
    survey["Interest"] = pd.to_numeric(survey["Interest"], errors="coerce")

    # Stage 4: verify primary keys before using the tables in relationships.
    require_unique(categories, "Category ID", "Categories")
    require_unique(products, "Product ID", "Products")
    require_unique(stores, "ID", "E-Presso Stores")
    require_unique(survey, "Survey ID", "Survey Results")
    require_unique(sales, "Sales ID", "Sales")

    if sales.isna().any().any():
        raise ValueError("Sales contains missing values.")
    if (sales["Revenue"] < 0).any():
        raise ValueError("Sales contains negative revenue values.")

    # Stage 5: build the flat analytical table with four LEFT JOIN operations.
    #
    # Sales is always the left table. That means the result must retain the Sales
    # grain: one row per store, month, and product. Each lookup table is on the
    # right and must have exactly one row for every matching key. The
    # validate="many_to_one" rule inside validated_join enforces that cardinality.
    # After every join, validated_join also confirms that:
    #   1. the row count still equals the Sales row count,
    #   2. every left-side key found a right-side match, and
    #   3. total Revenue did not change.
    # These controls prevent a duplicate lookup key from multiplying sales rows
    # and inflating revenue.
    #
    # Temporary names such as Category Key prevent pandas from creating
    # confusing _x and _y suffixes when two tables contain similarly named keys.

    # JOIN 1
    # Left:  Sales[Category ID] (many sales rows per category)
    # Right: Categories[Category ID] (one row per category)
    # Adds:  the readable Category name
    enriched = validated_join(
        sales,
        categories.rename(columns={"Category ID": "Category Key"}),
        left_on="Category ID",
        right_on="Category Key",
        label="Category",
    ).drop(columns="Category Key")

    # JOIN 2
    # Left:  enriched Sales[Product ID] (many sales rows per product)
    # Right: Products[Product ID] (one row per product)
    # Adds:  the readable Product name. Product ID is required because the
    #        Product text is not unique (three products are named "Base Model").
    enriched = validated_join(
        enriched,
        products.rename(columns={"Product ID": "Product Key"}),
        left_on="Product ID",
        right_on="Product Key",
        label="Product",
    ).drop(columns="Product Key")

    # JOIN 3
    # Left:  enriched Sales[Store ID] (many sales rows per store)
    # Right: E-Presso Stores[ID] (one row per store or website)
    # Adds:  City, State, PostalCode, StoreType, Market, and Location
    enriched = validated_join(
        enriched,
        stores.rename(columns={"ID": "Store Key"}),
        left_on="Store ID",
        right_on="Store Key",
        label="Store",
    ).drop(columns="Store Key")

    # JOIN 4
    # Left:  enriched Sales[StoreYear] (many monthly/product rows per store-year)
    # Right: Survey Results[Survey ID] (one annual survey row per store-year)
    # Adds:  Survey Year, Satisfaction, and Interest
    #
    # Example: Sales StoreYear "SH01_25" matches Survey ID "SH01_25".
    # Do not join Sales[Store ID] to Survey Results[Survey ID]: values such as
    # "SH01" and "SH01_25" are different keys and would produce no matches.
    enriched = validated_join(
        enriched,
        survey.rename(
            columns={
                "Survey ID": "Survey Key",
                "Store ID": "Survey Store ID",
                "Year": "Survey Year",
            }
        ),
        left_on="StoreYear",
        right_on="Survey Key",
        label="Survey",
    ).drop(columns="Survey Key")

    # Stage 6: reconcile the prepared data to the known five-year revenue total.
    revenue_total = float(sales["Revenue"].sum())
    if revenue_total != EXPECTED_REVENUE:
        raise ValueError(
            f"Revenue control failed: expected {EXPECTED_REVENUE:.2f}, got {revenue_total:.2f}."
        )

    # Stage 7: export both normalized tables and a flat Looker Studio-ready table.
    # These generated files stay local because data/processed is Git-ignored.
    output_dir.mkdir(parents=True, exist_ok=True)
    exports = {
        "categories.csv": categories,
        "products.csv": products,
        "stores.csv": stores,
        "survey_results.csv": survey,
        "sales.csv": sales,
        "sales_enriched.csv": enriched,
    }
    for filename, frame in exports.items():
        frame.to_csv(output_dir / filename, index=False, date_format="%Y-%m-%d")

    # The quality report records row count, missing count, distinct count, and
    # inferred data type for every column in every prepared table.
    pd.DataFrame(
        quality_rows(
            {
                "Categories": categories,
                "Products": products,
                "E-Presso Stores": stores,
                "Survey Results": survey,
                "Sales": sales,
                "Sales Enriched": enriched,
            }
        )
    ).to_csv(output_dir / "data_quality_report.csv", index=False)

    # A compact machine-readable summary supports later Streamlit checks and the
    # Looker Studio versus Streamlit validation table.
    summary: dict[str, object] = {
        "source_files": {
            "access": access_file.name,
            "survey": survey_file.name,
            "stores": stores_file.name,
        },
        "rows": {name: len(frame) for name, frame in exports.items()},
        "sales_date_min": sales["Date"].min().date().isoformat(),
        "sales_date_max": sales["Date"].max().date().isoformat(),
        "revenue_total": revenue_total,
        "expected_revenue_total": EXPECTED_REVENUE,
        "revenue_control_passed": revenue_total == EXPECTED_REVENUE,
        "survey_missing_satisfaction": int(survey["Satisfaction"].isna().sum()),
        "survey_missing_interest": int(survey["Interest"].isna().sum()),
        "joins_preserved_sales_rows": len(enriched) == len(sales),
        "joins_preserved_revenue": float(enriched["Revenue"].sum()) == revenue_total,
    }
    (output_dir / "validation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def parse_args() -> argparse.Namespace:
    """Read the source and destination folders supplied on the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    return parser.parse_args()


def main() -> None:
    """Run preparation and print the validation summary for the user."""

    args = parse_args()
    summary = prepare(args.input_dir.resolve(), args.output_dir.resolve())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
