# E-Presso data dictionary

## Source tables

### Sales

Grain: one monthly revenue record for one store and one product.

- `Sales ID`: unique sales-row identifier
- `Date`: month-end date, January 2025 through December 2029
- `Store ID`: store or website identifier
- `StoreYear`: store-year key matching `Survey ID`
- `Category ID`: product-category key
- `Product ID`: product key
- `Revenue`: stored monthly revenue in dollars

### Products

Grain: one row per product ID. Product names are not unique; joins use
`Product ID`.

### Categories

Grain: one row per category ID.

### E-Presso Stores

Grain: one row per store or website ID. The preparation pipeline excludes
phone and manager fields because they are not needed for the analysis.

### Survey Results

Grain: one annual survey record per store or website. Satisfaction uses a
0-to-5 scale and Interest uses a 0-to-100 scale. The website records have
missing Satisfaction and Interest values in every year.

## Verified relationships

- `Sales[Category ID]` many-to-one `Categories[Category ID]`
- `Sales[Product ID]` many-to-one `Products[Product ID]`
- `Sales[Store ID]` many-to-one `E-Presso Stores[ID]`
- `Sales[StoreYear]` many-to-one `Survey Results[Survey ID]`

All four joins preserve the sales row count and revenue total.

## Prepared analytical table

`sales_enriched.csv` retains the sales-table grain and adds category, product,
store, geography, and annual survey attributes. The join does not duplicate
sales rows or inflate revenue.
