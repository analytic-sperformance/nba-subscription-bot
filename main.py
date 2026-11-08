import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.admin import router as admin_router
from bot.config import get_settings
from bot.database import init_db
from bot.handlers import router as user_router


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    settings = get_settings()
    init_db()

    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())

    dispatcher.include_router(admin_router)
    dispatcher.include_router(user_router)

    try:
        logging.info("Starting Analytics Performance bot")
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
