
import logging

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile

from bot.config import get_settings
from bot.database import (
    active_users,
    activate_subscription,
    deactivate_subscription,
    list_pending_receipts,
    process_receipt_decision,
)
from bot.keyboards import admin_panel_kb, receipt_admin_kb
from bot.states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id == get_settings().admin_id


@router.callback_query(
    F.data.startswith("admin|") | F.data.startswith("receipt|")
)
async def admin_callback(
    query: types.CallbackQuery,
    state: FSMContext,
) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("Нет прав", show_alert=True)
        return

    data = query.data or ""
    bot = query.bot
    admin_id = get_settings().admin_id

    if data.startswith("admin|"):
        action = data.split("|", 1)[1]

        if action in {"activate", "deactivate"}:
            await state.update_data(admin_action=action)
            await state.set_state(
                AdminStates.waiting_for_user_id
            )
            await query.message.answer(
                "Отправьте числовой Telegram ID пользователя."
            )
            await query.answer()
            return

        if action == "broadcast":
            await state.set_state(
                AdminStates.waiting_for_broadcast
            )
            await query.message.answer(
                "Отправьте текст рассылки для пользователей "
                "с действующим доступом."
            )
            await query.answer()
            return

        if action == "check_receipts":
            receipts = list_pending_receipts()

            if not receipts:
                await query.message.answer(
                    "Нет чеков, ожидающих проверки."
                )
                await query.answer()
                return

            for receipt in receipts:
                receipt_id = receipt["id"]
                file_id = receipt["file_id"]

                try:
                    await bot.send_document(admin_id, file_id)
                except Exception:
                    try:
                        await bot.send_photo(admin_id, file_id)
                    except Exception:
                        logger.exception(
                            "Cannot send receipt %s to admin",
                            receipt_id,
                        )

                await bot.send_message(
                    admin_id,
                    f"Чек #{receipt_id}. "
                    f"Пользователь: {receipt['from_user']}. "
                    f"Тариф: {receipt['tariff']}. "
                    f"Дата: {receipt['created_at']}.",
                    reply_markup=receipt_admin_kb(receipt_id),
                )

            await query.answer()
            return

        await query.answer(
            "Неизвестное действие",
            show_alert=True,
        )
        return

    parts = data.split("|")

    if len(parts) != 3:
        await query.answer(
            "Некорректный запрос",
            show_alert=True,
        )
        return

    _, decision, receipt_id_raw = parts

    if decision not in {"accept", "reject"}:
        await query.answer(
            "Неизвестное решение",
            show_alert=True,
        )
        return

    try:
        receipt_id = int(receipt_id_raw)
    except ValueError:
        await query.answer(
            "Некорректный номер чека",
            show_alert=True,
        )
        return

    new_status = (
        "accepted" if decision == "accept" else "rejected"
    )

    try:
        result = process_receipt_decision(
            receipt_id,
            new_status,
        )
    except ValueError as error:
        logger.warning(
            "Cannot process receipt %s: %s",
            receipt_id,
            error,
        )
        await query.answer(
            "Неизвестный тариф. Чек не обработан.",
            show_alert=True,
        )
        return
    except Exception:
        logger.exception(
            "Failed to process receipt %s",
            receipt_id,
        )
        await query.answer(
            "Ошибка обработки чека",
            show_alert=True,
        )
        return

    if result is None:
        await query.answer(
            "Чек не найден или уже обработан",
            show_alert=True,
        )
        return

    user_id, description = result

    if decision == "accept":
        await query.message.edit_text(
            f"Чек #{receipt_id} принят.\n"
            f"Пользователь: {user_id}.\n"
            f"{description}"
        )

        try:
            await bot.send_message(
                user_id,
                f"Оплата подтверждена. {description}",
            )
        except Exception:
            logger.exception(
                "Cannot notify user %s about accepted receipt",
                user_id,
            )

    else:
        await query.message.edit_text(
            f"Чек #{receipt_id} отклонён."
        )

        try:
            await bot.send_message(
                user_id,
                "Чек отклонён администратором. "
                "Свяжитесь с поддержкой для уточнения.",
            )
        except Exception:
            logger.exception(
                "Cannot notify user %s about rejected receipt",
                user_id,
            )

    await query.answer()


@router.message(
    StateFilter(AdminStates.waiting_for_user_id),
    F.text,
)
async def admin_receive_user_id(
    message: types.Message,
    state: FSMContext,
) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    action = data.get("admin_action")

    try:
        target_id = int(message.text.strip())
    except (ValueError, AttributeError):
        await message.answer(
            "ID должен быть целым числом."
        )
        return

    if action == "activate":
        until = activate_subscription(target_id)

        response = (
            f"Безлимитный доступ пользователя {target_id} "
            f"активирован до {until}."
        )
        notification = (
            f"Администратор активировал безлимитный доступ "
            f"до {until}."
        )

    elif action == "deactivate":
        deactivate_subscription(target_id)

        response = (
            f"Безлимитный доступ пользователя {target_id} "
            f"деактивирован."
        )
        notification = (
            "Администратор деактивировал ваш безлимитный доступ. "
            "Пакетные прогнозы, если они есть, сохранены."
        )

    else:
        await state.clear()
        await message.answer("Неизвестное действие.")
        return

    await message.answer(
        response,
        reply_markup=admin_panel_kb(),
    )

    try:
        await message.bot.send_message(
            target_id,
            notification,
        )
    except Exception:
        logger.exception(
            "Cannot notify user %s about access change",
            target_id,
        )

    await state.clear()


@router.message(
    StateFilter(AdminStates.waiting_for_broadcast),
    F.text,
)
async def admin_broadcast(
    message: types.Message,
    state: FSMContext,
) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    sent = 0
    failed = 0

    for user_id in active_users():
        try:
            await message.bot.send_message(
                user_id,
                message.text,
            )
            sent += 1
        except Exception:
            failed += 1
            logger.exception(
                "Broadcast failed for user %s",
                user_id,
            )

    await message.answer(
        f"Рассылка завершена.\n"
        f"Успешно: {sent}\n"
        f"Ошибок: {failed}",
        reply_markup=admin_panel_kb(),
    )

    await state.clear()


@router.message(Command("sendfile"))
async def send_predictions_file(
    message: types.Message,
) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    prediction_file = get_settings().prediction_file

    if not prediction_file.is_file():
        await message.answer(
            "Файл прогнозов не найден. "
            "Проверьте внешний процесс формирования CSV."
        )
        return

    sent = 0
    failed = 0

    for user_id in active_users():
        try:
            await message.bot.send_document(
                user_id,
                FSInputFile(prediction_file),
            )
            sent += 1
        except Exception:
            failed += 1
            logger.exception(
                "Cannot send predictions to user %s",
                user_id,
            )

    await message.answer(
        f"Рассылка прогнозов завершена.\n"
        f"Успешно: {sent}\n"
        f"Ошибок: {failed}",
    )
