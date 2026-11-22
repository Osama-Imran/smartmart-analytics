# SmartMart Retail: Sales & Customer Analytics

A cloud analytics solution built only on free tiers: **GitHub** (code + data) and **Streamlit Community Cloud** (hosting), with an optional **Supabase Postgres** upgrade (Stage 2).

Think of it as a small factory line: messy CSVs go in, a cleaning script produces tidy tables, SQL views act as the shelves, and Streamlit is the shop window.

```
generate_data.py  ->  clean_data.py  ->  build_db.py  ->  SQL views  ->  app.py (Streamlit)
 raw CSVs (dirty)     clean CSVs +        SQLite file       v_sales etc.    filters, KPIs, charts,
                      cleaning_report     (or Postgres)                     segments, CSV export
```

## Business scenario

SmartMart sells electronics, clothing, home appliances and grocery through 10 physical stores and 4 online hubs in 8 Pakistani cities (4 regions). Sales were scattered across spreadsheets. This project consolidates them and answers: how are we trending, who are our best customers, which products and regions win?

Data is **synthetic** (seeded, reproducible): about 15,000 transactions, 2,000 customers, 40 products, 14 stores, Jan 2025 to Oct 2026, amounts in PKR. Raw files are deliberately dirty so the cleaning step has real work to do.

## Data model

| Table | Columns |
|---|---|
| customers | customer_id, name, city, region, signup_date |
| products | product_id, product_name, category, unit_price, unit_cost |
| stores | store_id, store_name, city, region, channel (Store / Online) |
| transactions | transaction_id, date, customer_id, product_id, store_id, quantity, discount, payment_method |
| dim_date | date, year, quarter, month, month_name, year_month, day_of_week, is_weekend |

Views (`sql/schema_views.sql`): `v_sales` (fact + all dimensions + revenue/cost/profit), `v_customer_first`, `v_customer_summary` (with spend tier), `v_product_summary`, `v_region_summary`, `v_monthly_sales`.

One transaction = one order line = one order (one product per order). Prices are current list prices (no price history).

## KPI definitions

| KPI | Definition |
|---|---|
| Revenue | quantity x unit_price x (1 - discount) |
| Profit | revenue - quantity x unit_cost |
| Orders | distinct transaction_id |
| Average order value | revenue / orders |
| Active customers | distinct customer_id with at least 1 order in the filtered slice |
| Repeat-buyer rate | customers with 2 or more orders in the slice / active customers |
| New customers | customers whose first-ever purchase date falls inside the selected date range |
| Spend tier | percent rank of a customer's total spend: top 20% High, next 40% Medium, bottom 40% Low |

Guest orders (no customer ID, about 2%) count in revenue, profit and orders but not in customer metrics.

## Data-quality rules (clean_data.py)

| Problem injected into raw files | What the cleaner does |
|---|---|
| Exact duplicate transactions | Removed, counted |
| Missing customer_id | Kept as guest sale |
| Quantity zero or negative, impossible or unparseable dates, unknown product IDs | Rejected to `rejected_transactions.csv` with a reason |
| Dates written DD/MM/YYYY | Parsed and standardised to ISO |
| Missing discount | Filled with 0 |
| Payment method casing and spaces | Normalised |
| Same product under two IDs and spellings | Merged to one ID, transactions remapped |
| Product names or categories in odd case | Standardised |
| Duplicate customers, mixed-case or missing city/name | Deduped, normalised, "Unknown" where blank |

Every run writes `data/clean/cleaning_report.json`, and rows in = rows out + duplicates + rejected is asserted.

## Run locally

```bash
pip install -r requirements-dev.txt
python -m pipeline.run_all      # generate -> clean -> build data/smartmart.db
streamlit run app.py
pytest -q                       # 31 tests: validation, KPI accuracy, filters, errors, UI
python check_resources.py       # timings, memory, sizes -> docs/RESOURCE_REPORT.md
```

## Deploy (Stage 1: GitHub + Streamlit Community Cloud)

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the click-by-click steps and the Supabase upgrade. Free-tier limits and measured usage: [docs/FREE_TIER_LIMITS.md](docs/FREE_TIER_LIMITS.md).

## Project layout

```
app.py                  Streamlit UI
queries.py              every SQL query + shared filter logic
db.py                   SQLite by default, Postgres when DATABASE_URL is set
pipeline/               generate_data, clean_data, build_db, run_all
sql/schema_views.sql    indexes + views (SQLite and Postgres compatible)
data/raw, data/clean    input CSVs and cleaned output (committed so the app deploys with no build step)
data/smartmart.db       SQLite database used by the deployed app
tests/                  pytest suite
.github/workflows/ci.yml  free CI: runs the tests on every push
```
