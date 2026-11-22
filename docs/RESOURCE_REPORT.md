# Resource report

Python 3.13.18. Measured by `check_resources.py`.

| Measurement | Value |
|---|---|
| Generate 15,000 raw transactions | 0.33 s |
| Validate and clean | 0.19 s |
| Load SQLite and create views | 1.47 s |
| Query: KPI cards (all data, avg of 5) | 75 ms |
| Query: Daily trend (all data, avg of 5) | 20 ms |
| Query: Customer segments (all data, avg of 5) | 29 ms |
| Query: Product ranking (all data, avg of 5) | 26 ms |
| Query: Transaction export (all data, avg of 5) | 144 ms |
| Peak memory of this script (RSS) | 172 MB |
| Peak memory incl. dashboard render (RSS) | 242 MB |
| data/ folder (raw + clean + db) | 3.24 MB |
| Whole project folder | 3.45 MB |
| Dashboard first render (headless test) | 1.46 s |
