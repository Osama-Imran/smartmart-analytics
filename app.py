"""SmartMart Retail - Sales & Customer Analytics (Streamlit)."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

import db
import queries as q

st.set_page_config(page_title="SmartMart Analytics", layout="wide")
REPORT = Path(__file__).parent / "data" / "clean" / "cleaning_report.json"


def money(x: float) -> str:
    return f"Rs {x:,.0f}"


@st.cache_resource
def get_engine():
    url = None
    try:
        url = st.secrets.get("DATABASE_URL")
    except Exception:  # no secrets file: use the bundled SQLite database
        pass
    return db.get_engine(url)


@st.cache_data(ttl=600, show_spinner=False)
def run(fn: str, f: q.Filters, *args):
    return getattr(q, fn)(get_engine(), f, *args)


@st.cache_data(ttl=600, show_spinner=False)
def load_options():
    engine = get_engine()
    return q.filter_options(engine), q.date_bounds(engine)


def subset(selected, everything):
    return () if set(selected) == set(everything) else tuple(sorted(selected))


def main():
    st.title("SmartMart Retail: Sales & Customer Analytics")

    try:
        opts, (lo, hi) = load_options()
    except FileNotFoundError as e:
        st.error(str(e))
        st.stop()
    except SQLAlchemyError:
        st.error("Could not read the database. Check DATABASE_URL, or rebuild with `python -m pipeline.run_all`.")
        st.stop()
    if lo is None:
        st.error("The database has no sales rows. Rebuild it with `python -m pipeline.run_all`.")
        st.stop()

    backend = get_engine().dialect.name
    st.caption(f"Data source: {'bundled SQLite file' if backend == 'sqlite' else 'cloud PostgreSQL'} "
               f"| {lo} to {hi} | amounts in PKR")

    # ---- filters -------------------------------------------------------------------------
    sb = st.sidebar
    sb.header("Filters")
    picked = sb.date_input("Date range", value=(pd.Timestamp(lo).date(), pd.Timestamp(hi).date()),
                           min_value=pd.Timestamp(lo).date(), max_value=pd.Timestamp(hi).date())
    if not isinstance(picked, (tuple, list)) or len(picked) != 2:
        st.info("Pick both a start and an end date.")
        st.stop()
    regions = sb.multiselect("Region", opts["regions"], default=opts["regions"])
    city_opts = sorted({c for r, c in opts["region_city"] if r in regions})
    cities = sb.multiselect("City", city_opts, default=city_opts)
    categories = sb.multiselect("Category", opts["categories"], default=opts["categories"])
    channels = sb.multiselect("Channel", opts["channels"], default=opts["channels"])
    if not (regions and cities and categories and channels):
        st.warning("Select at least one option in every filter.")
        st.stop()

    all_cities = sorted({c for _, c in opts["region_city"]})
    f = q.Filters(start=str(picked[0]), end=str(picked[1]),
                  regions=subset(regions, opts["regions"]), cities=subset(cities, all_cities),
                  categories=subset(categories, opts["categories"]), channels=subset(channels, opts["channels"]))

    try:
        k = run("kpis", f)
        if k["orders"] == 0:
            st.warning("No sales match these filters. Widen the date range or clear some filters.")
            st.stop()

        cols = st.columns(6)
        cols[0].metric("Revenue", money(k["revenue"]))
        cols[1].metric("Profit", money(k["profit"]), f"{k['margin_pct']:.1f}% margin", delta_color="off")
        cols[2].metric("Orders", f"{k['orders']:,}")
        cols[3].metric("Avg order value", money(k["aov"]))
        cols[4].metric("Active customers", f"{k['active_customers']:,}")
        cols[5].metric("Repeat-buyer rate", f"{k['repeat_rate']:.1%}")
        st.caption("Orders without a customer ID count in sales figures but not in customer metrics.")

        t_sales, t_cust, t_prod, t_reg, t_data = st.tabs(
            ["Sales trends", "Customers", "Products", "Regions", "Data quality & export"])

        with t_sales:
            c1, c2 = st.columns(2)
            grain = c1.radio("Group by", ["Daily", "Monthly", "Yearly"], horizontal=True, index=1)
            metric = c2.selectbox("Metric", ["Revenue", "Profit", "Orders"])
            t = run("trend", f, grain)
            t["period"] = t.period.astype(str) if grain == "Yearly" else pd.to_datetime(t.period)
            series = t.set_index("period")[metric.lower()]
            (st.bar_chart if grain == "Yearly" else st.line_chart)(series)
            st.caption(f"{metric} by {grain.lower()} period for the selected filters.")

        seg = run("customer_segments", f)
        with t_cust:
            c1, c2, c3 = st.columns(3)
            c1.metric("New customers in range", f"{k['new_customers']:,}")
            c2.metric("Repeat customers", f"{k['repeat_customers']:,}")
            c3.metric("One-time customers", f"{k['active_customers'] - k['repeat_customers']:,}")
            left, right = st.columns(2)
            nr = run("new_vs_returning", f)
            left.subheader("New vs returning customers per month")
            left.bar_chart(nr.set_index("year_month")[["new_customers", "returning_customers"]])
            summary = q.segment_summary(seg)
            right.subheader("Spend-tier segments")
            right.bar_chart(summary.set_index("spend_tier")["customers"])
            right.caption("High = top 20% of spenders, Medium = next 40%, Low = bottom 40%.")
            st.dataframe(summary.style.format({"revenue": "{:,.0f}", "avg_spend": "{:,.0f}",
                                               "share_of_revenue": "{:.1%}"}), width="stretch", hide_index=True)
            st.subheader("Top 10 customers by spend")
            st.dataframe(seg.head(10), width="stretch", hide_index=True)

        with t_prod:
            prod = run("products", f)
            left, right = st.columns(2)
            left.subheader("Top 10 products by revenue")
            left.bar_chart(prod.head(10).set_index("product_name")["revenue"], horizontal=True)
            right.subheader("Bottom 10 products by revenue")
            right.dataframe(prod.tail(10).iloc[::-1][["product_name", "category", "units", "revenue", "profit"]],
                            width="stretch", hide_index=True)
            cat = run("by_dimension", f, "category")
            st.subheader("Revenue and margin by category")
            st.bar_chart(cat.set_index("label")["revenue"])
            st.dataframe(cat.rename(columns={"label": "category"}).style.format(
                {"revenue": "{:,.0f}", "profit": "{:,.0f}", "margin_pct": "{:.1f}"}), width="stretch", hide_index=True)

        with t_reg:
            left, right = st.columns(2)
            reg = run("by_dimension", f, "region")
            left.subheader("Revenue by region")
            left.bar_chart(reg.set_index("label")["revenue"])
            city = run("by_dimension", f, "city")
            right.subheader("Revenue by city")
            right.bar_chart(city.set_index("label")["revenue"])
            left, right = st.columns(2)
            left.subheader("Store vs online")
            left.dataframe(run("by_dimension", f, "channel").rename(columns={"label": "channel"}),
                           width="stretch", hide_index=True)
            right.subheader("Payment methods")
            right.dataframe(run("by_dimension", f, "payment_method").rename(columns={"label": "payment"}),
                            width="stretch", hide_index=True)
            st.subheader("Stores")
            st.dataframe(run("by_dimension", f, "store").rename(columns={"label": "store"}),
                         width="stretch", hide_index=True)

        with t_data:
            st.subheader("Export (respects the filters in the sidebar)")
            export = run("export_transactions", f)
            kpi_df = pd.DataFrame({"kpi": list(k), "value": list(k.values())})
            d1, d2, d3 = st.columns(3)
            d1.download_button("Transactions (CSV)", export.to_csv(index=False).encode(),
                               "smartmart_transactions.csv", "text/csv")
            d2.download_button("KPI summary (CSV)", kpi_df.to_csv(index=False).encode(),
                               "smartmart_kpis.csv", "text/csv")
            d3.download_button("Customer segments (CSV)", seg.to_csv(index=False).encode(),
                               "smartmart_segments.csv", "text/csv")
            st.caption(f"{len(export):,} transaction rows in the current export.")

            st.subheader("What the cleaning script fixed")
            if REPORT.exists():
                rep = json.loads(REPORT.read_text())["transactions"]
                m = st.columns(4)
                m[0].metric("Raw rows", f"{rep['rows_in']:,}")
                m[1].metric("Duplicates removed", f"{rep['exact_duplicates_removed'] + rep['duplicate_transaction_id_removed']:,}")
                m[2].metric("Rejected rows", f"{rep['rejected_total']:,}")
                m[3].metric("Clean rows", f"{rep['rows_out']:,}")
                detail = pd.DataFrame({"check": list(rep), "rows": list(rep.values())})
                st.dataframe(detail[detail.check != "reconciles"], width="stretch", hide_index=True)
            else:
                st.info("No cleaning report found. Run `python -m pipeline.run_all` to create one.")
    except SQLAlchemyError:
        st.error("A database query failed. If you use a cloud database, check that the project is not paused.")
        st.stop()


main()
