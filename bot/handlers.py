
import logging

from aiogram import F, Router, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile

from bot.config import TARIFFS, get_settings
from bot.database import (
    access_status,
    add_user,
    consume_prediction,
    get_tariff,
    refund_prediction,
    save_receipt,
    set_tariff,
)
from bot.keyboards import (
    main_menu_kb,
    receipt_upload_kb,
    tariffs_kb,
)
from bot.states import UserStates

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    add_user(
        message.from_user.id,
        message.from_user.username,
    )

    await message.answer(
        "Добро пожаловать в Analytics Performance!\n"
        "Прогнозы NBA на основе статистической модели.\n"
        "Используйте кнопки ниже.",
        reply_markup=main_menu_kb(),
    )

    if message.from_user.id == get_settings().admin_id:
        from bot.keyboards import admin_panel_kb

        await message.answer(
            "Панель администратора:",
            reply_markup=admin_panel_kb(),
        )


async def send_info(chat_id: int, bot) -> None:
    await bot.send_message(
        chat_id,
        "Информация о сервисе\n\n"
        "1. Выберите тариф.\n"
        "2. Оплатите подписку согласованным способом.\n"
        "3. Отправьте чек через бота.\n"
        "4. После ручной проверки администратор активирует доступ.\n\n"
        "Пакеты на 5 и 15 прогнозов не имеют срока действия.\n"
        "Тариф «Все прогнозы месяца» даёт безлимит на 30 дней.\n\n"
        "В этой версии автоматическая платёжная интеграция "
        "не реализована.",
    )


@router.callback_query(
    F.data.in_(
        {"info", "buy", "check", "get_pred", "back", "send_receipt"}
    )
    | F.data.startswith("tariff|")
)
async def user_callback(
    query: types.CallbackQuery,
    state: FSMContext,
) -> None:
    data = query.data or ""
    user_id = query.from_user.id
    bot = query.bot

    if data == "info":
        await send_info(user_id, bot)
        await query.answer()
        return

    if data == "buy":
        await bot.send_message(
            user_id,
            "Выберите тариф:",
            reply_markup=tariffs_kb(),
        )
        await query.answer()
        return

    if data == "check":
        active, credits, until = access_status(user_id)

        if until:
            message_text = (
                f"Безлимитный доступ действует до {until}."
            )
        elif credits > 0:
            message_text = f"Осталось прогнозов: {credits}."
        else:
            message_text = (
                "Доступ не активен. Выберите тариф."
            )

        await bot.send_message(
            user_id,
            message_text,
            reply_markup=(
                main_menu_kb() if not active else None
            ),
        )

        await query.answer()
        return

    if data == "get_pred":
        active, _, _ = access_status(user_id)

        if not active:
            await query.answer(
                "Нет доступных прогнозов",
                show_alert=True,
            )
            await bot.send_message(
                user_id,
                "Доступ закончился. Выберите тариф.",
                reply_markup=main_menu_kb(),
            )
            return

        prediction_file = get_settings().prediction_file

        if not prediction_file.is_file():
            await query.answer(
                "Файл прогноза пока недоступен",
                show_alert=True,
            )
            return

        # Reserve one credit before sending to prevent concurrent
        # requests from using the same last credit.
        consumed, access_type = consume_prediction(user_id)

        if not consumed:
            await query.answer(
                "Доступ закончился",
                show_alert=True,
            )
            return

        await query.answer()

        try:
            await bot.send_document(
                user_id,
                FSInputFile(prediction_file),
                caption="Актуальный прогноз NBA",
            )
        except Exception:
            if access_type == "credit":
                refund_prediction(user_id)

            logger.exception(
                "Failed to send prediction to user %s",
                user_id,
            )
            await bot.send_message(
                user_id,
                "Не удалось отправить файл. "
                "Если использовался пакетный прогноз, "
                "он возвращён на баланс. Попробуйте позже.",
            )
            return

        if access_type == "credit":
            _, remaining, _ = access_status(user_id)
            await bot.send_message(
                user_id,
                f"Осталось прогнозов: {remaining}.",
            )

        return

    if data == "back":
        await bot.send_message(
            user_id,
            "Главное меню:",
            reply_markup=main_menu_kb(),
        )
        await query.answer()
        return

    if data.startswith("tariff|"):
        tariff = data.split("|", 1)[1]

        if tariff not in TARIFFS:
            await query.answer(
                "Неизвестный тариф",
                show_alert=True,
            )
            return

        set_tariff(user_id, tariff)

        await bot.send_message(
            user_id,
            f"Вы выбрали тариф «{tariff}» "
            f"стоимостью {TARIFFS[tariff]} ₽.\n\n"
            "После оплаты отправьте чек администратору "
            "через кнопку ниже.",
            reply_markup=receipt_upload_kb(),
        )
        await query.answer()
        return

    if data == "send_receipt":
        await state.set_state(
            UserStates.waiting_for_receipt
        )
        await bot.send_message(
            user_id,
            "Отправьте фотографию или документ "
            "с подтверждением оплаты.",
        )
        await query.answer()
        return

    await query.answer()


@router.message(
    StateFilter(UserStates.waiting_for_receipt),
    F.photo | F.document,
)
async def receive_receipt(
    message: types.Message,
    state: FSMContext,
) -> None:
    if message.document:
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await message.answer(
            "Отправьте фотографию или документ."
        )
        return

    tariff = get_tariff(message.from_user.id)

    receipt_id = save_receipt(
        message.from_user.id,
        file_id,
        tariff,
    )

    await message.answer(
        "Чек получен и ожидает проверки администратора."
    )

    settings = get_settings()

    try:
        if message.document:
            await message.bot.send_document(
                settings.admin_id,
                message.document.file_id,
            )
        else:
            await message.bot.send_photo(
                settings.admin_id,
                message.photo[-1].file_id,
            )

        from bot.keyboards import receipt_admin_kb

        await message.bot.send_message(
            settings.admin_id,
            f"Новый чек #{receipt_id} от пользователя "
            f"{message.from_user.id}. "
            f"Тариф: {tariff or 'не выбран'}.",
            reply_markup=receipt_admin_kb(receipt_id),
        )

    except Exception:
        logger.exception(
            "Failed to notify admin about receipt %s",
            receipt_id,
        )

    await state.clear()


@router.message()
async def fallback(message: types.Message) -> None:
    await message.answer(
        "Используйте кнопки меню.",
        reply_markup=main_menu_kb(),
    )
