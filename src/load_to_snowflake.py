"""Load a validated CSV snapshot and publish it to Snowflake."""

import logging
import os
from decimal import Decimal
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

import snowflake.connector
from dotenv import load_dotenv
from snowflake.connector.connection import SnowflakeConnection
from snowflake.connector.cursor import SnowflakeCursor

from src.generate_data import CSV_COLUMNS
from src.validate_data import DatasetSummary, validate_data

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
DATABASE = "ECOMMERCE_DB"
RAW = f"{DATABASE}.RAW"
STAGE = f"{RAW}.ECOMMERCE_CSV_STAGE"
OAUTH_AUTHENTICATOR = "OAUTH_AUTHORIZATION_CODE"
SESSION_SETTINGS = {
    "role": "SYSADMIN",
    "warehouse": "COMPUTE_WH",
    "database": DATABASE,
    "schema": "RAW",
}


def connect() -> SnowflakeConnection:
    load_dotenv(ROOT / ".env")
    account = os.getenv("SNOWFLAKE_ACCOUNT", "").strip()
    user = os.getenv("SNOWFLAKE_USER", "").strip()
    authenticator = os.getenv("SNOWFLAKE_AUTHENTICATOR", OAUTH_AUTHENTICATOR).strip().upper()
    if not account or not user:
        raise ValueError("Set SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER in .env before connecting")
    if "://" in account or "/" in account or account.lower().endswith("snowflakecomputing.com"):
        raise ValueError("SNOWFLAKE_ACCOUNT must be an account identifier, excluding the URL")

    if authenticator != OAUTH_AUTHENTICATOR:
        raise ValueError(f"Set SNOWFLAKE_AUTHENTICATOR={OAUTH_AUTHENTICATOR} in .env")

    # The connector supplies the client and loopback defaults for SNOWFLAKE$LOCAL_APPLICATION.
    return snowflake.connector.connect(
        account=account,
        user=user,
        authenticator=authenticator,
        login_timeout=120,
        client_store_temporary_credential=False,
        autocommit=True,
        **SESSION_SETTINGS,
    )


def verify_session(cursor: SnowflakeCursor) -> None:
    cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()")
    active = cursor.fetchone()
    expected = tuple(SESSION_SETTINGS.values())
    if active != expected:
        raise RuntimeError(f"Unexpected Snowflake session {active}. Expected {expected}")
    LOGGER.info("Snowflake session verified: %s", " / ".join(expected))


def apply_sql(connection: SnowflakeConnection, filename: str) -> None:
    with (ROOT / "sql" / filename).open(encoding="utf-8") as statements:
        for cursor in connection.execute_stream(statements, remove_comments=True):
            cursor.close()


def copy_to_temporary_table(
    cursor: SnowflakeCursor, file: Path, table: str, expected_count: int
) -> None:
    target = f"{RAW}.ECOMMERCE_LOAD_{table.upper()}"
    cursor.execute(f"CREATE TEMPORARY TABLE {target} LIKE {RAW}.{table}")

    # With file_stream only the URI's basename matters, even for Windows paths.
    with file.open("rb") as stream:
        cursor.execute(
            f"PUT 'file:///{file.name}' @{STAGE} AUTO_COMPRESS=FALSE SOURCE_COMPRESSION=NONE",
            file_stream=stream,
        )
        uploaded = cursor.fetchall()
    if len(uploaded) != 1 or uploaded[0][6] != "UPLOADED":
        raise RuntimeError(f"PUT did not upload {file.name}: {uploaded}")

    cursor.execute(
        f"COPY INTO {target} FROM @{STAGE} "
        f"FILES = ('{file.name}') "
        f"FILE_FORMAT = (FORMAT_NAME = '{RAW}.ECOMMERCE_CSV') ON_ERROR = ABORT_STATEMENT"
    )
    copied = cursor.fetchall()
    if len(copied) != 1 or copied[0][1:4] != ("LOADED", expected_count, expected_count):
        raise RuntimeError(f"Unexpected COPY result for {file.name}: {copied}")
    LOGGER.info("Loaded %s rows from %s into a temporary table", expected_count, file.name)


def verify_warehouse(
    cursor: SnowflakeCursor, expected_revenue: Decimal | None, *, show_checks: bool = False
) -> None:
    sql = (ROOT / "sql" / "04_data_quality_checks.sql").read_text(encoding="utf-8")
    cursor.execute(sql)
    checks = cursor.fetchall()
    if not checks:
        raise RuntimeError("The warehouse quality query returned no checks")
    if show_checks:
        print("CHECK | OBSERVED | EXPECTED | STATUS")
        for name, observed, expected, passed in checks:
            print(f"{name} | {observed} | {expected} | {'PASS' if passed else 'FAIL'}")
    failures = [
        f"{name}: got {observed}, expected {expected}"
        for name, observed, expected, passed in checks
        if not passed
    ]
    observed_totals = {name: observed for name, observed, _, _ in checks}
    if expected_revenue is not None and observed_totals.get("monthly_revenue") != expected_revenue:
        failures.append(
            f"Snowflake monthly revenue does not match expected revenue {expected_revenue}"
        )
    if failures:
        raise RuntimeError("Warehouse data quality checks failed: " + "; ".join(failures))
    LOGGER.info("Passed %s SQL checks. Reconciled revenue: %s",
                len(checks), observed_totals.get("monthly_revenue"))


def publish_snapshot(cursor: SnowflakeCursor, summary: DatasetSummary, refresh: bool) -> None:
    cursor.execute("BEGIN")
    try:
        cursor.execute(
            f"UPDATE {RAW}.ECOMMERCE_PIPELINE_STATE SET successful_loads = successful_loads + 1"
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Expected exactly one pipeline state row")
        if not refresh:
            for table in CSV_COLUMNS:
                cursor.execute(f"SELECT 1 FROM {RAW}.{table} LIMIT 1")
                if cursor.fetchone() is not None:
                    raise RuntimeError(
                        "RAW already contains data. Use run --refresh only to replace "
                        "the three project tables with the current CSV snapshot."
                    )

        insert = "INSERT OVERWRITE INTO" if refresh else "INSERT INTO"
        for table, columns in CSV_COLUMNS.items():
            column_list = ", ".join(columns)
            cursor.execute(
                f"{insert} {RAW}.{table} ({column_list}) "
                f"SELECT {column_list} FROM {RAW}.ECOMMERCE_LOAD_{table.upper()}"
            )
        verify_warehouse(cursor, summary.revenue)
        cursor.execute("COMMIT")
    except BaseException:
        try:
            cursor.execute("ROLLBACK")
        except snowflake.connector.Error:
            LOGGER.exception("Rollback could not be confirmed. Check the Snowflake session history.")
        raise


def check_connection() -> None:
    with connect() as connection, connection.cursor() as cursor:
        verify_session(cursor)


def print_analytics(connection: SnowflakeConnection) -> None:
    with (ROOT / "sql" / "05_analytics_queries.sql").open(encoding="utf-8") as statements:
        for result in connection.execute_stream(statements, remove_comments=True):
            with result:
                print("\n" + " | ".join(column.name for column in result.description))
                for row in result:
                    print(" | ".join(str(value) for value in row))


def run_analytics(expected_revenue: Decimal | None, create_missing_views: bool) -> None:
    with connect() as connection, connection.cursor() as cursor:
        verify_session(cursor)
        if create_missing_views:
            apply_sql(connection, "03_transformations.sql")
            LOGGER.info("Applied create-if-missing definitions in %s.ANALYTICS", DATABASE)
        verify_warehouse(cursor, expected_revenue, show_checks=True)
        print_analytics(connection)


def run_pipeline(data_dir: Path, refresh: bool) -> None:
    # Use the same bytes for local validation and upload, even if data/ is edited later.
    with TemporaryDirectory() as snapshot_dir:
        snapshot = Path(snapshot_dir)
        for table in CSV_COLUMNS:
            name = f"{table}.csv"
            copyfile(data_dir / name, snapshot / name)
        summary = validate_data(snapshot)
        LOGGER.info("Validated local CSVs: %s. Revenue: %s", summary.counts, summary.revenue)

        with connect() as connection, connection.cursor() as cursor:
            verify_session(cursor)
            apply_sql(connection, "02_create_tables.sql")
            cursor.execute(f"CREATE TEMPORARY STAGE {STAGE}")
            for table, count in summary.counts.items():
                copy_to_temporary_table(cursor, snapshot / f"{table}.csv", table, count)

            # Snowflake DDL implicitly commits, so install views before the data transaction.
            apply_sql(connection, "03_transformations.sql")
            publish_snapshot(cursor, summary, refresh)
            LOGGER.info("Published %s RAW rows to %s", sum(summary.counts.values()), DATABASE)

            print_analytics(connection)
