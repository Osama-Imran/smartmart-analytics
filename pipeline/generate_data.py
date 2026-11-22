"""Generate synthetic SmartMart CSVs with deliberate data-quality problems.

Run:  python -m pipeline.generate_data
Out:  data/raw/{customers,products,stores,transactions}.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
START, END = "2025-01-01", "2026-10-31"

# id, name, city, region, channel
STORES = [
    ("S01", "SmartMart Clifton", "Karachi", "South", "Store"),
    ("S02", "SmartMart Gulshan", "Karachi", "South", "Store"),
    ("S03", "SmartMart Hyderabad", "Hyderabad", "South", "Store"),
    ("S04", "SmartMart Gulberg", "Lahore", "Punjab", "Store"),
    ("S05", "SmartMart DHA Lahore", "Lahore", "Punjab", "Store"),
    ("S06", "SmartMart Faisalabad", "Faisalabad", "Punjab", "Store"),
    ("S07", "SmartMart Multan", "Multan", "Punjab", "Store"),
    ("S08", "SmartMart Islamabad", "Islamabad", "North", "Store"),
    ("S09", "SmartMart Peshawar", "Peshawar", "North", "Store"),
    ("S10", "SmartMart Quetta", "Quetta", "West", "Store"),
    ("S11", "SmartMart Online Karachi", "Karachi", "South", "Online"),
    ("S12", "SmartMart Online Lahore", "Lahore", "Punjab", "Online"),
    ("S13", "SmartMart Online Islamabad", "Islamabad", "North", "Online"),
    ("S14", "SmartMart Online Peshawar", "Peshawar", "North", "Online"),
]
CITY_WEIGHT = {
    "Karachi": .26, "Lahore": .22, "Islamabad": .12, "Peshawar": .10,
    "Faisalabad": .08, "Quetta": .08, "Hyderabad": .07, "Multan": .07,
}
CITY_REGION = {
    "Karachi": "South", "Hyderabad": "South", "Lahore": "Punjab", "Faisalabad": "Punjab",
    "Multan": "Punjab", "Islamabad": "North", "Peshawar": "North", "Quetta": "West",
}
CATEGORY_SHARE = {"Grocery": .40, "Clothing": .25, "Electronics": .20, "Home Appliances": .15}
QTY = {
    "Electronics": ([1, 2], [.9, .1]),
    "Clothing": ([1, 2, 3], [.6, .3, .1]),
    "Home Appliances": ([1, 2], [.92, .08]),
    "Grocery": ([1, 2, 3, 4, 5, 6], [.3, .25, .2, .1, .1, .05]),
}
MONTH_BOOST = {3: 1.15, 4: 1.10, 11: 1.20, 12: 1.25}

# name, category, unit_price (PKR), unit_cost (PKR), popularity weight
PRODUCTS = [
    ("Smartphone", "Electronics", 85000, 68000, 5), ("Laptop", "Electronics", 140000, 118000, 2),
    ("LED TV 43 Inch", "Electronics", 75000, 60000, 2), ("Bluetooth Speaker", "Electronics", 9000, 6000, 4),
    ("Wireless Earbuds", "Electronics", 12000, 8000, 5), ("Smartwatch", "Electronics", 18000, 12500, 3),
    ("Tablet", "Electronics", 55000, 44000, 2), ("Power Bank", "Electronics", 4500, 3000, 6),
    ("Gaming Console", "Electronics", 95000, 82000, 1), ("Digital Camera", "Electronics", 120000, 102000, .5),
    ("Men's Kurta", "Clothing", 4500, 2800, 6), ("Women's Lawn Suit", "Clothing", 6500, 4000, 7),
    ("Denim Jeans", "Clothing", 5500, 3300, 6), ("Cotton T-Shirt", "Clothing", 1800, 950, 8),
    ("Winter Jacket", "Clothing", 12000, 7500, 3), ("Sneakers", "Clothing", 9500, 6000, 5),
    ("Formal Shirt", "Clothing", 4200, 2500, 4), ("Shalwar Kameez", "Clothing", 5000, 3000, 5),
    ("Hoodie", "Clothing", 5500, 3200, 4), ("Leather Belt", "Clothing", 2200, 1200, 1),
    ("Refrigerator", "Home Appliances", 95000, 78000, 2), ("Washing Machine", "Home Appliances", 65000, 52000, 2),
    ("Microwave Oven", "Home Appliances", 28000, 21000, 3), ("Air Conditioner 1.5 Ton", "Home Appliances", 140000, 115000, 2),
    ("Electric Kettle", "Home Appliances", 5500, 3600, 5), ("Iron", "Home Appliances", 4800, 3200, 5),
    ("Vacuum Cleaner", "Home Appliances", 32000, 24000, 1.5), ("Air Fryer", "Home Appliances", 18000, 12500, 4),
    ("Ceiling Fan", "Home Appliances", 12500, 8800, 4), ("Water Dispenser", "Home Appliances", 36000, 27500, 1),
    ("Basmati Rice 5kg", "Grocery", 2400, 1900, 10), ("Cooking Oil 5L", "Grocery", 3200, 2700, 10),
    ("Tea 950g", "Grocery", 2600, 2100, 8), ("Sugar 5kg", "Grocery", 800, 700, 9),
    ("Wheat Flour 10kg", "Grocery", 1500, 1250, 9), ("Milk Pack (12x1L)", "Grocery", 3000, 2500, 8),
    ("Lentils 1kg", "Grocery", 450, 360, 6), ("Family Biscuit Pack", "Grocery", 900, 650, 6),
    ("Spice Mix Pack", "Grocery", 700, 480, 4), ("Juice Carton Pack", "Grocery", 1400, 1000, 5),
]
FIRST = ["Ahmed", "Ayesha", "Bilal", "Fatima", "Hassan", "Hira", "Imran", "Zainab", "Usman", "Sana",
         "Ali", "Maryam", "Omar", "Nida", "Hamza", "Sara", "Faisal", "Mehwish", "Kamran", "Amna"]
LAST = ["Khan", "Ahmed", "Malik", "Sheikh", "Qureshi", "Raza", "Siddiqui", "Butt", "Chaudhry", "Hussain",
        "Ansari", "Mirza", "Baig", "Iqbal", "Javed", "Abbasi", "Rizvi", "Farooqi", "Zaidi", "Shah"]
ALIAS_SOURCES = ["P005", "P016", "P032"]  # these get a second, badly spelled product_id


def make_tables(n_txn: int, n_cust: int, rng: np.random.Generator):
    """Build the clean 'truth' tables."""
    stores = pd.DataFrame(STORES, columns=["store_id", "store_name", "city", "region", "channel"])
    products = pd.DataFrame(
        [(f"P{i + 1:03d}", n, c, pr, co) for i, (n, c, pr, co, _) in enumerate(PRODUCTS)],
        columns=["product_id", "product_name", "category", "unit_price", "unit_cost"],
    )
    pop = np.array([p[4] for p in PRODUCTS], float)
    cat = products.category.to_numpy()
    p_prod = np.array([CATEGORY_SHARE[c] * pop[i] / pop[cat == c].sum() for i, c in enumerate(cat)])
    p_prod /= p_prod.sum()

    cities = list(CITY_WEIGHT)
    city = rng.choice(cities, n_cust, p=list(CITY_WEIGHT.values()))
    customers = pd.DataFrame({
        "customer_id": [f"C{i + 1:04d}" for i in range(n_cust)],
        "name": [f"{rng.choice(FIRST)} {rng.choice(LAST)}" for _ in range(n_cust)],
        "city": city,
        "region": [CITY_REGION[c] for c in city],
    })
    activity = rng.lognormal(0, 1.1, n_cust)
    activity /= activity.sum()

    days = pd.date_range(START, END)
    w = (np.linspace(1, 1.5, len(days))
         * np.array([MONTH_BOOST.get(m, 1.0) for m in days.month])
         * np.where(days.dayofweek >= 5, 1.25, 1.0))
    w /= w.sum()
    dates = np.sort(rng.choice(days.to_numpy(), n_txn, p=w))

    cust_idx = rng.choice(n_cust, n_txn, p=activity)
    prod_idx = rng.choice(len(products), n_txn, p=p_prod)

    store_city = stores.city.to_numpy()
    by_city = {c: np.where(store_city == c)[0] for c in cities}
    store_idx = rng.integers(0, len(stores), n_txn)
    cust_city = customers.city.to_numpy()
    for i in np.where(rng.random(n_txn) < 0.85)[0]:
        store_idx[i] = rng.choice(by_city[cust_city[cust_idx[i]]])

    qty = np.ones(n_txn, int)
    tx_cat = cat[prod_idx]
    for c, (vals, probs) in QTY.items():
        m = tx_cat == c
        qty[m] = rng.choice(vals, int(m.sum()), p=probs)
    discount = rng.choice([0, .05, .10, .15, .20], n_txn, p=[.55, .20, .12, .08, .05])
    pay = rng.choice(["Cash", "Card", "Online Transfer", "Mobile Wallet"], n_txn, p=[.35, .30, .15, .20])
    online = stores.channel.to_numpy()[store_idx] == "Online"
    pay[online & (pay == "Cash")] = "Card"

    tx = pd.DataFrame({
        "transaction_id": [f"T{i + 1:06d}" for i in range(n_txn)],
        "date": pd.to_datetime(dates).strftime("%Y-%m-%d"),
        "customer_id": customers.customer_id.to_numpy()[cust_idx],
        "product_id": products.product_id.to_numpy()[prod_idx],
        "store_id": stores.store_id.to_numpy()[store_idx],
        "quantity": qty,
        "discount": discount,
        "payment_method": pay,
    })

    first = pd.Series(pd.to_datetime(dates)).groupby(cust_idx).min()
    signup = pd.Series(pd.Timestamp("2024-06-01") + pd.to_timedelta(rng.integers(0, 880, n_cust), unit="D"))
    signup.loc[first.index] = first.to_numpy() - pd.to_timedelta(rng.integers(0, 90, len(first)), unit="D").to_numpy()
    customers["signup_date"] = signup.dt.strftime("%Y-%m-%d")
    return customers, products, stores, tx


def dirty_transactions(tx: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    tx = tx.copy()
    n = len(tx)
    perm = rng.permutation(n)
    pos = 0

    def take(k):
        nonlocal pos
        idx = perm[pos:pos + k]
        pos += k
        return idx

    tx.loc[take(int(.02 * n)), "customer_id"] = ""              # missing customer
    tx.loc[take(40), "quantity"] = rng.choice([0, -1, -2], 40)   # impossible quantity
    tx.loc[take(10), "date"] = "31/02/2026"                      # impossible date
    tx.loc[take(5), "date"] = "N/A"
    tx.loc[take(10), "product_id"] = "P999"                      # unknown product
    tx.loc[take(int(.005 * n)), "discount"] = np.nan             # missing discount
    for i in take(int(.01 * n)):                                 # valid but DD/MM/YYYY
        tx.iat[i, tx.columns.get_loc("date")] = pd.Timestamp(tx.iat[i, 1]).strftime("%d/%m/%Y")
    pm = take(int(.05 * n))
    tx.loc[pm, "payment_method"] = [rng.choice(["{}", "{} ", " {}"]).format(p.lower() if rng.random() < .5 else p.upper())
                                    for p in tx.loc[pm, "payment_method"]]

    for k, src in enumerate(ALIAS_SOURCES):                      # sales recorded under alias product ids
        rows = np.where(tx.product_id == src)[0]
        tx.iloc[rng.choice(rows, min(40, len(rows)), replace=False), tx.columns.get_loc("product_id")] = f"P{41 + k}"

    dup = tx.sample(n=int(.01 * n), random_state=int(rng.integers(1_000_000)))
    return pd.concat([tx, dup]).sample(frac=1, random_state=int(rng.integers(1_000_000))).reset_index(drop=True)


def dirty_products(products: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    p = products.copy()
    pos = rng.permutation(len(p))
    p.loc[pos[:6], "product_name"] = p.loc[pos[:6], "product_name"].str.lower()
    p.loc[pos[6:9], "product_name"] = p.loc[pos[6:9], "product_name"].str.upper()
    p.loc[pos[9:13], "product_name"] = "  " + p.loc[pos[9:13], "product_name"] + " "
    p.loc[pos[13:18], "category"] = p.loc[pos[13:18], "category"].str.lower()
    p.loc[pos[18:23], "category"] = " " + p.loc[pos[18:23], "category"].str.upper() + " "
    alias = products[products.product_id.isin(ALIAS_SOURCES)].copy()
    alias["product_id"] = [f"P{41 + k}" for k in range(len(alias))]
    alias["product_name"] = alias.product_name.str.lower().str.replace(" ", "  ", regex=False)
    dup = p.sample(2, random_state=int(rng.integers(1_000_000)))
    return pd.concat([p, alias, dup]).reset_index(drop=True)


def dirty_customers(customers: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    c = customers.copy()
    pos = rng.permutation(len(c))
    c.loc[pos[:20], "city"] = c.loc[pos[:20], "city"].str.lower()
    c.loc[pos[20:40], "city"] = " " + c.loc[pos[20:40], "city"].str.upper() + " "
    c.loc[pos[40:70], ["city", "region"]] = ""
    c.loc[pos[70:85], "name"] = ""
    dup = c.sample(25, random_state=int(rng.integers(1_000_000)))
    return pd.concat([c, dup]).reset_index(drop=True)


def generate(raw_dir: Path | str = ROOT / "data" / "raw", n_txn: int = 15000,
             n_cust: int = 2000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    customers, products, stores, tx = make_tables(n_txn, n_cust, rng)
    out = {
        "customers": dirty_customers(customers, rng),
        "products": dirty_products(products, rng),
        "stores": stores,
        "transactions": dirty_transactions(tx, rng),
    }
    for name, df in out.items():
        df.to_csv(raw_dir / f"{name}.csv", index=False)
    return {k: len(v) for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=ROOT / "data" / "raw")
    ap.add_argument("--rows", type=int, default=15000)
    ap.add_argument("--customers", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    print("raw rows written:", generate(a.out, a.rows, a.customers, a.seed))


if __name__ == "__main__":
    main()
