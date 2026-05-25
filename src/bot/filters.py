from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from src.config import Settings


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        user = event.from_user
        return bool(user and user.id in settings.admin_ids)
