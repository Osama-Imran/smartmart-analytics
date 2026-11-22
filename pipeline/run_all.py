"""Run the whole Stage 1 pipeline: generate raw -> clean -> build SQLite.

Run:  python -m pipeline.run_all
"""
from pipeline import build_db, clean_data, generate_data


def main():
    print("raw rows:", generate_data.generate())
    t = clean_data.clean()["transactions"]
    print(f"clean transactions: {t['rows_out']} (rejected {t['rejected_total']}, reconciles={t['reconciles']})")
    print("database rows:", build_db.build())


if __name__ == "__main__":
    main()
