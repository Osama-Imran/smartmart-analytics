"""Measure how much of a free tier this project uses. Writes docs/RESOURCE_REPORT.md.

Run:  python check_resources.py
"""
import resource
import sys
import tempfile
import time
from pathlib import Path

import db
import queries as q
from pipeline import build_db, clean_data, generate_data

ROOT = Path(__file__).resolve().parent


def mb(n):
    return n / 1024 / 1024


def folder_mb(p):
    return mb(sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file()))


def timed(fn, *a):
    t = time.perf_counter()
    fn(*a)
    return time.perf_counter() - t


def main():
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        rows.append(("Generate 15,000 raw transactions", f"{timed(generate_data.generate, tmp / 'raw'):.2f} s"))
        rows.append(("Validate and clean", f"{timed(clean_data.clean, tmp / 'raw', tmp / 'clean'):.2f} s"))
        rows.append(("Load SQLite and create views", f"{timed(build_db.build, tmp / 'clean', db.sqlite_url(tmp / 'x.db')):.2f} s"))

    engine = db.get_engine()
    lo, hi = q.date_bounds(engine)
    f = q.Filters(start=lo, end=hi)
    for name, fn, args in [("KPI cards", q.kpis, ()), ("Daily trend", q.trend, ("Daily",)),
                           ("Customer segments", q.customer_segments, ()), ("Product ranking", q.products, ()),
                           ("Transaction export", q.export_transactions, ())]:
        fn(engine, f, *args)  # warm-up
        avg = sum(timed(fn, engine, f, *args) for _ in range(5)) / 5
        rows.append((f"Query: {name} (all data, avg of 5)", f"{avg * 1000:.0f} ms"))

    rows += [
        ("Peak memory of this script (RSS)", f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB"),
        ("SQLite database file", f"{mb(db.DEFAULT_SQLITE.stat().st_size):.2f} MB"),
        ("data/ folder (raw + clean + db)", f"{folder_mb(ROOT / 'data'):.2f} MB"),
        ("Whole project folder", f"{folder_mb(ROOT):.2f} MB"),
    ]
    try:
        from streamlit.testing.v1 import AppTest
        t = time.perf_counter()
        AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
        rows.append(("Dashboard first render (headless test)", f"{time.perf_counter() - t:.2f} s"))
        rows[-4] = ("Peak memory incl. dashboard render (RSS)",
                    f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB")
    except Exception as e:  # pragma: no cover
        rows.append(("Dashboard first render", f"skipped ({type(e).__name__})"))

    md = ["# Resource report", "", f"Python {sys.version.split()[0]}. Measured by `check_resources.py`.", "",
          "| Measurement | Value |", "|---|---|"] + [f"| {a} | {b} |" for a, b in rows]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "RESOURCE_REPORT.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
