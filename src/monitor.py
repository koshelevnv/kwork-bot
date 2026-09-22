import asyncio
from datetime import datetime, timedelta

import aiohttp
from aiogram import Bot
from loguru import logger

from src.database import (
    cleanup_order_history, get_all_monitored_categories,
    get_all_monitored_keywords, get_all_monitored_packs,
    get_due_users, get_orders_since, get_user_categories,
    get_user_keywords, get_user_minus_words, get_user_packs,
    store_order, update_last_notified, get_global_settings,
)
from src.constants import ALL_CATEGORIES
from src.matching import order_matches
from src.notifier import send_order
from src.parser import fetch_orders, fetch_orders_by_keyword
from src.topics import pack_keywords, pack_search_terms

_CLEANUP_EVERY = 120  # итераций до очистки истории (~1 час)
# Поиск на kwork — дополнительный источник к ленте: он находит заказы старше
# двух страниц и сам сшивает «телеграм» с «Telegram». Гонять его каждые 30
# секунд незачем, поэтому раз в несколько циклов и с потолком по числу слов.
_SEARCH_EVERY = 4
_SEARCH_TERMS_LIMIT = 20
_SEARCH_PAUSE = 0.3  # секунд между запросами к поиску


def _in_window(hour: int, frm: int, to: int) -> bool:
    """Проверить, входит ли час в окно уведомлений (поддерживает переход через полночь)."""
    if frm <= to:
        return frm <= hour <= to
    return hour >= frm or hour <= to  # окно переходит через полночь


async def _deliver(bot: Bot, user: dict) -> None:
    uid = user["user_id"]
    try:
        cats = await get_user_categories(uid)
        # Пустой список категорий = без фильтра, заказы из всех разделов
        cat_ids = [c["category_id"] for c in cats] or [ALL_CATEGORIES]

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
        keywords = await get_user_keywords(uid) + pack_keywords(await get_user_packs(uid))
        minus    = await get_user_minus_words(uid)

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

            # Фильтр по ключевым словам: пустой список = проходят все заказы
            if not order_matches(
                order["title"] + " " + order["description"], keywords, minus
            ):
                continue

            await send_order(bot=bot, chat_id=uid, order=order)
            sent += 1

        if sent:
            logger.info(f"Пользователь {uid}: отправлено {sent} заказов")

    except Exception:
        logger.exception(f"Ошибка доставки для пользователя {uid}")
    finally:
        await update_last_notified(uid)


async def _search_terms() -> list[str]:
    """Слова для поиска на kwork: свои слова пользователей плюс семена тем."""
    terms = await get_all_monitored_keywords()
    for term in pack_search_terms(await get_all_monitored_packs()):
        if term not in terms:
            terms.append(term)
    return terms[:_SEARCH_TERMS_LIMIT]


async def _fetch_from_search(session: aiohttp.ClientSession) -> tuple[int, int]:
    """Запросы к поиску kwork. Заказ кладётся и в свой раздел, и в общую ленту,
    чтобы его увидели и те, кто выбрал категории, и те, кто читает всё подряд."""
    terms = await _search_terms()
    fetched = fresh = 0
    for term in terms:
        try:
            orders = await fetch_orders_by_keyword(session, term)
        except Exception as e:
            logger.warning(f"Ошибка поиска «{term}»: {e!r}")
            continue
        for order in orders:
            fetched += 1
            if await store_order(order):
                fresh += 1
            if order["category_id"] != ALL_CATEGORIES:
                await store_order({**order, "category_id": ALL_CATEGORIES})
        await asyncio.sleep(_SEARCH_PAUSE)
    if terms:
        logger.debug(f"Поиск kwork: слов {len(terms)}, заказов {fetched}, новых {fresh}")
    return fetched, fresh


async def monitoring_loop(bot: Bot) -> None:
    logger.info("Мониторинг запущен")
    cleanup_counter = 0
    search_counter = 0
    idle_warned = False

    async with aiohttp.ClientSession() as session:
        while True:
            # 1. Фетч всех категорий → запись в order_history
            categories = await get_all_monitored_categories()
            if categories:
                idle_warned = False
                results = await asyncio.gather(
                    *[fetch_orders(session, cat) for cat in categories],
                    return_exceptions=True,
                )
                fetched = fresh = 0
                for cat_id, result in zip(categories, results):
                    if isinstance(result, Exception):
                        logger.error(f"Ошибка фетча категории {cat_id}: {result!r}")
                        continue
                    for order in result:
                        fetched += 1
                        if await store_order(order):
                            fresh += 1
                logger.debug(
                    f"Фетч: категорий {len(categories)}, заказов {fetched}, новых {fresh}"
                )
            elif not idle_warned:
                # Список пуст только когда нет ни одного активного пользователя:
                # пользователь без выбранных категорий даёт псевдо-категорию «все».
                logger.warning("Нет активных пользователей — мониторинг простаивает")
                idle_warned = True

            # 2. Поиск по словам на самом kwork — добор к ленте
            search_counter += 1
            if search_counter >= _SEARCH_EVERY:
                search_counter = 0
                await _fetch_from_search(session)

            # 3. Доставка пользователям с истёкшим интервалом
            due_users = await get_due_users()
            if due_users:
                await asyncio.gather(*[_deliver(bot, user) for user in due_users])

            # 4. Периодическая очистка истории
            cleanup_counter += 1
            if cleanup_counter >= _CLEANUP_EVERY:
                await cleanup_order_history()
                cleanup_counter = 0

            gs = await get_global_settings()
            fetch_interval = gs.get("fetch_interval", 30)
            logger.debug(f"Следующий фетч через {fetch_interval} сек")
            await asyncio.sleep(fetch_interval)
