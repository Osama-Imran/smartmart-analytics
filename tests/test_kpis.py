"""KPI accuracy: every SQL result is compared with an independent pandas calculation."""
import numpy as np
import pandas as pd
import pytest

import queries as q


def full(sales):
    return q.Filters(start=sales.date.min(), end=sales.date.max())


def test_headline_kpis_match_pandas(built, sales):
    k = q.kpis(built["engine"], full(sales))
    assert k["revenue"] == pytest.approx(sales.revenue.sum())
    assert k["profit"] == pytest.approx(sales.profit.sum())
    assert k["orders"] == sales.transaction_id.nunique() == len(sales)
    assert k["units"] == sales.quantity.sum()
    assert k["aov"] == pytest.approx(sales.revenue.sum() / len(sales))
    assert k["margin_pct"] == pytest.approx(100 * sales.profit.sum() / sales.revenue.sum())


def test_customer_kpis_match_pandas(built, sales):
    k = q.kpis(built["engine"], full(sales))
    known = sales[sales.customer_id.notna()]
    per = known.groupby("customer_id").transaction_id.nunique()
    assert k["active_customers"] == len(per)
    assert k["repeat_customers"] == (per >= 2).sum()
    assert k["repeat_rate"] == pytest.approx((per >= 2).sum() / len(per))
    assert k["new_customers"] == len(per)  # full range: every active customer is new at some point


def test_date_filter(built, sales):
    f = q.Filters(start="2026-01-01", end="2026-03-31")
    sub = sales[(sales.date >= f.start) & (sales.date <= f.end)]
    k = q.kpis(built["engine"], f)
    assert k["revenue"] == pytest.approx(sub.revenue.sum())
    assert k["orders"] == len(sub)


def test_combined_filters(built, sales):
    f = q.Filters(start=sales.date.min(), end=sales.date.max(), regions=("South", "North"),
                  categories=("Electronics",), channels=("Online",))
    sub = sales[sales.region.isin(["South", "North"]) & (sales.category == "Electronics") & (sales.channel == "Online")]
    k = q.kpis(built["engine"], f)
    assert len(sub) > 0
    assert k["revenue"] == pytest.approx(sub.revenue.sum())
    assert k["orders"] == len(sub)


def test_no_matching_rows_returns_zeros_not_errors(built, sales):
    f = q.Filters(start=sales.date.min(), end=sales.date.max(), regions=("Atlantis",))
    k = q.kpis(built["engine"], f)
    assert k["orders"] == 0 and k["revenue"] == 0 and k["aov"] == 0 and k["repeat_rate"] == 0
    assert q.customer_segments(built["engine"], f).empty


@pytest.mark.parametrize("grain", ["Daily", "Monthly", "Yearly"])
def test_trends_add_up_to_total(built, sales, grain):
    t = q.trend(built["engine"], full(sales), grain)
    assert t.revenue.sum() == pytest.approx(sales.revenue.sum())
    assert t.orders.sum() == len(sales)


def test_monthly_trend_matches_pandas(built, sales):
    t = q.trend(built["engine"], full(sales), "Monthly").set_index("period").revenue
    expected = sales.assign(m=sales.date.str[:7]).groupby("m").revenue.sum()
    assert np.allclose(t.sort_index().to_numpy(), expected.sort_index().to_numpy())


@pytest.mark.parametrize("dim,col", [("category", "category"), ("region", "region"), ("city", "city"),
                                     ("channel", "channel"), ("payment_method", "payment_method")])
def test_dimension_breakdowns(built, sales, dim, col):
    d = q.by_dimension(built["engine"], full(sales), dim).set_index("label").revenue
    expected = sales.groupby(col).revenue.sum()
    assert d.sum() == pytest.approx(sales.revenue.sum())
    for label, value in expected.items():
        assert d[label] == pytest.approx(value)


def test_product_ranking(built, sales):
    p = q.products(built["engine"], full(sales))
    expected = sales.groupby("product_id").revenue.sum().sort_values(ascending=False)
    assert p.product_id.iloc[0] == expected.index[0]
    assert p.revenue.sum() == pytest.approx(sales.revenue.sum())
    assert len(p) == sales.product_id.nunique()


def test_spend_tiers_match_pandas_percent_rank(built, sales):
    seg = q.customer_segments(built["engine"], full(sales))
    spend = sales[sales.customer_id.notna()].groupby("customer_id").revenue.sum()
    pr = (spend.rank(method="min") - 1) / (len(spend) - 1)
    expected = pd.Series(np.where(pr >= .8, "High", np.where(pr >= .4, "Medium", "Low")), index=spend.index)
    got = seg.set_index("customer_id").spend_tier
    assert (got.sort_index() == expected.sort_index()).all()
    assert len(seg) == len(spend)
    summary = q.segment_summary(seg)
    assert summary.customers.sum() == len(spend)
    assert summary.share_of_revenue.sum() == pytest.approx(1.0)


def test_new_vs_returning(built, sales):
    nr = q.new_vs_returning(built["engine"], full(sales))
    known = sales[sales.customer_id.notna()]
    assert nr.new_customers.sum() == known.customer_id.nunique()
    first_month = known.assign(m=known.date.str[:7]).groupby("customer_id").m.min()
    assert nr.set_index("year_month").new_customers.to_dict() == first_month.value_counts().to_dict()


def test_export_matches_filter(built, sales):
    f = q.Filters(start="2026-05-01", end="2026-05-31", categories=("Grocery",))
    exp = q.export_transactions(built["engine"], f)
    sub = sales[(sales.date >= f.start) & (sales.date <= f.end) & (sales.category == "Grocery")]
    assert len(exp) == len(sub)
    assert exp.revenue.sum() == pytest.approx(sub.revenue.sum())


def test_bad_inputs_are_rejected(built, sales):
    with pytest.raises(ValueError):
        q.trend(built["engine"], full(sales), "Hourly")
    with pytest.raises(ValueError):
        q.by_dimension(built["engine"], full(sales), "customer_id; DROP TABLE x")
