"""Load the Olist CSVs from data/raw into data/olist.db (SQLite).

Usage:  python load_olist.py [raw_dir] [db_path]
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd


# csv file -> table name
FILES = {
    "olist_customers_dataset.csv": "customers",
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "product_category_name_translation.csv": "category_translation",
}
INDEXES = [
    "CREATE INDEX idx_customers_id ON customers(customer_id)",
    "CREATE INDEX idx_customers_unique ON customers(customer_unique_id)",
    "CREATE INDEX idx_products_id ON products(product_id)",
    "CREATE INDEX idx_sellers_id ON sellers(seller_id)",
    "CREATE INDEX idx_orders_id ON orders(order_id)",
    "CREATE INDEX idx_orders_customer ON orders(customer_id)",
    "CREATE INDEX idx_orders_status ON orders(order_status)",
    "CREATE INDEX idx_items_order ON order_items(order_id)",
    "CREATE INDEX idx_items_product ON order_items(product_id)",
    "CREATE INDEX idx_items_seller ON order_items(seller_id)",
    "CREATE INDEX idx_pay_order ON order_payments(order_id)",
    "CREATE INDEX idx_rev_order ON order_reviews(order_id)",
]


def build(RAW: Path = Path("data/raw"), DB: Path = Path("data/olist.db"), log=print) -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    for fname, table in FILES.items():
        path = RAW / fname
        if not path.exists():
            sys.exit(f"Missing file: {path}")
        df = pd.read_csv(path, encoding="utf-8-sig")
        df.to_sql(table, con, index=False)
        log(f"{table:22s} {len(df):>8,} rows")
    for stmt in INDEXES:
        con.execute(stmt)
    con.commit()
    con.close()
    log(f"\nBuilt {DB}")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/raw"),
          Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/olist.db"))
