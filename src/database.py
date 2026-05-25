import aiosqlite
from pathlib import Path

DB_PATH = Path("kwork_bot.db")


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id         INTEGER PRIMARY KEY,
                username        TEXT,
                first_name      TEXT,
                is_admin        INTEGER DEFAULT 0,
                is_active       INTEGER DEFAULT 1,
                poll_interval   INTEGER DEFAULT 30,
                last_notified_at TEXT,
                notify_from     INTEGER DEFAULT 0,
                notify_to       INTEGER DEFAULT 23,
                utc_offset      INTEGER DEFAULT 3,
                price_from      INTEGER DEFAULT 0,
                price_to        INTEGER DEFAULT 0,
                notify_days     INTEGER DEFAULT 31,
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS user_categories (
                user_id       INTEGER NOT NULL,
                category_id   TEXT    NOT NULL,
                category_name TEXT    NOT NULL,
                PRIMARY KEY (user_id, category_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS user_keywords (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                keyword    TEXT    NOT NULL COLLATE NOCASE,
                UNIQUE (user_id, keyword),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS order_history (
                order_id      INTEGER NOT NULL,
                category_id   TEXT    NOT NULL,
                title         TEXT    NOT NULL DEFAULT '',
                description   TEXT    NOT NULL DEFAULT '',
                budget        TEXT    NOT NULL DEFAULT '',
                price_min     INTEGER NOT NULL DEFAULT 0,
                category_name TEXT    NOT NULL DEFAULT '',
                published_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (order_id, category_id)
            );

            CREATE INDEX IF NOT EXISTS idx_order_history_published
                ON order_history (category_id, published_at);

            CREATE TABLE IF NOT EXISTS kwork_categories (
                parent_name   TEXT    NOT NULL,
                category_id   TEXT    NOT NULL,
                category_name TEXT    NOT NULL,
                sort_index    INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (category_id)
            );

            CREATE TABLE IF NOT EXISTS global_settings (
                id                INTEGER PRIMARY KEY CHECK (id = 1),
                fetch_interval    INTEGER NOT NULL DEFAULT 30,
                registration_open INTEGER NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO global_settings (id) VALUES (1);
        """)
        # Миграции для существующих БД без новых колонок
        for stmt in [
            "ALTER TABLE users ADD COLUMN poll_interval   INTEGER DEFAULT 30",
            "ALTER TABLE users ADD COLUMN last_notified_at TEXT",
            "ALTER TABLE users ADD COLUMN notify_from     INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN notify_to       INTEGER DEFAULT 23",
            "ALTER TABLE users ADD COLUMN utc_offset      INTEGER DEFAULT 3",
            "ALTER TABLE users ADD COLUMN price_from      INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN price_to        INTEGER DEFAULT 0",
            "ALTER TABLE order_history ADD COLUMN price_min INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN notify_days INTEGER DEFAULT 31",
        ]:
            try:
                await db.execute(stmt)
            except Exception:
                pass
        await db.commit()


# ── Пользователи ───────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str | None, first_name: str, admin_ids: list[int]) -> tuple[bool, bool]:
    """Регистрирует или обновляет пользователя.
    Возвращает (registered, is_new): registered=False если регистрация закрыта."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)) as cur:
            existing = await cur.fetchone()

        if existing is None:
            # Новый пользователь — проверяем, есть ли уже юзеры в БД
            async with db.execute("SELECT COUNT(*) FROM users") as cur:
                user_count = (await cur.fetchone())[0]

            if user_count == 0:
                # Первый пользователь → автоматически администратор
                is_admin = 1
            else:
                # Проверяем, открыта ли регистрация
                async with db.execute(
                    "SELECT registration_open FROM global_settings WHERE id = 1"
                ) as cur:
                    row = await cur.fetchone()
                    registration_open = row[0] if row else 0
                if not registration_open:
                    return False, False
                is_admin = 1 if user_id in admin_ids else 0

            await db.execute(
                """INSERT INTO users (user_id, username, first_name, is_admin, last_notified_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                (user_id, username, first_name, is_admin),
            )
            await db.commit()
            return True, True
        else:
            # Существующий — обновляем имя/username, is_admin не понижаем
            is_admin = max(existing[0], 1 if user_id in admin_ids else 0)
            await db.execute(
                "UPDATE users SET username = ?, first_name = ?, is_admin = ? WHERE user_id = ?",
                (username, first_name, is_admin, user_id),
            )
            await db.commit()
            return True, False


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            return (await cur.fetchone())[0]


async def get_admin_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE is_admin = 1") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY created_at") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def set_user_active(user_id: int, active: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_active = ? WHERE user_id = ?",
            (1 if active else 0, user_id),
        )
        await db.commit()


async def update_poll_interval(user_id: int, seconds: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        # Сбрасываем last_notified_at чтобы не слать сразу всё накопленное
        await db.execute(
            "UPDATE users SET poll_interval = ?, last_notified_at = datetime('now') WHERE user_id = ?",
            (seconds, user_id),
        )
        await db.commit()


async def update_time_window(user_id: int, notify_from: int, notify_to: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET notify_from = ?, notify_to = ? WHERE user_id = ?",
            (notify_from, notify_to, user_id),
        )
        await db.commit()


async def update_price_filter(user_id: int, price_from: int, price_to: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET price_from = ?, price_to = ? WHERE user_id = ?",
            (price_from, price_to, user_id),
        )
        await db.commit()


async def get_global_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM global_settings WHERE id = 1") as cur:
            row = await cur.fetchone()
            return dict(row) if row else {"fetch_interval": 30, "registration_open": 0}


async def update_global_fetch_interval(seconds: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE global_settings SET fetch_interval = ? WHERE id = 1", (seconds,)
        )
        await db.commit()


async def update_registration_open(open: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE global_settings SET registration_open = ? WHERE id = 1",
            (1 if open else 0,),
        )
        await db.commit()


async def update_notify_days(user_id: int, days_mask: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET notify_days = ? WHERE user_id = ?",
            (days_mask, user_id),
        )
        await db.commit()


async def update_utc_offset(user_id: int, utc_offset: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET utc_offset = ? WHERE user_id = ?",
            (utc_offset, user_id),
        )
        await db.commit()


# ── Категории ──────────────────────────────────────────────────────────────

async def get_user_categories(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_categories WHERE user_id = ? ORDER BY category_name",
            (user_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def add_user_category(user_id: int, category_id: str, category_name: str) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO user_categories (user_id, category_id, category_name) VALUES (?, ?, ?)",
                (user_id, category_id, category_name),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def remove_user_category(user_id: int, category_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM user_categories WHERE user_id = ? AND category_id = ?",
            (user_id, category_id),
        )
        await db.commit()
        return cur.rowcount > 0


# ── Ключевые слова ─────────────────────────────────────────────────────────

async def get_user_keywords(user_id: int) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT keyword FROM user_keywords WHERE user_id = ? ORDER BY keyword",
            (user_id,),
        ) as cur:
            return [r[0] for r in await cur.fetchall()]


async def add_user_keyword(user_id: int, keyword: str) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO user_keywords (user_id, keyword) VALUES (?, ?)",
                (user_id, keyword.strip().lower()),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def remove_user_keyword(user_id: int, keyword: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM user_keywords WHERE user_id = ? AND keyword = ?",
            (user_id, keyword.strip().lower()),
        )
        await db.commit()
        return cur.rowcount > 0


# ── История заказов ────────────────────────────────────────────────────────

async def store_order(order: dict) -> bool:
    """Сохранить заказ. Возвращает True если заказ новый."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT OR IGNORE INTO order_history
                (order_id, category_id, title, description, budget, price_min, category_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["order_id"], order["category_id"],
                order["title"], order["description"],
                order["budget"], order.get("price_min", 0), order["category_name"],
            ),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_orders_since(category_ids: list[str], since: str) -> list[dict]:
    """Заказы из указанных категорий, опубликованные после since (UTC ISO string)."""
    if not category_ids:
        return []
    placeholders = ",".join("?" * len(category_ids))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT * FROM order_history
            WHERE category_id IN ({placeholders})
              AND published_at > ?
            ORDER BY published_at ASC
            """,
            (*category_ids, since),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def cleanup_order_history() -> None:
    """Удалить записи старше 25 часов."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM order_history WHERE published_at < datetime('now', '-25 hours')"
        )
        await db.commit()


# ── Логика монитора ────────────────────────────────────────────────────────

async def get_all_monitored_categories() -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT DISTINCT uc.category_id
            FROM user_categories uc
            JOIN users u ON uc.user_id = u.user_id
            WHERE u.is_active = 1
            """
        ) as cur:
            return [r[0] for r in await cur.fetchall()]


async def get_due_users() -> list[dict]:
    """Пользователи, у которых истёк интервал с последнего уведомления."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM users
            WHERE is_active = 1
              AND last_notified_at IS NOT NULL
              AND datetime(last_notified_at, '+' || poll_interval || ' seconds') <= datetime('now')
            """
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def save_categories(categories: dict[str, list[tuple[str, str]]]) -> None:
    """Сохранить категории в БД (полная замена)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM kwork_categories")
        for parent_name, cats in categories.items():
            for idx, (cat_id, cat_name) in enumerate(cats):
                await db.execute(
                    "INSERT INTO kwork_categories (parent_name, category_id, category_name, sort_index) VALUES (?, ?, ?, ?)",
                    (parent_name, cat_id, cat_name, idx),
                )
        await db.commit()


async def load_categories() -> dict[str, list[tuple[str, str]]]:
    """Загрузить категории из БД. Возвращает пустой dict если таблица пуста."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT parent_name, category_id, category_name FROM kwork_categories ORDER BY parent_name, sort_index"
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        return {}
    result: dict[str, list[tuple[str, str]]] = {}
    for parent_name, cat_id, cat_name in rows:
        result.setdefault(parent_name, []).append((cat_id, cat_name))
    return result


async def update_last_notified(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_notified_at = datetime('now') WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def reset_all_last_notified() -> None:
    """Сбрасывает last_notified_at для всех пользователей на текущее время.
    Вызывается при старте бота чтобы не слать накопленные заказы."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET last_notified_at = datetime('now')")
        await db.commit()
