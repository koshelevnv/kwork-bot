from aiogram import Bot
from aiogram.enums import ParseMode
from loguru import logger

from src.constants import ORDER_MESSAGE


async def send_order(bot: Bot, chat_id: int, order: dict) -> None:
    text = ORDER_MESSAGE.format(**order)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"Ошибка отправки в {chat_id}: {e}")
