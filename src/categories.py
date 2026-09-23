import re

import aiohttp
import orjson
from loguru import logger

from src.constants import PARENT_CATEGORY_NAMES, update_attributes, update_categories
from src.database import save_attributes, save_categories

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


async def fetch_and_update_categories() -> tuple[bool, str]:
    """
    Загружает актуальные категории с kwork.ru, обновляет их в памяти и БД.
    Возвращает (success, message).
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://kwork.ru/projects", headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                html = await resp.text()
    except Exception as e:
        logger.warning(f"Ошибка загрузки страницы kwork.ru: {e}")
        return False, f"Ошибка загрузки страницы: {e}"

    m = re.search(r"window\.stateData=(\{.+?\});window\.", html)
    if not m:
        return False, "Не удалось найти stateData на странице kwork.ru"

    try:
        data = orjson.loads(m.group(1))
    except Exception as e:
        return False, f"Ошибка разбора JSON: {e}"

    cats_raw = data.get("categoriesWithFavoritesList", {})
    if not cats_raw:
        return False, "Категории не найдены в stateData"

    new_cats: dict[str, list[tuple[str, str]]] = {}
    new_attrs: dict[str, list[tuple[str, str]]] = {}
    for parent_id, parent_data in cats_raw.items():
        if not isinstance(parent_data, dict):
            continue
        # Имя с эмодзи — наше, но новый раздел биржи не должен пропасть молча,
        # поэтому для незнакомого родителя берём название с сайта как есть.
        parent_display = (
            PARENT_CATEGORY_NAMES.get(str(parent_id)) or parent_data.get("name")
        )
        if not parent_display:
            continue
        children = parent_data.get("cats", [])
        parsed = []
        for c in children:
            if not (isinstance(c, dict) and c.get("id") and c.get("name")):
                continue
            cat_id = str(c["id"])
            parsed.append((cat_id, c["name"]))
            attrs = _parse_attributes(c)
            if attrs:
                new_attrs[cat_id] = attrs
        if parsed:
            new_cats[parent_display] = sorted(parsed, key=lambda x: x[0])

    if not new_cats:
        return False, "Не удалось извлечь ни одной категории"

    update_categories(new_cats)
    await save_categories(new_cats)
    update_attributes(new_attrs)
    await save_attributes(new_attrs)

    total = sum(len(v) for v in new_cats.values())
    total_attrs = sum(len(v) for v in new_attrs.values())
    logger.info(
        f"Категории обновлены: {len(new_cats)} разделов, {total} категорий, "
        f"{total_attrs} подрубрик"
    )
    return (
        True,
        f"✅ Обновлено {len(new_cats)} разделов, {total} категорий, "
        f"{total_attrs} подрубрик",
    )


def _parse_attributes(cat: dict) -> list[tuple[str, str]]:
    """Подрубрики категории. visible=1 — то, что kwork показывает в фильтрах;
    остальные (visible=2) на сайте скрыты, в боте их тоже нет."""
    raw = cat.get("attributes")
    if not isinstance(raw, dict):
        return []
    attrs = [
        a for a in raw.values()
        if isinstance(a, dict) and a.get("id") and a.get("title")
        and str(a.get("visible")) == "1"
    ]
    return [(str(a["id"]), a["title"]) for a in attrs]
