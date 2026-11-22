"""Load raw CSVs, validate fields, fix/dedupe, and write clean CSVs plus a cleaning report.

Run:  python -m pipeline.clean_data
In:   data/raw/*.csv
Out:  data/clean/*.csv, data/clean/rejected_transactions.csv, data/clean/cleaning_report.json
"""
from __future__ import annotations

import argparse
import json
import string
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

CATEGORIES = {"electronics": "Electronics", "clothing": "Clothing",
              "home appliances": "Home Appliances", "grocery": "Grocery"}
PAYMENTS = {"cash": "Cash", "card": "Card", "online transfer": "Online Transfer", "mobile wallet": "Mobile Wallet"}
CHANNELS = {"store": "Store", "online": "Online"}
CITY_REGION = {"Karachi": "South", "Hyderabad": "South", "Lahore": "Punjab", "Faisalabad": "Punjab",
               "Multan": "Punjab", "Islamabad": "North", "Peshawar": "North", "Quetta": "West"}
REQUIRED = {
    "customers": ["customer_id", "name", "city", "region", "signup_date"],
    "products": ["product_id", "product_name", "category", "unit_price", "unit_cost"],
    "stores": ["store_id", "store_name", "city", "region", "channel"],
    "transactions": ["transaction_id", "date", "customer_id", "product_id", "store_id",
                     "quantity", "discount", "payment_method"],
}


class ValidationError(Exception):
    """Raised when an input file is missing or lacks required columns."""


def _read(raw_dir: Path, name: str) -> pd.DataFrame:
    path = raw_dir / f"{name}.csv"
    if not path.exists():
        raise ValidationError(f"Missing input file: {path}. Run: python -m pipeline.generate_data")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in REQUIRED[name] if c not in df.columns]
    if missing:
        raise ValidationError(f"{path.name} is missing required column(s): {', '.join(missing)}")
    return df[REQUIRED[name]]


def _ws(s: pd.Series) -> pd.Series:
    return s.str.replace(r"\s+", " ", regex=True).str.strip()


def _fix_case(s: str) -> str:
    return string.capwords(s) if (s.isupper() or s.islower()) else s


def clean_products(df: pd.DataFrame, rep: dict):
    df = df.copy()
    for c in ("product_id", "product_name", "category"):
        df[c] = _ws(df[c])
    df = df[df.product_id != ""]
    n = len(df)
    df = df.drop_duplicates("product_id", keep="first")
    rep["duplicate_product_rows_removed"] = n - len(df)

    df["category"] = df.category.str.lower().map(CATEGORIES)
    for c in ("unit_price", "unit_cost"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    bad = df.category.isna() | ~((df.unit_price > 0) & (df.unit_cost > 0))
    rep["invalid_product_rows_removed"] = int(bad.sum())
    df = df[~bad].copy()

    df["product_name"] = df.product_name.map(_fix_case)
    df = df.sort_values("product_id")
    key = df.product_name.str.lower()
    canon = df.groupby(key).product_id.transform("first")
    id_map = {p: c for p, c in zip(df.product_id, canon) if p != c}
    rep["product_aliases_merged"] = len(id_map)
    return df[df.product_id == canon].reset_index(drop=True), id_map


def clean_stores(df: pd.DataFrame, rep: dict) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        df[c] = _ws(df[c])
    df["channel"] = df.channel.str.lower().map(CHANNELS)
    n = len(df)
    df = df[(df.store_id != "") & df.channel.notna()].drop_duplicates("store_id")
    rep["invalid_or_duplicate_store_rows_removed"] = n - len(df)
    return df.reset_index(drop=True)


def clean_customers(df: pd.DataFrame, rep: dict) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        df[c] = _ws(df[c])
    df = df[df.customer_id != ""]
    n = len(df)
    df["_complete"] = (df[["name", "city", "region", "signup_date"]] != "").sum(axis=1)
    df = (df.sort_values(["customer_id", "_complete"], ascending=[True, False])
            .drop_duplicates("customer_id").drop(columns="_complete"))
    rep["duplicate_customer_rows_removed"] = n - len(df)

    rep["customers_missing_name_set_unknown"] = int((df.name == "").sum())
    df.loc[df.name == "", "name"] = "Unknown"
    city = df.city.str.lower().map(lambda x: string.capwords(x) if x else "Unknown")
    rep["customers_missing_city_set_unknown"] = int((city == "Unknown").sum())
    df["region"] = city.map(CITY_REGION).fillna(df.region.replace("", "Unknown"))
    df["city"] = city
    d = pd.to_datetime(df.signup_date, format="%Y-%m-%d", errors="coerce")
    df["signup_date"] = d.dt.strftime("%Y-%m-%d")
    return df.reset_index(drop=True)


def clean_transactions(df: pd.DataFrame, product_ids: set, id_map: dict, store_ids: set,
                       customer_ids: set, report: dict):
    df = df.copy()
    for c in df.columns:
        df[c] = _ws(df[c])
    rep = report["transactions"] = {"rows_in": len(df)}
    rejected: list[pd.DataFrame] = []

    def reject(mask: pd.Series, reason: str):
        nonlocal df
        if mask.any():
            r = df[mask].copy()
            r["reject_reason"] = reason
            rejected.append(r)
        rep[f"rejected_{reason}"] = int(mask.sum())
        df = df[~mask]

    reject(df.transaction_id == "", "missing_transaction_id")
    n = len(df)
    df = df.drop_duplicates()
    rep["exact_duplicates_removed"] = n - len(df)
    n = len(df)
    df = df.drop_duplicates("transaction_id", keep="first")
    rep["duplicate_transaction_id_removed"] = n - len(df)

    iso = pd.to_datetime(df.date, format="%Y-%m-%d", errors="coerce")
    dmy = pd.to_datetime(df.date, format="%d/%m/%Y", errors="coerce")
    rep["dates_reformatted_dmy"] = int((iso.isna() & dmy.notna()).sum())
    df = df.assign(_d=iso.fillna(dmy))
    reject(df._d.isna(), "invalid_date")

    q = pd.to_numeric(df.quantity, errors="coerce")
    df = df.assign(_q=q)
    reject(~(df._q > 0) | (df._q % 1 != 0), "invalid_quantity")

    mapped = df.product_id.map(lambda x: id_map.get(x, x))
    rep["product_ids_remapped_from_alias"] = int((mapped != df.product_id).sum())
    df = df.assign(product_id=mapped)
    reject(~df.product_id.isin(product_ids), "unknown_product_id")
    reject(~df.store_id.isin(store_ids), "unknown_store_id")

    disc = pd.to_numeric(df.discount, errors="coerce")
    rep["missing_discount_filled_with_0"] = int(disc.isna().sum())
    df = df.assign(discount=disc.fillna(0.0))
    reject((df.discount < 0) | (df.discount >= 1), "invalid_discount")

    blank = df.customer_id == ""
    orphan = ~blank & ~df.customer_id.isin(customer_ids)
    rep["missing_customer_id_kept_as_guest"] = int(blank.sum())
    rep["unknown_customer_id_set_to_guest"] = int(orphan.sum())
    df.loc[blank | orphan, "customer_id"] = pd.NA

    df["payment_method"] = df.payment_method.str.lower().map(PAYMENTS).fillna("Other")
    df["date"] = df._d.dt.strftime("%Y-%m-%d")
    df["quantity"] = df._q.astype(int)
    out = df[REQUIRED["transactions"]].sort_values(["date", "transaction_id"]).reset_index(drop=True)

    rep["rows_out"] = len(out)
    removed = rep["exact_duplicates_removed"] + rep["duplicate_transaction_id_removed"]
    rep["rejected_total"] = sum(v for k, v in rep.items() if k.startswith("rejected_") and k != "rejected_total")
    rep["reconciles"] = rep["rows_in"] == rep["rows_out"] + removed + rep["rejected_total"]
    rej = (pd.concat(rejected)[REQUIRED["transactions"] + ["reject_reason"]] if rejected
           else pd.DataFrame(columns=REQUIRED["transactions"] + ["reject_reason"]))
    return out, rej


def clean(raw_dir: Path | str = ROOT / "data" / "raw", clean_dir: Path | str = ROOT / "data" / "clean") -> dict:
    raw_dir, clean_dir = Path(raw_dir), Path(clean_dir)
    clean_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"products": {}, "stores": {}, "customers": {}}

    products, id_map = clean_products(_read(raw_dir, "products"), report["products"])
    stores = clean_stores(_read(raw_dir, "stores"), report["stores"])
    customers = clean_customers(_read(raw_dir, "customers"), report["customers"])
    tx, rejected = clean_transactions(_read(raw_dir, "transactions"), set(products.product_id), id_map,
                                      set(stores.store_id), set(customers.customer_id), report)
    for name, df in {"products": products, "stores": stores, "customers": customers, "transactions": tx}.items():
        df.to_csv(clean_dir / f"{name}.csv", index=False)
    rejected.to_csv(clean_dir / "rejected_transactions.csv", index=False)
    (clean_dir / "cleaning_report.json").write_text(json.dumps(report, indent=2))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default=ROOT / "data" / "raw")
    ap.add_argument("--out", default=ROOT / "data" / "clean")
    a = ap.parse_args()
    try:
        t = clean(a.raw, a.out)["transactions"]
    except ValidationError as e:
        raise SystemExit(f"Validation failed: {e}")
    print(f"transactions: {t['rows_in']} in -> {t['rows_out']} clean "
          f"({t['rejected_total']} rejected, reconciles={t['reconciles']})")


if __name__ == "__main__":
    main()
