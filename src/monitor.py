import asyncio
from datetime import datetime, timedelta

import aiohttp
from aiogram import Bot
from loguru import logger

from src.database import (
    cleanup_order_history, get_all_monitored_categories,
    get_due_users, get_orders_since, get_user_categories,
    get_user_keywords, store_order, update_last_notified,
    get_global_settings,
)
from src.notifier import send_order
from src.parser import fetch_orders

_CLEANUP_EVERY = 120  # итераций до очистки истории (~1 час)


def _in_window(hour: int, frm: int, to: int) -> bool:
    """Проверить, входит ли час в окно уведомлений (поддерживает переход через полночь)."""
    if frm <= to:
        return frm <= hour <= to
    return hour >= frm or hour <= to  # окно переходит через полночь


async def _deliver(bot: Bot, user: dict) -> None:
    uid = user["user_id"]
    try:
        cats = await get_user_categories(uid)
        cat_ids = [c["category_id"] for c in cats]

        if not cat_ids:
            await update_last_notified(uid)
            return

        utc_offset  = user.get("utc_offset", 3)
        notify_from = user.get("notify_from", 0)
        notify_to   = user.get("notify_to", 23)
        notify_days = user.get("notify_days", 31)
        price_from  = user.get("price_from", 0)
        price_to    = user.get("price_to", 0)

        # Проверяем день недели в часовом поясе пользователя (0=Пн, 6=Вс)
        local_now = datetime.utcnow() + timedelta(hours=utc_offset)
        if not (notify_days >> local_now.weekday()) & 1:
            return

        since    = user["last_notified_at"]
        orders   = await get_orders_since(cat_ids, since)
        keywords = await get_user_keywords(uid)

        sent = 0
        for order in orders:
            # Фильтр по времени публикации в часовом поясе пользователя
            try:
                pub_utc   = datetime.fromisoformat(order["published_at"])
                local_hour = (pub_utc.hour + utc_offset) % 24
            except Exception:
                local_hour = datetime.utcnow().hour

            if not _in_window(local_hour, notify_from, notify_to):
                continue

            # Фильтр по цене (заказы без цены пропускаем)
            order_price = order.get("price_min", 0)
            if order_price > 0:
                if price_from > 0 and order_price < price_from:
                    continue
                if price_to > 0 and order_price > price_to:
                    continue

            # Фильтр по ключевым словам
            if keywords:
                text = (order["title"] + " " + order["description"]).lower()
                if not any(kw in text for kw in keywords):
                    continue

            await send_order(bot=bot, chat_id=uid, order=order)
            sent += 1

        if sent:
            logger.info(f"Пользователь {uid}: отправлено {sent} заказов")

    except Exception:
        logger.exception(f"Ошибка доставки для пользователя {uid}")
    finally:
        await update_last_notified(uid)


async def monitoring_loop(bot: Bot) -> None:
    logger.info("Мониторинг запущен")
    cleanup_counter = 0

    async with aiohttp.ClientSession() as session:
        while True:
            # 1. Фетч всех категорий → запись в order_history
            categories = await get_all_monitored_categories()
            if categories:
                results = await asyncio.gather(
                    *[fetch_orders(session, cat) for cat in categories],
                    return_exceptions=True,
                )
                for cat_id, result in zip(categories, results):
                    if isinstance(result, Exception):
                        logger.exception(f"Ошибка фетча категории {cat_id}: {result}")
                        continue
                    for order in result:
                        await store_order(order)

            # 2. Доставка пользователям с истёкшим интервалом
            due_users = await get_due_users()
            if due_users:
                await asyncio.gather(*[_deliver(bot, user) for user in due_users])

            # 3. Периодическая очистка истории
            cleanup_counter += 1
            if cleanup_counter >= _CLEANUP_EVERY:
                await cleanup_order_history()
                cleanup_counter = 0

            gs = await get_global_settings()
            fetch_interval = gs.get("fetch_interval", 30)
            logger.debug(f"Следующий фетч через {fetch_interval} сек")
            await asyncio.sleep(fetch_interval)
