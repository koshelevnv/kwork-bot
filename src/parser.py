import asyncio
import html
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import orjson
from loguru import logger

from src.constants import (
    ALL_CATEGORIES, CATEGORY_NAME_BY_ID, HEADERS, KWORK_API_URL,
    attr_full_name, attr_id_of,
)

_TIMEOUT = aiohttp.ClientTimeout(total=10)
_KWORK_TZ_OFFSET = timedelta(hours=3)  # kwork отдаёт даты по Москве (UTC+3)
# Страница общей ленты покрывает всего ~7 минут заказов, поэтому берём две:
# с запасом хватает даже на максимальный интервал опроса (10 минут).
_ALL_FEED_PAGES = 2


def _clean(text: Any) -> str:
    """kwork отдаёт текст с HTML-сущностями (&mdash;, &laquo;, &quot;) — раскодируем их."""
    return html.unescape(str(text or "")).replace("\xa0", " ")


def _published_at(order: dict) -> str:
    """Время появления заказа в ленте (UTC, формат SQLite datetime).

    Берём date_active — момент публикации/поднятия заказа; date_create у поднятых
    заказов может быть многомесячной давности. Без этого поля временем публикации
    считался момент первого фетча, и после каждого рестарта бот слал всю ленту заново.
    """
    raw = order.get("date_active") or order.get("date_create") or ""
    try:
        moscow = datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return (moscow - _KWORK_TZ_OFFSET).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_price(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _budget_str(order: dict) -> str:
    price_min = _fmt_price(order.get("priceLimit"))
    price_max = _fmt_price(order.get("possiblePriceLimit"))
    is_range  = order.get("isHigherPrice", False)

    if price_min == 0:
        return "не указан"
    if is_range and price_max > price_min:
        return f"{price_min:,} – {price_max:,} ₽".replace(",", " ")
    return f"{price_min:,} ₽".replace(",", " ")


async def _fetch_page(
    session: aiohttp.ClientSession, fields: dict[str, str], label: str
) -> list[dict]:
    """Одна страница выдачи. Без поля c kwork отдаёт общую ленту всех разделов."""
    data = aiohttp.FormData()
    for name, value in fields.items():
        data.add_field(name, value)

    try:
        async with session.post(
            KWORK_API_URL, data=data, headers=HEADERS, timeout=_TIMEOUT
        ) as resp:
            raw = await resp.read()
    except asyncio.TimeoutError:
        logger.warning(f"Таймаут для {label}")
        return []
    except aiohttp.ClientError as e:
        logger.warning(f"Сетевая ошибка для {label}: {e}")
        return []

    try:
        payload = orjson.loads(raw)
        return payload.get("data", {}).get("wants", [])
    except Exception as e:
        logger.error(f"Ошибка разбора JSON для {label}: {e}")
        return []


def _category_name(own_id: str, category_id: str) -> str:
    # В общей ленте раздел у каждого заказа свой — берём его из самого заказа.
    if category_id == ALL_CATEGORIES:
        return CATEGORY_NAME_BY_ID.get(own_id, "Все категории")
    attr_id = attr_id_of(category_id)
    if attr_id:
        # Заказ пришёл из запроса по подрубрике — только так она и известна.
        return attr_full_name(attr_id)
    return CATEGORY_NAME_BY_ID.get(category_id, f"Категория {category_id}")


def _build_order(raw: dict, category_id: str) -> dict:
    # own_category_id — настоящий раздел заказа. В общей ленте он единственный
    # способ понять, откуда заказ: сама запись лежит под псевдо-категорией «all»,
    # а по этому полю работают минус-категории пользователя.
    own_id = str(raw.get("category_id") or "")
    return {
        "order_id":      int(raw["id"]),
        "title":         _clean(raw.get("name")) or "Без названия",
        "description":   _clean(raw.get("description"))[:2000].strip(),
        "budget":        _budget_str(raw),
        "price_min":     _fmt_price(raw.get("priceLimit")),
        "category_id":   category_id,
        "own_category_id": own_id,
        "category_name": _category_name(own_id, category_id),
        "published_at":  _published_at(raw),
    }


async def fetch_orders(session: aiohttp.ClientSession, category_id: str) -> list[dict]:
    """Свежие заказы источника: категории, подрубрики (id с префиксом «a») или
    всей ленты, если category_id == ALL_CATEGORIES."""
    pages = _ALL_FEED_PAGES if category_id == ALL_CATEGORIES else 1
    attr_id = attr_id_of(category_id)
    label = f"подрубрики {attr_id}" if attr_id else f"категории {category_id}"

    raw_orders: list[dict] = []
    for page in range(1, pages + 1):
        fields = {"page": str(page)}
        if attr_id:
            # attr самодостаточен: вместе с ним поле c не нужно, а несколько
            # значений за раз kwork не принимает — побеждает последнее.
            fields["attr"] = attr_id
        elif category_id != ALL_CATEGORIES:
            fields["c"] = category_id
        raw_orders.extend(await _fetch_page(session, fields, label))

    return [_build_order(o, category_id) for o in raw_orders if o.get("id")]


async def fetch_orders_by_keyword(
    session: aiohttp.ClientSession, keyword: str
) -> list[dict]:
    """Заказы из поиска самого kwork (поле формы keyword).

    Поиск биржи сам сшивает «телеграм» с «Telegram» и учитывает морфологию, а
    заодно достаёт заказы старше двух страниц общей ленты. Раздел у каждого
    найденного заказа свой, поэтому category_id берётся из самого заказа.
    """
    raw_orders = await _fetch_page(
        session, {"keyword": keyword, "page": "1"}, f"поиска «{keyword}»"
    )
    orders = []
    for raw in raw_orders:
        if not raw.get("id"):
            continue
        own = str(raw.get("category_id") or "") or ALL_CATEGORIES
        orders.append(_build_order(raw, own))
    return orders
