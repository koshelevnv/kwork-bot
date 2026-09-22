import asyncio
import html
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import orjson
from loguru import logger

from src.constants import HEADERS, KWORK_API_URL, CATEGORY_NAME_BY_ID

_TIMEOUT = aiohttp.ClientTimeout(total=10)
_KWORK_TZ_OFFSET = timedelta(hours=3)  # kwork отдаёт даты по Москве (UTC+3)


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


async def fetch_orders(session: aiohttp.ClientSession, category_id: str) -> list[dict]:
    """Получить все заказы со страницы 1 для категории."""
    data = aiohttp.FormData()
    data.add_field("c", category_id)
    data.add_field("page", "1")

    try:
        async with session.post(
            KWORK_API_URL, data=data, headers=HEADERS, timeout=_TIMEOUT
        ) as resp:
            raw = await resp.read()
    except asyncio.TimeoutError:
        logger.warning(f"Таймаут для категории {category_id}")
        return []
    except aiohttp.ClientError as e:
        logger.warning(f"Сетевая ошибка для категории {category_id}: {e}")
        return []

    try:
        payload = orjson.loads(raw)
        orders: list[dict] = payload.get("data", {}).get("wants", [])
    except Exception as e:
        logger.error(f"Ошибка разбора JSON для категории {category_id}: {e}")
        return []

    return [
        {
            "order_id":      int(o["id"]),
            "title":         _clean(o.get("name")) or "Без названия",
            "description":   _clean(o.get("description"))[:2000].strip(),
            "budget":        _budget_str(o),
            "price_min":     _fmt_price(o.get("priceLimit")),
            "category_id":   category_id,
            "category_name": CATEGORY_NAME_BY_ID.get(category_id, f"Категория {category_id}"),
            "published_at":  _published_at(o),
        }
        for o in orders
        if o.get("id")
    ]
