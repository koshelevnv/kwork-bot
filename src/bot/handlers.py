from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup

from src.bot.keyboards import (
    main_reply_kb, start_kb, my_categories_kb, category_groups_kb,
    category_list_kb, keywords_kb, settings_kb,
    hour_grid_kb, timezone_kb, back_kb, cancel_kb, skip_cancel_kb,
    interval_kb, INTERVALS, filters_kb, global_interval_kb, days_kb, DAYS,
)
from src.config import Settings
from src.constants import KWORK_CATEGORIES, TIMEZONES, CATEGORY_NAME_BY_ID
from src.database import (
    upsert_user, get_user, get_user_categories, add_user_category,
    remove_user_category, get_user_keywords, add_user_keyword,
    remove_user_keyword, update_poll_interval, update_time_window,
    update_utc_offset, update_price_filter, update_notify_days,
    get_global_settings, update_global_fetch_interval, update_registration_open,
    get_user_count, get_admin_users,
)

router = Router()


class Form(StatesGroup):
    add_keyword    = State()
    manual_cat     = State()
    set_hour_to    = State()  # от-час выбран, ждём до-час
    set_price_from = State()
    set_price_to   = State()


# ── /cancel ────────────────────────────────────────────────────────────────

@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_reply_kb())


# ── Вспомогалки ────────────────────────────────────────────────────────────

async def _reg(event: Message | CallbackQuery, settings: Settings) -> tuple[bool, bool]:
    user = event.from_user
    return await upsert_user(user.id, user.username, user.first_name or "", settings.admin_ids)


async def _settings_kb_for(user_id: int) -> tuple[dict, InlineKeyboardMarkup]:
    """Возвращает (user_dict, settings_keyboard) с учётом прав администратора."""
    user = await get_user(user_id)
    is_admin = bool((user or {}).get("is_admin", 0))
    gs = await get_global_settings() if is_admin else None
    count = await get_user_count() if is_admin else None
    kb = settings_kb(user or {}, is_admin=is_admin, global_settings=gs, user_count=count)
    return user or {}, kb


# ── /start ─────────────────────────────────────────────────────────────────

@router.message(CommandStart())
@router.message(F.text == "🚀 Запустить бота")
@router.message(F.text == "🔄 Перезапустить бота")
async def cmd_start(message: Message, settings: Settings) -> None:
    registered, is_new = await _reg(message, settings)
    if not registered:
        await message.answer(
            "🔒 Регистрация закрыта.\nОбратитесь к администратору бота.",
            reply_markup=start_kb(),
        )
        return

    if is_new:
        admins = await get_admin_users()
        count = await get_user_count()
        u = message.from_user
        username = f"@{u.username}" if u.username else "—"
        text = (
            f"👤 <b>Новый пользователь</b>\n\n"
            f"Имя: {u.first_name}\n"
            f"Username: {username}\n"
            f"ID: <code>{u.id}</code>\n\n"
            f"Всего пользователей: <b>{count}</b>"
        )
        for admin in admins:
            if admin["user_id"] != u.id:
                try:
                    await message.bot.send_message(admin["user_id"], text, parse_mode="HTML")
                except Exception:
                    pass

    cats = await get_user_categories(message.from_user.id)
    kws  = await get_user_keywords(message.from_user.id)
    await message.answer(
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        "Я слежу за новыми заказами на kwork.ru и присылаю их сюда.\n\n"
        f"📋 Категорий: <b>{len(cats)}</b>\n"
        f"🔍 Ключевых слов: <b>{len(kws)}</b>\n\n"
        "Используй кнопки ниже 👇",
        parse_mode="HTML",
        reply_markup=main_reply_kb(),
    )


# ── Статус ─────────────────────────────────────────────────────────────────

@router.message(F.text == "📊 Статус")
async def btn_status(message: Message, settings: Settings) -> None:
    await _reg(message, settings)
    uid  = message.from_user.id
    user = await get_user(uid)
    cats = await get_user_categories(uid)
    kws  = await get_user_keywords(uid)

    cat_lines = "\n".join(f"  • {c['category_name']}" for c in cats) or "  нет"
    kw_lines  = ", ".join(kws) or "нет (все заказы)"

    interval    = user.get("poll_interval", 30) if user else 30
    notify_from = user.get("notify_from", 0) if user else 0
    notify_to   = user.get("notify_to", 23) if user else 23
    utc_offset  = user.get("utc_offset", 3) if user else 3
    notify_days = user.get("notify_days", 31) if user else 31
    price_from  = user.get("price_from", 0) if user else 0
    price_to    = user.get("price_to", 0) if user else 0
    sign        = "+" if utc_offset >= 0 else ""

    days_label = " ".join(d for i, d in enumerate(DAYS) if (notify_days >> i) & 1) or "нет"

    if price_from == 0 and price_to == 0:
        price_label = "без ограничений"
    elif price_from > 0 and price_to == 0:
        price_label = f"от {price_from:,} ₽".replace(",", " ")
    elif price_from == 0 and price_to > 0:
        price_label = f"до {price_to:,} ₽".replace(",", " ")
    else:
        price_label = f"{price_from:,} – {price_to:,} ₽".replace(",", " ")

    await message.answer(
        f"📊 <b>Ваши настройки</b>\n\n"
        f"⏱ Частота уведомлений: {interval} сек\n"
        f"🕐 Период уведомлений: {notify_from:02d}:00 – {'23:59' if notify_to == 23 else f'{notify_to:02d}:00'}\n"
        f"📅 Дни недели: {days_label}\n"
        f"🌍 Часовой пояс: UTC{sign}{utc_offset}\n"
        f"💰 Цена: {price_label}\n\n"
        f"<b>Категории ({len(cats)}):</b>\n{cat_lines}\n\n"
        f"<b>Ключевые слова:</b> {kw_lines}",
        parse_mode="HTML",
    )


# ── Мои категории ──────────────────────────────────────────────────────────

@router.message(F.text == "📋 Мои категории")
async def btn_my_cats(message: Message, settings: Settings) -> None:
    await _reg(message, settings)
    await _show_my_cats(message, message.from_user.id)


@router.callback_query(F.data == "my_cats")
async def cb_my_cats(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    await call.answer()
    await _show_my_cats(call.message, call.from_user.id, edit=True)


async def _show_my_cats(msg: Message, user_id: int, edit: bool = False) -> None:
    cats = await get_user_categories(user_id)
    text = (
        f"📋 <b>Ваши категории</b> ({len(cats)})\n\nНажми ❌ чтобы удалить 👇"
        if cats else
        "📋 У вас нет отслеживаемых категорий.\n\nНажми <b>Добавить категорию</b> 👇"
    )
    kb = my_categories_kb(cats)
    if edit:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("del_cat:"))
async def cb_del_cat(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    cat_id = call.data.split(":")[1]
    removed = await remove_user_category(call.from_user.id, cat_id)
    await call.answer("❌ Категория удалена" if removed else "Не найдена")
    await _show_my_cats(call.message, call.from_user.id, edit=True)


# ── Добавить категорию ─────────────────────────────────────────────────────

@router.message(F.text == "➕ Добавить категорию")
async def btn_add_cat(message: Message, settings: Settings) -> None:
    await _reg(message, settings)
    await message.answer("Выбери группу категорий 👇", reply_markup=category_groups_kb())


@router.callback_query(F.data == "browse_cats")
async def cb_browse_cats(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    await call.answer()
    await call.message.edit_text("Выбери группу категорий 👇", reply_markup=category_groups_kb())


@router.callback_query(F.data.startswith("catgroup:"))
async def cb_catgroup(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    group = call.data[len("catgroup:"):]
    if group not in KWORK_CATEGORIES:
        await call.answer("Группа не найдена")
        return
    user_cats    = await get_user_categories(call.from_user.id)
    user_cat_ids = {c["category_id"] for c in user_cats}
    await call.answer()
    await call.message.edit_text(
        f"<b>{group}</b>\nВыбери категории — повторный клик удаляет ✅",
        parse_mode="HTML",
        reply_markup=category_list_kb(group, user_cat_ids),
    )


@router.callback_query(F.data.startswith("add_cat:"))
async def cb_add_cat(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    _, cat_id = call.data.split(":")
    cat_name = CATEGORY_NAME_BY_ID.get(cat_id, cat_id)
    added = await add_user_category(call.from_user.id, cat_id, cat_name)
    await call.answer(f"✅ Добавлена: {cat_name}" if added else "Уже отслеживается")
    group = next(
        (g for g, cats in KWORK_CATEGORIES.items() if any(c[0] == cat_id for c in cats)), None
    )
    if group:
        user_cat_ids = {c["category_id"] for c in await get_user_categories(call.from_user.id)}
        await call.message.edit_reply_markup(reply_markup=category_list_kb(group, user_cat_ids))


@router.callback_query(F.data.startswith("rm_from_group:"))
async def cb_rm_from_group(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    cat_id = call.data[len("rm_from_group:"):]
    removed = await remove_user_category(call.from_user.id, cat_id)
    await call.answer("❌ Удалена" if removed else "Не найдена")
    group = next(
        (g for g, cats in KWORK_CATEGORIES.items() if any(c[0] == cat_id for c in cats)), None
    )
    if group:
        user_cat_ids = {c["category_id"] for c in await get_user_categories(call.from_user.id)}
        await call.message.edit_reply_markup(reply_markup=category_list_kb(group, user_cat_ids))


@router.callback_query(F.data == "cat_manual")
async def cb_cat_manual(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await _reg(call, settings)
    await state.set_state(Form.manual_cat)
    await call.answer()
    await call.message.answer(
        "Введи ID категории числом.\n\n"
        "Найди его в URL: kwork.ru/projects?<b>c=41</b>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(Form.manual_cat)
async def process_manual_cat(message: Message, state: FSMContext, settings: Settings) -> None:
    await _reg(message, settings)
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно ввести только цифры. Попробуй ещё раз.", reply_markup=cancel_kb())
        return
    from src.constants import CATEGORY_NAME_BY_ID
    cat_name = CATEGORY_NAME_BY_ID.get(text, f"Категория {text}")
    added = await add_user_category(message.from_user.id, text, cat_name)
    await state.clear()
    if added:
        await message.answer(
            f"✅ Добавлена: <b>{cat_name}</b> (#{text})",
            parse_mode="HTML", reply_markup=main_reply_kb(),
        )
    else:
        await message.answer("Эта категория уже отслеживается.", reply_markup=main_reply_kb())


# ── Ключевые слова ─────────────────────────────────────────────────────────

@router.message(F.text == "🎛 Фильтры")
async def btn_filters(message: Message, settings: Settings) -> None:
    await _reg(message, settings)
    await message.answer("🎛 <b>Фильтры</b>", parse_mode="HTML", reply_markup=filters_kb())


@router.message(F.text == "🔍 Ключевые слова")
async def btn_keywords(message: Message, settings: Settings) -> None:
    await _reg(message, settings)
    await _show_keywords(message, message.from_user.id)


@router.callback_query(F.data == "kw_list")
async def cb_kw_list(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    await call.answer()
    await _show_keywords(call.message, call.from_user.id, edit=True)


async def _show_keywords(msg: Message, user_id: int, edit: bool = False) -> None:
    kws = await get_user_keywords(user_id)
    text = (
        f"🔍 <b>Ключевые слова ({len(kws)})</b>\n\n"
        "Приходят только заказы, где есть хотя бы одно слово.\nНажми ❌ чтобы удалить 👇"
        if kws else
        "🔍 <b>Ключевые слова</b>\n\nСписок пуст — проходят <b>все</b> заказы из категорий без фильтров.\n\n"
        "Добавь слова для фильтрации."
    )
    kb = keywords_kb(kws)
    if edit:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "add_kw")
async def cb_add_kw(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await _reg(call, settings)
    await state.set_state(Form.add_keyword)
    await call.answer()
    await call.message.answer(
        "Введи ключевое слово или фразу (регистр не важен).",
        reply_markup=cancel_kb(),
    )


@router.message(Form.add_keyword)
async def process_keyword(message: Message, state: FSMContext, settings: Settings) -> None:
    await _reg(message, settings)
    kw = (message.text or "").strip()
    if not kw:
        await message.answer("Пустое слово. Попробуй ещё.", reply_markup=cancel_kb())
        return
    added = await add_user_keyword(message.from_user.id, kw)
    await state.clear()
    if added:
        await message.answer(f"✅ Добавлено: <b>{kw}</b>", parse_mode="HTML", reply_markup=main_reply_kb())
    else:
        await message.answer("Это слово уже есть.", reply_markup=main_reply_kb())


@router.callback_query(F.data.startswith("del_kw:"))
async def cb_del_kw(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    kw = call.data[len("del_kw:"):]
    removed = await remove_user_keyword(call.from_user.id, kw)
    await call.answer("❌ Удалено" if removed else "Не найдено")
    await _show_keywords(call.message, call.from_user.id, edit=True)


# ── Настройки ──────────────────────────────────────────────────────────────

@router.message(F.text == "⚙️ Настройки")
async def btn_settings(message: Message, settings: Settings) -> None:
    await _reg(message, settings)
    _, kb = await _settings_kb_for(message.from_user.id)
    await message.answer(
        "⚙️ <b>Настройки</b>\n\nНажми на параметр чтобы изменить:",
        parse_mode="HTML",
        reply_markup=kb,
    )


# ── Настройки: частота ─────────────────────────────────────────────────────

@router.callback_query(F.data == "edit_interval")
async def cb_edit_interval(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    user = await get_user(call.from_user.id)
    current = user.get("poll_interval", 30) if user else 30
    await call.answer()
    await call.message.answer(
        "⏱ <b>Выбери частоту уведомлений</b>\n\n"
        "Уведомления приходят кратно 30 сек: 30, 60, 90...",
        parse_mode="HTML",
        reply_markup=interval_kb(current),
    )


@router.callback_query(F.data.startswith("set_interval:"))
async def cb_set_interval(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    seconds = int(call.data.split(":")[1])
    await update_poll_interval(call.from_user.id, seconds)
    label = next((l for s, l in INTERVALS if s == seconds), f"{seconds} сек")
    await call.answer(f"✅ {label}")
    _, kb = await _settings_kb_for(call.from_user.id)
    await call.message.edit_text(
        "⚙️ <b>Настройки</b>\n\nНажми на параметр чтобы изменить:",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data == "back_to_settings")
async def cb_back_to_settings(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    _, kb = await _settings_kb_for(call.from_user.id)
    await call.answer()
    await call.message.edit_text(
        "⚙️ <b>Настройки</b>\n\nНажми на параметр чтобы изменить:",
        parse_mode="HTML",
        reply_markup=kb,
    )


# ── Настройки: период уведомлений ──────────────────────────────────────────

@router.callback_query(F.data == "edit_window")
async def cb_edit_window(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await _reg(call, settings)
    await call.answer()
    await call.message.answer(
        "🕐 Выбери <b>час начала</b> уведомлений:",
        parse_mode="HTML",
        reply_markup=hour_grid_kb("hour_from"),
    )


@router.callback_query(F.data.startswith("hour_from:"))
async def cb_hour_from(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await _reg(call, settings)
    hour = int(call.data.split(":")[1])
    await state.set_state(Form.set_hour_to)
    await state.update_data(hour_from=hour)
    await call.answer(f"Начало: {hour:02d}:00")
    await call.message.edit_text(
        f"🕐 Начало: <b>{hour:02d}:00</b>\n\nТеперь выбери <b>час окончания</b>:",
        parse_mode="HTML",
        reply_markup=hour_grid_kb("hour_to", is_end=True),
    )


@router.callback_query(F.data.startswith("hour_to:"), Form.set_hour_to)
async def cb_hour_to(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await _reg(call, settings)
    data     = await state.get_data()
    hour_from = data.get("hour_from", 0)
    hour_to   = int(call.data.split(":")[1])
    await update_time_window(call.from_user.id, hour_from, hour_to)
    await state.clear()
    await call.answer(f"Окончание: {hour_to:02d}:00")
    user = await get_user(call.from_user.id)
    await call.message.edit_text(
        f"✅ Уведомления: <b>{hour_from:02d}:00 – {'23:59' if hour_to == 23 else f'{hour_to:02d}:00'}</b>\n\n"
        "⚙️ <b>Настройки</b>",
        parse_mode="HTML",
        reply_markup=settings_kb(user or {}),
    )


@router.callback_query(F.data == "cancel_window")
async def cb_cancel_window(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer("Отменено")
    await call.message.delete()


# ── Настройки: часовой пояс ────────────────────────────────────────────────

@router.callback_query(F.data == "edit_tz")
async def cb_edit_tz(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    await call.answer()
    await call.message.answer(
        "🌍 Выбери свой часовой пояс:",
        reply_markup=timezone_kb(),
    )


@router.callback_query(F.data.startswith("set_tz:"))
async def cb_set_tz(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    offset = int(call.data.split(":")[1])
    await update_utc_offset(call.from_user.id, offset)
    sign  = "+" if offset >= 0 else ""
    label = next((l for l, o in TIMEZONES if o == offset), f"UTC{sign}{offset}")
    await call.answer(f"✅ {label}")
    user = await get_user(call.from_user.id)
    await call.message.edit_text(
        f"✅ Часовой пояс: <b>{label}</b>\n\n⚙️ <b>Настройки</b>",
        parse_mode="HTML",
        reply_markup=settings_kb(user or {}),
    )


@router.callback_query(F.data == "cancel_tz")
async def cb_cancel_tz(call: CallbackQuery) -> None:
    await call.answer("Отменено")
    await call.message.delete()


# ── Настройки: дни недели ─────────────────────────────────────────────────

@router.callback_query(F.data == "edit_days")
async def cb_edit_days(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    user = await get_user(call.from_user.id)
    notify_days = (user or {}).get("notify_days", 31)
    await call.answer()
    await call.message.edit_text(
        "📅 <b>Дни недели</b>\n\nНажми на день чтобы включить или отключить:",
        parse_mode="HTML",
        reply_markup=days_kb(notify_days),
    )


@router.callback_query(F.data.startswith("toggle_day:"))
async def cb_toggle_day(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    day_idx = int(call.data.split(":")[1])
    user = await get_user(call.from_user.id)
    notify_days = (user or {}).get("notify_days", 31)
    notify_days ^= (1 << day_idx)          # XOR — переключаем бит
    if notify_days == 0:                   # нельзя отключить все дни
        await call.answer("Нельзя отключить все дни!", show_alert=True)
        return
    await update_notify_days(call.from_user.id, notify_days)
    state = "✅" if (notify_days >> day_idx) & 1 else "☐"
    await call.answer(f"{state} {DAYS[day_idx]}")
    await call.message.edit_reply_markup(reply_markup=days_kb(notify_days))


# ── Настройки: фильтр цены ─────────────────────────────────────────────────

@router.callback_query(F.data == "edit_price")
async def cb_edit_price(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await _reg(call, settings)
    await state.set_state(Form.set_price_from)
    await call.answer()
    await call.message.answer(
        "💰 Введи <b>минимальную цену</b> (₽).\n\n"
        "Нажми «Пропустить» — без ограничения снизу.",
        parse_mode="HTML",
        reply_markup=skip_cancel_kb(),
    )


@router.message(Form.set_price_from)
async def process_price_from(message: Message, state: FSMContext, settings: Settings) -> None:
    await _reg(message, settings)
    text = (message.text or "").strip()
    if text == "⏭ Пропустить":
        price_from = 0
    elif text.isdigit():
        price_from = int(text)
    else:
        await message.answer("Введи целое число или нажми «Пропустить».", reply_markup=skip_cancel_kb())
        return
    await state.update_data(price_from=price_from)
    await state.set_state(Form.set_price_to)
    await message.answer(
        "💰 Введи <b>максимальную цену</b> (₽).\n\n"
        "Нажми «Пропустить» — без ограничения сверху.",
        parse_mode="HTML",
        reply_markup=skip_cancel_kb(),
    )


@router.message(Form.set_price_to)
async def process_price_to(message: Message, state: FSMContext, settings: Settings) -> None:
    await _reg(message, settings)
    text = (message.text or "").strip()
    if text == "⏭ Пропустить":
        price_to = 0
    elif text.isdigit():
        price_to = int(text)
    else:
        await message.answer("Введи целое число или нажми «Пропустить».", reply_markup=skip_cancel_kb())
        return
    data = await state.get_data()
    price_from = data.get("price_from", 0)
    await update_price_filter(message.from_user.id, price_from, price_to)
    await state.clear()
    _, kb = await _settings_kb_for(message.from_user.id)
    await message.answer(
        "⚙️ <b>Настройки</b>\n\nНажми на параметр чтобы изменить:",
        parse_mode="HTML",
        reply_markup=kb,
    )


# ── Админ: глобальный интервал парсера ────────────────────────────────────

@router.callback_query(F.data == "edit_global_interval")
async def cb_edit_global_interval(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    user = await get_user(call.from_user.id)
    if not user or not user.get("is_admin"):
        await call.answer("Нет прав", show_alert=True)
        return
    gs = await get_global_settings()
    await call.answer()
    await call.message.answer(
        "🌐 <b>Глобальный интервал парсера</b>\n\n"
        "Как часто бот проверяет новые заказы на kwork.ru:",
        parse_mode="HTML",
        reply_markup=global_interval_kb(gs.get("fetch_interval", 30)),
    )


@router.callback_query(F.data.startswith("set_global_interval:"))
async def cb_set_global_interval(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    user = await get_user(call.from_user.id)
    if not user or not user.get("is_admin"):
        await call.answer("Нет прав", show_alert=True)
        return
    seconds = int(call.data.split(":")[1])
    await update_global_fetch_interval(seconds)
    label = next((l for s, l in INTERVALS if s == seconds), f"{seconds} сек")
    await call.answer(f"✅ Парсер: {label}")
    _, kb = await _settings_kb_for(call.from_user.id)
    await call.message.edit_text(
        "⚙️ <b>Настройки</b>\n\nНажми на параметр чтобы изменить:",
        parse_mode="HTML",
        reply_markup=kb,
    )


# ── Админ: обновление категорий ───────────────────────────────────────────

@router.callback_query(F.data == "refresh_categories")
async def cb_refresh_categories(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    user = await get_user(call.from_user.id)
    if not user or not user.get("is_admin"):
        await call.answer("Нет прав", show_alert=True)
        return
    await call.answer()
    msg = await call.message.answer("⏳ Загружаю категории с kwork.ru...")
    from src.categories import fetch_and_update_categories
    success, text = await fetch_and_update_categories()
    await msg.edit_text(f"{'✅' if success else '❌'} {text}")


# ── Админ: регистрация ─────────────────────────────────────────────────────

@router.callback_query(F.data == "toggle_registration")
async def cb_toggle_registration(call: CallbackQuery, settings: Settings) -> None:
    await _reg(call, settings)
    user = await get_user(call.from_user.id)
    if not user or not user.get("is_admin"):
        await call.answer("Нет прав", show_alert=True)
        return
    gs = await get_global_settings()
    new_state = not gs.get("registration_open", 0)
    await update_registration_open(new_state)
    label = "открыта 🔓" if new_state else "закрыта 🔒"
    await call.answer(f"Регистрация {label}", show_alert=True)
    _, kb = await _settings_kb_for(call.from_user.id)
    await call.message.edit_reply_markup(reply_markup=kb)


# ── noop ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()


# ── Заглушка ───────────────────────────────────────────────────────────────

@router.message()
async def unknown_message(message: Message, settings: Settings) -> None:
    await _reg(message, settings)
    await message.answer("Используй кнопки ниже 👇\nЕсли их нет — напиши /start", reply_markup=main_reply_kb())
