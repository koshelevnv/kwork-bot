import html

from aiogram import Bot
from aiogram.enums import ParseMode
from loguru import logger

from src.constants import ORDER_MESSAGE

_ESCAPED_FIELDS = ("title", "description", "budget", "category_name")


async def send_order(bot: Bot, chat_id: int, order: dict) -> None:
    # Текст заказа подставляется в HTML-шаблон: символы < > & нужно экранировать,
    # иначе Telegram отвечает "can't parse entities" и заказ теряется.
    safe = dict(order)
    for field in _ESCAPED_FIELDS:
        safe[field] = html.escape(str(safe.get(field, "")))

    text = ORDER_MESSAGE.format(**safe)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"Ошибка отправки в {chat_id}: {e}")
