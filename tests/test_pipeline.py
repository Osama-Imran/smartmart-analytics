import pandas as pd
import pytest

from pipeline import clean_data


def test_raw_data_really_is_dirty(built):
    raw = pd.read_csv(built["raw"] / "transactions.csv", dtype=str, keep_default_na=False)
    assert raw.duplicated().sum() > 0
    assert (raw.customer_id == "").sum() > 0
    assert (pd.to_numeric(raw.quantity) <= 0).sum() > 0
    assert (raw.product_id == "P999").sum() > 0


def test_clean_transactions_valid(built):
    tx = built["tx"]
    assert tx.transaction_id.is_unique
    assert (pd.to_numeric(tx.quantity) > 0).all()
    assert pd.to_datetime(tx.date, format="%Y-%m-%d", errors="coerce").notna().all()
    disc = pd.to_numeric(tx.discount)
    assert ((disc >= 0) & (disc < 1)).all()
    assert set(tx.payment_method) <= {"Cash", "Card", "Online Transfer", "Mobile Wallet"}


def test_row_counts_reconcile(built):
    t = built["report"]["transactions"]
    assert t["reconciles"] is True
    assert t["rows_out"] == len(built["tx"])
    assert t["exact_duplicates_removed"] > 0 and t["rejected_total"] > 0


def test_guests_kept_not_dropped(built):
    assert (built["tx"].customer_id == "").sum() == built["report"]["transactions"]["missing_customer_id_kept_as_guest"]


def test_product_aliases_merged_and_referential_integrity(built):
    prod = pd.read_csv(built["clean"] / "products.csv")
    stores = pd.read_csv(built["clean"] / "stores.csv")
    cust = pd.read_csv(built["clean"] / "customers.csv")
    assert prod.product_id.is_unique
    assert prod.product_name.str.lower().is_unique
    assert not (prod.product_name.str.isupper() | prod.product_name.str.islower()).any()
    assert set(prod.category) == {"Electronics", "Clothing", "Home Appliances", "Grocery"}
    tx = built["tx"]
    assert set(tx.product_id) <= set(prod.product_id)
    assert set(tx.store_id) <= set(stores.store_id)
    ids = tx.customer_id[tx.customer_id != ""]
    assert set(ids) <= set(cust.customer_id)
    assert built["report"]["products"]["product_aliases_merged"] == 3


def test_customers_deduped_and_normalised(built):
    cust = pd.read_csv(built["clean"] / "customers.csv")
    assert cust.customer_id.is_unique
    assert set(cust.city) <= set(clean_data.CITY_REGION) | {"Unknown"}
    assert not cust.name.isna().any()


def test_missing_input_file_gives_clear_error(tmp_path):
    with pytest.raises(clean_data.ValidationError, match="Missing input file"):
        clean_data.clean(tmp_path / "nope", tmp_path / "out")


def test_missing_column_gives_clear_error(built, tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name in ("customers", "products", "stores", "transactions"):
        df = pd.read_csv(built["raw"] / f"{name}.csv", dtype=str, keep_default_na=False)
        if name == "transactions":
            df = df.drop(columns=["quantity"])
        df.to_csv(raw / f"{name}.csv", index=False)
    with pytest.raises(clean_data.ValidationError, match="quantity"):
        clean_data.clean(raw, tmp_path / "out")
