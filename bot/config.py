import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_id: int
    subscription_days: int
    database_path: Path
    prediction_file: Path


def get_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    admin_id_raw = os.getenv("ADMIN_ID", "").strip()

    if not token:
        raise ValueError("BOT_TOKEN is not configured in .env")

    if not admin_id_raw:
        raise ValueError("ADMIN_ID is not configured in .env")

    try:
        admin_id = int(admin_id_raw)
    except ValueError as exc:
        raise ValueError("ADMIN_ID must be an integer") from exc

    days = int(os.getenv("SUBSCRIPTION_DAYS", "30"))

    if days <= 0:
        raise ValueError("SUBSCRIPTION_DAYS must be greater than zero")

    database_path = Path(os.getenv("DB_PATH", "subscribers.db"))
    prediction_file = Path(
        os.getenv(
            "PREDICTION_FILE",
            "output/Future_Matches_Predictions.csv"
        )
    )

    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path

    if not prediction_file.is_absolute():
        prediction_file = PROJECT_ROOT / prediction_file

    return Settings(
        bot_token=token,
        admin_id=admin_id,
        subscription_days=days,
        database_path=database_path,
        prediction_file=prediction_file,
    )


TARIFFS = {
    "5 прогнозов": 500,
    "15 прогнозов": 1200,
    "Все прогнозы месяца": 2500,
}
