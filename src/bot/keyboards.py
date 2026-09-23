from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from src.constants import (
    KWORK_ATTRIBUTES, KWORK_CATEGORIES, TIMEZONES,
    attr_id_of, attr_source,
)
from src.topics import TOPIC_PACKS, pack_title

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
        KeyboardButton(text="🎛 Фильтры"),
        KeyboardButton(text="📊 Статус"),
    )
    builder.row(
        KeyboardButton(text="⚙️ Настройки"),
        KeyboardButton(text="🏠 Главная / Обновить"),
    )
    return builder.as_markup(resize_keyboard=True)


def filters_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Мои категории",     callback_data="my_cats"))
    builder.row(InlineKeyboardButton(text="➕ Добавить категорию", callback_data="browse_cats"))
    builder.row(InlineKeyboardButton(text="🚫 Исключить категорию", callback_data="browse_excl"))
    builder.row(InlineKeyboardButton(text="💰 Фильтр по цене",    callback_data="edit_price"))
    builder.row(InlineKeyboardButton(text="🔍 Ключевые слова",    callback_data="kw_list"))
    return builder.as_markup()


# ── Inline: мои категории ───────────────────────────────────────────────────

def my_categories_kb(
    categories: list[dict], excluded: list[dict] | None = None
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        attr_id = attr_id_of(cat["category_id"])
        mark    = "🔹" if attr_id else "✅"
        number  = attr_id or cat["category_id"]
        builder.row(
            InlineKeyboardButton(
                text=f"{mark} {cat['category_name']} #{number}",
                callback_data="noop",
            ),
            InlineKeyboardButton(text="❌", callback_data=f"del_cat:{cat['category_id']}"),
        )
    for cat in excluded or []:
        builder.row(
            InlineKeyboardButton(
                text=f"🚫 {cat['category_name']} #{cat['category_id']}",
                callback_data="noop",
            ),
            InlineKeyboardButton(text="❌", callback_data=f"del_cat:{cat['category_id']}"),
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить категорию", callback_data="browse_cats"))
    builder.row(InlineKeyboardButton(text="🚫 Исключить категорию", callback_data="browse_excl"))
    return builder.as_markup()


# ── Inline: браузер групп категорий ────────────────────────────────────────
# mode="add" — выбираем, что отслеживать; mode="excl" — что выкинуть из ленты.

def _cat_callbacks(mode: str) -> tuple[str, str, str, str]:
    """(группа, добавить, убрать, ручной ввод) — префиксы callback_data."""
    if mode == "excl":
        return "xgroup", "add_excl", "rm_excl", "xcat_manual"
    return "catgroup", "add_cat", "rm_from_group", "cat_manual"


def category_groups_kb(mode: str = "add") -> InlineKeyboardMarkup:
    group_cb, _, _, manual_cb = _cat_callbacks(mode)
    builder = InlineKeyboardBuilder()
    for group in KWORK_CATEGORIES:
        builder.row(InlineKeyboardButton(text=group, callback_data=f"{group_cb}:{group}"))
    builder.row(InlineKeyboardButton(text="✏️ Ввести ID вручную", callback_data=manual_cb))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="my_cats"))
    return builder.as_markup()


def category_list_kb(
    group: str, user_cat_ids: set[str], mode: str = "add"
) -> InlineKeyboardMarkup:
    _, add_cb, rm_cb, _ = _cat_callbacks(mode)
    mark = "🚫" if mode == "excl" else "✅"
    back = "browse_excl" if mode == "excl" else "browse_cats"
    builder = InlineKeyboardBuilder()
    for cat_id, name in KWORK_CATEGORIES[group]:
        already = cat_id in user_cat_ids
        label = f"{mark} {name} #{cat_id}" if already else f"{name} #{cat_id}"
        cb    = f"{rm_cb}:{cat_id}" if already else f"{add_cb}:{cat_id}"
        row = [InlineKeyboardButton(text=label, callback_data=cb)]
        # Подрубрики — только для отслеживания: исключать по ним нечего, заказ
        # в ленте свою подрубрику не сообщает.
        attrs = KWORK_ATTRIBUTES.get(cat_id)
        if mode != "excl" and attrs:
            chosen = sum(
                1 for a_id, _ in attrs if attr_source(a_id) in user_cat_ids
            )
            row.append(InlineKeyboardButton(
                text=f"{chosen}/{len(attrs)} ›" if chosen else f"{len(attrs)} ›",
                callback_data=f"catattrs:{cat_id}",
            ))
        builder.row(*row)
    builder.row(InlineKeyboardButton(text="🔙 К группам", callback_data=back))
    return builder.as_markup()


def attributes_kb(cat_id: str, user_cat_ids: set[str]) -> InlineKeyboardMarkup:
    """Подрубрики одной категории. Категория целиком и её подрубрики —
    разные источники: первая даёт один запрос к ленте, каждая вторая — свой."""
    builder = InlineKeyboardBuilder()
    whole = cat_id in user_cat_ids
    builder.row(InlineKeyboardButton(
        text="✅ Вся категория" if whole else "Вся категория",
        callback_data=f"{'attr_all_off' if whole else 'attr_all_on'}:{cat_id}",
    ))
    for attr_id, name in KWORK_ATTRIBUTES.get(cat_id, []):
        source  = attr_source(attr_id)
        already = source in user_cat_ids
        builder.row(InlineKeyboardButton(
            text=f"🔹 {name}" if already else name,
            callback_data=f"{'rm_attr' if already else 'add_attr'}:{attr_id}",
        ))
    builder.row(InlineKeyboardButton(text="🔙 К категориям", callback_data=f"catback:{cat_id}"))
    return builder.as_markup()


# ── Inline: ключевые слова ─────────────────────────────────────────────────

def keywords_kb(
    keywords: list[str], minus_words: list[str], packs: list[str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for pack_id in packs:
        builder.row(
            InlineKeyboardButton(text=f"📦 {pack_title(pack_id)}", callback_data="kw_packs"),
            InlineKeyboardButton(text="❌", callback_data=f"off_pack:{pack_id}"),
        )
    for kw in keywords:
        builder.row(
            InlineKeyboardButton(text=f"🔑 {kw}", callback_data="noop"),
            InlineKeyboardButton(text="❌", callback_data=f"del_kw:{kw}"),
        )
    for kw in minus_words:
        builder.row(
            InlineKeyboardButton(text=f"🚫 {kw}", callback_data="noop"),
            InlineKeyboardButton(text="❌", callback_data=f"del_kw:{kw}"),
        )
    builder.row(InlineKeyboardButton(text="📦 Темы одной кнопкой", callback_data="kw_packs"))
    builder.row(
        InlineKeyboardButton(text="➕ Слово", callback_data="add_kw"),
        InlineKeyboardButton(text="🚫 Минус-слово", callback_data="add_minus"),
    )
    return builder.as_markup()


def packs_kb(selected: list[str]) -> InlineKeyboardMarkup:
    """Темы: одно нажатие включает весь набор синонимов, включая сленг."""
    builder = InlineKeyboardBuilder()
    for pack_id, (title, words, _seeds) in TOPIC_PACKS.items():
        mark = "✅ " if pack_id in selected else ""
        builder.row(InlineKeyboardButton(
            text=f"{mark}{title} · {len(words)} слов",
            callback_data=f"toggle_pack:{pack_id}",
        ))
    builder.row(InlineKeyboardButton(text="🔙 К словам", callback_data="kw_list"))
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
