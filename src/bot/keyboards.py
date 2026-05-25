from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from src.constants import KWORK_CATEGORIES, TIMEZONES

DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

INTERVALS = [
    (30,  "30 сек"),
    (60,  "1 мин"),
    (90,  "90 сек"),
    (120, "2 мин"),
    (180, "3 мин"),
    (300, "5 мин"),
    (600, "10 мин"),
]


# ── Reply-клавиатура (постоянная снизу) ────────────────────────────────────

def start_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🚀 Запустить бота"))
    return builder.as_markup(resize_keyboard=True)


def main_reply_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📋 Мои категории"),
        KeyboardButton(text="🎛 Фильтры"),
    )
    builder.row(
        KeyboardButton(text="📊 Статус"),
        KeyboardButton(text="⚙️ Настройки"),
    )
    builder.row(KeyboardButton(text="🔄 Перезапустить бота"))
    return builder.as_markup(resize_keyboard=True)


def filters_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить категорию", callback_data="browse_cats"))
    builder.row(InlineKeyboardButton(text="💰 Фильтр по цене",    callback_data="edit_price"))
    builder.row(InlineKeyboardButton(text="🔍 Ключевые слова",    callback_data="kw_list"))
    return builder.as_markup()


# ── Inline: мои категории ───────────────────────────────────────────────────

def my_categories_kb(categories: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(
            InlineKeyboardButton(
                text=f"✅ {cat['category_name']} #{cat['category_id']}",
                callback_data="noop",
            ),
            InlineKeyboardButton(text="❌", callback_data=f"del_cat:{cat['category_id']}"),
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить категорию", callback_data="browse_cats"))
    return builder.as_markup()


# ── Inline: браузер групп категорий ────────────────────────────────────────

def category_groups_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in KWORK_CATEGORIES:
        builder.row(InlineKeyboardButton(text=group, callback_data=f"catgroup:{group}"))
    builder.row(InlineKeyboardButton(text="✏️ Ввести ID вручную", callback_data="cat_manual"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="my_cats"))
    return builder.as_markup()


def category_list_kb(group: str, user_cat_ids: set[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat_id, name in KWORK_CATEGORIES[group]:
        already = cat_id in user_cat_ids
        label = f"✅ {name} #{cat_id}" if already else f"{name} #{cat_id}"
        cb    = f"rm_from_group:{cat_id}" if already else f"add_cat:{cat_id}"
        builder.row(InlineKeyboardButton(text=label, callback_data=cb))
    builder.row(InlineKeyboardButton(text="🔙 К группам", callback_data="browse_cats"))
    return builder.as_markup()


# ── Inline: ключевые слова ─────────────────────────────────────────────────

def keywords_kb(keywords: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for kw in keywords:
        builder.row(
            InlineKeyboardButton(text=f"🔑 {kw}", callback_data="noop"),
            InlineKeyboardButton(text="❌", callback_data=f"del_kw:{kw}"),
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить слово", callback_data="add_kw"))
    return builder.as_markup()


# ── Inline: выбор интервала ────────────────────────────────────────────────

def interval_kb(current: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for secs, label in INTERVALS:
        text = f"✅ {label}" if secs == current else label
        builder.button(text=text, callback_data=f"set_interval:{secs}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings"))
    return builder.as_markup()


# ── Inline: настройки ──────────────────────────────────────────────────────

def global_interval_kb(current: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for secs, label in INTERVALS:
        text = f"✅ {label}" if secs == current else label
        builder.button(text=text, callback_data=f"set_global_interval:{secs}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings"))
    return builder.as_markup()


def days_kb(notify_days: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, name in enumerate(DAYS):
        enabled = bool((notify_days >> i) & 1)
        builder.button(
            text=f"✅ {name}" if enabled else name,
            callback_data=f"toggle_day:{i}",
        )
    builder.adjust(7)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings"))
    return builder.as_markup()


def settings_kb(user: dict, is_admin: bool = False, global_settings: dict | None = None, user_count: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    interval    = user.get("poll_interval", 30)
    notify_from = user.get("notify_from", 0)
    notify_to   = user.get("notify_to", 23)
    utc_offset  = user.get("utc_offset", 3)
    price_from  = user.get("price_from", 0)
    price_to    = user.get("price_to", 0)
    sign        = "+" if utc_offset >= 0 else ""

    if price_from == 0 and price_to == 0:
        price_label = "без ограничений"
    elif price_from > 0 and price_to == 0:
        price_label = f"от {price_from:,} ₽".replace(",", " ")
    elif price_from == 0 and price_to > 0:
        price_label = f"до {price_to:,} ₽".replace(",", " ")
    else:
        price_label = f"{price_from:,} – {price_to:,} ₽".replace(",", " ")

    builder.row(InlineKeyboardButton(
        text=f"⏱ Частота уведомлений: {interval} сек",
        callback_data="edit_interval",
    ))
    builder.row(InlineKeyboardButton(
        text=f"🕐 Период уведомлений: {notify_from:02d}:00 – {'23:59' if notify_to == 23 else f'{notify_to:02d}:00'}",
        callback_data="edit_window",
    ))
    notify_days = user.get("notify_days", 31)
    active_days = " ".join(d for i, d in enumerate(DAYS) if (notify_days >> i) & 1) or "нет"
    builder.row(InlineKeyboardButton(
        text=f"📅 Дни: {active_days}",
        callback_data="edit_days",
    ))
    builder.row(InlineKeyboardButton(
        text=f"🌍 Часовой пояс: UTC{sign}{utc_offset}",
        callback_data="edit_tz",
    ))
    builder.row(InlineKeyboardButton(
        text=f"💰 Цена: {price_label}",
        callback_data="edit_price",
    ))

    if is_admin and global_settings is not None:
        gs_interval = global_settings.get("fetch_interval", 30)
        reg_open    = global_settings.get("registration_open", 0)
        reg_label   = "🔓 открыта" if reg_open else "🔒 закрыта"
        builder.row(InlineKeyboardButton(text="─────── Админ ───────", callback_data="noop"))
        if user_count is not None:
            builder.row(InlineKeyboardButton(
                text=f"👥 Пользователей: {user_count}",
                callback_data="noop",
            ))
        builder.row(InlineKeyboardButton(
            text=f"🌐 Парсер: {gs_interval} сек",
            callback_data="edit_global_interval",
        ))
        builder.row(InlineKeyboardButton(
            text=f"👥 Регистрация: {reg_label}",
            callback_data="toggle_registration",
        ))
        builder.row(InlineKeyboardButton(
            text="🔄 Обновить категории",
            callback_data="refresh_categories",
        ))

    return builder.as_markup()


def hour_grid_kb(prefix: str, is_end: bool = False) -> InlineKeyboardMarkup:
    """Сетка выбора часа 00–23."""
    builder = InlineKeyboardBuilder()
    minutes = "59" if is_end else "00"
    for h in range(24):
        builder.button(text=f"{h:02d}:{minutes}", callback_data=f"{prefix}:{h}")
    builder.adjust(6)  # 6 колонок × 4 строки
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_window"))
    return builder.as_markup()


def timezone_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, offset in TIMEZONES:
        builder.row(InlineKeyboardButton(
            text=label,
            callback_data=f"set_tz:{offset}",
        ))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_tz"))
    return builder.as_markup()


# ── Reply: отмена (для FSM-состояний) ─────────────────────────────────────

def cancel_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True)


def skip_cancel_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="⏭ Пропустить"), KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True)


# ── Inline: назад ──────────────────────────────────────────────────────────

def back_kb(callback: str = "my_cats") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data=callback)
    return builder.as_markup()
