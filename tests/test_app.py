"""Smoke tests for the Streamlit UI: filters, KPI cards, empty states, missing database."""
import pytest
from streamlit.testing.v1 import AppTest

import db

APP = str(db.DEFAULT_SQLITE.parent.parent / "app.py")


@pytest.fixture
def app(built, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", built["url"])
    return AppTest.from_file(APP, default_timeout=90).run()


def metric_values(at):
    return {m.label: m.value for m in at.metric}


def test_app_loads_with_kpi_cards(app):
    assert not app.exception
    values = metric_values(app)
    for label in ("Revenue", "Profit", "Orders", "Avg order value", "Active customers", "Repeat-buyer rate"):
        assert label in values
    assert len(app.tabs) == 5


def test_region_filter_changes_kpis(app):
    before = metric_values(app)["Orders"]
    app.sidebar.multiselect[0].set_value(["South"]).run()
    assert not app.exception
    after = metric_values(app)["Orders"]
    assert int(after.replace(",", "")) < int(before.replace(",", ""))


def test_empty_filter_shows_warning_not_crash(app):
    app.sidebar.multiselect[3].set_value([]).run()
    assert not app.exception
    assert any("at least one" in w.value for w in app.warning)


def test_missing_database_shows_friendly_error(tmp_path, monkeypatch):
    import streamlit as st
    st.cache_resource.clear()
    st.cache_data.clear()
    monkeypatch.setenv("DATABASE_URL", db.sqlite_url(tmp_path / "missing.db"))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("not found" in e.value for e in at.error)
    assert not (tmp_path / "missing.db").exists()
