"""Download (if needed), clean and load the dataset into PostgreSQL.

    python scripts/load.py
"""

import io
import os
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import psycopg
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.clean import clean, load_raw  # noqa: E402

DATA = ROOT / "data"
CSV = DATA / "online_retail_ii.csv"
SOURCE = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
DB = os.getenv("DATABASE_URL", "postgresql://retail:retail@localhost:5552/retail")


def ensure_csv() -> None:
    if CSV.exists():
        return
    DATA.mkdir(exist_ok=True)
    print("downloading UCI Online Retail II (45 MB)...")
    xlsx = zipfile.ZipFile(io.BytesIO(requests.get(SOURCE, timeout=300).content)).read("online_retail_II.xlsx")
    sheets = pd.read_excel(io.BytesIO(xlsx), sheet_name=None, dtype={"Invoice": str, "StockCode": str})
    pd.concat(sheets.values(), ignore_index=True).to_csv(CSV, index=False)


def copy(conn, table: str, df: pd.DataFrame, columns: list[str]) -> None:
    buf = io.StringIO()
    df[columns].to_csv(buf, index=False, header=False)
    buf.seek(0)
    with conn.cursor().copy(f"COPY retail.{table} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv)") as cp:
        while chunk := buf.read(1 << 20):
            cp.write(chunk)


def main() -> None:
    t0 = time.monotonic()
    ensure_csv()
    result = clean(load_raw(CSV))
    with psycopg.connect(DB, autocommit=True) as conn:
        conn.execute((ROOT / "sql" / "01_schema.sql").read_text())
        copy(conn, "sales", result.sales,
             ["invoice", "stock_code", "description", "quantity", "invoice_date", "unit_price",
              "customer_id", "country", "line_revenue"])
        copy(conn, "cancellations", result.cancellations,
             ["invoice", "stock_code", "description", "quantity", "invoice_date", "unit_price",
              "customer_id", "country"])
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO retail.data_quality VALUES (%s, %s, %s, %s)",
                            [(i, s.rule, s.removed, s.remaining) for i, s in enumerate(result.steps, 1)])
        conn.execute((ROOT / "sql" / "02_analytics.sql").read_text())
        conn.execute("ANALYZE")
    for s in result.steps:
        print(f"{s.removed:>9,} removed  {s.remaining:>10,} left  {s.rule}")
    print(f"loaded {len(result.sales):,} sales and {len(result.cancellations):,} cancellation lines "
          f"in {time.monotonic() - t0:.0f}s")


if __name__ == "__main__":
    main()
