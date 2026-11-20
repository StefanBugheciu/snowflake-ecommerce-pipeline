"""Exercise the shared SQL logic locally with SQLite and a DATE_TRUNC shim."""

import csv
import sqlite3
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from src.generate_data import generate_data

ROOT = Path(__file__).resolve().parents[1]


def local_sql(filename):
    return (
        (ROOT / "sql" / filename).read_text(encoding="utf-8")
        .replace("ECOMMERCE_DB.RAW.", "raw_")
        .replace("ECOMMERCE_DB.ANALYTICS.", "analytics_")
    )


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        data_dir = Path(directory.name)
        generate_data(data_dir, date(2026, 11, 20))
        self.db.create_function("DATE_TRUNC", 2, lambda unit, day: day[:7] + "-01")
        self.db.executescript("""
            CREATE TABLE raw_customers (customer_id INT, customer_name TEXT, city TEXT);
            CREATE TABLE raw_products (product_id INT, product_name TEXT, category TEXT, price NUMERIC);
            CREATE TABLE raw_orders (order_id INT, customer_id INT, product_id INT, quantity INT,
                                     unit_price_at_sale NUMERIC, order_date TEXT);
        """)
        for table, columns in (("customers", 3), ("products", 4), ("orders", 6)):
            with (data_dir / f"{table}.csv").open(encoding="utf-8", newline="") as source:
                reader = csv.reader(source)
                next(reader)
                placeholders = ", ".join(["?"] * columns)
                self.db.executemany(f"INSERT INTO raw_{table} VALUES ({placeholders})", reader)
        self.db.executescript(local_sql("03_transformations.sql"))

    def test_views_reconcile_to_raw_revenue_and_counts(self):
        # Catalog changes must leave historical sales unchanged.
        self.db.execute("UPDATE raw_products SET price = price * 2")
        results = self.db.execute(local_sql("04_data_quality_checks.sql")).fetchall()
        self.assertEqual(len(results), 25)
        self.assertTrue(all(passed for _, _, _, passed in results), results)
        self.assertIn(("monthly_revenue", 932270, 932270, 1), results)

    def test_quality_query_detects_duplicate_and_missing_references(self):
        self.db.execute("UPDATE raw_orders SET order_id = 1, customer_id = 999 WHERE order_id = 2")
        checks = self.db.execute(local_sql("04_data_quality_checks.sql")).fetchall()
        failures = {name for name, _, _, passed in checks if not passed}
        self.assertIn("orders_duplicate_ids", failures)
        self.assertIn("missing_customer_references", failures)
        self.assertIn("monthly_revenue", failures)

    def test_business_queries_return_ranked_products_and_five_customers(self):
        statements = local_sql("05_analytics_queries.sql").strip().rstrip(";").split(";")
        monthly, products, cities, customers, categories = [
            self.db.execute(statement).fetchall() for statement in statements
        ]
        self.assertEqual(sum(row[2] for row in monthly), 932270)
        self.assertEqual([row[0] for row in products], [1, 1, 2, 3])
        self.assertEqual(len(cities), 5)
        self.assertEqual(len(customers), 5)
        self.assertEqual(sum(row[1] for row in categories), 500)

    def test_creating_missing_views_preserves_existing_definitions(self):
        self.db.execute("DROP VIEW analytics_monthly_revenue")
        self.db.execute("CREATE VIEW analytics_monthly_revenue AS SELECT 42 AS sentinel")
        self.db.executescript(local_sql("03_transformations.sql"))
        self.assertEqual(self.db.execute("SELECT sentinel FROM analytics_monthly_revenue").fetchone(),
                         (42,))
