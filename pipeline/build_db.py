"""Load clean CSVs into a database (tables + date dimension + reporting views).

Run:  python -m pipeline.build_db                      # SQLite file data/smartmart.db
      python -m pipeline.build_db --url "postgresql://..."   # Stage 2: Supabase Postgres
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import make_url

import db

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ["v_monthly_sales", "v_region_summary", "v_product_summary",
         "v_customer_summary", "v_customer_first", "v_sales"]  # dependents first
ID_COLS = {"customer_id": str, "product_id": str, "store_id": str, "transaction_id": str}


def make_dim_date(dates: pd.Series) -> pd.DataFrame:
    d = pd.date_range(pd.to_datetime(dates).min(), pd.to_datetime(dates).max(), freq="D")
    return pd.DataFrame({
        "date": d.strftime("%Y-%m-%d"), "year": d.year, "quarter": d.quarter, "month": d.month,
        "month_name": d.strftime("%B"), "year_month": d.strftime("%Y-%m"),
        "day_of_week": d.strftime("%A"), "is_weekend": (d.dayofweek >= 5).astype(int),
    })


def build(clean_dir: Path | str = ROOT / "data" / "clean", url: str | None = None) -> dict:
    clean_dir = Path(clean_dir)
    url = url or db.sqlite_url()
    if url.startswith("sqlite"):
        Path(make_url(url).database).parent.mkdir(parents=True, exist_ok=True)
    engine = db.get_engine(url, must_exist=False)

    tables = {n: pd.read_csv(clean_dir / f"{n}.csv", dtype=ID_COLS)
              for n in ("customers", "products", "stores", "transactions")}
    tables["dim_date"] = make_dim_date(tables["transactions"]["date"])
    statements = [s.strip() for s in (ROOT / "sql" / "schema_views.sql").read_text().split(";") if s.strip()]

    with engine.begin() as conn:
        for v in VIEWS:
            conn.execute(text(f"DROP VIEW IF EXISTS {v}"))
        for name, df in tables.items():
            df.to_sql(name, conn, if_exists="replace", index=False, method="multi", chunksize=500)
        for stmt in statements:
            conn.exec_driver_sql(stmt)
        counts = {n: conn.execute(text(f"SELECT COUNT(*) FROM {n}")).scalar() for n in tables}
        counts["v_sales"] = conn.execute(text("SELECT COUNT(*) FROM v_sales")).scalar()
    engine.dispose()
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clean", default=ROOT / "data" / "clean")
    ap.add_argument("--url", default=None, help="Target DB URL (default: bundled SQLite file)")
    a = ap.parse_args()
    print("rows loaded:", build(a.clean, a.url))


if __name__ == "__main__":
    main()
