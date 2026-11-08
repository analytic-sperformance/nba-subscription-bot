
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

from bot.config import get_settings


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    path = get_settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    with db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                chosen_tariff TEXT,
                subscription_active INTEGER NOT NULL DEFAULT 0,
                subscription_until TEXT,
                predictions_remaining INTEGER NOT NULL DEFAULT 0,
                unlimited_until TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                tariff TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
            """
        )

        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        }

        if "predictions_remaining" not in columns:
            connection.execute(
                """
                ALTER TABLE users
                ADD COLUMN predictions_remaining INTEGER NOT NULL DEFAULT 0
                """
            )

        if "unlimited_until" not in columns:
            connection.execute(
                """
                ALTER TABLE users
                ADD COLUMN unlimited_until TEXT
                """
            )

        # Migrate existing active subscriptions to the new field.
        connection.execute(
            """
            UPDATE users
            SET unlimited_until = subscription_until
            WHERE subscription_active = 1
              AND subscription_until IS NOT NULL
              AND (
                  unlimited_until IS NULL
                  OR unlimited_until < subscription_until
              )
            """
        )


def add_user(user_id: int, username: str | None) -> None:
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username
            """,
            (user_id, username),
        )


def set_tariff(user_id: int, tariff: str) -> None:
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (user_id, chosen_tariff)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chosen_tariff = excluded.chosen_tariff
            """,
            (user_id, tariff),
        )


def get_tariff(user_id: int) -> str | None:
    with db_connection() as connection:
        row = connection.execute(
            "SELECT chosen_tariff FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    return row["chosen_tariff"] if row else None


def add_prediction_credits(user_id: int, amount: int) -> int:
    if amount <= 0:
        raise ValueError("Prediction credits must be positive")

    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (user_id, predictions_remaining)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                predictions_remaining =
                    users.predictions_remaining + excluded.predictions_remaining
            """,
            (user_id, amount),
        )

        row = connection.execute(
            """
            SELECT predictions_remaining
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

    return row["predictions_remaining"]


def activate_unlimited(user_id: int, days: int = 30) -> str:
    if days <= 0:
        raise ValueError("Subscription duration must be positive")

    today = date.today()

    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT unlimited_until
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        current_until = None

        if row and row["unlimited_until"]:
            try:
                current_until = date.fromisoformat(
                    row["unlimited_until"]
                )
            except ValueError:
                current_until = None

        if current_until and current_until >= today:
            until = (
                current_until + timedelta(days=days)
            ).isoformat()
        else:
            until = (
                today + timedelta(days=days - 1)
            ).isoformat()

        connection.execute(
            """
            INSERT INTO users (user_id, unlimited_until)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                unlimited_until = excluded.unlimited_until
            """,
            (user_id, until),
        )

    return until


def consume_prediction(user_id: int) -> tuple[bool, str]:
    today = date.today().isoformat()

    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT predictions_remaining, unlimited_until
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if row is None:
            return False, "no_access"

        unlimited_until = row["unlimited_until"]

        if unlimited_until and unlimited_until >= today:
            return True, "unlimited"

        cursor = connection.execute(
            """
            UPDATE users
            SET predictions_remaining = predictions_remaining - 1
            WHERE user_id = ?
              AND predictions_remaining > 0
            """,
            (user_id,),
        )

        if cursor.rowcount == 1:
            return True, "credit"

    return False, "no_access"


def refund_prediction(user_id: int) -> None:
    """Restore one credit if Telegram failed to deliver the file."""
    with db_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET predictions_remaining = predictions_remaining + 1
            WHERE user_id = ?
            """,
            (user_id,),
        )


def access_status(
    user_id: int,
) -> tuple[bool, int, str | None]:
    today = date.today()

    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT predictions_remaining, unlimited_until
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        return False, 0, None

    credits = row["predictions_remaining"]
    unlimited_until = row["unlimited_until"]

    if unlimited_until:
        try:
            expiration_date = date.fromisoformat(unlimited_until)

            if today <= expiration_date:
                return True, credits, unlimited_until
        except ValueError:
            pass

    return credits > 0, credits, None


def deactivate_subscription(user_id: int) -> None:
    with db_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET unlimited_until = NULL,
                subscription_active = 0,
                subscription_until = NULL
            WHERE user_id = ?
            """,
            (user_id,),
        )


def activate_subscription(
    user_id: int,
    days: int | None = None,
) -> str:
    """Backward-compatible alias for admin.py."""
    if days is None:
        days = get_settings().subscription_days

    return activate_unlimited(user_id, days)


def subscription_status(
    user_id: int,
) -> tuple[int, str | None]:
    """Backward-compatible access status."""
    active, _, until = access_status(user_id)
    return int(active), until


def active_users() -> list[int]:
    today = date.today().isoformat()

    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT user_id
            FROM users
            WHERE predictions_remaining > 0
               OR unlimited_until >= ?
            """,
            (today,),
        ).fetchall()

    return [row["user_id"] for row in rows]


def save_receipt(
    from_user: int,
    file_id: str,
    tariff: str | None,
) -> int:
    with db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO receipts (
                from_user, file_id, tariff, status, created_at
            )
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (from_user, file_id, tariff, datetime.now().isoformat()),
        )

        return int(cursor.lastrowid)


def process_receipt_decision(
    receipt_id: int,
    decision: str,
    unlimited_days: int = 30,
) -> tuple[int, str] | None:
    if decision not in {"accepted", "rejected"}:
        raise ValueError("Unsupported receipt decision")

    if unlimited_days <= 0:
        raise ValueError("Subscription duration must be positive")

    package_credits = {
        "5 прогнозов": 5,
        "15 прогнозов": 15,
    }
    unlimited_tariff = "Все прогнозы месяца"

    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        receipt = connection.execute(
            """
            SELECT from_user, tariff
            FROM receipts
            WHERE id = ? AND status = 'pending'
            """,
            (receipt_id,),
        ).fetchone()

        if receipt is None:
            return None

        user_id = receipt["from_user"]
        tariff = receipt["tariff"]

        if decision == "accepted":
            if tariff not in package_credits and tariff != unlimited_tariff:
                raise ValueError(
                    f"Unsupported tariff for receipt: {tariff}"
                )

        cursor = connection.execute(
            """
            UPDATE receipts
            SET status = ?
            WHERE id = ? AND status = 'pending'
            """,
            (decision, receipt_id),
        )

        if cursor.rowcount != 1:
            return None

        if decision == "rejected":
            return user_id, "Чек отклонён."

        if tariff in package_credits:
            amount = package_credits[tariff]

            connection.execute(
                """
                INSERT INTO users (
                    user_id,
                    predictions_remaining
                )
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    predictions_remaining =
                        users.predictions_remaining
                        + excluded.predictions_remaining
                """,
                (user_id, amount),
            )

            row = connection.execute(
                """
                SELECT predictions_remaining
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

            description = (
                f"Начислено прогнозов: {amount}. "
                f"Текущий баланс: {row['predictions_remaining']}."
            )

        else:
            today = date.today()

            row = connection.execute(
                """
                SELECT unlimited_until
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

            current_until = None

            if row and row["unlimited_until"]:
                try:
                    current_until = date.fromisoformat(
                        row["unlimited_until"]
                    )
                except ValueError:
                    current_until = None

            if current_until and current_until >= today:
                until = (
                    current_until + timedelta(days=unlimited_days)
                )
            else:
                until = (
                    today + timedelta(days=unlimited_days - 1)
                )

            until_text = until.isoformat()

            connection.execute(
                """
                INSERT INTO users (
                    user_id,
                    unlimited_until
                )
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    unlimited_until = excluded.unlimited_until
                """,
                (user_id, until_text),
            )

            description = (
                f"Безлимитный доступ активирован до {until_text}."
            )

        return user_id, description


def list_pending_receipts() -> list[sqlite3.Row]:
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, from_user, file_id, tariff, created_at
            FROM receipts
            WHERE status = 'pending'
            ORDER BY created_at
            """
        ).fetchall()

    return rows


def get_receipt(receipt_id: int) -> sqlite3.Row | None:
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT id, from_user, file_id, tariff, status
            FROM receipts
            WHERE id = ?
            """,
            (receipt_id,),
        ).fetchone()

    return row


def set_receipt_status(
    receipt_id: int,
    status: str,
) -> bool:
    if status not in {"accepted", "rejected"}:
        raise ValueError("Unsupported receipt status")

    with db_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE receipts
            SET status = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, receipt_id),
        )

        return cursor.rowcount == 1
