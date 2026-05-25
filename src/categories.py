import re

import aiohttp
import orjson
from loguru import logger

from src.constants import PARENT_CATEGORY_NAMES, update_categories
from src.database import save_categories

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
    for parent_id, parent_data in cats_raw.items():
        parent_display = PARENT_CATEGORY_NAMES.get(str(parent_id))
        if not parent_display:
            continue
        children = parent_data.get("cats", []) if isinstance(parent_data, dict) else []
        parsed = [
            (str(c["id"]), c["name"])
            for c in children
            if isinstance(c, dict) and c.get("id") and c.get("name")
        ]
        if parsed:
            new_cats[parent_display] = sorted(parsed, key=lambda x: x[0])

    if not new_cats:
        return False, "Не удалось извлечь ни одной категории"

    update_categories(new_cats)
    await save_categories(new_cats)

    total = sum(len(v) for v in new_cats.values())
    logger.info(f"Категории обновлены: {len(new_cats)} разделов, {total} категорий")
    return True, f"✅ Обновлено {len(new_cats)} разделов, {total} категорий"
