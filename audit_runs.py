"""Сводка прогонов (recorded_at) и A-B-A по сети.

  python audit_runs.py --db prices.db --retailer Yohananof
"""
from __future__ import annotations

import argparse
import sqlite3


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="prices.db")
    ap.add_argument("--retailer", default="Yohananof")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    print(f"DB={args.db} retailer={args.retailer}")
    print("--- top recorded_at batches ---")
    rows = conn.execute(
        """
        SELECT p.recorded_at, COUNT(*) n
        FROM prices p
        JOIN stores s ON s.id = p.store_id
        WHERE s.retailer = ?
        GROUP BY p.recorded_at
        ORDER BY n DESC
        LIMIT ?
        """,
        (args.retailer, args.top),
    ).fetchall()
    for ra, n in rows:
        print(f"  {ra}  {n}")

    aba = conn.execute(
        """
        WITH ranked AS (
          SELECT p.product_id, p.store_id, p.price,
                 ROW_NUMBER() OVER (
                   PARTITION BY p.product_id, p.store_id ORDER BY p.id DESC
                 ) AS rn
          FROM prices p
          JOIN stores s ON s.id = p.store_id
          WHERE s.retailer = ?
        )
        SELECT COUNT(*) FROM ranked a
        JOIN ranked b ON b.product_id=a.product_id AND b.store_id=a.store_id AND b.rn=2
        JOIN ranked c ON c.product_id=a.product_id AND c.store_id=a.store_id AND c.rn=3
        WHERE a.rn=1 AND a.price=c.price AND a.price!=b.price
        """,
        (args.retailer,),
    ).fetchone()[0]
    print(f"A-B-A triples: {aba}")
    conn.close()


if __name__ == "__main__":
    main()
