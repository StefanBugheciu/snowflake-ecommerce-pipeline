"""Generate, validate, and load the e-commerce warehouse dataset."""

import argparse
import csv
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from src.generate_data import generate_data
from src.validate_data import DatasetSummary, validate_data

DATA_DIR = Path(__file__).resolve().parent / "data"


def report(summary: DatasetSummary) -> None:
    logging.info("Validated CSV rows: %s", summary.counts)
    logging.info("Total rows: %s. Source revenue: %s", sum(summary.counts.values()), summary.revenue)


def revenue_amount(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError("Expected revenue must be a decimal amount") from error
    if not amount.is_finite() or amount < 0:
        raise argparse.ArgumentTypeError("Expected revenue must be a finite nonnegative amount")
    return amount


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Generate and validate the three CSV files")
    generate.add_argument("--reference-date", type=date.fromisoformat, default=date.today())
    commands.add_parser("validate", help="Validate the current CSV files")
    commands.add_parser("check-connection", help="Sign in via OAuth and verify the Snowflake session")
    analytics = commands.add_parser("analytics", help="Check and report on the current RAW snapshot")
    analytics.add_argument("--expected-revenue", type=revenue_amount, help="Expected total revenue")
    analytics.add_argument(
        "--create-missing-views", action="store_true", help="Create missing ANALYTICS views"
    )
    run = commands.add_parser("run", help="Load the current CSVs, check quality, and run analytics")
    run.add_argument("--refresh", action="store_true", help="Replace existing project RAW data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("snowflake.connector").setLevel(logging.WARNING)

    try:
        if args.command == "generate":
            generate_data(DATA_DIR, args.reference_date)
            report(validate_data(DATA_DIR, args.reference_date))
        elif args.command == "validate":
            report(validate_data(DATA_DIR))
        else:
            from snowflake.connector import Error

            from src.load_to_snowflake import check_connection, run_analytics, run_pipeline

            try:
                if args.command == "check-connection":
                    check_connection()
                elif args.command == "analytics":
                    run_analytics(args.expected_revenue, args.create_missing_views)
                else:
                    run_pipeline(DATA_DIR, args.refresh)
            except Error as error:
                logging.error("Snowflake connection or query failed: %s", error)
                return 1
    except (OSError, ValueError, OverflowError, RuntimeError, csv.Error) as error:
        logging.error("%s", error)
        return 1
    except ModuleNotFoundError as error:
        if error.name not in {"snowflake", "dotenv"}:
            raise
        logging.error("Install requirements.txt in the project environment before connecting")
        return 1
    except KeyboardInterrupt:
        logging.error("Interrupted")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
