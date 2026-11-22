import pandas as pd
import pytest

import db
from pipeline import build_db, clean_data, generate_data


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    """Run the full pipeline once in a temp folder and expose everything tests need."""
    base = tmp_path_factory.mktemp("smartmart")
    raw, clean = base / "raw", base / "clean"
    generate_data.generate(raw)
    report = clean_data.clean(raw, clean)
    url = db.sqlite_url(base / "test.db")
    build_db.build(clean, url)
    return {
        "raw": raw, "clean": clean, "report": report, "url": url, "engine": db.get_engine(url),
        "tx": pd.read_csv(clean / "transactions.csv", dtype=str, keep_default_na=False),
    }


@pytest.fixture(scope="session")
def sales(built):
    """Independent pandas computation of the sales fact table (no SQL involved)."""
    c = built["clean"]
    tx = pd.read_csv(c / "transactions.csv", dtype={"customer_id": str})
    prod = pd.read_csv(c / "products.csv")
    st = pd.read_csv(c / "stores.csv")
    df = tx.merge(prod, on="product_id").merge(st, on="store_id")
    df["revenue"] = df.quantity * df.unit_price * (1 - df.discount)
    df["profit"] = df.revenue - df.quantity * df.unit_cost
    return df
