import asyncio
import signal

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

    await init_db(settings.poll_interval)
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

    tasks = asyncio.gather(
        # handle_signals=False: сигналы обрабатываем сами, иначе aiogram гасит
        # только поллинг, а мониторинг продолжает крутиться и systemd ждёт таймаут
        dp.start_polling(bot, skip_updates=True, handle_signals=False),
        monitoring_loop(bot),
    )

    # Без этого SIGTERM от systemd игнорируется и остановка занимает 90 секунд
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, tasks.cancel)
        except NotImplementedError:
            pass  # Windows: сигналы сюда не приходят, работает KeyboardInterrupt

    try:
        await tasks
    except asyncio.CancelledError:
        logger.info("Получен сигнал остановки — завершаемся")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем")
