import csv
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from src.generate_data import CITIES, generate_data
from src.validate_data import validate_data

REFERENCE_DATE = date(2026, 11, 20)


class DatasetTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.data = Path(directory.name) / "data"
        generate_data(self.data, REFERENCE_DATE)

    def read_csv(self, name):
        with (self.data / name).open(encoding="utf-8", newline="") as source:
            return list(csv.reader(source))

    def replace_cell(self, name, row, column, value):
        rows = self.read_csv(name)
        rows[row][column] = value
        with (self.data / name).open("w", encoding="utf-8", newline="") as output:
            csv.writer(output).writerows(rows)

    def test_csv_schema_and_counts(self):
        for name, header, count in (
            ("customers.csv", ["customer_id", "customer_name", "city"], 50),
            ("products.csv", ["product_id", "product_name", "category", "price"], 6),
            ("orders.csv", ["order_id", "customer_id", "product_id", "quantity",
                            "unit_price_at_sale", "order_date"], 500),
        ):
            with self.subTest(name=name):
                actual_header, *rows = self.read_csv(name)
                self.assertEqual(actual_header, header)
                self.assertEqual(len(rows), count)
                self.assertTrue(all(len(row) == len(header) for row in rows))
                self.assertEqual([int(row[0]) for row in rows], list(range(1, count + 1)))
                self.assertEqual((self.data / name).read_bytes().count(b"\r\n"), count + 1)

    def test_customers_and_catalog(self):
        customers = self.read_csv("customers.csv")[1:]
        self.assertTrue(all(name == f"Customer_{key}" and city in CITIES
                            for key, name, city in customers))
        self.assertEqual(self.read_csv("products.csv")[1:], [
            ["1", "Laptop", "Electronics", "3500.00"],
            ["2", "Mouse", "Accessories", "85.00"],
            ["3", "Keyboard", "Accessories", "150.00"],
            ["4", "Monitor", "Electronics", "900.00"],
            ["5", "Headphones", "Audio", "250.00"],
            ["6", "Webcam", "Accessories", "180.00"],
        ])

    def test_orders_have_valid_references_quantities_prices_and_dates(self):
        customers = {row[0] for row in self.read_csv("customers.csv")[1:]}
        catalog = {row[0]: row[3] for row in self.read_csv("products.csv")[1:]}
        for _, customer, product, quantity, price, day in self.read_csv("orders.csv")[1:]:
            self.assertIn(customer, customers)
            self.assertIn(product, catalog)
            self.assertIn(int(quantity), range(1, 5))
            self.assertEqual(price, catalog[product])
            self.assertLessEqual(REFERENCE_DATE - timedelta(days=179), date.fromisoformat(day))
            self.assertLessEqual(date.fromisoformat(day), REFERENCE_DATE)

    def test_reproducible_with_fixed_reference_date(self):
        other = self.data.with_name("other")
        generate_data(other, REFERENCE_DATE)
        for path in self.data.glob("*.csv"):
            self.assertEqual(path.read_bytes(), (other / path.name).read_bytes())

    def test_compute_source_revenue_from_sale_price(self):
        summary = validate_data(self.data, REFERENCE_DATE)
        self.assertEqual(summary.counts, {"customers": 50, "products": 6, "orders": 500})
        self.assertEqual(summary.revenue, Decimal("932270.00"))
        self.replace_cell("products.csv", 1, 3, "4000.00")
        self.assertEqual(validate_data(self.data).revenue, summary.revenue)

    def test_reject_invalid_rows(self):
        for name, row, column, value, message in (
            ("customers.csv", 2, 0, "1", "duplicate customer_id"),
            ("products.csv", 2, 0, "1", "duplicate product_id"),
            ("orders.csv", 2, 0, "1", "duplicate order_id"),
            ("orders.csv", 1, 1, "51", "no matching row in customers"),
            ("orders.csv", 1, 2, "7", "no matching row in products"),
            ("orders.csv", 1, 3, "0", "positive integer"),
            ("orders.csv", 1, 3, "5", "between 1 and 4"),
            ("orders.csv", 1, 4, "1.234", "positive amount"),
            ("orders.csv", 1, 4, "0", "positive amount"),
            ("orders.csv", 1, 5, "2026-02-30", "orders.csv:2:"),
            ("orders.csv", 1, 5, "2026-01-01", "outside the 180-day window"),
            ("customers.csv", 1, 2, "", "missing or extra fields"),
            ("customers.csv", 0, 2, "country", "expected header"),
        ):
            with self.subTest(name=name, row=row, column=column, value=value):
                generate_data(self.data, REFERENCE_DATE)
                self.replace_cell(name, row, column, value)
                with self.assertRaisesRegex(ValueError, message):
                    validate_data(self.data, REFERENCE_DATE)

    def test_reject_missing_data_row(self):
        path = self.data / "products.csv"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "expected 6 rows, got 5"):
            validate_data(self.data)
