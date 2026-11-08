
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import sqlite3

import bot.database as database


class DatabaseLogicTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"

        self.settings = SimpleNamespace(
            database_path=self.db_path,
            subscription_days=30,
        )

        self.settings_patcher = patch.object(
            database,
            "get_settings",
            return_value=self.settings,
        )
        self.settings_patcher.start()

        database.init_db()

    def tearDown(self):
        self.settings_patcher.stop()
        self.temp_dir.cleanup()

    def create_receipt(self, user_id, tariff):
        return database.save_receipt(
            from_user=user_id,
            file_id="test-file-id",
            tariff=tariff,
        )

    def test_package_credits_accumulate(self):
        receipt_5 = self.create_receipt(1001, "5 прогнозов")
        receipt_15 = self.create_receipt(1001, "15 прогнозов")

        database.process_receipt_decision(receipt_5, "accepted")
        database.process_receipt_decision(receipt_15, "accepted")

        active, credits, until = database.access_status(1001)

        self.assertTrue(active)
        self.assertEqual(credits, 20)
        self.assertIsNone(until)

    def test_rejected_receipt_does_not_grant_access(self):
        receipt_id = self.create_receipt(1002, "5 прогнозов")

        result = database.process_receipt_decision(
            receipt_id,
            "rejected",
        )

        self.assertEqual(result[0], 1002)

        receipt = database.get_receipt(receipt_id)
        self.assertEqual(receipt["status"], "rejected")

        active, credits, until = database.access_status(1002)

        self.assertFalse(active)
        self.assertEqual(credits, 0)
        self.assertIsNone(until)

        second_result = database.process_receipt_decision(
            receipt_id,
            "accepted",
        )
        self.assertIsNone(second_result)

    def test_unlimited_period_and_extension(self):
        first_receipt = self.create_receipt(
            1003,
            "Все прогнозы месяца",
        )
        second_receipt = self.create_receipt(
            1003,
            "Все прогнозы месяца",
        )

        database.process_receipt_decision(
            first_receipt,
            "accepted",
        )
        first_until = date.fromisoformat(
            database.access_status(1003)[2]
        )

        database.process_receipt_decision(
            second_receipt,
            "accepted",
        )
        second_until = date.fromisoformat(
            database.access_status(1003)[2]
        )

        self.assertEqual(
            first_until,
            date.today() + timedelta(days=29),
        )
        self.assertEqual(
            second_until,
            first_until + timedelta(days=30),
        )

    def test_unlimited_does_not_consume_package_credits(self):
        database.add_prediction_credits(1004, 5)
        database.activate_unlimited(1004, 30)

        result = database.consume_prediction(1004)

        self.assertEqual(result, (True, "unlimited"))
        self.assertEqual(
            database.access_status(1004)[1],
            5,
        )

    def test_credit_consumption_and_refund(self):
        database.add_prediction_credits(1005, 2)

        self.assertEqual(
            database.consume_prediction(1005),
            (True, "credit"),
        )
        self.assertEqual(
            database.access_status(1005)[1],
            1,
        )

        database.refund_prediction(1005)

        self.assertEqual(
            database.access_status(1005)[1],
            2,
        )

    def test_expired_unlimited_falls_back_to_credits(self):
        database.add_prediction_credits(1006, 3)

        with database.db_connection() as connection:
            expired = (
                date.today() - timedelta(days=1)
            ).isoformat()

            connection.execute(
                """
                UPDATE users
                SET unlimited_until = ?
                WHERE user_id = ?
                """,
                (expired, 1006),
            )

        self.assertEqual(
            database.consume_prediction(1006),
            (True, "credit"),
        )
        self.assertEqual(
            database.access_status(1006)[1],
            2,
        )

    def test_deactivation_preserves_package_credits(self):
        database.add_prediction_credits(1007, 15)
        database.activate_unlimited(1007, 30)

        database.deactivate_subscription(1007)

        active, credits, until = database.access_status(1007)

        self.assertTrue(active)
        self.assertEqual(credits, 15)
        self.assertIsNone(until)

    def test_unknown_tariff_is_not_processed(self):
        receipt_id = self.create_receipt(
            1008,
            "Неизвестный тариф",
        )

        with self.assertRaises(ValueError):
            database.process_receipt_decision(
                receipt_id,
                "accepted",
            )

        receipt = database.get_receipt(receipt_id)

        self.assertEqual(receipt["status"], "pending")
        self.assertEqual(
            database.access_status(1008)[1],
            0,
        )

    def test_receipt_cannot_be_processed_twice(self):
        receipt_id = self.create_receipt(1009, "5 прогнозов")

        first = database.process_receipt_decision(
            receipt_id,
            "accepted",
        )
        second = database.process_receipt_decision(
            receipt_id,
            "accepted",
        )

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(
            database.access_status(1009)[1],
            5,
        )

    def test_failed_credit_grant_rolls_back_receipt_status(self):
        receipt_id = self.create_receipt(1010, "5 прогнозов")

        with database.db_connection() as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_user_insert
                BEFORE INSERT ON users
                BEGIN
                    SELECT RAISE(ABORT, 'forced test failure');
                END
                """
            )

        with self.assertRaises(sqlite3.IntegrityError):
            database.process_receipt_decision(
                receipt_id,
                "accepted",
            )

        receipt = database.get_receipt(receipt_id)

    def test_migration_from_legacy_schema(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"

        connection = sqlite3.connect(legacy_path)
        try:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        chosen_tariff TEXT,
                        subscription_active INTEGER NOT NULL DEFAULT 0,
                        subscription_until TEXT
                    )
                    """
                )

                old_until = (
                    date.today() + timedelta(days=10)
                ).isoformat()

                connection.execute(
                    """
                    INSERT INTO users (
                        user_id,
                        username,
                        chosen_tariff,
                        subscription_active,
                        subscription_until
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (2001, "legacy_user", "Месячный", 1, old_until),
                )
        finally:
            connection.close()

        legacy_settings = SimpleNamespace(
            database_path=legacy_path,
            subscription_days=30,
        )

        with patch.object(
            database,
            "get_settings",
            return_value=legacy_settings,
        ):
            database.init_db()

            with database.db_connection() as connection:
                columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(users)"
                    ).fetchall()
                }

                user = connection.execute(
                    """
                    SELECT predictions_remaining, unlimited_until
                    FROM users
                    WHERE user_id = ?
                    """,
                    (2001,),
                ).fetchone()

        self.assertIn("predictions_remaining", columns)
        self.assertIn("unlimited_until", columns)
        self.assertEqual(user["predictions_remaining"], 0)
        self.assertEqual(user["unlimited_until"], old_until)

if __name__ == "__main__":
    unittest.main(verbosity=2)
