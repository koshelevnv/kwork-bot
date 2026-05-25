import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from src.bot.handlers import router
from src.config import Settings
from src.constants import update_categories
from src.database import init_db, load_categories, reset_all_last_notified
from src.monitor import monitoring_loop


async def main() -> None:
    settings = Settings()

    if not settings.tg_token:
        logger.error("Не задан TELEGRAM_BOT_TOKEN в .env")
        return
    if not settings.admin_ids:
        logger.warning("ADMIN_IDS не задан — любой может пользоваться ботом")

    logger.add("logs/parser.log", rotation="1 week", retention="1 month", compression="zip")

    await init_db()
    await reset_all_last_notified()
    logger.info("База данных готова")

    cats_from_db = await load_categories()
    if cats_from_db:
        update_categories(cats_from_db)
        logger.info(f"Категории загружены из БД: {len(cats_from_db)} разделов")
    else:
        logger.info("Категории загружены из constants.py (БД пуста)")

    bot = Bot(token=settings.tg_token)
    dp  = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings
    dp.include_router(router)

    await asyncio.gather(
        dp.start_polling(bot, skip_updates=True),
        monitoring_loop(bot),
    )


if __name__ == "__main__":
    asyncio.run(main())
