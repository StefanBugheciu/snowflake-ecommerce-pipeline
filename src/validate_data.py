"""Validate the synthetic dataset and compute a source revenue control total."""

import csv
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from src.generate_data import CITIES, CSV_COLUMNS, EXPECTED_COUNTS, ORDER_WINDOW_DAYS


@dataclass(frozen=True)
class DatasetSummary:
    counts: dict[str, int]
    revenue: Decimal


def read_csv(data_dir: Path, table: str) -> list[tuple[int, dict[str, str]]]:
    filename = f"{table}.csv"
    columns = CSV_COLUMNS[table]
    with (data_dir / filename).open(encoding="utf-8", newline="") as source:
        reader = csv.reader(source, strict=True)
        if next(reader, None) != list(columns):
            raise ValueError(f"{filename}: expected header {', '.join(columns)}")

        rows = []
        for fields in reader:
            if len(fields) != len(columns) or any(not field.strip() for field in fields):
                raise ValueError(f"{filename}:{reader.line_num}: missing or extra fields")
            rows.append((reader.line_num, dict(zip(columns, fields, strict=True))))

    if len(rows) != EXPECTED_COUNTS[table]:
        raise ValueError(f"{filename}: expected {EXPECTED_COUNTS[table]} rows, got {len(rows)}")
    return rows


def positive_integer(value: str, field: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]{0,8}", value):
        raise ValueError(f"{field} must be a positive integer with at most nine digits")
    return int(value)


def money(value: str, field: str) -> Decimal:
    if not re.fullmatch(r"[0-9]{1,8}(\.[0-9]{1,2})?", value) or Decimal(value) <= 0:
        raise ValueError(f"{field} must be a positive amount with at most two decimal places")
    return Decimal(value)


def validate_data(data_dir: Path, reference_date: date | None = None) -> DatasetSummary:
    """Require valid CSV rows and relationships before any warehouse changes."""
    ids: dict[str, set[int]] = {}
    revenue = Decimal("0.00")
    for table, columns in CSV_COLUMNS.items():
        primary_key = columns[0]
        seen: set[int] = set()
        for line_number, row in read_csv(data_dir, table):
            try:
                row_id = positive_integer(row[primary_key], primary_key)
                if row_id in seen:
                    raise ValueError(f"duplicate {primary_key} {row_id}")
                seen.add(row_id)
                if table == "customers" and row["city"] not in CITIES:
                    raise ValueError("city is outside the supported list")
                if table == "products":
                    money(row["price"], "price")
                if table == "orders":
                    revenue += validate_order(row, ids, reference_date)
            except ValueError as error:
                raise ValueError(f"{table}.csv:{line_number}: {error}") from error
        ids[table] = seen
    return DatasetSummary({table: len(keys) for table, keys in ids.items()}, revenue)


def validate_order(
    row: dict[str, str], ids: dict[str, set[int]], reference_date: date | None
) -> Decimal:
    for table, key in (("customers", "customer_id"), ("products", "product_id")):
        if positive_integer(row[key], key) not in ids[table]:
            raise ValueError(f"{key} {row[key]} has no matching row in {table}")

    quantity = positive_integer(row["quantity"], "quantity")
    if quantity > 4:
        raise ValueError("quantity must be between 1 and 4")

    order_date = date.fromisoformat(row["order_date"])
    if order_date.isoformat() != row["order_date"]:
        raise ValueError("order_date must use YYYY-MM-DD")
    if reference_date and not timedelta(0) <= reference_date - order_date < timedelta(days=ORDER_WINDOW_DAYS):
        raise ValueError("order_date is outside the 180-day window")

    return quantity * money(row["unit_price_at_sale"], "unit_price_at_sale")
