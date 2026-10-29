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


EXPECTED_REVENUE = 42_174_440.00


def find_one(folder: Path, pattern: str) -> Path:
    matches = sorted(path for path in folder.glob(pattern) if not path.name.startswith("~$"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected exactly one file matching {pattern!r} in {folder}; found {len(matches)}."
        )
    return matches[0]


def read_access_table(database: Path, table: str) -> pd.DataFrame:
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
    access_file = find_one(input_dir, "Support_EX_B_Sales*.accdb")
    survey_file = find_one(input_dir, "Support_EX_B_Survey*.xlsx")
    stores_file = find_one(input_dir, "Support_EX_B_Stores*.csv")

    categories = read_access_table(access_file, "Categories")
    products = read_access_table(access_file, "Products")
    sales = read_access_table(access_file, "Sales")

    stores = pd.read_csv(stores_file, sep="\t", dtype=str)
    stores = stores.drop(columns=["Phone", "Manager"])

    survey = pd.read_excel(survey_file, sheet_name="Survey Results", header=2, dtype=str)
    survey = survey.dropna(how="all")

    sales["Date"] = pd.to_datetime(sales["Date"], format="%m/%d/%y %H:%M:%S")
    sales["Revenue"] = pd.to_numeric(sales["Revenue"], errors="raise")
    survey["Satisfaction"] = pd.to_numeric(survey["Satisfaction"], errors="coerce")
    survey["Interest"] = pd.to_numeric(survey["Interest"], errors="coerce")

    require_unique(categories, "Category ID", "Categories")
    require_unique(products, "Product ID", "Products")
    require_unique(stores, "ID", "E-Presso Stores")
    require_unique(survey, "Survey ID", "Survey Results")
    require_unique(sales, "Sales ID", "Sales")

    if sales.isna().any().any():
        raise ValueError("Sales contains missing values.")
    if (sales["Revenue"] < 0).any():
        raise ValueError("Sales contains negative revenue values.")

    enriched = validated_join(
        sales,
        categories.rename(columns={"Category ID": "Category Key"}),
        left_on="Category ID",
        right_on="Category Key",
        label="Category",
    ).drop(columns="Category Key")
    enriched = validated_join(
        enriched,
        products.rename(columns={"Product ID": "Product Key"}),
        left_on="Product ID",
        right_on="Product Key",
        label="Product",
    ).drop(columns="Product Key")
    enriched = validated_join(
        enriched,
        stores.rename(columns={"ID": "Store Key"}),
        left_on="Store ID",
        right_on="Store Key",
        label="Store",
    ).drop(columns="Store Key")
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

    revenue_total = float(sales["Revenue"].sum())
    if revenue_total != EXPECTED_REVENUE:
        raise ValueError(
            f"Revenue control failed: expected {EXPECTED_REVENUE:.2f}, got {revenue_total:.2f}."
        )

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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = prepare(args.input_dir.resolve(), args.output_dir.resolve())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
