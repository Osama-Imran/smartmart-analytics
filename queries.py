"""All SQL used by the dashboard.

Every query reads the v_sales view (one row per transaction, already joined to
product, store, date and customer). Filters are applied identically everywhere
through where(), so a KPI card and its chart can never disagree.
An empty filter tuple means "no restriction" for that field.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import text


@dataclass(frozen=True)
class Filters:
    start: str
    end: str
    regions: tuple = ()
    cities: tuple = ()
    categories: tuple = ()
    channels: tuple = ()


_FILTER_COLS = (("region", "regions"), ("city", "cities"), ("category", "categories"), ("channel", "channels"))
GRAINS = {"Daily": "s.date", "Monthly": "s.year_month", "Yearly": "s.year"}
DIMENSIONS = {"category": "s.category", "region": "s.region", "city": "s.city", "channel": "s.channel",
              "payment_method": "s.payment_method", "store": "s.store_name"}


def where(f: Filters) -> tuple[str, dict]:
    clauses = ["s.date BETWEEN :start AND :end"]
    params: dict = {"start": f.start, "end": f.end}
    for col, attr in _FILTER_COLS:
        values = getattr(f, attr)
        if values:
            keys = [f"{col}_{i}" for i in range(len(values))]
            clauses.append(f"s.{col} IN ({', '.join(':' + k for k in keys)})")
            params.update(zip(keys, values))
    return " AND ".join(clauses), params


def _df(engine, sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params or {})


def date_bounds(engine):
    row = _df(engine, "SELECT MIN(date) AS lo, MAX(date) AS hi FROM v_sales").iloc[0]
    return row.lo, row.hi


def filter_options(engine) -> dict:
    stores = _df(engine, "SELECT DISTINCT region, city FROM stores ORDER BY region, city")
    return {
        "regions": sorted(stores.region.unique()),
        "region_city": list(zip(stores.region, stores.city)),
        "categories": list(_df(engine, "SELECT DISTINCT category FROM products ORDER BY category").category),
        "channels": list(_df(engine, "SELECT DISTINCT channel FROM stores ORDER BY channel").channel),
    }


def kpis(engine, f: Filters) -> dict:
    w, p = where(f)
    base = _df(engine, f"""
        SELECT COALESCE(SUM(s.revenue), 0) AS revenue,
               COALESCE(SUM(s.profit), 0) AS profit,
               COUNT(DISTINCT s.transaction_id) AS orders,
               COALESCE(SUM(s.quantity), 0) AS units,
               COUNT(DISTINCT s.customer_id) AS active_customers
        FROM v_sales s WHERE {w}""", p).iloc[0]
    repeat = _df(engine, f"""
        WITH c AS (
            SELECT s.customer_id, COUNT(DISTINCT s.transaction_id) AS orders
            FROM v_sales s WHERE {w} AND s.customer_id IS NOT NULL GROUP BY s.customer_id)
        SELECT COALESCE(SUM(CASE WHEN orders >= 2 THEN 1 ELSE 0 END), 0) AS n FROM c""", p).iloc[0, 0]
    new = _df(engine, f"""
        SELECT COUNT(*) AS n FROM v_customer_first f
        WHERE f.first_date BETWEEN :start AND :end
          AND f.customer_id IN (SELECT s.customer_id FROM v_sales s WHERE {w} AND s.customer_id IS NOT NULL)""",
              p).iloc[0, 0]
    revenue, profit = float(base.revenue), float(base.profit)
    orders, active, repeat = int(base.orders), int(base.active_customers), int(repeat)
    return {
        "revenue": revenue, "profit": profit, "orders": orders, "units": int(base.units),
        "aov": revenue / orders if orders else 0.0,
        "margin_pct": 100 * profit / revenue if revenue else 0.0,
        "active_customers": active, "repeat_customers": repeat,
        "repeat_rate": repeat / active if active else 0.0,
        "new_customers": int(new),
    }


def trend(engine, f: Filters, grain: str) -> pd.DataFrame:
    if grain not in GRAINS:
        raise ValueError(f"grain must be one of {list(GRAINS)}")
    col = GRAINS[grain]
    w, p = where(f)
    return _df(engine, f"""
        SELECT {col} AS period, SUM(s.revenue) AS revenue, SUM(s.profit) AS profit,
               COUNT(DISTINCT s.transaction_id) AS orders
        FROM v_sales s WHERE {w} GROUP BY {col} ORDER BY {col}""", p)


def by_dimension(engine, f: Filters, dim: str) -> pd.DataFrame:
    if dim not in DIMENSIONS:
        raise ValueError(f"dim must be one of {list(DIMENSIONS)}")
    col = DIMENSIONS[dim]
    w, p = where(f)
    df = _df(engine, f"""
        SELECT {col} AS label, SUM(s.revenue) AS revenue, SUM(s.profit) AS profit,
               COUNT(DISTINCT s.transaction_id) AS orders, SUM(s.quantity) AS units
        FROM v_sales s WHERE {w} GROUP BY {col} ORDER BY revenue DESC""", p)
    df["margin_pct"] = 100 * df.profit / df.revenue
    return df


def products(engine, f: Filters) -> pd.DataFrame:
    w, p = where(f)
    return _df(engine, f"""
        SELECT s.product_id, s.product_name, s.category, SUM(s.quantity) AS units,
               COUNT(DISTINCT s.transaction_id) AS orders, SUM(s.revenue) AS revenue, SUM(s.profit) AS profit
        FROM v_sales s WHERE {w}
        GROUP BY s.product_id, s.product_name, s.category ORDER BY revenue DESC""", p)


def customer_segments(engine, f: Filters) -> pd.DataFrame:
    """One row per identified customer in the filtered slice, with spend tier.
    Tier = percent rank of total spend: top 20% High, next 40% Medium, rest Low."""
    w, p = where(f)
    return _df(engine, f"""
        WITH c AS (
            SELECT s.customer_id, s.customer_name, COUNT(DISTINCT s.transaction_id) AS orders,
                   SUM(s.revenue) AS total_spend
            FROM v_sales s WHERE {w} AND s.customer_id IS NOT NULL
            GROUP BY s.customer_id, s.customer_name),
        r AS (SELECT c.*, PERCENT_RANK() OVER (ORDER BY c.total_spend) AS pr FROM c)
        SELECT customer_id, customer_name, orders, total_spend,
               CASE WHEN pr >= 0.8 THEN 'High' WHEN pr >= 0.4 THEN 'Medium' ELSE 'Low' END AS spend_tier
        FROM r ORDER BY total_spend DESC, customer_id""", p)


def segment_summary(seg: pd.DataFrame) -> pd.DataFrame:
    order = ["High", "Medium", "Low"]
    g = seg.groupby("spend_tier").agg(customers=("customer_id", "count"), revenue=("total_spend", "sum"))
    g = g.reindex(order).fillna(0)
    total = g.revenue.sum()
    g["avg_spend"] = g.revenue / g.customers.where(g.customers > 0)
    g["share_of_revenue"] = g.revenue / total if total else 0.0
    return g.reset_index()


def new_vs_returning(engine, f: Filters) -> pd.DataFrame:
    """Per month: customers making their first-ever purchase vs customers who bought before."""
    w, p = where(f)
    return _df(engine, f"""
        SELECT s.year_month,
               COUNT(DISTINCT CASE WHEN fc.first_year_month = s.year_month THEN s.customer_id END) AS new_customers,
               COUNT(DISTINCT CASE WHEN fc.first_year_month < s.year_month THEN s.customer_id END) AS returning_customers
        FROM v_sales s JOIN v_customer_first fc ON fc.customer_id = s.customer_id
        WHERE {w} GROUP BY s.year_month ORDER BY s.year_month""", p)


def export_transactions(engine, f: Filters) -> pd.DataFrame:
    w, p = where(f)
    return _df(engine, f"""
        SELECT s.transaction_id, s.date, s.customer_id, s.customer_name, s.product_id, s.product_name,
               s.category, s.store_name, s.city, s.region, s.channel, s.quantity, s.discount,
               s.payment_method, s.revenue, s.profit
        FROM v_sales s WHERE {w} ORDER BY s.date, s.transaction_id""", p)
