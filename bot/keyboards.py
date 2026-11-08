from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import TARIFFS


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💳 Купить подписку",
                callback_data="buy",
            )],
            [InlineKeyboardButton(
                text="📅 Проверить подписку",
                callback_data="check",
            )],
            [InlineKeyboardButton(
                text="📊 Получить прогноз",
                callback_data="get_pred",
            )],
            [InlineKeyboardButton(
                text="ℹ️ Информация",
                callback_data="info",
            )],
        ]
    )


def tariffs_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{name} — {price}₽",
            callback_data=f"tariff|{name}",
        )]
        for name, price in TARIFFS.items()
    ]

    rows.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="back",
    )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🟢 Активировать подписку",
                callback_data="admin|activate",
            )],
            [InlineKeyboardButton(
                text="🔴 Деактивировать подписку",
                callback_data="admin|deactivate",
            )],
            [InlineKeyboardButton(
                text="✅ Проверить чеки",
                callback_data="admin|check_receipts",
            )],
            [InlineKeyboardButton(
                text="📨 Рассылка подписчикам",
                callback_data="admin|broadcast",
            )],
        ]
    )


def receipt_admin_kb(receipt_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Принять и активировать",
                callback_data=f"receipt|accept|{receipt_id}",
            )],
            [InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"receipt|reject|{receipt_id}",
            )],
        ]
    )


def receipt_upload_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Отправить чек",
                callback_data="send_receipt",
            )],
            [InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="back",
            )],
        ]
    )
