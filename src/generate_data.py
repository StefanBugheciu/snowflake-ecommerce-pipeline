"""Generate the three synthetic e-commerce CSV files."""

import csv
import random
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

CITIES = ("Bucharest", "Cluj", "Brasov", "Iasi", "Timisoara")
PRODUCTS = (
    (1, "Laptop", "Electronics", "3500.00"),
    (2, "Mouse", "Accessories", "85.00"),
    (3, "Keyboard", "Accessories", "150.00"),
    (4, "Monitor", "Electronics", "900.00"),
    (5, "Headphones", "Audio", "250.00"),
    (6, "Webcam", "Accessories", "180.00"),
)
CUSTOMER_COUNT = 50
ORDER_COUNT = 500
ORDER_WINDOW_DAYS = 180
SEED = 42

CSV_COLUMNS = {
    "customers": ("customer_id", "customer_name", "city"),
    "products": ("product_id", "product_name", "category", "price"),
    "orders": ("order_id", "customer_id", "product_id", "quantity",
               "unit_price_at_sale", "order_date"),
}
EXPECTED_COUNTS = {
    "customers": CUSTOMER_COUNT,
    "products": len(PRODUCTS),
    "orders": ORDER_COUNT,
}


def write_csv(path: Path, columns: tuple[str, ...], rows: Iterable[tuple]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        # Snowflake's SKIP_HEADER expects CRLF-delimited header lines.
        writer = csv.writer(output)
        writer.writerow(columns)
        writer.writerows(rows)


def generate_data(data_dir: Path, reference_date: date) -> None:
    """Generate 180 calendar dates ending on reference_date (inclusive)."""
    earliest_order = reference_date - timedelta(days=ORDER_WINDOW_DAYS - 1)
    rng = random.Random(SEED)
    data_dir.mkdir(parents=True, exist_ok=True)

    customers = [
        (customer_id, f"Customer_{customer_id}", rng.choice(CITIES))
        for customer_id in range(1, CUSTOMER_COUNT + 1)
    ]
    orders = []
    for order_id in range(1, ORDER_COUNT + 1):
        customer_id = rng.randint(1, CUSTOMER_COUNT)
        product_id, _, _, price = rng.choice(PRODUCTS)
        quantity = rng.randint(1, 4)
        order_date = earliest_order + timedelta(days=rng.randrange(ORDER_WINDOW_DAYS))
        orders.append((order_id, customer_id, product_id, quantity, price, order_date))

    write_csv(data_dir / "customers.csv", CSV_COLUMNS["customers"], customers)
    write_csv(data_dir / "products.csv", CSV_COLUMNS["products"], PRODUCTS)
    write_csv(data_dir / "orders.csv", CSV_COLUMNS["orders"], orders)
