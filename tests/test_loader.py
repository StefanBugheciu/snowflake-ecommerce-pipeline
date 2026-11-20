import os
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

from src.generate_data import generate_data
from src.load_to_snowflake import (
    check_connection,
    connect,
    copy_to_temporary_table,
    publish_snapshot,
    run_analytics,
    run_pipeline,
)
from src.validate_data import DatasetSummary

SUMMARY = DatasetSummary({"customers": 50, "products": 6, "orders": 500}, Decimal("932270.00"))


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.cursor = Mock(rowcount=1)
        self.cursor.fetchone.return_value = None
        self.cursor.fetchall.return_value = [
            ("monthly_revenue", SUMMARY.revenue, SUMMARY.revenue, True)
        ]

    def statements(self):
        return [entry.args[0] for entry in self.cursor.execute.call_args_list]

    def test_first_load_publishes_all_tables_in_one_transaction(self):
        publish_snapshot(self.cursor, SUMMARY, refresh=False)
        statements = self.statements()
        self.assertEqual(statements[0], "BEGIN")
        self.assertEqual(statements[-1], "COMMIT")
        self.assertTrue(statements[1].startswith("UPDATE ECOMMERCE_DB.RAW.ECOMMERCE_PIPELINE_STATE"))
        for table in SUMMARY.counts:
            self.assertTrue(any(s.startswith(f"INSERT INTO ECOMMERCE_DB.RAW.{table} ")
                                for s in statements))

    def test_refresh_uses_overwrite_for_all_raw_tables(self):
        publish_snapshot(self.cursor, SUMMARY, refresh=True)
        self.assertEqual(sum(s.startswith("INSERT OVERWRITE INTO") for s in self.statements()), 3)

    def test_first_load_protects_existing_rows(self):
        self.cursor.fetchone.return_value = (1,)
        with self.assertRaisesRegex(RuntimeError, "RAW already contains data"):
            publish_snapshot(self.cursor, SUMMARY, refresh=False)
        self.assertFalse(any(s.startswith("INSERT") for s in self.statements()))
        self.assertEqual(self.statements()[-1], "ROLLBACK")

    def test_failed_sql_check_rolls_back(self):
        self.cursor.fetchall.return_value.append(("orders_rows", 499, 500, False))
        with self.assertRaisesRegex(RuntimeError, "orders_rows"):
            publish_snapshot(self.cursor, SUMMARY, refresh=True)
        self.assertEqual(self.statements()[-1], "ROLLBACK")
        self.assertNotIn("COMMIT", self.statements())

    def test_warehouse_revenue_must_match_csv_even_if_sql_checks_pass(self):
        self.cursor.fetchall.return_value = [("monthly_revenue", 1, 1, True)]
        with self.assertRaisesRegex(RuntimeError, "does not match expected revenue"):
            publish_snapshot(self.cursor, SUMMARY, refresh=True)
        self.assertEqual(self.statements()[-1], "ROLLBACK")

    def test_copy_rejects_unexpected_row_count(self):
        self.cursor.fetchall.side_effect = [
            [("orders.csv", "orders.csv", 1, 1, "NONE", "NONE", "UPLOADED", "")],
            [("orders.csv", "LOADED", 499, 499, 1, 0, None, None, None, None)],
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "orders.csv"
            path.write_bytes(b"order_id\n")
            with self.assertRaisesRegex(RuntimeError, "Unexpected COPY result"):
                copy_to_temporary_table(self.cursor, path, "orders", 500)
        self.assertIn("ON_ERROR = ABORT_STATEMENT", self.statements()[-1])

    @patch("src.load_to_snowflake.connect")
    def test_invalid_source_never_connects(self, connection):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            generate_data(path, date(2026, 11, 20))
            (path / "orders.csv").write_text("invalid header\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "orders.csv: expected header"):
                run_pipeline(path, refresh=False)
        connection.assert_not_called()

    @patch("src.load_to_snowflake.load_dotenv")
    @patch("src.load_to_snowflake.snowflake.connector.connect")
    def test_connection_requires_an_account_and_user(self, driver, _):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER"):
                connect()
        driver.assert_not_called()

    @patch("src.load_to_snowflake.load_dotenv")
    @patch("src.load_to_snowflake.snowflake.connector.connect")
    def test_local_oauth_uses_expected_project_session(self, driver, _):
        with patch.dict(os.environ, {"SNOWFLAKE_ACCOUNT": "ORG-TEST", "SNOWFLAKE_USER": "USER"},
                        clear=True):
            connect()
        options = driver.call_args.kwargs
        self.assertEqual(options["authenticator"], "OAUTH_AUTHORIZATION_CODE")
        self.assertEqual(options["role"], "SYSADMIN")
        self.assertEqual(options["warehouse"], "COMPUTE_WH")
        self.assertEqual(options["database"], "ECOMMERCE_DB")
        self.assertEqual(options["schema"], "RAW")
        self.assertFalse(options["client_store_temporary_credential"])
        for field in ("password", "token", "oauth_client_id", "oauth_client_secret",
                      "oauth_authorization_url", "oauth_token_request_url"):
            self.assertNotIn(field, options)

    @patch("src.load_to_snowflake.load_dotenv")
    @patch("src.load_to_snowflake.snowflake.connector.connect")
    def test_explicit_oauth_setting_is_accepted(self, driver, _):
        settings = {
            "SNOWFLAKE_ACCOUNT": "ORG-TEST",
            "SNOWFLAKE_USER": "USER",
            "SNOWFLAKE_AUTHENTICATOR": "oauth_authorization_code",
        }
        with patch.dict(os.environ, settings, clear=True):
            connect()
        self.assertEqual(driver.call_args.kwargs["authenticator"], "OAUTH_AUTHORIZATION_CODE")

    @patch("src.load_to_snowflake.load_dotenv")
    @patch("src.load_to_snowflake.snowflake.connector.connect")
    def test_legacy_authenticator_requests_migration_without_connecting(self, driver, _):
        settings = {
            "SNOWFLAKE_ACCOUNT": "ORG-TEST",
            "SNOWFLAKE_USER": "USER",
            "SNOWFLAKE_AUTHENTICATOR": "externalbrowser",
        }
        with patch.dict(os.environ, settings, clear=True):
            with self.assertRaisesRegex(ValueError, "SNOWFLAKE_AUTHENTICATOR=OAUTH_AUTHORIZATION_CODE"):
                connect()
        driver.assert_not_called()

    @patch("src.load_to_snowflake.connect")
    def test_connection_check_only_reads_session_context(self, open_connection):
        connection = MagicMock()
        open_connection.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = self.cursor
        self.cursor.fetchone.return_value = ("SYSADMIN", "COMPUTE_WH", "ECOMMERCE_DB", "RAW")
        check_connection()
        self.cursor.execute.assert_called_once_with(
            "SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()"
        )

    @patch("src.load_to_snowflake.print_analytics")
    @patch("src.load_to_snowflake.apply_sql")
    @patch("src.load_to_snowflake.connect")
    def test_analytics_only_installs_views_when_requested(self, open_connection, apply_sql, reports):
        connection = MagicMock()
        open_connection.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = self.cursor
        self.cursor.fetchone.return_value = ("SYSADMIN", "COMPUTE_WH", "ECOMMERCE_DB", "RAW")

        for create_missing_views in (False, True):
            with self.subTest(create_missing_views=create_missing_views), patch("builtins.print"):
                self.cursor.reset_mock()
                apply_sql.reset_mock()
                reports.reset_mock()
                run_analytics(SUMMARY.revenue, create_missing_views)
                if create_missing_views:
                    apply_sql.assert_called_once_with(connection, "03_transformations.sql")
                else:
                    apply_sql.assert_not_called()
                reports.assert_called_once_with(connection)
                session, checks = self.statements()
                self.assertTrue(session.startswith("SELECT CURRENT_ROLE()"))
                self.assertIn("WITH raw_order_totals", checks)
