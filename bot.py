"""
MestiDelivery — Partners Bot (Бот для ресторанов-партнёров)
============================================================
Задачи:
  • Мини HTTP-сервер: принимает POST /api/bot/v1/restaurant/new-order от бэкенда
  • Отправляет уведомление о новом заказе в Telegram-чат ресторана
  • Партнёр нажимает [✅ Принять] или [❌ Отклонить]
  • Бот шлёт ответ обратно на бэкенд PATCH /api/v1/orders/{id}/status
  • Партнёр может зарегистрировать свой chat_id через /start или /register <код>

Архитектура:
  - aiogram 3.x  — Telegram Bot Framework
  - aiohttp       — встроенный HTTP-сервер для webhook от бэкенда
  - aiosqlite     — хранение chat_id партнёров
  - python-dotenv — конфигурация из .env
"""

import asyncio
import html
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ButtonStyle, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    WebAppInfo,
    BufferedInputFile,
    InputMediaPhoto,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import aiohttp as _aiohttp
from dotenv import load_dotenv
import bcrypt
from banner_renderer import render as render_banner


# ─────────────────────────────────────────────
#  Конфигурация
# ─────────────────────────────────────────────
load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
SECURITY_TOKEN: str = os.getenv("BOT_SECURITY_TOKEN", "")
if not BOT_TOKEN:
    raise SystemExit("FATAL: BOT_TOKEN environment variable is not set. Refusing to start.")
if not SECURITY_TOKEN:
    raise SystemExit("FATAL: BOT_SECURITY_TOKEN environment variable is not set. Refusing to start.")
HTTP_HOST: str = os.getenv("PARTNERS_HTTP_HOST", "0.0.0.0")
HTTP_PORT: int = int(os.getenv("PARTNERS_HTTP_PORT", "50061"))
BACKEND_URL: str = os.getenv("MAIN_BACKEND_URL", "http://localhost:8080")
CLIENT_BOT_URL: str = os.getenv("CLIENT_BOT_BASE_URL", "http://127.0.0.1:50062").rstrip("/")
CLIENT_BOT_TOKEN: str = os.getenv("CLIENT_BOT_SECURITY_TOKEN", "") or SECURITY_TOKEN
CATALOG_INTERNAL_URL: str = os.getenv("CATALOG_INTERNAL_URL", "http://127.0.0.1:50055")
BOT_PUBLIC_URL: str = os.getenv("BOT_PUBLIC_URL", "")  # URL для Telegram Webhook
DB_PATH: str = os.getenv("PARTNERS_DB_PATH", "partners_bot.db")


# Единственный живой data-dir бэкенда: сервисы стартуют из build/ → build/data/*.db
# Старый Backend/data переименован в data.legacy (не читать).
_BACKEND_DATA = r"c:\MestiDelivery\Backend GO\Backend\build\data"
BACKEND_DB_PATHS = [os.path.join(_BACKEND_DATA, "auth.db")]
CATALOG_DB_PATHS = [os.path.join(_BACKEND_DATA, "catalog.db")]
ORDER_DB_PATHS = [os.path.join(_BACKEND_DATA, "order.db")]

# Доли от суммы позиций (items = total - delivery_fee - service_fee) после delivered.
PLATFORM_ITEMS_COMMISSION = 0.10  # 10% сервису
RESTAURANT_ITEMS_SHARE = 0.90     # 90% ресторану
# delivery_fee → 100% курьеру; service_fee → 100% сервису (поверх 10%).

SECURITY_HEADER = "X-Bot-Security-Token"

# Telegram ID владельца — получает панель администратора вместо обычного меню
ADMIN_TG_ID: int = int(os.getenv("ADMIN_TELEGRAM_ID", "5564438585"))

def connect_sqlite_wal(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn

# ─────────────────────────────────────────────
#  Логирование
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("partners_bot")

# ─────────────────────────────────────────────
#  База данных
# ─────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS partners (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id   TEXT    NOT NULL UNIQUE,  -- ID ресторана из бэкенда
    telegram_id     INTEGER NOT NULL UNIQUE,  -- chat_id в Telegram
    restaurant_name TEXT    NOT NULL DEFAULT '',
    registered_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL,
    telegram_id INTEGER NOT NULL,
    message_id  INTEGER NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(order_id, telegram_id)
);

CREATE TABLE IF NOT EXISTS bot_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL,
    telegram_id  INTEGER NOT NULL,
    message_id   INTEGER NOT NULL,
    role         TEXT    NOT NULL,            -- 'restaurant' | 'courier'
    kind         TEXT    NOT NULL DEFAULT ''  -- 'new_order' | 'broadcast' | 'winner' | 'tracking'
);

CREATE TABLE IF NOT EXISTS bot_users (
    telegram_id INTEGER PRIMARY KEY,
    language    TEXT    NOT NULL DEFAULT 'ru',
    role        TEXT    NOT NULL DEFAULT '',
    backend_username TEXT,
    is_online   INTEGER NOT NULL DEFAULT 0,
    registered_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payout_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id      TEXT    NOT NULL,
    role            TEXT    NOT NULL,
    amount          REAL    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    resolved_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_partners_tid   ON partners(telegram_id);
CREATE INDEX IF NOT EXISTS idx_partners_rid   ON partners(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_order_messages ON order_messages(order_id);
CREATE INDEX IF NOT EXISTS idx_bot_messages_order  ON bot_messages(order_id);
CREATE INDEX IF NOT EXISTS idx_bot_messages_lookup ON bot_messages(order_id, telegram_id, kind);
CREATE INDEX IF NOT EXISTS idx_payout_requests_partner ON payout_requests(partner_id);

CREATE TABLE IF NOT EXISTS admin_panel_state (
    chat_id     INTEGER PRIMARY KEY,
    message_id  INTEGER NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS admin_sla_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL,
    alert_type  TEXT NOT NULL,
    sent_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(order_id, alert_type)
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.executescript(SCHEMA)
        try:
            await self._db.execute("ALTER TABLE bot_users ADD COLUMN is_online INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            # Локальный UI-статус open/close (каталог меняет админ вручную)
            await self._db.execute("ALTER TABLE partners ADD COLUMN ui_is_open INTEGER")
        except Exception:
            pass
        await self._db.commit()
        log.info("Database connected: %s (WAL enabled)", self.path)

    async def close(self):
        if self._db:
            await self._db.close()

    # ── Партнёры ──────────────────────────────────
    async def get_partner_by_telegram(self, telegram_id: int) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM partners WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_partner_by_restaurant(self, restaurant_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM partners WHERE restaurant_id = ?", (restaurant_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def register_partner(
        self, telegram_id: int, restaurant_id: str, restaurant_name: str = ""
    ) -> bool:
        try:
            await self._db.execute(
                """INSERT INTO partners (telegram_id, restaurant_id, restaurant_name)
                   VALUES (?, ?, ?)
                   ON CONFLICT(restaurant_id) DO UPDATE SET
                     telegram_id     = excluded.telegram_id,
                     restaurant_name = excluded.restaurant_name""",
                (telegram_id, restaurant_id, restaurant_name),
            )
            await self._db.commit()
            return True
        except Exception as e:
            log.error("register_partner error: %s", e)
            return False

    async def set_partner_ui_open(self, restaurant_id: str, ui_is_open: int) -> bool:
        try:
            await self._db.execute(
                "UPDATE partners SET ui_is_open = ? WHERE restaurant_id = ?",
                (ui_is_open, restaurant_id),
            )
            await self._db.commit()
            return True
        except Exception as e:
            log.error("set_partner_ui_open error: %s", e)
            return False

    async def list_partners(self) -> list[dict]:
        async with self._db.execute("SELECT * FROM partners ORDER BY registered_at DESC") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ── Сообщения заказов ──────────────────────────
    async def save_order_message(
        self, order_id: int, telegram_id: int, message_id: int
    ):
        await self._db.execute(
            """INSERT INTO order_messages (order_id, telegram_id, message_id)
               VALUES (?, ?, ?)
               ON CONFLICT(order_id, telegram_id) DO UPDATE SET message_id = excluded.message_id""",
            (order_id, telegram_id, message_id),
        )
        await self._db.commit()

    async def get_order_message(self, order_id: int, telegram_id: int) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM order_messages WHERE order_id = ? AND telegram_id = ?",
            (order_id, telegram_id),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def update_order_status(self, order_id: int, telegram_id: int, status: str):
        await self._db.execute(
            "UPDATE order_messages SET status = ? WHERE order_id = ? AND telegram_id = ?",
            (status, order_id, telegram_id),
        )
        await self._db.commit()

    # ── Сообщения ботов (Go-bot StateStore equivalents) ──────────────────
    async def save_message(
        self, order_id: int, telegram_id: int, message_id: int, role: str, kind: str
    ) -> bool:
        try:
            await self._db.execute(
                """INSERT INTO bot_messages (order_id, telegram_id, message_id, role, kind)
                   VALUES (?, ?, ?, ?, ?)""",
                (order_id, telegram_id, message_id, role, kind),
            )
            await self._db.commit()
            return True
        except Exception as e:
            log.error("save_message error: %s", e)
            return False

    async def get_messages_for_order(self, order_id: int) -> list[dict]:
        async with self._db.execute(
            "SELECT telegram_id, message_id, role, kind FROM bot_messages WHERE order_id = ?",
            (order_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_messages_for_order_kind(self, order_id: int, kind: str) -> list[dict]:
        async with self._db.execute(
            "SELECT telegram_id, message_id, role, kind FROM bot_messages WHERE order_id = ? AND kind = ?",
            (order_id, kind),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_broadcast_recipients(self, order_id: int) -> list[int]:
        async with self._db.execute(
            "SELECT DISTINCT telegram_id FROM bot_messages WHERE order_id = ? AND kind = ?",
            (order_id, "broadcast"),
        ) as cur:
            rows = await cur.fetchall()
            return [r["telegram_id"] for r in rows]

    async def delete_for_order(self, order_id: int):
        try:
            await self._db.execute("DELETE FROM bot_messages WHERE order_id = ?", (order_id,))
            await self._db.commit()
        except Exception as e:
            log.error("delete_for_order error: %s", e)

    async def update_kind(self, order_id: int, telegram_id: int, kind: str) -> bool:
        try:
            await self._db.execute(
                "UPDATE bot_messages SET kind = ? WHERE order_id = ? AND telegram_id = ?",
                (kind, order_id, telegram_id),
            )
            await self._db.commit()
            return True
        except Exception as e:
            log.error("update_kind error: %s", e)
            return False

    async def get_bot_user(self, telegram_id: int) -> Optional[dict]:
        async with self._db.execute("SELECT * FROM bot_users WHERE telegram_id = ?", (telegram_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_online_courier_ids(self) -> list[int]:
        """Returns list of telegram_ids of couriers currently online (is_online=1)."""
        async with self._db.execute(
            "SELECT telegram_id FROM bot_users WHERE role = 'courier' AND is_online = 1"
        ) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]

    async def get_all_courier_ids(self) -> list[int]:
        """Returns list of telegram_ids of all registered couriers."""
        async with self._db.execute(
            "SELECT telegram_id FROM bot_users WHERE role = 'courier'"
        ) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]

    async def get_stats(self) -> dict:
        """Returns bot stats: couriers total/online, restaurants total."""
        async with self._db.execute(
            "SELECT COUNT(*) FROM bot_users WHERE role = 'courier'"
        ) as cur:
            row = await cur.fetchone()
            couriers_total = row[0] if row else 0
        async with self._db.execute(
            "SELECT COUNT(*) FROM bot_users WHERE role = 'courier' AND is_online = 1"
        ) as cur:
            row = await cur.fetchone()
            couriers_online = row[0] if row else 0
        async with self._db.execute(
            "SELECT COUNT(*) FROM bot_users WHERE role = 'restaurant_admin'"
        ) as cur:
            row = await cur.fetchone()
            restaurants_total = row[0] if row else 0
        return {
            "couriers_total": couriers_total,
            "couriers_online": couriers_online,
            "restaurants_total": restaurants_total,
        }

    async def save_bot_user(self, telegram_id: int, language: str, role: str, backend_username: str):
        try:
            await self._db.execute(
                """INSERT INTO bot_users (telegram_id, language, role, backend_username)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(telegram_id) DO UPDATE SET
                     language = excluded.language,
                     role = excluded.role,
                     backend_username = excluded.backend_username""",
                (telegram_id, language, role, backend_username),
            )
            await self._db.commit()
        except Exception as e:
            log.error("save_bot_user error: %s", e)

    async def set_courier_online_status(self, telegram_id: int, is_online: int) -> bool:
        try:
            await self._db.execute("UPDATE bot_users SET is_online = ? WHERE telegram_id = ?", (is_online, telegram_id))
            await self._db.commit()
            return True
        except Exception as e:
            log.error("set_courier_online_status error: %s", e)
            return False

    async def offline_other_sessions(self, telegram_id: int, username: str) -> None:
        """Снимает is_online с других TG того же логина (после смены аккаунта)."""
        try:
            await self._db.execute(
                "UPDATE bot_users SET is_online = 0 "
                "WHERE backend_username = ? AND telegram_id != ? AND role = 'courier'",
                (username, telegram_id),
            )
            await self._db.commit()
        except Exception as e:
            log.error("offline_other_sessions error: %s", e)

    async def get_online_couriers(self) -> list[int]:
        async with self._db.execute("SELECT telegram_id FROM bot_users WHERE role = 'courier' AND is_online = 1") as cur:
            rows = await cur.fetchall()
            return [r["telegram_id"] for r in rows]

    # ── Дополнительные хелперы для Профиля ──
    async def get_courier_id_by_telegram(self, telegram_id: int) -> Optional[int]:
        def _query():
            for path in BACKEND_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id FROM admin_users WHERE telegram_id = ? AND role = 'courier'",
                        (str(telegram_id),),
                    )
                    row = cursor.fetchone()
                    conn.close()
                    if row:
                        return int(row[0])
                except Exception:
                    pass
            return None
        return await asyncio.to_thread(_query)

    async def get_courier_ids_by_telegram(self, telegram_id: int) -> list[int]:
        """Все id курьера по TG во всех auth.db (защита от drift data/build)."""
        def _query():
            ids: list[int] = []
            seen: set[int] = set()
            for path in BACKEND_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id FROM admin_users WHERE telegram_id = ? AND role = 'courier'",
                        (str(telegram_id),),
                    )
                    for row in cursor.fetchall():
                        cid = int(row[0])
                        if cid not in seen:
                            seen.add(cid)
                            ids.append(cid)
                    conn.close()
                except Exception:
                    pass
            return ids
        return await asyncio.to_thread(_query)

    @staticmethod
    def _items_amount_sql() -> str:
        # items = total - delivery - service - tips (чаевые курьеру, не в долю ресторана/платформы)
        return (
            "MAX(0, COALESCE(total, 0) - COALESCE(delivery_fee, 0) "
            "- COALESCE(service_fee, 0) - COALESCE(tips, 0))"
        )

    @staticmethod
    def _restaurant_income_expr() -> str:
        # ресторан получает 90% items
        return f"SUM({RESTAURANT_ITEMS_SHARE} * {Database._items_amount_sql()})"

    @staticmethod
    def _courier_income_expr() -> str:
        # 100% delivery_fee + 100% tips
        return "SUM(COALESCE(delivery_fee, 0) + COALESCE(tips, 0))"

    @staticmethod
    def _platform_income_expr() -> str:
        # 10% items + 100% service_fee
        return (
            f"SUM({PLATFORM_ITEMS_COMMISSION} * {Database._items_amount_sql()} "
            "+ COALESCE(service_fee, 0))"
        )

    async def get_restaurant_active_orders(self, restaurant_id: str) -> int:
        """Активные заказы ресторана (ещё не доставлены / не отменены)."""
        def _query():
            for path in ORDER_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT COUNT(*) FROM orders "
                        "WHERE restaurant_id = ? AND lower(status) NOT IN "
                        "('delivered', 'cancelled', 'canceled', 'rejected')",
                        (restaurant_id,),
                    )
                    row = cur.fetchone()
                    conn.close()
                    if row and row[0] is not None:
                        return int(row[0])
                except Exception as e:
                    log.error("Error active orders: %s", e)
            return 0
        return await asyncio.to_thread(_query)

    async def get_restaurant_today_income(self, restaurant_id: str) -> float:
        def _query():
            expr = Database._restaurant_income_expr()
            for path in ORDER_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        f"SELECT {expr} FROM orders "
                        "WHERE restaurant_id = ? AND status = 'delivered' "
                        "AND date(replace(substr(created_at, 1, 10), 'T', ' ')) = date('now')",
                        (restaurant_id,),
                    )
                    row = cursor.fetchone()
                    conn.close()
                    if row and row[0] is not None:
                        return float(row[0])
                except Exception as e:
                    log.error("Error today income: %s", e)
            return 0.0
        return await asyncio.to_thread(_query)

    async def get_restaurant_lifetime_income(self, restaurant_id: str) -> float:
        def _query():
            expr = Database._restaurant_income_expr()
            for path in ORDER_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        f"SELECT {expr} FROM orders "
                        "WHERE restaurant_id = ? AND status = 'delivered'",
                        (restaurant_id,),
                    )
                    row = cursor.fetchone()
                    conn.close()
                    if row and row[0] is not None:
                        return float(row[0])
                except Exception as e:
                    log.error("Error lifetime income: %s", e)
            return 0.0
        return await asyncio.to_thread(_query)

    async def get_restaurant_payouts(self, restaurant_id: str) -> float:
        async with self._db.execute(
            "SELECT SUM(amount) FROM payout_requests WHERE partner_id = ? AND role = 'restaurant_admin' AND status IN ('pending', 'approved')",
            (restaurant_id,)
        ) as cur:
            row = await cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0

    async def get_courier_today_income(self, courier_id: int) -> float:
        return await self.get_courier_today_income_multi([courier_id])

    async def get_courier_lifetime_income(self, courier_id: int) -> float:
        return await self.get_courier_lifetime_income_multi([courier_id])

    async def get_courier_today_income_multi(self, courier_ids: list[int]) -> float:
        if not courier_ids:
            return 0.0
        def _query():
            expr = Database._courier_income_expr()
            placeholders = ",".join("?" * len(courier_ids))
            for path in ORDER_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        f"SELECT {expr} FROM orders "
                        f"WHERE courier_id IN ({placeholders}) AND status = 'delivered' "
                        "AND date(replace(substr(created_at, 1, 10), 'T', ' ')) = date('now')",
                        tuple(courier_ids),
                    )
                    row = cursor.fetchone()
                    conn.close()
                    if row and row[0] is not None:
                        return float(row[0])
                except Exception as e:
                    log.error("Error courier today income: %s", e)
            return 0.0
        return await asyncio.to_thread(_query)

    async def get_courier_today_deliveries_multi(self, courier_ids: list[int]) -> int:
        """Доставки курьера за сегодня (status=delivered)."""
        if not courier_ids:
            return 0

        def _query():
            placeholders = ",".join("?" * len(courier_ids))
            for path in ORDER_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        f"SELECT COUNT(*) FROM orders "
                        f"WHERE courier_id IN ({placeholders}) AND lower(status) = 'delivered' "
                        "AND date(replace(substr(created_at, 1, 10), 'T', ' ')) = date('now')",
                        tuple(courier_ids),
                    )
                    row = cursor.fetchone()
                    conn.close()
                    if row and row[0] is not None:
                        return int(row[0])
                except Exception as e:
                    log.error("Error courier today deliveries: %s", e)
            return 0

        return await asyncio.to_thread(_query)

    async def get_courier_lifetime_deliveries_multi(self, courier_ids: list[int]) -> int:
        """Все доставленные заказы курьера (для баннера THIS SHIFT / deliveries)."""
        if not courier_ids:
            return 0

        def _query():
            placeholders = ",".join("?" * len(courier_ids))
            for path in ORDER_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        f"SELECT COUNT(*) FROM orders "
                        f"WHERE courier_id IN ({placeholders}) AND lower(status) = 'delivered'",
                        tuple(courier_ids),
                    )
                    row = cursor.fetchone()
                    conn.close()
                    if row and row[0] is not None:
                        return int(row[0])
                except Exception as e:
                    log.error("Error courier lifetime deliveries: %s", e)
            return 0

        return await asyncio.to_thread(_query)

    async def get_courier_lifetime_income_multi(self, courier_ids: list[int]) -> float:
        if not courier_ids:
            return 0.0
        def _query():
            expr = Database._courier_income_expr()
            placeholders = ",".join("?" * len(courier_ids))
            for path in ORDER_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        f"SELECT {expr} FROM orders "
                        f"WHERE courier_id IN ({placeholders}) AND status = 'delivered'",
                        tuple(courier_ids),
                    )
                    row = cursor.fetchone()
                    conn.close()
                    if row and row[0] is not None:
                        return float(row[0])
                except Exception as e:
                    log.error("Error courier lifetime income: %s", e)
            return 0.0
        return await asyncio.to_thread(_query)

    async def get_platform_today_income(self) -> float:
        def _query():
            expr = Database._platform_income_expr()
            for path in ORDER_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        f"SELECT {expr} FROM orders WHERE status = 'delivered' "
                        "AND date(replace(substr(created_at, 1, 10), 'T', ' ')) = date('now')"
                    )
                    row = cursor.fetchone()
                    conn.close()
                    if row and row[0] is not None:
                        return float(row[0])
                except Exception as e:
                    log.error("Error platform today income: %s", e)
            return 0.0
        return await asyncio.to_thread(_query)

    async def get_platform_lifetime_income(self) -> float:
        def _query():
            expr = Database._platform_income_expr()
            for path in ORDER_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        f"SELECT {expr} FROM orders WHERE status = 'delivered'"
                    )
                    row = cursor.fetchone()
                    conn.close()
                    if row and row[0] is not None:
                        return float(row[0])
                except Exception as e:
                    log.error("Error platform lifetime income: %s", e)
            return 0.0
        return await asyncio.to_thread(_query)

    async def get_courier_payouts(self, telegram_id: int) -> float:
        async with self._db.execute(
            "SELECT SUM(amount) FROM payout_requests WHERE partner_id = ? AND role = 'courier' AND status IN ('pending', 'approved')",
            (str(telegram_id),)
        ) as cur:
            row = await cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0

    async def get_last_payout(self, partner_id: str, role: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT amount, created_at FROM payout_requests WHERE partner_id = ? AND role = ? AND status = 'approved' ORDER BY id DESC LIMIT 1",
            (str(partner_id), role)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def create_payout_request(self, partner_id: str, role: str, amount: float) -> bool:
        try:
            await self._db.execute(
                "INSERT INTO payout_requests (partner_id, role, amount) VALUES (?, ?, ?)",
                (str(partner_id), role, amount)
            )
            await self._db.commit()
            return True
        except Exception as e:
            log.error(f"Error creating payout request: {e}")
            return False

    async def get_restaurant_status_and_hours(self, restaurant_id: str) -> tuple[int, str]:
        """Ищет ресторан во всех catalog.db. По умолчанию открыт (is_active=1)."""
        def _query():
            found = False
            is_active = 1
            working_hours = ""
            for path in CATALOG_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT is_active, working_hours FROM restaurants WHERE id = ?",
                        (restaurant_id,),
                    )
                    row = cursor.fetchone()
                    conn.close()
                    if row:
                        found = True
                        # NULL / missing → считаем открытым
                        is_active = 1 if row[0] is None else int(row[0])
                        working_hours = row[1] if row[1] is not None else ""
                        log.info(
                            "Restaurant %s status from %s: is_active=%s",
                            restaurant_id, path, is_active,
                        )
                        break
                except Exception as e:
                    log.error(f"Error fetching status/hours from {path}: {e}")
            if not found:
                log.warning(
                    "Restaurant %s not found in any catalog.db — defaulting to open",
                    restaurant_id,
                )
            return is_active, working_hours
        return await asyncio.to_thread(_query)

    async def update_restaurant_status(self, restaurant_id: str, is_active: int) -> bool:
        """Обновляет is_active во всех catalog.db, где есть этот ресторан."""
        def _query():
            updated = 0
            for path in CATALOG_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE restaurants SET is_active = ? WHERE id = ?",
                        (is_active, restaurant_id),
                    )
                    if cursor.rowcount > 0:
                        updated += cursor.rowcount
                        log.info(
                            "Updated restaurant %s is_active=%s in %s (rows=%s)",
                            restaurant_id, is_active, path, cursor.rowcount,
                        )
                    conn.commit()
                    conn.close()
                except Exception as e:
                    log.error(f"Error updating restaurant status in {path}: {e}")
            if updated == 0:
                log.error(
                    "Failed to update is_active for %s — restaurant not found in catalog DBs",
                    restaurant_id,
                )
            return updated > 0
        return await asyncio.to_thread(_query)

    async def update_restaurant_hours(self, restaurant_id: str, hours_json: str) -> bool:
        def _query():
            updated = 0
            for path in CATALOG_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE restaurants SET working_hours = ? WHERE id = ?",
                        (hours_json, restaurant_id),
                    )
                    if cursor.rowcount > 0:
                        updated += cursor.rowcount
                    conn.commit()
                    conn.close()
                except Exception as e:
                    log.error(f"Error updating restaurant hours in {path}: {e}")
            return updated > 0
        return await asyncio.to_thread(_query)

    async def update_restaurant_name_and_desc(self, restaurant_id: str, name: Optional[str] = None, desc: Optional[str] = None) -> bool:
        def _query():
            success = False
            for path in CATALOG_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    if name is not None and desc is not None:
                        cursor.execute("UPDATE restaurants SET name = ?, description = ? WHERE id = ?", (name, desc, restaurant_id))
                    elif name is not None:
                        cursor.execute("UPDATE restaurants SET name = ? WHERE id = ?", (name, restaurant_id))
                    elif desc is not None:
                        cursor.execute("UPDATE restaurants SET description = ? WHERE id = ?", (desc, restaurant_id))
                    conn.commit()
                    conn.close()
                    success = True
                except Exception as e:
                    log.error(f"Error updating restaurant metadata: {e}")
            return success
        return await asyncio.to_thread(_query)

    async def update_restaurant_image(self, restaurant_id: str, relative_path: str) -> bool:
        def _query():
            success = False
            for path in CATALOG_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE restaurants SET img = ? WHERE id = ?", (relative_path, restaurant_id))
                    conn.commit()
                    conn.close()
                    success = True
                except Exception as e:
                    log.error(f"Error updating restaurant image: {e}")
            return success
        return await asyncio.to_thread(_query)

    # ── Административные методы для выплат ──
    async def is_super_admin(self, telegram_id: int) -> bool:
        def _query():
            for path in BACKEND_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT role FROM admin_users WHERE telegram_id = ?", (str(telegram_id),))
                    row = cursor.fetchone()
                    conn.close()
                    if row and row[0] == "super_admin":
                        return True
                except Exception:
                    pass
            return False
        return await asyncio.to_thread(_query)

    async def get_pending_payout_requests(self) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM payout_requests WHERE status = 'pending' ORDER BY id ASC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_payout_request_by_id(self, request_id: int) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM payout_requests WHERE id = ?",
            (request_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def approve_payout_request(self, request_id: int) -> bool:
        try:
            await self._db.execute(
                "UPDATE payout_requests SET status = 'approved', resolved_at = datetime('now') WHERE id = ?",
                (request_id,)
            )
            await self._db.commit()
            return True
        except Exception as e:
            log.error(f"Error approving payout: {e}")
            return False

    async def reject_payout_request(self, request_id: int) -> bool:
        try:
            await self._db.execute(
                "UPDATE payout_requests SET status = 'rejected', resolved_at = datetime('now') WHERE id = ?",
                (request_id,)
            )
            await self._db.commit()
            return True
        except Exception as e:
            log.error(f"Error rejecting payout: {e}")
            return False



# ─────────────────────────────────────────────
#  Telegram Bot — роутер
# ─────────────────────────────────────────────
router = Router()
db: Optional[Database] = None
bot: Optional[Bot] = None


def make_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для нового заказа: Принять / Отклонить + Подробности."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Принять",
                    callback_data=f"accept_{order_id}",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"reject_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Открыть подробности",
                    web_app=WebAppInfo(url=f"{MINIAPP_DIRECT_URL}?order_id={order_id}"),
                    icon_custom_emoji_id="5384138412053796842",
                )
            ],
        ]
    )


# Окна принятия заказа (баннер + caption + SLA).
RESTAURANT_ACCEPT_MIN = 5   # ресторану ~5 минут
COURIER_ACCEPT_MIN = 10     # курьеру обычно 5–10 мин (пока готовится); дедлайн = верхняя граница


def _format_order_time(value, *, minutes: int = RESTAURANT_ACCEPT_MIN) -> tuple[str, str]:
    """Возвращает (создан HH:MM, принять_до HH:MM)."""
    created_dt = datetime.now()
    if value:
        if isinstance(value, (int, float)):
            created_dt = datetime.fromtimestamp(value)
        else:
            raw = str(value).strip()
            try:
                created_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if created_dt.tzinfo is not None:
                    created_dt = created_dt.astimezone().replace(tzinfo=None)
            except ValueError:
                for fmt in ("%H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
                    try:
                        parsed = datetime.strptime(raw, fmt)
                        if fmt == "%H:%M":
                            created_dt = datetime.now().replace(
                                hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0
                            )
                        else:
                            created_dt = parsed
                        break
                    except ValueError:
                        continue
    deadline = created_dt + timedelta(minutes=minutes)
    return created_dt.strftime("%H:%M"), deadline.strftime("%H:%M")


def _format_banner_items(items: list) -> str:
    """Формат зоны ITEMS на баннере 2a: «3 items · A, B, C»."""
    if not items:
        return "—"
    names: list[str] = []
    count = 0
    for it in items:
        name = str(it.get("name") or "Товар").strip() or "Товар"
        qty = int(it.get("quantity") or 1)
        count += max(qty, 1)
        if qty > 1:
            names.append(f"{name} ×{qty}")
        else:
            names.append(name)
    word = "item" if count == 1 else "items"
    return f"{count} {word} · {', '.join(names)}"


def _clean_order_comment(comment: str) -> str:
    """Убирает служебные хвосты вроде «[оплата: Cash]» из комментария."""
    text = (comment or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s*\[оплата:[^\]]*\]\s*", " ", text, flags=re.IGNORECASE)
    return text.strip(" \n·—-")


def format_order_message(data: dict) -> str:
    """HTML-карточка нового заказа: состав + сумма только по позициям (без доставки/сервиса)."""
    order_id = data.get("order_id", "?")
    currency = data.get("currency") or "GEL"
    comment = _clean_order_comment(data.get("comment") or "")
    items = data.get("items") or []
    created_hm, deadline_hm = _format_order_time(
        data.get("created_at"), minutes=RESTAURANT_ACCEPT_MIN
    )

    items_lines: list[str] = []
    food_total = 0.0
    for item in items:
        name = html.escape(str(item.get("name") or "Товар"))
        qty = int(item.get("quantity") or 1)
        unit = float(item.get("price") or 0)
        line_total = unit * qty
        food_total += line_total
        items_lines.append(f" • <b>{name}</b> × {qty} — {line_total:.0f} {currency}")

    items_block = "\n".join(items_lines) if items_lines else " —"

    parts = [
        f'{ce("5384244502040975393", "🔔")} <b>НОВЫЙ ЗАКАЗ #{order_id}</b>',
        f" <b>Создан</b>: {created_hm} · <b>Принять до</b>: {deadline_hm}"
        f" (~{RESTAURANT_ACCEPT_MIN} мин)",
        "",
        f'{ce("5384312315279612142", "🛒")} <b>Состав заказа</b>:',
        items_block,
        "",
        f'{ce("5384520939021048827", "💰")} <b>Сумма заказа</b>: {food_total:.0f} {currency}',
    ]
    if comment:
        parts.append(
            f'{ce("5382097310450753507", "💬")} <b>Комментарий к заказу</b>: {html.escape(comment)}'
        )
    return "\n".join(parts)


# ── Команды ───────────────────────────────────



CUSTOM_EMOJI = {
    "welcome": "5384489194917765397",
    "point_down": "5382351125838077755",
    "profile_setup": "5384244502040975393",
    "success": "5384244502040975393",
    "courier": "5384520939021048827",
    "restaurateur": "5384312315279612142",
    "credentials": "5384138412053796842",
    "dashboard": "5384222159621102491",
    "nav_hint": "5382248944271140910",
    "btn_profile": "5381848533060067195",
    "btn_orders": "5384138412053796842",
    "btn_menu": "5384312315279612142",
    "btn_stats": "5384518714227990146",
    "btn_support": "5382097310450753507",
    "balance": "5384520939021048827",
    "income_today": "5384518714227990146",
    "close_restaurant": "5348083587532994863",
    "open_restaurant": "5348348011489542390",
    "hours": "5382351125838077755",
    "payouts": "5384518714227990146",
    "flag_ru": "5449408995691341691",
    "flag_en": "5202196682497859879",
    "flag_ka": "5440371950708864925",
}


def ce(emoji_id: str, alt: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{alt}</tg-emoji>'


I18N = {
    "ru": {
        "welcome": (
            f'{ce(CUSTOM_EMOJI["welcome"], "👋")} Welcome, <b>{{first_name}}</b>!\n\n'
            f'To continue, choose your language {ce(CUSTOM_EMOJI["point_down"], "👇")}'
        ),
        "choose_role": (
            f'{ce(CUSTOM_EMOJI["profile_setup"], "⚙️")} <b>Настройка профиля</b>\n\n'
            f"Для входа в систему укажите вашу роль:"
        ),
        "enter_login": (
            f'{ce(CUSTOM_EMOJI["credentials"], "🔑")} Введите ваш <b>логин</b> '
            f"из личного кабинета (/partners):"
        ),
        "enter_password": (
            f'{ce(CUSTOM_EMOJI["credentials"], "🔒")} Теперь введите ваш <b>пароль</b>:'
        ),
        "checking_data": "⏳ Проверяем данные...",
        "auth_success_rest": (
            f'{ce(CUSTOM_EMOJI["success"], "✅")} Готово! <b>{{rest_name}}</b> '
            f"подключён к MestiDelivery"
        ),
        "auth_success_courier": (
            f'{ce("5384244502040975393", "✅")} Готово! Вы авторизованы как Курьер MestiDelivery'
        ),
        "auth_fail": "❌ <b>Неверный логин или пароль</b>. Пожалуйста, проверьте данные и введите логин заново.",
        "role_courier": "Курьер",
        "role_rest": "Ресторатор",
        "menu_history": "📜 История заказов",
        "menu_profile": "Профиль",
        "menu_orders": "Заказы",
        "menu_menu": "Меню",
        "menu_shifts": "Смены",
        "menu_income": "Статистика",
        "menu_support": "Поддержка",
        "menu_courier_offline": "Выйти на линию",
        "menu_courier_online": "Сойти с линии",
        "status_online_now": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} Вы вышли на линию! Теперь вы будете получать заказы.'
        ),
        "status_offline_now": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} Вы не на линии. Заказы не поступают.'
        ),
        "courier_offline_alert": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} Не на линии. Заказы не поступают.'
        ),
        "courier_online_alert": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} На линии! Заказы будут поступать.'
        ),
        "courier_line_status_offline": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} Не на линии. Заказы не поступают.'
        ),
        "courier_line_status_online": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} На линии! Заказы будут поступать.'
        ),
    },
    "en": {
        "welcome": (
            f'{ce(CUSTOM_EMOJI["welcome"], "👋")} Welcome, <b>{{first_name}}</b>!\n\n'
            f'To continue, please select a language {ce(CUSTOM_EMOJI["point_down"], "👇")}'
        ),
        "choose_role": (
            f'{ce(CUSTOM_EMOJI["profile_setup"], "⚙️")} <b>Profile Setup</b>\n\n'
            f"To log in, please select your role:"
        ),
        "enter_login": (
            f'{ce(CUSTOM_EMOJI["credentials"], "🔑")} Enter your <b>login</b> '
            f"from the dashboard (/partners):"
        ),
        "enter_password": (
            f'{ce(CUSTOM_EMOJI["credentials"], "🔒")} Now enter your <b>password</b>:'
        ),
        "checking_data": "⏳ Checking credentials...",
        "auth_success_rest": (
            f'{ce(CUSTOM_EMOJI["success"], "✅")} Done! <b>{{rest_name}}</b> '
            f"is connected to MestiDelivery"
        ),
        "auth_success_courier": (
            f'{ce("5384244502040975393", "✅")} Done! You are authorized as a MestiDelivery Courier'
        ),
        "auth_fail": "❌ <b>Invalid login or password</b>. Please check your credentials and enter your login again.",
        "role_courier": "Courier",
        "role_rest": "Restaurateur",
        "menu_history": "📜 Order History",
        "menu_profile": "Profile",
        "menu_orders": "Orders",
        "menu_menu": "Menu",
        "menu_shifts": "Shifts",
        "menu_income": "Stats",
        "menu_support": "Support",
        "menu_courier_offline": "Go online",
        "menu_courier_online": "Go offline",
        "status_online_now": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} You are online! You will now receive orders.'
        ),
        "status_offline_now": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} You are offline. Orders are not incoming.'
        ),
        "courier_offline_alert": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} Offline. Orders are not incoming.'
        ),
        "courier_online_alert": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} Online! Orders will be incoming.'
        ),
        "courier_line_status_offline": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} Offline. Orders are not incoming.'
        ),
        "courier_line_status_online": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} Online! Orders will be incoming.'
        ),
    },
    "ka": {
        "welcome": (
            f'{ce(CUSTOM_EMOJI["welcome"], "👋")} მოგესალმებით, <b>{{first_name}}</b>!\n\n'
            f'გაგრძელებისთვის, გთხოვთ აირჩიოთ ენა {ce(CUSTOM_EMOJI["point_down"], "👇")}'
        ),
        "choose_role": (
            f'{ce(CUSTOM_EMOJI["profile_setup"], "⚙️")} <b>პროფილის დაყენება</b>\n\n'
            f"სისტემაში შესასვლელად, გთხოვთ აირჩიოთ თქვენი როლი:"
        ),
        "enter_login": (
            f'{ce(CUSTOM_EMOJI["credentials"], "🔑")} შეიყვანეთ თქვენი <b>ლოგინი</b> '
            f"პირადი კაბინეტიდან (/partners):"
        ),
        "enter_password": (
            f'{ce(CUSTOM_EMOJI["credentials"], "🔒")} ახლა შეიყვანეთ თქვენი <b>პაროლი</b>:'
        ),
        "checking_data": "⏳ მონაცემების შემოწმება...",
        "auth_success_rest": (
            f'{ce(CUSTOM_EMOJI["success"], "✅")} მზადაა! <b>{{rest_name}}</b> '
            f"დაკავშირებულია MestiDelivery-სთან"
        ),
        "auth_success_courier": (
            f'{ce("5384244502040975393", "✅")} მზადაა! თქვენ ავტორიზებული ხართ როგორც MestiDelivery კურიერი'
        ),
        "auth_fail": "❌ <b>არასწორი ლოგინი ან პაროლი</b>. გთხოვთ შეამოწმოთ მონაცემები და ხელახლა შეიყვანოთ ლოგინი.",
        "role_courier": "კურიერი",
        "role_rest": "რესტორატორი",
        "menu_history": "📜 შეკვეთების ისტორია",
        "menu_profile": "პროფილი",
        "menu_orders": "შეკვეთები",
        "menu_menu": "მენიუ",
        "menu_shifts": "ცვლები",
        "menu_income": "სტატისტიკა",
        "menu_support": "მხარდაჭერა",
        "menu_courier_online": "ხაზიდან გამოსვლა",
        "menu_courier_offline": "ხაზზე გასვლა",
        "status_online_now": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} თქვენ ხაზზე ხართ! ახლა მიიღებთ შეკვეთებს.'
        ),
        "status_offline_now": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} თქვენ ხაზგარეშე ხართ. შეკვეთებს არ მიიღებთ.'
        ),
        "courier_offline_alert": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} ხაზგარეშე. შეკვეთებს არ მიიღებთ.'
        ),
        "courier_online_alert": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} ხაზზე! შეკვეთები შემოვა.'
        ),
        "courier_line_status_offline": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} ხაზგარეშე. შეკვეთებს არ მიიღებთ.'
        ),
        "courier_line_status_online": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} ხაზზე! შეკვეთები შემოვა.'
        ),
    }
}

def get_text(lang: str, key: str, **kwargs) -> str:
    text = I18N.get(lang, I18N["ru"]).get(key, I18N["ru"][key])
    return text.format(**kwargs) if kwargs else text


def get_partner_dashboard_caption(lang: str, role: str = "") -> str:
    if role == "courier":
        if lang == "en":
            mid = (
                "Courier panel — get orders, track routes and stats right in Telegram."
            )
            welcome = f'{ce(CUSTOM_EMOJI["dashboard"], "🚀")} <b>Welcome!</b>'
            nav = f'{ce(CUSTOM_EMOJI["nav_hint"], "⚡")} Use the menu below to navigate:'
        elif lang == "ka":
            mid = (
                "კურიერის პანელი — მიიღეთ შეკვეთები, თვალყური ადევნეთ მარშრუტებს და სტატისტიკას პირდაპირ Telegram-ში."
            )
            welcome = f'{ce(CUSTOM_EMOJI["dashboard"], "🚀")} <b>კეთილი იყოს თქვენი მობრძანება!</b>'
            nav = f'{ce(CUSTOM_EMOJI["nav_hint"], "⚡")} ნავიგაციისთვის გამოიყენეთ ქვემოთ მოცემული მენიუ:'
        else:
            mid = (
                "Панель курьера — получайте заказы, отслеживайте маршруты и статистику прямо в Telegram."
            )
            welcome = f'{ce(CUSTOM_EMOJI["dashboard"], "🚀")} <b>Добро пожаловать!</b>'
            nav = f'{ce(CUSTOM_EMOJI["nav_hint"], "⚡")} Используйте меню ниже для навигации:'
        return f"{welcome}\n\n{mid}\n\n{nav}"

    if lang == "en":
        return (
            f'{ce(CUSTOM_EMOJI["dashboard"], "🚀")} <b>Welcome!</b>\n\n'
            f"Partner dashboard — manage your restaurant right from Telegram: "
            f"orders, menu, and stats in one click.\n\n"
            f'{ce(CUSTOM_EMOJI["nav_hint"], "⚡")} Use the menu below to navigate:'
        )
    if lang == "ka":
        return (
            f'{ce(CUSTOM_EMOJI["dashboard"], "🚀")} <b>კეთილი იყოს თქვენი მობრძანება!</b>\n\n'
            f"პარტნიორის პანელი — მართეთ რესტორანი პირდაპირ Telegram-იდან: "
            f"შეკვეთები, მენიუ და სტატისტიკა ერთი დაწკაპუნებით.\n\n"
            f'{ce(CUSTOM_EMOJI["nav_hint"], "⚡")} ნავიგაციისთვის გამოიყენეთ ქვემოთ მოცემული მენიუ:'
        )
    return (
        f'{ce(CUSTOM_EMOJI["dashboard"], "🚀")} <b>Добро пожаловать!</b>\n\n'
        f"Панель партнёра — управляйте рестораном прямо из Telegram: "
        f"заказы, меню и статистика в один клик.\n\n"
        f'{ce(CUSTOM_EMOJI["nav_hint"], "⚡")} Используйте меню ниже для навигации:'
    )


class RegistrationFlow(StatesGroup):

    language = State()
    role = State()
    username = State()
    password = State()


class CancelFlowState(StatesGroup):
    waiting_for_reason = State()  # legacy; reject идёт через inline-callback'и


# order_id → метаданные отмены рестораном (чтобы /orders/cancel не перетёр «админом»)
_RESTAURANT_CANCEL_META: dict[int, dict] = {}
# Кэш полей баннера 5a на время веера → для замены на 7a у проигравших.
_COURIER_BROADCAST_FIELDS: dict[int, dict] = {}

# Причины отклонения рестораном: code → (label, предлагает_отложить)
REJECT_REASON_DEFS: dict[str, tuple[str, bool]] = {
    "ns": ("Нет продуктов", False),
    "kb": ("Завал на кухне", True),
    "lq": ("Большая очередь", True),
    "cl": ("Ресторан закрывается", False),
    "ot": ("Другая причина", False),
}

# Причины отказа курьера: code → (label, предлагает_напомнить_через_5_мин)
COURIER_REFUSE_REASON_DEFS: dict[str, tuple[str, bool]] = {
    "ao": ("На другом заказе", True),
    "far": ("Не по пути / далеко", False),
    "busy": ("Сейчас не могу", False),
    "ot": ("Другая причина", False),
}
COURIER_SNOOZE_MIN = 5
# (order_id, telegram_id) → asyncio.Task отложенного напоминания
_COURIER_SNOOZE_TASKS: dict[tuple[int, int], asyncio.Task] = {}
# order_id → последняя выбранная причина (для финализации после delay)
_COURIER_REFUSE_META: dict[int, dict] = {}


class ProfileEditState(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_photo = State()


class ProfileHoursState(StatesGroup):
    waiting_for_hours = State()


# chat_id -> message_id последнего носителя reply-клавиатуры курьера
_COURIER_REPLY_CARRIER: dict[int, int] = {}
# chat_id -> отложенный анонс «На линии / Не на линии» после /start или регистрации
_COURIER_LINE_STATUS_TASKS: dict[int, asyncio.Task] = {}
COURIER_LINE_STATUS_DELAY_SEC = 90  # 1.5 мин (в окне 1–2 мин)


def get_courier_reply_kb(lang: str, is_online: bool = False) -> ReplyKeyboardMarkup:
    """Reply-клавиатура курьера: статус линии (persistent). Только для courier."""
    text = get_text(lang, "menu_courier_online" if is_online else "menu_courier_offline")
    icon = (
        CUSTOM_EMOJI["close_restaurant"] if is_online else CUSTOM_EMOJI["open_restaurant"]
    )
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text, icon_custom_emoji_id=icon)]],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
    )


async def _place_courier_reply_kb(
    chat_id: int,
    lang: str,
    is_online: bool,
    text: str,
) -> None:
    """Шлёт носитель reply-клавиатуры и удаляет только ПРЕДЫДУЩИЙ носитель.

    Важно: само сообщение с reply_markup удалять нельзя — на мобильном
    Telegram вместе с ним пропадает нижняя кнопка.
    """
    kb = get_courier_reply_kb(lang, is_online)
    old_id = _COURIER_REPLY_CARRIER.get(chat_id)

    try:
        msg = await bot.send_message(
            chat_id,
            text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
            disable_notification=True,
        )
    except Exception as err:
        log.warning("_place_courier_reply_kb send failed: %s", err)
        return

    _COURIER_REPLY_CARRIER[chat_id] = msg.message_id

    if old_id and old_id != msg.message_id:
        try:
            await bot.delete_message(chat_id, old_id)
        except Exception:
            pass


async def set_courier_reply_kb(chat_id: int, lang: str, is_online: bool) -> None:
    """Статус линии одной строкой + reply-клавиатура (носитель остаётся)."""
    text = get_text(
        lang,
        "courier_online_alert" if is_online else "courier_offline_alert",
    )
    await _place_courier_reply_kb(chat_id, lang, is_online, text)


def cancel_scheduled_courier_line_status(chat_id: int) -> None:
    task = _COURIER_LINE_STATUS_TASKS.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


def schedule_courier_line_status(
    chat_id: int,
    lang: str,
    is_online: bool,
    *,
    delay_sec: int = COURIER_LINE_STATUS_DELAY_SEC,
) -> None:
    """После /start или регистрации: статус линии через delay_sec, не сразу."""
    cancel_scheduled_courier_line_status(chat_id)

    async def _job() -> None:
        try:
            await asyncio.sleep(delay_sec)
            user = await db.get_bot_user(chat_id) or {}
            online = user.get("is_online", 0) == 1 if user else is_online
            use_lang = user.get("language", lang) if user else lang
            await set_courier_reply_kb(chat_id, use_lang, online)
        except asyncio.CancelledError:
            return
        except Exception as err:
            log.warning("schedule_courier_line_status failed chat=%s: %s", chat_id, err)
        finally:
            _COURIER_LINE_STATUS_TASKS.pop(chat_id, None)

    _COURIER_LINE_STATUS_TASKS[chat_id] = asyncio.create_task(_job())


async def ensure_courier_reply_kb(
    chat_id: int,
    lang: str,
    is_online: bool,
    *,
    force: bool = False,
) -> None:
    """Гарантирует reply-кнопку. Без пустых «невидимых» сообщений.

    force=False — если носитель уже есть, ничего не шлём.
    force=True — перевешиваем (после welcome-фото с inline).
    """
    if not force and chat_id in _COURIER_REPLY_CARRIER:
        return
    await set_courier_reply_kb(chat_id, lang, is_online)


async def refresh_courier_reply_kb(chat_id: int, lang: str, is_online: bool) -> None:
    """Alias на ensure (раньше тут был send+delete пустышки — из‑за него баги)."""
    await ensure_courier_reply_kb(chat_id, lang, is_online, force=True)


async def send_courier_welcome(
    chat_id: int,
    *,
    partner_name: str,
    lang: str,
    is_online: bool,
    caption: str,
    set_reply_kb: bool = True,
    delay_line_status: bool = False,
):
    """Welcome курьера: баннер + inline-меню под caption (как раньше).

    delay_line_status=True (/start, регистрация): статус «На линии…» через
    COURIER_LINE_STATUS_DELAY_SEC; меню не трогаем.
    """
    inline = get_main_inline_kb(lang, role="courier")
    try:
        png = render_banner("welcome", {"partner_name": partner_name})
        photo = BufferedInputFile(png, filename="welcome.png")
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=inline,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        log.error("send_courier_welcome photo failed: %s — text fallback", e)
        msg = await bot.send_message(
            chat_id,
            caption or "—",
            reply_markup=inline,
            parse_mode=ParseMode.HTML,
        )

    if delay_line_status:
        # Кнопка линии: на регистрации уже стоит на «Готово!»;
        # анонс статуса — позже, без ломания inline-меню.
        schedule_courier_line_status(chat_id, lang, is_online)
    elif set_reply_kb:
        await ensure_courier_reply_kb(chat_id, lang, is_online, force=True)
    return msg


async def toggle_courier_line_status(tg_id: int, chat_id: int, user: dict) -> int:
    """Переключает online/offline курьера. Возвращает новый статус 0/1."""
    cancel_scheduled_courier_line_status(chat_id)
    is_online = user.get("is_online", 0)
    new_status = 1 if is_online == 0 else 0
    log.info(
        "Courier line toggle tg=%d chat=%d %d -> %d",
        tg_id,
        chat_id,
        is_online,
        new_status,
    )
    await db.set_courier_online_status(tg_id, new_status)
    action = "set_online" if new_status == 1 else "set_offline"
    await update_courier_online_backend(tg_id, action)
    lang = user.get("language", "ru")
    await set_courier_reply_kb(chat_id, lang, new_status == 1)
    return new_status


async def force_courier_online(tg_id: int, chat_id: int, user: dict) -> None:
    """Принудительно выводит курьера на линию (/line)."""
    cancel_scheduled_courier_line_status(chat_id)
    await db.set_courier_online_status(tg_id, 1)
    await update_courier_online_backend(tg_id, "set_online")
    lang = user.get("language", "ru")
    await set_courier_reply_kb(chat_id, lang, True)


async def ensure_no_reply_kb(chat_id: int) -> None:
    """Снимает reply-клавиатуру (для ресторатора и гостей)."""
    _COURIER_REPLY_CARRIER.pop(chat_id, None)
    await clear_reply_keyboard(chat_id)


async def clear_reply_keyboard(chat_id: int) -> None:
    """Убирает нижнюю reply-клавиатуру.

    Не оставляем в чате пустые пузыри: если удалить служебное сообщение
    не удалось — не шлём «невидимые» символы повторно.
    """
    tmp = None
    try:
        tmp = await bot.send_message(
            chat_id,
            "·",
            reply_markup=ReplyKeyboardRemove(),
            disable_notification=True,
        )
        await bot.delete_message(chat_id, tmp.message_id)
        return
    except Exception as err:
        if tmp is not None:
            try:
                await bot.delete_message(chat_id, tmp.message_id)
            except Exception:
                pass
        log.warning("clear_reply_keyboard failed: %s", err)


async def notify_admin_restaurant_status_request(
    *,
    partner_tg_id: int,
    partner_username: str,
    partner_name: str,
    restaurant_id: str,
    restaurant_name: str,
    want_open: bool,
) -> None:
    """Уведомляет главного админа о запросе открыть/закрыть ресторан."""
    action = "открыть" if want_open else "закрыть"
    action_en = "OPEN" if want_open else "CLOSE"
    uname = f"@{partner_username}" if partner_username else "—"
    text = (
        f"🔔 <b>Запрос партнёра: {action} ресторан</b>\n\n"
        f"🍽 <b>Ресторан:</b> {restaurant_name}\n"
        f"🆔 <code>{restaurant_id}</code>\n\n"
        f"👤 <b>Партнёр:</b> {partner_name} ({uname})\n"
        f"tg_id: <code>{partner_tg_id}</code>\n\n"
        f"Действие: <b>{action_en}</b>\n"
        f"<i>Каталог не менялся автоматически — сделайте вручную, если нужно.</i>"
    )
    try:
        await bot.send_message(ADMIN_TG_ID, text, parse_mode=ParseMode.HTML)
    except Exception as err:
        log.error("Failed to notify admin about restaurant status request: %s", err)


MINIAPP_URL = "https://t.me/MestiDelivery_Robot/partners"
MINIAPP_DIRECT_URL = os.getenv("MINIAPP_URL", "https://mestigo.opik.net").rstrip("/") + "/partners"
SUPPORT_BOT_URL = "https://t.me/MestigoSupport_Bot"

def get_main_inline_kb(lang: str, role: str = "") -> InlineKeyboardMarkup:
    """Генерирует инлайн-кнопки для главного меню под приветственным баннером."""
    if lang == "ru":
        lbl_profile  = "Профиль"
        lbl_orders   = "Заказы"
        lbl_history  = "📜 История"
        lbl_stats    = "Статистика"
        lbl_menu     = "Меню"
        lbl_schedule = "📅 График смен"
        lbl_support  = "Поддержка"
    elif lang == "en":
        lbl_profile  = "Profile"
        lbl_orders   = "Orders"
        lbl_history  = "📜 History"
        lbl_stats    = "Stats"
        lbl_menu     = "Menu"
        lbl_schedule = "📅 Schedule"
        lbl_support  = "Support"
    else:
        lbl_profile  = "პროფილი"
        lbl_orders   = "შეკვეთები"
        lbl_history  = "📜 ისტორია"
        lbl_stats    = "სტატისტიკა"
        lbl_menu     = "მენიუ"
        lbl_schedule = "📅 განრიგი"
        lbl_support  = "მხარდაჭერა"

    if role == "restaurant_admin":
        kb = [
            [
                InlineKeyboardButton(
                    text=lbl_profile,
                    icon_custom_emoji_id=CUSTOM_EMOJI["btn_profile"],
                    callback_data="nav_profile",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=lbl_orders,
                    icon_custom_emoji_id=CUSTOM_EMOJI["btn_orders"],
                    web_app=WebAppInfo(url=MINIAPP_DIRECT_URL),
                ),
                InlineKeyboardButton(
                    text=lbl_menu,
                    icon_custom_emoji_id=CUSTOM_EMOJI["btn_menu"],
                    web_app=WebAppInfo(url=MINIAPP_DIRECT_URL),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=lbl_stats,
                    icon_custom_emoji_id=CUSTOM_EMOJI["btn_stats"],
                    web_app=WebAppInfo(url=MINIAPP_DIRECT_URL),
                ),
                InlineKeyboardButton(
                    text=lbl_support,
                    icon_custom_emoji_id=CUSTOM_EMOJI["btn_support"],
                    url=SUPPORT_BOT_URL,
                ),
            ],
        ]
    else:
        # Курьер: Профиль (полная ширина) → Заказы+Смены → Статистика+Поддержка
        lbl_shifts = get_text(lang, "menu_shifts")
        kb = [
            [
                InlineKeyboardButton(
                    text=lbl_profile,
                    icon_custom_emoji_id="5381848533060067195",
                    callback_data="nav_profile",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=lbl_orders,
                    icon_custom_emoji_id="5384138412053796842",
                    web_app=WebAppInfo(url=MINIAPP_DIRECT_URL),
                ),
                InlineKeyboardButton(
                    text=lbl_shifts,
                    icon_custom_emoji_id="5384312315279612142",
                    web_app=WebAppInfo(url=MINIAPP_DIRECT_URL),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=lbl_stats,
                    icon_custom_emoji_id="5384518714227990146",
                    web_app=WebAppInfo(url=MINIAPP_DIRECT_URL),
                ),
                InlineKeyboardButton(
                    text=lbl_support,
                    icon_custom_emoji_id="5382097310450753507",
                    url=SUPPORT_BOT_URL,
                ),
            ],
        ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def send_banner_photo(
    chat_id,
    kind: str,
    fields: dict,
    *,
    keyboard=None,
    caption: str = "",
    parse_mode: str = ParseMode.HTML,
):
    """Рендерит баннер и шлёт фото с кнопками. При ошибке рендера — fallback на текст."""
    try:
        png = render_banner(kind, fields)
        photo = BufferedInputFile(png, filename=f"{kind}.png")
        return await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=keyboard,
            parse_mode=parse_mode,
        )
    except Exception as e:
        log.error("send_banner_photo(%s) failed: %s — fallback to text", kind, e)
        return await bot.send_message(
            chat_id=chat_id,
            text=caption or "—",
            reply_markup=keyboard,
            parse_mode=parse_mode,
        )

async def edit_banner_media(
    chat_id,
    message_id: int,
    kind: str,
    fields: dict,
    *,
    caption: str = "",
    keyboard=None,
    parse_mode: str = ParseMode.HTML,
):
    """Редактирует медиа-баннер в чате. При ошибке — fallback на caption / reply_markup.

    Returns True если удалось обновить сообщение (включая «not modified»),
    False если нужен resend.
    """
    try:
        png = render_banner(kind, fields)
        media = InputMediaPhoto(media=BufferedInputFile(png, filename=f"{kind}.png"), caption=caption, parse_mode=parse_mode)
        await bot.edit_message_media(
            chat_id=chat_id,
            message_id=message_id,
            media=media,
            reply_markup=keyboard,
        )
        return True
    except Exception as e:
        err_text = str(e)
        if "message is not modified" in err_text.lower():
            # Содержимое то же — дожимаем кнопки отдельно, если переданы.
            if keyboard is not None:
                try:
                    await bot.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=keyboard,
                    )
                except Exception:
                    pass
            return True
        log.error("edit_banner_media(%s) failed: %s", kind, e)
        try:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode=parse_mode,
            )
            return True
        except Exception:
            pass
        if keyboard is not None:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=keyboard,
                )
                return True
            except Exception:
                pass
        return False


def get_language_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Русский",
                    icon_custom_emoji_id=CUSTOM_EMOJI["flag_ru"],
                    callback_data="lang_ru",
                ),
                InlineKeyboardButton(
                    text="English",
                    icon_custom_emoji_id=CUSTOM_EMOJI["flag_en"],
                    callback_data="lang_en",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="ქართული",
                    icon_custom_emoji_id=CUSTOM_EMOJI["flag_ka"],
                    callback_data="lang_ka",
                ),
            ],
        ]
    )

def get_role_kb(lang: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text(lang, "role_courier"),
                    icon_custom_emoji_id=CUSTOM_EMOJI["courier"],
                    callback_data="role_courier",
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text(lang, "role_rest"),
                    icon_custom_emoji_id=CUSTOM_EMOJI["restaurateur"],
                    callback_data="role_restaurant_admin",
                )
            ],
        ]
    )

# ─────────────────────────────────────────────
#  Панель администратора — см. admin_panel.py
#  (выплаты суперадмина остаются ниже)
# ─────────────────────────────────────────────


# ── Панель управления выплатами (Суперадмины) ──
async def send_admin_payout_request(chat_id: int, message_id: Optional[int], index: int):
    reqs = await db.get_pending_payout_requests()
    if not reqs:
        text = "🏖️ <b>Нет активных заявок на выплату.</b>"
        if message_id:
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=None, parse_mode=ParseMode.HTML)
            except Exception:
                pass
        else:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        return

    if index < 0:
        index = 0
    if index >= len(reqs):
        index = len(reqs) - 1
        
    req = reqs[index]
    req_id = req["id"]
    partner_id = req["partner_id"]
    role = req["role"]
    amount = req["amount"]
    created_at = req["created_at"]
    
    partner_name = partner_id
    if role == "restaurant_admin":
        for path in CATALOG_DB_PATHS:
            try:
                if not os.path.exists(path):
                    continue
                conn = connect_sqlite_wal(path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM restaurants WHERE id = ?", (partner_id,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    partner_name = f"{row[0]} ({partner_id})"
                    break
            except Exception:
                pass
    else:
        try:
            tg_user = await db.get_bot_user(int(partner_id))
            if tg_user:
                partner_name = f"Курьер {tg_user.get('backend_username') or 'Courier'} (tg: {partner_id})"
        except Exception:
            pass

    text = (
        f"💳 <b>Заявка на выплату #{req_id}</b> ({index + 1} из {len(reqs)})\n\n"
        f"👤 <b>Партнёр:</b> {partner_name}\n"
        f"🎭 <b>Роль:</b> {role}\n"
        f"💰 <b>Сумма:</b> {amount:.2f} ₾\n"
        f"📅 <b>Создана:</b> {created_at}"
    )
    
    kb_list = [
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_payout_approve_{req_id}_{index}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_payout_reject_{req_id}_{index}"),
        ]
    ]
    
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"admin_payout_view_{index - 1}"))
    if index < len(reqs) - 1:
        nav_row.append(InlineKeyboardButton(text="След. ➡️", callback_data=f"admin_payout_view_{index + 1}"))
        
    if nav_row:
        kb_list.append(nav_row)
        
    kb = InlineKeyboardMarkup(inline_keyboard=kb_list)
    
    if message_id:
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            pass
    else:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.message(Command("payouts"))
async def cmd_payouts(message: Message):
    is_admin = (message.from_user.id == ADMIN_TG_ID) or (await db.is_super_admin(message.from_user.id))
    if not is_admin:
        return
    await send_admin_payout_request(message.chat.id, None, 0)


@router.callback_query(F.data.startswith("admin_payout_view_"))
async def admin_payout_view_callback(callback: CallbackQuery):
    is_admin = (callback.from_user.id == ADMIN_TG_ID) or (await db.is_super_admin(callback.from_user.id))
    if not is_admin:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    index = int(callback.data.split("_")[3])
    await callback.answer()
    await send_admin_payout_request(callback.message.chat.id, callback.message.message_id, index)


@router.callback_query(F.data.startswith("admin_payout_approve_"))
async def admin_payout_approve_callback(callback: CallbackQuery):
    is_admin = (callback.from_user.id == ADMIN_TG_ID) or (await db.is_super_admin(callback.from_user.id))
    if not is_admin:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
        
    parts = callback.data.split("_")
    req_id = int(parts[3])
    index = int(parts[4])
    
    req = await db.get_payout_request_by_id(req_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
        
    success = await db.approve_payout_request(req_id)
    if success:
        await callback.answer(f"Заявка #{req_id} успешно одобрена!", show_alert=True)
        
        partner_id = req["partner_id"]
        role = req["role"]
        amount = req["amount"]
        
        partner_chat_id = None
        if role == "restaurant_admin":
            async with db._db.execute("SELECT telegram_id FROM partners WHERE restaurant_id = ?", (partner_id,)) as cur:
                row = await cur.fetchone()
                if row:
                    partner_chat_id = row[0]
        else:
            partner_chat_id = int(partner_id)
            
        if partner_chat_id:
            try:
                tg_user = await db.get_bot_user(partner_chat_id) or {}
                lang = tg_user.get("language", "ru")
                
                if lang == "ru":
                    notif = f"🔔 <b>Ваша заявка на выплату {amount:.2f} ₾ одобрена!</b>\nСредства отправлены и будут зачислены в ближайшее время."
                elif lang == "en":
                    notif = f"🔔 <b>Your payout request for {amount:.2f} ₾ has been approved!</b>\nFunds have been sent and will be credited shortly."
                else:
                    notif = f"🔔 <b>თანხის გატანის მოთხოვნა {amount:.2f} ₾-ზე დამტკიცებულია!</b>\nთანხა გაგზავნილია და ჩაირიცხება უახლოეს დროში."
                    
                await bot.send_message(chat_id=partner_chat_id, text=notif, parse_mode=ParseMode.HTML)
            except Exception as e:
                log.warning(f"Failed sending payout approval notification to {partner_chat_id}: {e}")
                
        await send_admin_payout_request(callback.message.chat.id, callback.message.message_id, index)
    else:
        await callback.answer("Ошибка при одобрении заявки", show_alert=True)


@router.callback_query(F.data.startswith("admin_payout_reject_"))
async def admin_payout_reject_callback(callback: CallbackQuery):
    is_admin = (callback.from_user.id == ADMIN_TG_ID) or (await db.is_super_admin(callback.from_user.id))
    if not is_admin:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
        
    parts = callback.data.split("_")
    req_id = int(parts[3])
    index = int(parts[4])
    
    req = await db.get_payout_request_by_id(req_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
        
    success = await db.reject_payout_request(req_id)
    if success:
        await callback.answer(f"Заявка #{req_id} отклонена.", show_alert=True)
        
        partner_id = req["partner_id"]
        role = req["role"]
        amount = req["amount"]
        
        partner_chat_id = None
        if role == "restaurant_admin":
            async with db._db.execute("SELECT telegram_id FROM partners WHERE restaurant_id = ?", (partner_id,)) as cur:
                row = await cur.fetchone()
                if row:
                    partner_chat_id = row[0]
        else:
            partner_chat_id = int(partner_id)
            
        if partner_chat_id:
            try:
                tg_user = await db.get_bot_user(partner_chat_id) or {}
                lang = tg_user.get("language", "ru")
                
                if lang == "ru":
                    notif = f"⚠️ <b>Ваша заявка на выплату {amount:.2f} ₾ была отклонена администратором.</b>\nПожалуйста, обратитесь в поддержку для уточнения деталей."
                elif lang == "en":
                    notif = f"⚠️ <b>Your payout request for {amount:.2f} ₾ has been rejected by admin.</b>\nPlease contact support for more details."
                else:
                    notif = f"⚠️ <b>თანხის გატანის მოთხოვნა {amount:.2f} ₾-ზე უარყოფილია ადმინისტრატორის მიერ.</b>\nდეტალებისთვის გთხოვთ მიმართოთ მხარდაჭერას."
                    
                await bot.send_message(chat_id=partner_chat_id, text=notif, parse_mode=ParseMode.HTML)
            except Exception as e:
                log.warning(f"Failed sending payout rejection notification to {partner_chat_id}: {e}")
                
        await send_admin_payout_request(callback.message.chat.id, callback.message.message_id, index)
    else:
        await callback.answer("Ошибка при отклонении заявки", show_alert=True)


@router.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    async with aiosqlite.connect(db.path) as conn:
        await conn.execute("DELETE FROM bot_users WHERE telegram_id = ?", (telegram_id,))
        await conn.execute("DELETE FROM partners WHERE telegram_id = ?", (telegram_id,))
        await conn.commit()
        
    import sqlite3
    for path in BACKEND_DB_PATHS:
        try:
            if os.path.exists(path):
                conn = connect_sqlite_wal(path)
                cursor = conn.cursor()
                cursor.execute("UPDATE admin_users SET telegram_id = NULL WHERE telegram_id = ?", (str(telegram_id),))
                conn.commit()
                conn.close()
        except Exception as e:
            log.error(f"Error resetting auth.db for user {telegram_id}: {e}")
            
    await message.answer(
        f'{ce("5384244502040975393", "✨")} <b>Всё готово! Ваш профиль успешно сброшен.</b>\n\n'
        "Вы можете начать всё с чистого листа. Нажмите /start, чтобы зарегистрироваться заново.",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    first_name = message.from_user.first_name or message.from_user.username or "affiliate sxclipse"
    
    user = await db.get_bot_user(message.from_user.id)
    if user:
        lang = user["language"]
        role = user["role"]
        
        pname = message.from_user.first_name or "MestiDelivery"
        
        if role == "restaurant_admin":
            partner = await db.get_partner_by_telegram(message.from_user.id)
            if partner and partner.get("restaurant_name"):
                pname = partner["restaurant_name"]
                
        caption = get_partner_dashboard_caption(lang, role=role)

        if role == "restaurant_admin":
            # Не шлём служебные сообщения ради ReplyKeyboardRemove —
            # у ресторатора reply-кнопки нет, пустые пузыри только бесили.
            await send_banner_photo(
                message.chat.id, "welcome",
                {"partner_name": pname},
                keyboard=get_main_inline_kb(lang, role=role),
                caption=caption,
            )
        else:
            # Курьер: reply-KB ставится через welcome-фото (без пустого пузыря),
            # статус линии на /start не анонсируем.
            is_online = user.get("is_online", 0) == 1
            await send_courier_welcome(
                message.chat.id,
                partner_name=pname,
                lang=lang,
                is_online=is_online,
                caption=caption,
                delay_line_status=True,
            )
        return

    lang = message.from_user.language_code or "ru"
    if lang not in I18N:
        lang = "ru"
    
    await message.answer(
        get_text(lang, "welcome", first_name=first_name),
        reply_markup=get_language_kb(),
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data.startswith("lang_"))
async def process_language(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    await state.update_data(language=lang)
    await callback.message.edit_text(
        get_text(lang, "choose_role"),
        reply_markup=get_role_kb(lang),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(RegistrationFlow.role)

@router.callback_query(RegistrationFlow.role, F.data.startswith("role_"))
async def process_role(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split("_", 1)[1]
    await state.update_data(role=role)
    data = await state.get_data()
    lang = data.get("language", "ru")
    await callback.message.edit_text(
        get_text(lang, "enter_login"),
        parse_mode=ParseMode.HTML
    )
    await state.update_data(login_prompt_id=callback.message.message_id)
    await state.set_state(RegistrationFlow.username)

@router.message(RegistrationFlow.username)
async def process_username(message: Message, state: FSMContext):
    username = message.text.strip()
    await state.update_data(username=username)
    data = await state.get_data()
    lang = data.get("language", "ru")
    msg = await message.answer(get_text(lang, "enter_password"), parse_mode=ParseMode.HTML)
    await state.update_data(username_msg_id=message.message_id, password_prompt_id=msg.message_id)
    await state.set_state(RegistrationFlow.password)

@router.message(RegistrationFlow.password)
async def process_password(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    username = data.get("username")
    role = data.get("role")
    language = data.get("language")
    
    try:
        await message.delete()
    except Exception:
        pass

    import sqlite3
    import bcrypt
    
    auth_success = False
    backend_user_id = None
    restaurant_id = None
    tg_str = str(message.from_user.id)
    
    for path in BACKEND_DB_PATHS:
        try:
            if not os.path.exists(path):
                continue
            conn = connect_sqlite_wal(path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, password_hash, role, restaurant_id FROM admin_users WHERE username = ?",
                (username,),
            )
            row = cursor.fetchone()
            if row:
                hashed = row[1]
                if bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8")):
                    user_role = row[2]
                    if user_role == role or user_role == "super_admin":
                        backend_user_id = row[0]
                        restaurant_id = row[3]
                        auth_success = True
            conn.close()
        except Exception as e:
            log.error("Error checking auth.db at %s: %s", path, e)
            if "conn" in locals():
                try:
                    conn.close()
                except Exception:
                    pass

    # Gateway читает build/data/auth.db, логин часто матчится в data/auth.db —
    # пишем telegram_id во ВСЕ копии admin_users с этим username.
    if auth_success:
        for path in BACKEND_DB_PATHS:
            try:
                if not os.path.exists(path):
                    continue
                conn = connect_sqlite_wal(path)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE admin_users SET telegram_id = NULL WHERE telegram_id = ?",
                    (tg_str,),
                )
                cursor.execute(
                    "UPDATE admin_users SET telegram_id = ? WHERE username = ?",
                    (tg_str, username),
                )
                conn.commit()
                conn.close()
                log.info("Bound telegram_id=%s to username=%s in %s", tg_str, username, path)
            except Exception as e:
                log.error("Failed binding telegram in %s: %s", path, e)
    if auth_success:
        await db.save_bot_user(message.from_user.id, language, role, username)
        
        if role == "restaurant_admin" and restaurant_id:
            rest_name = restaurant_id
            for cpath in CATALOG_DB_PATHS:
                try:
                    if not os.path.exists(cpath):
                        continue
                    cconn = connect_sqlite_wal(cpath)
                    ccur = cconn.cursor()
                    ccur.execute("SELECT name FROM restaurants WHERE id = ?", (restaurant_id,))
                    r = ccur.fetchone()
                    if r:
                        rest_name = r[0]
                    cconn.close()
                except Exception:
                    pass
            await db.register_partner(message.from_user.id, restaurant_id, rest_name)
            
            success_text = get_text(language, "auth_success_rest", rest_name=rest_name)
            pname = rest_name
        else:
            success_text = get_text(language, "auth_success_courier")
            pname = message.from_user.first_name or "Courier"

        banner_caption = get_partner_dashboard_caption(language, role=role)

        if role == "restaurant_admin":
            await message.answer(
                success_text,
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardRemove(),
            )
            await send_banner_photo(
                message.chat.id, "welcome",
                {"partner_name": pname},
                keyboard=get_main_inline_kb(language, role=role),
                caption=banner_caption,
            )
            await ensure_no_reply_kb(message.chat.id)
        else:
            # Reply-кнопку вешаем на реальное сообщение авторизации — без пустого пузыря.
            await message.answer(
                success_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_courier_reply_kb(language, is_online=False),
            )
            await send_courier_welcome(
                message.chat.id,
                partner_name=pname,
                lang=language,
                is_online=False,
                caption=banner_caption,
                delay_line_status=True,
            )

        for mid in [data.get("login_prompt_id"), data.get("username_msg_id"), data.get("password_prompt_id")]:
            if mid:
                try:
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=mid)
                except Exception:
                    pass
        await state.clear()
    else:
        for mid in [data.get("login_prompt_id"), data.get("username_msg_id"), data.get("password_prompt_id")]:
            if mid:
                try:
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=mid)
                except Exception:
                    pass
        await message.answer(get_text(language, "auth_fail"), parse_mode=ParseMode.HTML)
        msg = await message.answer(get_text(language, "enter_login"), parse_mode=ParseMode.HTML)
        await state.update_data(login_prompt_id=msg.message_id)
        await state.set_state(RegistrationFlow.username)

@router.message(Command("help"))

async def cmd_help(message: Message):
    await message.answer(
        "📋 <b>Команды партнёрского бота</b>\n\n"
        "/start — приветствие\n"
        "/register &lt;ID&gt; — привязать ресторан к этому чату\n"
        "/status — проверить статус подключения\n"
        "/line — курьер: выйти на линию\n"
        "/offline — курьер: сойти с линии\n"
        "/help — эта справка\n\n"
        "📨 Как только поступит новый заказ, вы получите уведомление с кнопками:\n"
        "✅ <b>Принять</b> — начать приготовление\n"
        "❌ <b>Отклонить</b> — отменить заказ",
        parse_mode=ParseMode.HTML,
    )


def resolve_restaurant_and_user(input_str: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Разрешает введенную строку в (restaurant_id, restaurant_name, admin_username).
    Ищет по БД catalog.db и auth.db.
    """
    import sqlite3
    input_clean = input_str.strip().lower()
    
    # 1. Попробуем найти в catalog.db
    for path in CATALOG_DB_PATHS:
        try:
            conn = connect_sqlite_wal(path)
            cursor = conn.cursor()
            # Поиск по прямому совпадению ID
            cursor.execute("SELECT id, name FROM restaurants WHERE LOWER(id) = ?", (input_clean,))
            row = cursor.fetchone()
            if row:
                conn.close()
                return row[0], row[1], None
                
            # Поиск по совпадению имени
            cursor.execute("SELECT id, name FROM restaurants WHERE LOWER(name) = ?", (input_clean,))
            row = cursor.fetchone()
            if row:
                conn.close()
                return row[0], row[1], None

            # Поиск по подстроке имени (например "bbq" в "BBQ Garden")
            # Сначала очистим от "admin_"
            search_term = input_clean
            if search_term.startswith("admin_"):
                search_term = search_term[6:]
            elif search_term.startswith("admin"):
                search_term = search_term[5:]
                
            cursor.execute("SELECT id, name FROM restaurants WHERE LOWER(name) LIKE ? OR LOWER(id) LIKE ?", (f"%{search_term}%", f"%{search_term}%"))
            rows = cursor.fetchall()
            if len(rows) == 1:
                conn.close()
                return rows[0][0], rows[0][1], None
            elif len(rows) > 1:
                # Если совпадений несколько, выберем наиболее точное совпадение
                for r in rows:
                    if search_term in r[1].lower():
                        conn.close()
                        return r[0], r[1], None
            conn.close()
        except Exception as e:
            log.error("Error searching catalog.db at %s: %s", path, e)
            
    # 2. Попробуем найти в auth.db по имени пользователя (например admin2 или admin_bbq)
    for path in BACKEND_DB_PATHS:
        try:
            conn = connect_sqlite_wal(path)
            cursor = conn.cursor()
            cursor.execute("SELECT restaurant_id, username FROM admin_users WHERE LOWER(username) = ?", (input_clean,))
            row = cursor.fetchone()
            if row and row[0]:
                rest_id = row[0]
                conn.close()
                # Получим имя ресторана из каталога
                rest_name = rest_id
                for cpath in CATALOG_DB_PATHS:
                    try:
                        cconn = connect_sqlite_wal(cpath)
                        ccur = cconn.cursor()
                        ccur.execute("SELECT name FROM restaurants WHERE id = ?", (rest_id,))
                        r = ccur.fetchone()
                        if r:
                            rest_name = r[0]
                            cconn.close()
                            break
                        cconn.close()
                    except Exception:
                        pass
                return rest_id, rest_name, row[1]
            conn.close()
        except Exception as e:
            log.error("Error searching auth.db at %s: %s", path, e)
            
    return None, None, None


def sync_telegram_id_to_backend(restaurant_id: str, telegram_id: int, username: Optional[str] = None):
    """
    Записывает telegram_id в backend auth.db для пользователей с ролью restaurant_admin.
    Если пользователя нет, то создаёт его.
    """
    import sqlite3
    import datetime
    
    for path in BACKEND_DB_PATHS:
        try:
            conn = connect_sqlite_wal(path)
            cursor = conn.cursor()
            
            # Проверим, есть ли уже пользователь с таким restaurant_id и ролью restaurant_admin
            cursor.execute(
                "SELECT id, username FROM admin_users WHERE restaurant_id = ? AND role = ?", 
                (restaurant_id, "restaurant_admin")
            )
            row = cursor.fetchone()
            
            if row:
                # Обновим telegram_id
                cursor.execute(
                    "UPDATE admin_users SET telegram_id = ? WHERE id = ?", 
                    (str(telegram_id), row[0])
                )
                log.info("Updated telegram_id for user %s in %s", row[1], path)
            else:
                # Создаем нового пользователя
                new_username = username or f"admin_{restaurant_id.replace('rest-', '')}"
                now = datetime.datetime.utcnow().isoformat() + "Z"
                bcrypt_123 = "$2a$10$XZG9Bv0X7wB9.D5zR6UkeO18mXgJkEomz6jR1d0/LskfLwTjO87E."
                
                cursor.execute(
                    """INSERT INTO admin_users (username, password_hash, role, restaurant_id, telegram_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (new_username, bcrypt_123, "restaurant_admin", restaurant_id, str(telegram_id), now)
                )
                log.info("Created new restaurant_admin user %s for restaurant %s in %s", new_username, restaurant_id, path)
            
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("Failed to sync telegram_id to backend DB %s: %s", path, e)


@router.message(Command("register"))
async def cmd_register(message: Message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "❌ Укажите ID ресторана, его название или ваш логин администратора.\n"
            "Пример: <code>/register BBQ Garden</code> или <code>/register rest-1770828068354</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_input = parts[1].strip()
    telegram_id = message.from_user.id
    chat_id = message.chat.id  # Может быть группой

    # Интеллектуальный поиск ресторана
    rest_id, rest_name, admin_username = resolve_restaurant_and_user(raw_input)

    if not rest_id:
        await message.answer(
            f"❌ Не удалось найти ресторан или пользователя по запросу \"{raw_input}\".\n"
            "Пожалуйста, укажите точное ID ресторана, его имя из панели или ваш логин.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Регистрируем в локальной БД
    ok = await db.register_partner(
        telegram_id=chat_id,
        restaurant_id=rest_id,
        restaurant_name=rest_name or raw_input,
    )

    if ok:
        # Синхронизируем telegram_id с бэкендом
        sync_telegram_id_to_backend(rest_id, chat_id, admin_username)
        
        log.info(
            "Partner registered successfully: restaurant_id=%s telegram_id=%s (%s)",
            rest_id, chat_id, rest_name
        )
        await message.answer(
            f"✅ <b>Ресторан успешно привязан!</b>\n\n"
            f"🏪 Ресторан: <b>{rest_name}</b>\n"
            f"🆔 ID ресторана: <code>{rest_id}</code>\n"
            f"💬 Chat ID: <code>{chat_id}</code>\n\n"
            f"Бот успешно связал ваш Telegram-аккаунт с бэкендом MestiDelivery. "
            f"Теперь вы будете мгновенно получать новые заказы прямо в этот чат!",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(
            "❌ Произошла ошибка при сохранении регистрации. Пожалуйста, попробуйте ещё раз.",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("status"))
async def cmd_status(message: Message):
    partner = await db.get_partner_by_telegram(message.chat.id)
    if partner:
        await message.answer(
            f"✅ <b>Статус: подключён</b>\n\n"
            f"🏪 Ресторан: <b>{partner['restaurant_name'] or partner['restaurant_id']}</b>\n"
            f"🆔 ID ресторана: <code>{partner['restaurant_id']}</code>\n"
            f"📅 Зарегистрирован: {partner['registered_at']}",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(
            "❌ <b>Ресторан не подключён</b>\n\n"
            "Используйте <code>/register &lt;ID ресторана&gt;</code> для подключения.",
            parse_mode=ParseMode.HTML,
        )


_COURIER_STATUS_TEXTS = {
    # Текущие I18N (без unicode-эмодзи — иконка через icon_custom_emoji_id)
    "Сойти с линии", "Выйти на линию",
    "Go offline", "Go online",
    "ხაზიდან გამოსვლა", "ხაზზე გასვლა",
    # Legacy с эмодзи
    "🔴 Сойти с линии", "🔄 Выйти на линию",
    "🔴 Go offline", "🔄 Go online",
    "🔴 ხაზიდან გამოსვლა", "🔄 ხაზზე გასვლა",
    "🟢 Выйти на линию", "🔴 Уйти с линии", "🟢 Go online", "🟢 ხაზზე გასვლა",
}

# Старая reply-клавиатура ресторатора (хвосты) — только снимаем, не обрабатываем как команды
_LEGACY_RESTAURANT_REPLY_TEXTS = {
    "📜 История заказов", "👤 Профиль", "💰 Доход",
    "📜 Order History", "👤 Profile", "💰 Income", "📊 Stats", "📊 Статистика",
    "📜 შეკვეთების ისტორია", "👤 პროფილი", "💰 შემოსავალი",
}


@router.message(F.text.in_(_LEGACY_RESTAURANT_REPLY_TEXTS))
async def legacy_restaurant_reply_trap(message: Message):
    """Глушит старые reply-кнопки ресторатора и снимает клавиатуру."""
    tg = message.from_user.id
    user = await db.get_bot_user(tg) or {}
    role = user.get("role", "")
    lang = user.get("language", "ru")
    try:
        await message.delete()
    except Exception:
        pass
    if role == "courier":
        is_online = user.get("is_online", 0) == 1
        await set_courier_reply_kb(message.chat.id, lang, is_online)
        return
    await ensure_no_reply_kb(message.chat.id)


@router.message(F.text.in_(_COURIER_STATUS_TEXTS))
async def cmd_courier_status_toggle(message: Message):
    tg = message.from_user.id
    user = await db.get_bot_user(tg) or {}
    role = user.get("role", "")
    if role != "courier":
        return

    try:
        await message.delete()
    except Exception:
        pass

    await toggle_courier_line_status(tg, message.chat.id, user)


@router.message(Command("line", "online"))
async def cmd_line(message: Message):
    """Запасной вход на линию: /line или /online."""
    tg = message.from_user.id
    user = await db.get_bot_user(tg) or {}
    if user.get("role") != "courier":
        await message.answer("Команда только для курьеров.")
        return

    try:
        await message.delete()
    except Exception:
        pass

    if user.get("is_online", 0) == 1:
        await set_courier_reply_kb(message.chat.id, user.get("language", "ru"), True)
    else:
        await force_courier_online(tg, message.chat.id, user)


@router.message(Command("offline"))
async def cmd_offline(message: Message):
    """Снять с линии: /offline."""
    tg = message.from_user.id
    user = await db.get_bot_user(tg) or {}
    if user.get("role") != "courier":
        await message.answer("Команда только для курьеров.")
        return

    try:
        await message.delete()
    except Exception:
        pass

    cancel_scheduled_courier_line_status(message.chat.id)
    if user.get("is_online", 0) == 0:
        await set_courier_reply_kb(message.chat.id, user.get("language", "ru"), False)
        return

    await db.set_courier_online_status(tg, 0)
    await update_courier_online_backend(tg, "set_offline")
    await set_courier_reply_kb(message.chat.id, user.get("language", "ru"), False)

# ── Callback-кнопки ───────────────────────────

# ── Вспомогательные функции для профиля ──
def get_restaurant_profile_kb(is_open: bool, lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        toggle_text = "Close restaurant" if is_open else "Open restaurant"
        hours_text = "Working hours"
        payouts_text = "Payouts"
        back_text = "← Back"
    elif lang == "ka":
        toggle_text = "რესტორნის დახურვა" if is_open else "რესტორნის გახსნა"
        hours_text = "სამუშაო საათები"
        payouts_text = "გადახდები"
        back_text = "← უკან"
    else:
        toggle_text = "Закрыть ресторан" if is_open else "Открыть ресторан"
        hours_text = "Часы работы"
        payouts_text = "Выплаты"
        back_text = "← Назад"

    toggle_emoji = CUSTOM_EMOJI["close_restaurant"] if is_open else CUSTOM_EMOJI["open_restaurant"]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=toggle_text,
                    icon_custom_emoji_id=toggle_emoji,
                    callback_data="profile_toggle_status",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=hours_text,
                    icon_custom_emoji_id=CUSTOM_EMOJI["hours"],
                    callback_data="profile_hours",
                ),
                InlineKeyboardButton(
                    text=payouts_text,
                    icon_custom_emoji_id=CUSTOM_EMOJI["payouts"],
                    callback_data="profile_payouts",
                ),
            ],
            [
                InlineKeyboardButton(text=back_text, callback_data="profile_back"),
            ],
        ]
    )

def get_courier_profile_kb(is_online: bool) -> InlineKeyboardMarkup:
    toggle_text = "Вы на линии" if is_online else "Вы не на линии"
    toggle_icon = (
        CUSTOM_EMOJI["open_restaurant"] if is_online else CUSTOM_EMOJI["close_restaurant"]
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=toggle_text,
                    callback_data="profile_toggle_status",
                    icon_custom_emoji_id=toggle_icon,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Выплаты",
                    callback_data="profile_payouts",
                    icon_custom_emoji_id="5384518714227990146",
                ),
                InlineKeyboardButton(text="← Назад", callback_data="profile_back"),
            ],
        ]
    )

def parse_working_hours(hours_str: str) -> dict:
    try:
        if hours_str:
            return json.loads(hours_str)
    except Exception:
        pass
    return {
        "mon": "10:00-22:00",
        "tue": "10:00-22:00",
        "wed": "10:00-22:00",
        "thu": "10:00-22:00",
        "fri": "10:00-22:00",
        "sat": "10:00-22:00",
        "sun": "10:00-22:00",
    }

DAYS_MAP = {
    "mon": ("Пн", "Mon", "ორშ"),
    "tue": ("Вт", "Tue", "სამ"),
    "wed": ("Ср", "Wed", "ოთხ"),
    "thu": ("Чт", "Thu", "ხუთ"),
    "fri": ("Пт", "Fri", "პარ"),
    "sat": ("Сб", "Sat", "შაბ"),
    "sun": ("Вс", "Sun", "კვი"),
}

async def render_and_send_profile(chat_id: int, message_id: Optional[int], tg_id: int, user: dict):
    role = user.get("role", "")
    lang = user.get("language", "ru")

    if role == "restaurant_admin":
        partner = (
            await db.get_partner_by_telegram(chat_id)
            or await db.get_partner_by_telegram(tg_id)
            or {}
        )
        restaurant_id = partner.get("restaurant_id", "")
        name = partner.get("restaurant_name") or partner.get("restaurant_id") or "Restaurant"

        # UI open/close: локальный флаг партнёра (каталог меняет админ вручную)
        catalog_active, _ = await db.get_restaurant_status_and_hours(restaurant_id)
        ui_raw = partner.get("ui_is_open")
        if ui_raw is None:
            is_open = catalog_active == 1
        else:
            is_open = int(ui_raw) == 1

        today_income = await db.get_restaurant_today_income(restaurant_id)
        lifetime_income = await db.get_restaurant_lifetime_income(restaurant_id)
        total_payouts = await db.get_restaurant_payouts(restaurant_id)
        balance = max(0.0, lifetime_income - total_payouts)
        active_n = await db.get_restaurant_active_orders(restaurant_id)
        
        status_badge = "open" if is_open else "closed"
        
        if lang == "ru":
            cap = (
                f'{ce(CUSTOM_EMOJI["btn_profile"], "👤")} <b>Профиль ресторана</b>\n\n'
                f'{ce(CUSTOM_EMOJI["balance"], "💰")} <b>Баланс:</b> {balance:.2f} ₾\n'
                f'{ce(CUSTOM_EMOJI["income_today"], "📈")} <b>Доход сегодня:</b> {today_income:.2f} ₾'
            )
        elif lang == "en":
            cap = (
                f'{ce(CUSTOM_EMOJI["btn_profile"], "👤")} <b>Restaurant Profile</b>\n\n'
                f'{ce(CUSTOM_EMOJI["balance"], "💰")} <b>Balance:</b> {balance:.2f} ₾\n'
                f'{ce(CUSTOM_EMOJI["income_today"], "📈")} <b>Income today:</b> {today_income:.2f} ₾'
            )
        else:
            cap = (
                f'{ce(CUSTOM_EMOJI["btn_profile"], "👤")} <b>რესტორნის პროფილი</b>\n\n'
                f'{ce(CUSTOM_EMOJI["balance"], "💰")} <b>ბალანსი:</b> {balance:.2f} ₾\n'
                f'{ce(CUSTOM_EMOJI["income_today"], "📈")} <b>დღევანდელი შემოსავალი:</b> {today_income:.2f} ₾'
            )
            
        kb = get_restaurant_profile_kb(is_open, lang)
        
        fields = {
            "restaurant_name": name,
            "rating": "4.9",
            "status_badge": status_badge,
            "active_orders": f"{active_n} active orders",
            "payout": f"₾ {int(round(balance)):,}",
        }
        
        if message_id:
            await edit_banner_media(
                chat_id=chat_id,
                message_id=message_id,
                kind="profile_restaurant",
                fields=fields,
                caption=cap,
                keyboard=kb,
            )
        else:
            await send_banner_photo(
                chat_id=chat_id,
                kind="profile_restaurant",
                fields=fields,
                caption=cap,
                keyboard=kb,
            )
            
    else:
        name = user.get("backend_username") or "Courier"
        courier_ids = await db.get_courier_ids_by_telegram(tg_id)
        
        today_income = 0.0
        lifetime_income = 0.0
        if courier_ids:
            today_income = await db.get_courier_today_income_multi(courier_ids)
            lifetime_income = await db.get_courier_lifetime_income_multi(courier_ids)
            
        total_payouts = await db.get_courier_payouts(tg_id)
        balance = max(0.0, lifetime_income - total_payouts)
        
        is_online = user.get("is_online", 0) == 1
        deliveries_n = 0
        if courier_ids:
            # Баланс = lifetime income − payouts; deliveries тоже lifetime,
            # иначе при доходе «не сегодня» было 0 deliveries и ₾ 69.
            deliveries_n = await db.get_courier_lifetime_deliveries_multi(courier_ids)

        if lang == "ru":
            cap = (
                f'{ce("5381848533060067195", "👤")} <b>Профиль курьера</b>\n\n'
                f'{ce("5384520939021048827", "💰")} <b>Баланс:</b> {balance:.2f} ₾\n'
                f'{ce("5382351125838077755", "📈")} <b>Доход сегодня:</b> {today_income:.2f} ₾'
            )
        elif lang == "en":
            cap = (
                f'{ce("5381848533060067195", "👤")} <b>Courier Profile</b>\n\n'
                f'{ce("5384520939021048827", "💰")} <b>Balance:</b> {balance:.2f} ₾\n'
                f'{ce("5382351125838077755", "📈")} <b>Income today:</b> {today_income:.2f} ₾'
            )
        else:
            cap = (
                f'{ce("5381848533060067195", "👤")} <b>კურიერის პროფილი</b>\n\n'
                f'{ce("5384520939021048827", "💰")} <b>ბალანსი:</b> {balance:.2f} ₾\n'
                f'{ce("5382351125838077755", "📈")} <b>დღევანდელი შემოსავალი:</b> {today_income:.2f} ₾'
            )
            
        kb = get_courier_profile_kb(is_online)
        
        fields = {
            "courier_name": name,
            "rating": "5.0",
            # ON LINE запечён в Banner-6a — всегда ONLINE визуально.
            "status_badge": "online",
            "deliveries_count": f"{deliveries_n} deliveries",
            "earnings": f"₾ {int(round(balance)):,}",
        }
        
        if message_id:
            await edit_banner_media(
                chat_id=chat_id,
                message_id=message_id,
                kind="profile_courier",
                fields=fields,
                caption=cap,
                keyboard=kb,
            )
        else:
            await send_banner_photo(
                chat_id=chat_id,
                kind="profile_courier",
                fields=fields,
                caption=cap,
                keyboard=kb,
            )

async def render_payouts_screen(chat_id: int, message_id: int, tg_id: int, user: dict):
    role = user.get("role", "")
    lang = user.get("language", "ru")
    
    partner_id = ""
    if role == "restaurant_admin":
        partner = (
            await db.get_partner_by_telegram(chat_id)
            or await db.get_partner_by_telegram(tg_id)
            or {}
        )
        partner_id = partner.get("restaurant_id", "")
        lifetime_income = await db.get_restaurant_lifetime_income(partner_id)
        total_payouts = await db.get_restaurant_payouts(partner_id)
    else:
        partner_id = str(tg_id)
        courier_ids = await db.get_courier_ids_by_telegram(tg_id)
        lifetime_income = 0.0
        if courier_ids:
            lifetime_income = await db.get_courier_lifetime_income_multi(courier_ids)
        total_payouts = await db.get_courier_payouts(tg_id)
        
    balance = max(0.0, lifetime_income - total_payouts)
    
    last_payout = await db.get_last_payout(partner_id, role)
    if last_payout:
        date_str = last_payout["created_at"].split()[0]
        last_payout_text = f"{last_payout['amount']:.2f} ₾ ({date_str}) ✅"
    else:
        last_payout_text = "нет" if lang == "ru" else ("none" if lang == "en" else "არა")
        
    if lang == "ru":
        text = (
            f'{ce(CUSTOM_EMOJI["payouts"], "💳")} <b>Выплаты</b>\n\n'
            f'{ce(CUSTOM_EMOJI["balance"], "💰")} <b>Доступно к выводу:</b> {balance:.2f} ₾\n'
            f'{ce(CUSTOM_EMOJI["hours"], "🕒")} <b>Последняя выплата:</b> {last_payout_text}'
        )
        btn_request = "💸 Запросить выплату"
        btn_back = "← Назад"
    elif lang == "en":
        text = (
            f'{ce(CUSTOM_EMOJI["payouts"], "💳")} <b>Payouts</b>\n\n'
            f'{ce(CUSTOM_EMOJI["balance"], "💰")} <b>Available for withdrawal:</b> {balance:.2f} ₾\n'
            f'{ce(CUSTOM_EMOJI["hours"], "🕒")} <b>Last payout:</b> {last_payout_text}'
        )
        btn_request = "💸 Request payout"
        btn_back = "← Back"
    else:
        text = (
            f'{ce(CUSTOM_EMOJI["payouts"], "💳")} <b>გადახდები</b>\n\n'
            f'{ce(CUSTOM_EMOJI["balance"], "💰")} <b>გასატანად ხელმისაწვდომია:</b> {balance:.2f} ₾\n'
            f'{ce(CUSTOM_EMOJI["hours"], "🕒")} <b>ბოლო გადახდა:</b> {last_payout_text}'
        )
        btn_request = "💸 თანხის გატანის მოთხოვნა"
        btn_back = "← უკან"
        
    buttons = []
    if balance > 0:
        buttons.append([InlineKeyboardButton(text=btn_request, callback_data="payout_request_action")])
    buttons.append([InlineKeyboardButton(text=btn_back, callback_data="payout_back_to_profile")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    except Exception as err:
        log.error(f"Error rendering payouts screen: {err}")

async def render_hours_screen(chat_id: int, message_id: int, tg_id: int, user: dict):
    lang = user.get("language", "ru")
    
    partner = (
        await db.get_partner_by_telegram(chat_id)
        or await db.get_partner_by_telegram(tg_id)
        or {}
    )
    restaurant_id = partner.get("restaurant_id", "")
    _, working_hours_str = await db.get_restaurant_status_and_hours(restaurant_id)
    hours = parse_working_hours(working_hours_str)
    
    if lang == "ru":
        text = (
            f'{ce(CUSTOM_EMOJI["hours"], "⏰")} <b>Часы работы</b>\n'
            f"Выберите день недели для настройки рабочих часов:"
        )
        btn_back = "← Назад"
    elif lang == "en":
        text = (
            f'{ce(CUSTOM_EMOJI["hours"], "⏰")} <b>Working Hours</b>\n'
            f"Select a day of the week to set working hours:"
        )
        btn_back = "← Back"
    else:
        text = (
            f'{ce(CUSTOM_EMOJI["hours"], "⏰")} <b>სამუშაო საათები</b>\n'
            f"აირჩიეთ კვირის დღე სამუშაო საათების დასაყენებლად:"
        )
        btn_back = "← უკან"
        
    kb_list = []
    row = []
    lang_idx = 0 if lang == "ru" else (1 if lang == "en" else 2)
    
    for key, names in DAYS_MAP.items():
        day_name = names[lang_idx]
        day_val = hours.get(key, "10:00-22:00")
        button_text = f"{day_name}: {day_val}"
        
        row.append(InlineKeyboardButton(text=button_text, callback_data=f"hours_day_{key}"))
        if len(row) == 2:
            kb_list.append(row)
            row = []
            
    if row:
        kb_list.append(row)
        
    kb_list.append([InlineKeyboardButton(text=btn_back, callback_data="hours_back_to_profile")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=kb_list)
    
    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    except Exception as err:
        log.error(f"Error rendering hours screen: {err}")

async def render_edit_profile_menu(chat_id: int, message_id: int, tg_id: int, user: dict):
    lang = user.get("language", "ru")
    
    if lang == "ru":
        text = "✏️ <b>Редактирование профиля</b>\nВыберите, какое поле вы хотите изменить:"
        btn_name = "📝 Название"
        btn_desc = "📋 Описание"
        btn_photo = "🖼️ Фото"
        btn_back = "← Назад"
    elif lang == "en":
        text = "✏️ <b>Edit Profile</b>\nChoose which field you want to change:"
        btn_name = "📝 Name"
        btn_desc = "📋 Description"
        btn_photo = "🖼️ Photo"
        btn_back = "← Back"
    else:
        text = "✏️ <b>პროფილის რედაქტირება</b>\nაირჩიეთ ველი, რომლის შეცვლაც გსურთ:"
        btn_name = "📝 სახელი"
        btn_desc = "📋 აღწერა"
        btn_photo = "🖼️ ფოტო"
        btn_back = "← უკან"
        
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=btn_name, callback_data="edit_field_name"),
                InlineKeyboardButton(text=btn_desc, callback_data="edit_field_desc"),
            ],
            [
                InlineKeyboardButton(text=btn_photo, callback_data="edit_field_photo"),
            ],
            [
                InlineKeyboardButton(text=btn_back, callback_data="edit_back_to_profile"),
            ]
        ]
    )
    
    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        log.error(f"Error rendering edit profile menu: {e}")


@router.callback_query(F.data == "nav_profile")
async def nav_profile(callback: CallbackQuery):
    """Show profile banner when user taps Profile button."""
    await callback.answer()
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    await render_and_send_profile(callback.message.chat.id, callback.message.message_id, tg, user)

@router.callback_query(F.data == "profile_toggle_status")
async def profile_toggle_status(callback: CallbackQuery):
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    role = user.get("role", "")
    lang = user.get("language", "ru")
    
    if role == "restaurant_admin":
        partner = (
            await db.get_partner_by_telegram(callback.message.chat.id)
            or await db.get_partner_by_telegram(tg)
            or {}
        )
        restaurant_id = partner.get("restaurant_id", "")
        if not restaurant_id:
            await callback.answer("Ресторан не найден", show_alert=True)
            return

        catalog_active, _ = await db.get_restaurant_status_and_hours(restaurant_id)
        ui_raw = partner.get("ui_is_open")
        current_open = catalog_active == 1 if ui_raw is None else int(ui_raw) == 1
        new_open = not current_open

        ok = await db.set_partner_ui_open(restaurant_id, 1 if new_open else 0)
        if not ok:
            await callback.answer("Не удалось обновить статус. Попробуйте ещё раз.", show_alert=True)
            return

        rest_name = partner.get("restaurant_name") or restaurant_id
        partner_name = (
            callback.from_user.full_name
            or callback.from_user.first_name
            or user.get("backend_username")
            or str(tg)
        )
        partner_username = callback.from_user.username or ""

        await notify_admin_restaurant_status_request(
            partner_tg_id=tg,
            partner_username=partner_username,
            partner_name=partner_name,
            restaurant_id=restaurant_id,
            restaurant_name=rest_name,
            want_open=new_open,
        )

        if new_open:
            if lang == "ru":
                alert_text = "Ресторан открыт"
            elif lang == "en":
                alert_text = "Restaurant is open"
            else:
                alert_text = "რესტორანი ღიაა"
        else:
            if lang == "ru":
                alert_text = "Ресторан закрыт"
            elif lang == "en":
                alert_text = "Restaurant is closed"
            else:
                alert_text = "რესტორანი დაკეტილია"

        await callback.answer(alert_text, show_alert=True)
        await render_and_send_profile(callback.message.chat.id, callback.message.message_id, tg, user)
            
    else:
        is_online = user.get("is_online", 0) == 1
        new_status = 0 if is_online else 1
        
        await db.set_courier_online_status(tg, new_status)
        action = "set_online" if new_status == 1 else "set_offline"
        await update_courier_online_backend(tg, action)
        
        if new_status == 1:
            alert_text = get_text(lang, "courier_online_alert")
        else:
            alert_text = get_text(lang, "courier_offline_alert")
        # Без popup — статус одной строкой в чате (edit/replace одного сообщения).
        await callback.answer()
        
        user["is_online"] = new_status
        await render_and_send_profile(callback.message.chat.id, callback.message.message_id, tg, user)
        cancel_scheduled_courier_line_status(callback.message.chat.id)
        await set_courier_reply_kb(callback.message.chat.id, lang, new_status == 1)

@router.callback_query(F.data == "profile_back")
async def profile_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    role = user.get("role", "")
    language = user.get("language", "ru")
    
    pname = ""
    if role == "restaurant_admin":
        partner = (
            await db.get_partner_by_telegram(callback.message.chat.id)
            or await db.get_partner_by_telegram(tg)
            or {}
        )
        pname = partner.get("restaurant_name") or partner.get("restaurant_id") or "Restaurant"
    else:
        pname = callback.from_user.first_name or "Courier"

    banner_caption = get_partner_dashboard_caption(language, role=role)
    main_kb = get_main_inline_kb(language, role=role)

    ok = await edit_banner_media(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        kind="welcome",
        fields={"partner_name": pname},
        keyboard=main_kb,
        caption=banner_caption,
    )
    if not ok:
        # Edit не прошёл — шлём свежий баннер с меню, чтобы кнопки не «терялись».
        log.warning("profile_back edit failed chat=%s — resending welcome", callback.message.chat.id)
        if role == "courier":
            is_online = user.get("is_online", 0) == 1
            await send_courier_welcome(
                callback.message.chat.id,
                partner_name=pname,
                lang=language,
                is_online=is_online,
                caption=banner_caption,
                set_reply_kb=True,
            )
        else:
            await send_banner_photo(
                callback.message.chat.id,
                "welcome",
                {"partner_name": pname},
                keyboard=main_kb,
                caption=banner_caption,
            )
    if role == "courier":
        # Не спамим лишним сообщением, если носитель reply-KB уже есть.
        is_online = user.get("is_online", 0) == 1
        await ensure_courier_reply_kb(
            callback.message.chat.id, language, is_online, force=False
        )
    else:
        await ensure_no_reply_kb(callback.message.chat.id)

@router.callback_query(F.data == "profile_payouts")
async def profile_payouts(callback: CallbackQuery):
    await callback.answer()
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    await render_payouts_screen(callback.message.chat.id, callback.message.message_id, tg, user)

@router.callback_query(F.data == "payout_back_to_profile")
async def payout_back_to_profile(callback: CallbackQuery):
    await callback.answer()
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    await render_and_send_profile(callback.message.chat.id, callback.message.message_id, tg, user)

@router.callback_query(F.data == "payout_request_action")
async def payout_request_action(callback: CallbackQuery):
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    role = user.get("role", "")
    lang = user.get("language", "ru")
    
    partner_id = ""
    if role == "restaurant_admin":
        partner = (
            await db.get_partner_by_telegram(callback.message.chat.id)
            or await db.get_partner_by_telegram(tg)
            or {}
        )
        partner_id = partner.get("restaurant_id", "")
        lifetime_income = await db.get_restaurant_lifetime_income(partner_id)
        total_payouts = await db.get_restaurant_payouts(partner_id)
    else:
        partner_id = str(tg)
        courier_ids = await db.get_courier_ids_by_telegram(tg)
        lifetime_income = 0.0
        if courier_ids:
            lifetime_income = await db.get_courier_lifetime_income_multi(courier_ids)
        total_payouts = await db.get_courier_payouts(tg)
        
    balance = max(0.0, lifetime_income - total_payouts)
    
    if balance <= 0:
        await callback.answer("Ошибка: баланс равен 0", show_alert=True)
        return
        
    success = await db.create_payout_request(partner_id, role, balance)
    if success:
        if lang == "ru":
            msg = f"✅ Заявка на {balance:.2f} ₾ отправлена. Мы обработаем её в ближайшее время."
        elif lang == "en":
            msg = f"✅ Request for {balance:.2f} ₾ sent. We will process it shortly."
        else:
            msg = f"✅ მოთხოვნა {balance:.2f} ₾-ზე გაგზავნილია. ჩვენ მას უახლოეს დროში დავამუშავებთ."
            
        await callback.answer(msg, show_alert=True)
        await render_payouts_screen(callback.message.chat.id, callback.message.message_id, tg, user)
    else:
        await callback.answer("Error processing request", show_alert=True)

@router.callback_query(F.data == "profile_hours")
async def profile_hours(callback: CallbackQuery):
    await callback.answer()
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    await render_hours_screen(callback.message.chat.id, callback.message.message_id, tg, user)

@router.callback_query(F.data == "hours_back_to_profile")
async def hours_back_to_profile(callback: CallbackQuery):
    await callback.answer()
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    await render_and_send_profile(callback.message.chat.id, callback.message.message_id, tg, user)

@router.callback_query(F.data.startswith("hours_day_"))
async def hours_day_select(callback: CallbackQuery, state: FSMContext):
    day_key = callback.data.split("_", 2)[2]
    await callback.answer()
    
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    lang = user.get("language", "ru")
    
    partner = (
        await db.get_partner_by_telegram(callback.message.chat.id)
        or await db.get_partner_by_telegram(tg)
        or {}
    )
    restaurant_id = partner.get("restaurant_id", "")
    
    await state.set_state(ProfileHoursState.waiting_for_hours)
    await state.update_data(
        day_key=day_key,
        restaurant_id=restaurant_id,
        profile_msg_id=callback.message.message_id
    )
    
    day_names = DAYS_MAP[day_key]
    day_name = day_names[0] if lang == "ru" else (day_names[1] if lang == "en" else day_names[2])
    
    if lang == "ru":
        prompt = (
            f'{ce(CUSTOM_EMOJI["hours"], "✏️")} <b>Настройка часов для {day_name}</b>\n\n'
            f"Отправьте новое время в формате <code>ЧЧ:ММ-ЧЧ:ММ</code> (например, <code>10:00-22:00</code>) "
            f"или напишите <code>выходной</code>:"
        )
    elif lang == "en":
        prompt = (
            f'{ce(CUSTOM_EMOJI["hours"], "✏️")} <b>Set hours for {day_name}</b>\n\n'
            f"Send new hours in format <code>HH:MM-HH:MM</code> (e.g. <code>10:00-22:00</code>) "
            f"or write <code>day off</code>:"
        )
    else:
        prompt = (
            f'{ce(CUSTOM_EMOJI["hours"], "✏️")} <b>საათების დაყენება {day_name}-სთვის</b>\n\n'
            f"გამოაგზავნეთ ახალი დრო ფორმატში <code>სს:წწ-სს:წწ</code> (მაგალითად, <code>10:00-22:00</code>) "
            f"ან დაწერეთ <code>დასვენება</code>:"
        )
        
    prompt_msg = await callback.message.reply(prompt, parse_mode=ParseMode.HTML)
    await state.update_data(prompt_msg_id=prompt_msg.message_id)

@router.message(ProfileHoursState.waiting_for_hours)
async def hours_input_handler(message: Message, state: FSMContext):
    import re
    data = await state.get_data()
    day_key = data.get("day_key")
    restaurant_id = data.get("restaurant_id")
    profile_msg_id = data.get("profile_msg_id")
    prompt_msg_id = data.get("prompt_msg_id")
    
    try:
        await message.delete()
    except Exception:
        pass
    if prompt_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception:
            pass
            
    val = message.text.strip().lower()
    
    is_valid = False
    time_match = re.match(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$", val)
    if time_match:
        is_valid = True
        normalized_val = val
    elif val in ["выходной", "выходной день", "day off", "off", "closed", "დასვენება", "დასვენების დღე"]:
        is_valid = True
        tg = message.from_user.id
        user = await db.get_bot_user(tg) or {}
        lang = user.get("language", "ru")
        normalized_val = "выходной" if lang == "ru" else ("day off" if lang == "en" else "დასვენება")
        
    tg = message.from_user.id
    user = await db.get_bot_user(tg) or {}
    lang = user.get("language", "ru")
    
    if not is_valid:
        err_text = "❌ Неверный формат! Пожалуйста, используйте формат ЧЧ:ММ-ЧЧ:ММ или 'выходной'." if lang == "ru" else (
            "❌ Invalid format! Please use HH:MM-HH:MM or 'day off'." if lang == "en" else "❌ არასწორი ფორმატი! გამოიყენეთ სს:წწ-სს:წწ ან 'დასვენება'."
        )
        err_msg = await message.answer(err_text)
        await asyncio.sleep(3.0)
        try:
            await err_msg.delete()
        except Exception:
            pass
        return
        
    _, working_hours_str = await db.get_restaurant_status_and_hours(restaurant_id)
    hours = parse_working_hours(working_hours_str)
    
    hours[day_key] = normalized_val
    await db.update_restaurant_hours(restaurant_id, json.dumps(hours, ensure_ascii=False))
    await state.clear()
    await render_hours_screen(message.chat.id, profile_msg_id, tg, user)

@router.callback_query(F.data == "profile_edit")
async def profile_edit(callback: CallbackQuery):
    await callback.answer()
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    await render_edit_profile_menu(callback.message.chat.id, callback.message.message_id, tg, user)

@router.callback_query(F.data == "edit_back_to_profile")
async def edit_back_to_profile(callback: CallbackQuery):
    await callback.answer()
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    await render_and_send_profile(callback.message.chat.id, callback.message.message_id, tg, user)

@router.callback_query(F.data == "edit_field_name")
async def edit_field_name_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    lang = user.get("language", "ru")
    
    partner = (
        await db.get_partner_by_telegram(callback.message.chat.id)
        or await db.get_partner_by_telegram(tg)
        or {}
    )
    restaurant_id = partner.get("restaurant_id", "")
    
    await state.set_state(ProfileEditState.waiting_for_name)
    await state.update_data(
        restaurant_id=restaurant_id,
        profile_msg_id=callback.message.message_id
    )
    
    if lang == "ru":
        prompt = "📝 <b>Введите новое название ресторана:</b>"
    elif lang == "en":
        prompt = "📝 <b>Enter new restaurant name:</b>"
    else:
        prompt = "📝 <b>შეიყვანეთ რესტორნის ახალი სახელი:</b>"
        
    prompt_msg = await callback.message.reply(prompt, parse_mode=ParseMode.HTML)
    await state.update_data(prompt_msg_id=prompt_msg.message_id)

@router.callback_query(F.data == "edit_field_desc")
async def edit_field_desc_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    lang = user.get("language", "ru")
    
    partner = (
        await db.get_partner_by_telegram(callback.message.chat.id)
        or await db.get_partner_by_telegram(tg)
        or {}
    )
    restaurant_id = partner.get("restaurant_id", "")
    
    await state.set_state(ProfileEditState.waiting_for_description)
    await state.update_data(
        restaurant_id=restaurant_id,
        profile_msg_id=callback.message.message_id
    )
    
    if lang == "ru":
        prompt = "📋 <b>Введите новое описание ресторана:</b>"
    elif lang == "en":
        prompt = "📋 <b>Enter new restaurant description:</b>"
    else:
        prompt = "📋 <b>შეიყვანეთ რესტორნის ახალი აღწერა:</b>"
        
    prompt_msg = await callback.message.reply(prompt, parse_mode=ParseMode.HTML)
    await state.update_data(prompt_msg_id=prompt_msg.message_id)

@router.callback_query(F.data == "edit_field_photo")
async def edit_field_photo_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    lang = user.get("language", "ru")
    
    partner = (
        await db.get_partner_by_telegram(callback.message.chat.id)
        or await db.get_partner_by_telegram(tg)
        or {}
    )
    restaurant_id = partner.get("restaurant_id", "")
    
    await state.set_state(ProfileEditState.waiting_for_photo)
    await state.update_data(
        restaurant_id=restaurant_id,
        profile_msg_id=callback.message.message_id
    )
    
    if lang == "ru":
        prompt = "🖼️ <b>Отправьте новую фотографию для ресторана (одним сообщением):</b>"
    elif lang == "en":
        prompt = "🖼️ <b>Send a new photo for the restaurant (single message):</b>"
    else:
        prompt = "🖼️ <b>გამოაგზავნეთ რესტორნის ახალი ფოტო (ერთი შეტყობინებით):</b>"
        
    prompt_msg = await callback.message.reply(prompt, parse_mode=ParseMode.HTML)
    await state.update_data(prompt_msg_id=prompt_msg.message_id)

@router.message(ProfileEditState.waiting_for_name)
async def edit_name_input_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    restaurant_id = data.get("restaurant_id")
    profile_msg_id = data.get("profile_msg_id")
    prompt_msg_id = data.get("prompt_msg_id")
    
    try:
        await message.delete()
    except Exception:
        pass
    if prompt_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception:
            pass
            
    name = message.text.strip()
    if not name:
        return
        
    await db.update_restaurant_name_and_desc(restaurant_id, name=name)
    await state.clear()
    
    tg = message.from_user.id
    user = await db.get_bot_user(tg) or {}
    await render_edit_profile_menu(message.chat.id, profile_msg_id, tg, user)

@router.message(ProfileEditState.waiting_for_description)
async def edit_desc_input_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    restaurant_id = data.get("restaurant_id")
    profile_msg_id = data.get("profile_msg_id")
    prompt_msg_id = data.get("prompt_msg_id")
    
    try:
        await message.delete()
    except Exception:
        pass
    if prompt_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception:
            pass
            
    desc = message.text.strip()
    if not desc:
        return
        
    await db.update_restaurant_name_and_desc(restaurant_id, desc=desc)
    await state.clear()
    
    tg = message.from_user.id
    user = await db.get_bot_user(tg) or {}
    await render_edit_profile_menu(message.chat.id, profile_msg_id, tg, user)

@router.message(ProfileEditState.waiting_for_photo)
async def edit_photo_input_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    restaurant_id = data.get("restaurant_id")
    profile_msg_id = data.get("profile_msg_id")
    prompt_msg_id = data.get("prompt_msg_id")
    
    if not message.photo:
        tg = message.from_user.id
        user = await db.get_bot_user(tg) or {}
        lang = user.get("language", "ru")
        err_text = "❌ Пожалуйста, отправьте именно изображение!" if lang == "ru" else (
            "❌ Please send an image!" if lang == "en" else "❌ გთხოვთ გამოაგზავნოთ სურათი!"
        )
        err_msg = await message.answer(err_text)
        await asyncio.sleep(3.0)
        try:
            await err_msg.delete()
        except Exception:
            pass
        return
        
    try:
        await message.delete()
    except Exception:
        pass
    if prompt_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception:
            pass
            
    photo = message.photo[-1]
    file_id = photo.file_id
    file_unique_id = photo.file_unique_id
    
    file_info = await message.bot.get_file(file_id)
    telegram_file_path = file_info.file_path
    
    new_filename = f"bot_{file_unique_id}.jpg"
    relative_path = f"/uploads/{new_filename}"
    
    upload_dirs = [
        r"c:\MestiDelivery\Backend GO\Backend\uploads",
        r"c:\MestiDelivery\Backend GO\Backend\build\uploads"
    ]
    
    download_success = False
    for udir in upload_dirs:
        try:
            os.makedirs(udir, exist_ok=True)
            local_path = os.path.join(udir, new_filename)
            await message.bot.download_file(telegram_file_path, local_path)
            download_success = True
        except Exception as e:
            log.error(f"Failed downloading photo to {udir}: {e}")
            
    if download_success:
        await db.update_restaurant_image(restaurant_id, relative_path)
        
    await state.clear()
    
    tg = message.from_user.id
    user = await db.get_bot_user(tg) or {}
    await render_edit_profile_menu(message.chat.id, profile_msg_id, tg, user)


@router.callback_query(F.data.startswith("accept_"))
async def on_accept(callback: CallbackQuery):
    order_id = int(callback.data.split("_", 1)[1])
    telegram_id = callback.message.chat.id

    log.info("Order #%d accepted by partner tg=%d", order_id, telegram_id)

    # Обновляем бэкенд
    success = await update_order_status_backend(order_id, "accepted")

    if success:

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Начать готовить",
                    callback_data=f"prepare_{order_id}",
                    style=ButtonStyle.SUCCESS,
                    icon_custom_emoji_id="5382351125838077755",
                ),
            ]
        ])
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer("✅ Заказ принят! Можно начинать готовить.", show_alert=True)
        await db.update_order_status(order_id, telegram_id, "accepted")
    else:
        await callback.answer(
            "⚠️ Ошибка обновления статуса на сервере. Повторите попытку.",
            show_alert=True,
        )

@router.callback_query(F.data.startswith("prepare_"))
async def on_prepare(callback: CallbackQuery):
    order_id = int(callback.data.split("_", 1)[1])
    telegram_id = callback.message.chat.id

    log.info("Order #%d preparation started by partner tg=%d", order_id, telegram_id)

    success = await update_order_status_backend(order_id, "preparing")

    if success:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Готов к выдаче",
                    callback_data=f"ready_{order_id}",
                    style=ButtonStyle.SUCCESS,
                    icon_custom_emoji_id="5384312315279612142",
                ),
            ]
        ])
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer("👨‍🍳 Статус обновлён: заказ готовится.", show_alert=True)
        await db.update_order_status(order_id, telegram_id, "preparing")
    else:
        await callback.answer("⚠️ Ошибка обновления статуса.", show_alert=True)

@router.callback_query(F.data.startswith("ready_"))
async def on_ready(callback: CallbackQuery):
    order_id = int(callback.data.split("_", 1)[1])
    telegram_id = callback.message.chat.id

    log.info("Order #%d ready by partner tg=%d", order_id, telegram_id)

    success = await update_order_status_backend(order_id, "ready")

    if success:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("📦 Заказ отмечен как готовый. Ожидайте курьера.", show_alert=True)
        await db.update_order_status(order_id, telegram_id, "ready")
    else:
        await callback.answer("⚠️ Ошибка обновления статуса.", show_alert=True)


def _parse_cancel_total_from_caption(caption: str) -> str:
    """Достаёт сумму позиций из caption заказа → «₾ N.NN»."""
    if not caption:
        return _fmt_banner_lari(0)
    match = re.search(
        r"Сумма заказа\s*:</?b>?\s*([\d.,]+)|Сумма заказа:.*?(?:<b>)?([\d.,]+)",
        caption,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(r"([\d]+(?:[.,]\d+)?)\s*(?:GEL|₾|сом)", caption)
    raw_amt = None
    if match:
        raw_amt = next((g for g in match.groups() if g), None)
    if raw_amt:
        return _fmt_banner_lari(raw_amt.replace(",", "."))
    return _fmt_banner_lari(0)


def _reject_confirm_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, отклонить",
                    callback_data=f"rj_yes_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
                InlineKeyboardButton(
                    text="Нет, назад",
                    callback_data=f"rj_no_{order_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ]
        ]
    )


def _reject_reason_kb(order_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"rj_rs_{order_id}_{code}")]
        for code, (label, _) in REJECT_REASON_DEFS.items()
    ]
    rows.append(
        [InlineKeyboardButton(text="← Назад", callback_data=f"rj_no_{order_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _reject_delay_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="+10 мин",
                    callback_data=f"rj_dl_{order_id}_10",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    text="+15 мин",
                    callback_data=f"rj_dl_{order_id}_15",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    text="+20 мин",
                    callback_data=f"rj_dl_{order_id}_20",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Всё равно отклонить",
                    callback_data=f"rj_fx_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
            ],
            [
                InlineKeyboardButton(text="← Назад", callback_data=f"rj_yes_{order_id}"),
            ],
        ]
    )


def _apply_process_until_caption(html_text: str, extra_min: int) -> tuple[str, str]:
    """Меняет 2-ю строку на «Создан … · Обработать до …». Без отдельной заметки."""
    deadline = datetime.now() + timedelta(minutes=extra_min)
    new_hm = deadline.strftime("%H:%M")
    text = html_text or ""

    text = re.sub(
        r"\n?\s*⏱?\s*Ресторан запросил \+\d+\s*мин[^\n]*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    updated, n = re.subn(
        r"((?:Создан</b>\s*:\s*|Создан\s*:\s*)\d{1,2}:\d{2}\s*·\s*)"
        r"(?:<b>)?(?:Принять до|Обработать до)(?:</b>)?\s*:\s*"
        r"\d{1,2}:\d{2}(?:\s*\(~?\d+\s*мин\))?",
        rf"\1<b>Обработать до</b>: {new_hm}",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    if not n:
        updated, n = re.subn(
            r"(?:<b>)?(?:Принять до|Обработать до)(?:</b>)?\s*:\s*"
            r"\d{1,2}:\d{2}(?:\s*\(~?\d+\s*мин\))?",
            f"<b>Обработать до</b>: {new_hm}",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    if not n:
        updated = text.rstrip() + f"\n <b>Обработать до</b>: {new_hm}"

    return updated.strip(), new_hm


def _banner_fields_from_order_caption(order_id: int, caption: str, accept_timer: str) -> dict:
    names: list[str] = []
    count = 0
    for m in re.finditer(
        r"•\s*(?:<b>)?([^<\n—]+?)(?:</b>)?\s*×\s*(\d+)",
        caption or "",
    ):
        name = m.group(1).strip()
        qty = int(m.group(2))
        count += qty
        names.append(f"{name} ×{qty}" if qty > 1 else name)
    if names:
        word = "item" if count == 1 else "items"
        items = f"{count} {word} · {', '.join(names)}"
    else:
        items = "—"
    return {
        "order_number": f"#{order_id}",
        "items": items,
        "order_total": _parse_cancel_total_from_caption(caption or ""),
        "accept_timer": accept_timer,
    }


def _lookup_order_customer_notify(order_id: int) -> Optional[dict]:
    user_id = ""
    restaurant_name = ""
    for path in ORDER_DB_PATHS:
        if not os.path.exists(path):
            continue
        try:
            conn = connect_sqlite_wal(path)
            row = conn.execute(
                "SELECT user_id, restaurant_id FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            conn.close()
            if row:
                user_id = str(row[0] or "").strip()
                restaurant_name = str(row[1] or "").strip()  # id; имя подставит caller
                break
        except Exception as e:
            log.warning("lookup order %s failed: %s", order_id, e)

    if not user_id:
        return None

    tg_id = 0
    language = "ru"
    for path in BACKEND_DB_PATHS:
        if not os.path.exists(path):
            continue
        try:
            conn = connect_sqlite_wal(path)
            row = conn.execute(
                "SELECT telegram_user_id, preferred_language FROM customers WHERE cast(id as text) = ?",
                (user_id,),
            ).fetchone()
            conn.close()
            if row and row[0]:
                try:
                    tg_id = int(str(row[0]).strip())
                except ValueError:
                    tg_id = 0
                language = (row[1] or "ru").strip() or "ru"
                break
        except Exception as e:
            log.warning("lookup customer %s failed: %s", user_id, e)

    if tg_id <= 0:
        return None
    return {
        "telegram_user_id": tg_id,
        "language": language,
        "restaurant_name": restaurant_name or "MestiDelivery",
    }


async def _notify_prep_delay(
    *,
    order_id: int,
    extra_min: int,
    until_hm: str,
    restaurant_name: str = "",
) -> None:
    admin_text = (
        f"⏱ <b>Ресторан запросил доп. время</b>\n\n"
        f"Заказ <b>#{order_id}</b>\n"
        f"Ресторан: <b>{html.escape(restaurant_name or '—')}</b>\n"
        f"Задержка: <b>+{extra_min} мин</b>\n"
        f"Обработать до: <b>{until_hm}</b>"
    )
    try:
        await bot.send_message(ADMIN_TG_ID, admin_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        log.error("prep-delay admin notify failed: %s", e)

    info = await asyncio.to_thread(_lookup_order_customer_notify, int(order_id))
    if not info:
        log.warning("prep-delay: customer tg not found for order %s", order_id)
        return

    rest = restaurant_name or info.get("restaurant_name") or "MestiDelivery"
    payload = {
        "order_id": int(order_id),
        "telegram_user_id": int(info["telegram_user_id"]),
        "status": "prep_delayed",
        "language": info.get("language") or "ru",
        "restaurant_name": rest,
        "delay_minutes": int(extra_min),
        "until_time": until_hm,
    }
    url = f"{CLIENT_BOT_URL}/api/bot/v1/customer/order-status"
    headers = {
        "Content-Type": "application/json",
        SECURITY_HEADER: CLIENT_BOT_TOKEN,
    }
    try:
        async with _aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=_aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status >= 300:
                    body = await resp.text()
                    log.warning("prep-delay client bot HTTP %s: %s", resp.status, body[:300])
                else:
                    log.info(
                        "prep-delay notified customer tg=%s order=%s +%smin",
                        info["telegram_user_id"], order_id, extra_min,
                    )
    except Exception as e:
        log.error("prep-delay client bot notify failed: %s", e)


def format_restaurant_cancel_caption(
    order_id: int | str,
    *,
    reason: str = "",
    by: str = "restaurant",
) -> str:
    """Caption под баннером 3a: иконка + заголовок, причина отдельной мягкой строкой."""
    icon = ce("5384244502040975393", "❌")
    if by == "admin":
        return f"{icon} <b>Заказ #{order_id} отклонён администратором</b>"
    reason = (reason or "").strip()
    parts = [f"{icon} <b>Заказ #{order_id} отклонён</b>"]
    if reason:
        # Не «Причина:» сразу под жирным — отдельная строка с разделителем.
        parts.append("")
        parts.append(f"Ресторан · {html.escape(reason)}")
    else:
        parts.append("Ресторан отказался от заказа.")
    return "\n".join(parts)


def format_courier_cancel_caption(order_id: int | str) -> str:
    return f'{ce("5384244502040975393", "❌")} <b>Заказ #{order_id} отменён</b>'


async def _finalize_restaurant_reject(
    *,
    chat_id: int,
    message_id: int,
    order_id: int,
    caption_html: str,
    is_photo: bool,
    reason_label: str,
) -> bool:
    """Отмена рестораном: banner + caption, затем PATCH cancelled."""
    cancel_total = _parse_cancel_total_from_caption(caption_html or "")
    cancel_time = datetime.now().strftime("%H:%M")
    new_caption = format_restaurant_cancel_caption(
        order_id, reason=reason_label, by="restaurant"
    )
    meta = {
        "reason": reason_label,
        "cancelled_by": "Ресторан",
        "cancel_total": cancel_total,
        "cancel_time": cancel_time,
        "caption": new_caption,
    }
    # До PATCH — иначе /orders/cancel от бэкенда перетрёт текстом «администратором».
    _RESTAURANT_CANCEL_META[int(order_id)] = meta

    success = await update_order_status_backend(order_id, "cancelled")
    if not success:
        _RESTAURANT_CANCEL_META.pop(int(order_id), None)
        return False

    fields = {
        "order_number": f"#{order_id}",
        "cancel_total": cancel_total,
        "cancel_time": cancel_time,
        "cancel_reason": reason_label,
        "cancelled_by": "Ресторан",
    }
    try:
        if is_photo:
            await edit_banner_media(
                chat_id=chat_id,
                message_id=message_id,
                kind="order_cancelled_restaurant",
                fields=fields,
                caption=new_caption,
                keyboard=None,
            )
        else:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=new_caption,
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        log.error("finalize restaurant reject UI failed: %s", e)

    await db.update_order_status(order_id, chat_id, "cancelled")
    return True


@router.callback_query(F.data.startswith("reject_"))
async def on_reject(callback: CallbackQuery):
    """Шаг 1: подтверждение отклонения."""
    order_id = int(callback.data.split("_", 1)[1])
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_reject_confirm_kb(order_id)
        )
    except Exception as e:
        log.warning("reject confirm kb failed: %s", e)
    await callback.answer(
        f"Вы уверены, что хотите отклонить заказ #{order_id}?",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("rj_no_"))
async def on_reject_cancel(callback: CallbackQuery):
    """Отмена флоу отклонения — вернуть Accept/Reject."""
    order_id = int(callback.data.split("_", 2)[2])
    await callback.answer("Ок, заказ не отклонён")
    try:
        await callback.message.edit_reply_markup(
            reply_markup=make_order_keyboard(order_id)
        )
    except Exception as e:
        log.warning("rj_no restore kb failed: %s", e)


@router.callback_query(F.data.startswith("rj_yes_"))
async def on_reject_yes(callback: CallbackQuery):
    """Шаг 2: выбор причины."""
    order_id = int(callback.data.split("_", 2)[2])
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_reject_reason_kb(order_id)
        )
    except Exception as e:
        log.warning("rj_yes reason kb failed: %s", e)
    await callback.answer("Выберите причину отклонения")


@router.callback_query(F.data.startswith("rj_rs_"))
async def on_reject_reason(callback: CallbackQuery):
    """Шаг 3: причина → отложить или финализировать."""
    # rj_rs_{order_id}_{code}
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    order_id = int(parts[2])
    code = parts[3]
    info = REJECT_REASON_DEFS.get(code)
    if not info:
        await callback.answer("Неизвестная причина", show_alert=True)
        return
    label, delayable = info

    if delayable:
        _RESTAURANT_CANCEL_META[int(order_id)] = {
            "_pending_reason": label,
            "_pending_code": code,
        }
        try:
            await callback.message.edit_reply_markup(
                reply_markup=_reject_delay_kb(order_id)
            )
        except Exception as e:
            log.warning("rj_rs delay kb failed: %s", e)
        await callback.answer(
            f"«{label}»: отложить на +10 / +15 / +20 мин или отклонить?",
            show_alert=True,
        )
        return

    ok = await _finalize_restaurant_reject(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        order_id=order_id,
        caption_html=callback.message.html_text or callback.message.caption or "",
        is_photo=bool(callback.message.photo or callback.message.document),
        reason_label=label,
    )
    if ok:
        await callback.answer("❌ Заказ отклонён рестораном")
    else:
        await callback.answer("⚠️ Ошибка обновления статуса на сервере", show_alert=True)


@router.callback_query(F.data.startswith("rj_dl_"))
async def on_reject_delay(callback: CallbackQuery):
    """Задержка = авто-принятие заказа + сдвиг «Обработать до»."""
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    order_id = int(parts[2])
    extra_min = int(parts[3])
    chat_id = callback.message.chat.id
    _RESTAURANT_CANCEL_META.pop(int(order_id), None)

    # При информе о задержке заказ принимается автоматически.
    success = await update_order_status_backend(order_id, "accepted")
    if not success:
        await callback.answer(
            "⚠️ Не удалось принять заказ на сервере. Повторите.",
            show_alert=True,
        )
        return

    html_text = callback.message.html_text or callback.message.caption or ""
    new_caption, until_hm = _apply_process_until_caption(html_text, extra_min)
    timer_label = f"{extra_min}:00"
    fields = _banner_fields_from_order_caption(order_id, html_text, timer_label)
    prepare_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Начать готовить",
                    callback_data=f"prepare_{order_id}",
                    style=ButtonStyle.SUCCESS,
                    icon_custom_emoji_id="5382351125838077755",
                ),
            ]
        ]
    )

    partner = await db.get_partner_by_telegram(chat_id) or {}
    restaurant_name = partner.get("restaurant_name") or ""

    try:
        if callback.message.photo or callback.message.document:
            await edit_banner_media(
                chat_id=chat_id,
                message_id=callback.message.message_id,
                kind="order_new_restaurant",
                fields=fields,
                caption=new_caption,
                keyboard=prepare_kb,
            )
        else:
            await callback.message.edit_text(
                text=new_caption,
                reply_markup=prepare_kb,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        log.error("rj_dl edit failed: %s", e)
        # Статус уже accepted — хотя бы кнопки поменяем.
        try:
            await callback.message.edit_reply_markup(reply_markup=prepare_kb)
        except Exception:
            pass

    await db.update_order_status(order_id, chat_id, "accepted")
    await callback.answer(
        f"✅ Заказ принят. +{extra_min} мин — обработать до {until_hm}",
        show_alert=True,
    )
    await _notify_prep_delay(
        order_id=order_id,
        extra_min=extra_min,
        until_hm=until_hm,
        restaurant_name=restaurant_name,
    )


@router.callback_query(F.data.startswith("rj_fx_"))
async def on_reject_force(callback: CallbackQuery):
    """Всё равно отклонить после delayable-причины."""
    order_id = int(callback.data.split("_", 2)[2])
    meta = _RESTAURANT_CANCEL_META.get(int(order_id)) or {}
    label = meta.get("_pending_reason") or "Завал на кухне"
    ok = await _finalize_restaurant_reject(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        order_id=order_id,
        caption_html=callback.message.html_text or callback.message.caption or "",
        is_photo=bool(callback.message.photo or callback.message.document),
        reason_label=label,
    )
    if ok:
        await callback.answer("❌ Заказ отклонён рестораном")
    else:
        await callback.answer("⚠️ Ошибка обновления статуса на сервере", show_alert=True)


# ─── Отказ курьера от оффера (как reject у ресторана) ─────────────────────────

@router.callback_query(F.data.startswith("cr_ask_"))
async def on_courier_refuse_ask(callback: CallbackQuery):
    """Шаг 1: подтверждение отказа."""
    order_id = int(callback.data.rsplit("_", 1)[-1])
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_courier_refuse_confirm_kb(order_id)
        )
    except Exception as e:
        log.warning("cr_ask confirm kb failed: %s", e)
    await callback.answer(
        f"Отказаться от заказа #{order_id}?",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("cr_no_"))
async def on_courier_refuse_no(callback: CallbackQuery):
    """Отмена флоу — вернуть Принять / Отказаться."""
    order_id = int(callback.data.rsplit("_", 1)[-1])
    await callback.answer("Ок, заказ остаётся")
    try:
        await callback.message.edit_reply_markup(
            reply_markup=make_broadcast_keyboard(order_id)
        )
    except Exception as e:
        log.warning("cr_no restore kb failed: %s", e)


@router.callback_query(F.data.startswith("cr_yes_"))
async def on_courier_refuse_yes(callback: CallbackQuery):
    """Шаг 2: выбор причины."""
    order_id = int(callback.data.rsplit("_", 1)[-1])
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_courier_refuse_reason_kb(order_id)
        )
    except Exception as e:
        log.warning("cr_yes reason kb failed: %s", e)
    await callback.answer("Выберите причину отказа")


@router.callback_query(F.data.startswith("cr_rs_"))
async def on_courier_refuse_reason(callback: CallbackQuery):
    """Шаг 3: причина → snooze 5 мин или финальный отказ."""
    # cr_rs_{order_id}_{code}
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    order_id = int(parts[2])
    code = parts[3]
    info = COURIER_REFUSE_REASON_DEFS.get(code)
    if not info:
        await callback.answer("Неизвестная причина", show_alert=True)
        return
    label, snoozeable = info

    if snoozeable:
        _COURIER_REFUSE_META[int(order_id)] = {
            "_pending_reason": label,
            "_pending_code": code,
        }
        try:
            await callback.message.edit_reply_markup(
                reply_markup=_courier_snooze_kb(order_id)
            )
        except Exception as e:
            log.warning("cr_rs snooze kb failed: %s", e)
        await callback.answer(
            f"«{label}»: напомнить через {COURIER_SNOOZE_MIN} мин или отказаться сейчас?",
            show_alert=True,
        )
        return

    ok = await _finalize_courier_refuse(
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        order_id=order_id,
        reason_label=label,
        is_photo=bool(callback.message.photo or callback.message.document),
    )
    if ok:
        await callback.answer("Вы отказались от заказа")
    else:
        await callback.answer("⚠️ Ошибка связи с сервером", show_alert=True)
        try:
            await callback.message.edit_reply_markup(
                reply_markup=make_broadcast_keyboard(order_id)
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("cr_dl_"))
async def on_courier_refuse_snooze(callback: CallbackQuery):
    """Отложить предложение на 5 минут (только если на другом заказе)."""
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    order_id = int(parts[2])
    extra_min = int(parts[3])
    if extra_min > COURIER_SNOOZE_MIN:
        extra_min = COURIER_SNOOZE_MIN
    telegram_id = callback.from_user.id
    until_hm = (datetime.now() + timedelta(minutes=extra_min)).strftime("%H:%M")
    caption = format_courier_snooze_caption(order_id, until_hm)

    try:
        if callback.message.photo or callback.message.document:
            await bot.edit_message_caption(
                chat_id=telegram_id,
                message_id=callback.message.message_id,
                caption=caption,
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
        else:
            await callback.message.edit_text(
                text=caption,
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        log.warning("cr_dl edit failed: %s", e)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    await db.update_kind(order_id, telegram_id, "snooze")
    schedule_courier_snooze(
        order_id,
        telegram_id,
        callback.message.message_id,
        delay_sec=extra_min * 60,
    )
    _COURIER_REFUSE_META.pop(int(order_id), None)
    await callback.answer(
        f"Ок! Напомним в {until_hm} (через {extra_min} мин)",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("cr_fx_"))
async def on_courier_refuse_force(callback: CallbackQuery):
    """Отказаться сразу после delayable-причины."""
    order_id = int(callback.data.rsplit("_", 1)[-1])
    meta = _COURIER_REFUSE_META.get(int(order_id)) or {}
    label = meta.get("_pending_reason") or "На другом заказе"
    ok = await _finalize_courier_refuse(
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        order_id=order_id,
        reason_label=label,
        is_photo=bool(callback.message.photo or callback.message.document),
    )
    if ok:
        await callback.answer("Вы отказались от заказа")
    else:
        await callback.answer("⚠️ Ошибка связи с сервером", show_alert=True)


def decode_callback_data(data: str) -> tuple[Optional[str], Optional[int]]:
    if not data.startswith("mesti_"):
        return None, None
    payload = data[6:]  # Strip "mesti_"
    idx = payload.rfind("_")
    if idx < 0:
        return None, None
    action = payload[:idx]
    id_str = payload[idx+1:]
    try:
        order_id = int(id_str)
        return action, order_id
    except ValueError:
        return None, None


def clean_courier_caption(html_text: str) -> str:
    if not html_text:
        return ""
    lines = html_text.split("\n")
    cleaned_lines = []
    for i, line in enumerate(lines):
        cleaned_lines.append(line)
        if "Доход:" in line or "доход:" in line.lower():
            # Строка чаевых идёт сразу под доходом — оставляем её тоже.
            if i + 1 < len(lines) and "чаевые:" in lines[i + 1].lower():
                cleaned_lines.append(lines[i + 1])
            break
    return "\n".join(cleaned_lines)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _parse_courier_offer_from_caption(caption: str) -> dict:
    """Достаёт pickup / dropoff / fee из HTML-caption карточки курьера."""
    raw = caption or ""
    plain = _strip_html(raw)
    pickup = dropoff = ""
    fee_val = None

    m = re.search(
        r"Забрать:</b>\s*(.+?)(?:\n|$)",
        raw,
        flags=re.IGNORECASE,
    ) or re.search(r"Забрать:\s*(.+?)(?:\n|$)", plain, flags=re.IGNORECASE)
    if m:
        pickup = _strip_html(m.group(1))

    m = re.search(
        r"Привезти:</b>\s*(.+?)(?:\n|$)",
        raw,
        flags=re.IGNORECASE,
    ) or re.search(r"Привезти:\s*(.+?)(?:\n|$)", plain, flags=re.IGNORECASE)
    if m:
        dropoff = _strip_html(m.group(1))

    m = re.search(
        r"Доход:</b>\s*([0-9]+(?:[.,][0-9]+)?)",
        raw,
        flags=re.IGNORECASE,
    ) or re.search(r"Доход:\s*([0-9]+(?:[.,][0-9]+)?)", plain, flags=re.IGNORECASE)
    if m:
        try:
            fee_val = float(m.group(1).replace(",", "."))
        except ValueError:
            fee_val = None

    return {
        "pickup_address": pickup,
        "dropoff_address": dropoff,
        "fee": fee_val,
    }


def order_taken_banner_fields(
    order_id: int | str,
    *,
    pickup_address: str = "",
    dropoff_address: str = "",
    fee: float | None = None,
    caption: str = "",
    event_time: str | None = None,
) -> dict:
    """Поля для баннера 7a (заказ взят другим курьером)."""
    cached = _COURIER_BROADCAST_FIELDS.get(int(order_id), {})
    parsed = _parse_courier_offer_from_caption(caption) if caption else {}

    pickup = (
        (pickup_address or "").strip()
        or (parsed.get("pickup_address") or "").strip()
        or (cached.get("pickup_address") or "").strip()
        or "—"
    )
    dropoff = (
        (dropoff_address or "").strip()
        or (parsed.get("dropoff_address") or "").strip()
        or (cached.get("dropoff_address") or "").strip()
        or "—"
    )

    fee_val = fee
    if fee_val is None:
        fee_val = parsed.get("fee")
    if fee_val is None:
        fee_val = cached.get("fee")
    try:
        missed = f"₾ {float(fee_val):.2f}"
    except (TypeError, ValueError):
        missed = cached.get("missed_payout") or "₾ 0.00"

    return {
        "pickup_address": pickup,
        "dropoff_address": dropoff,
        "order_number": f"#{order_id}",
        "event_time": event_time or datetime.now().strftime("%H:%M"),
        "missed_payout": missed,
    }


def order_taken_caption(order_id: int | str) -> str:
    return (
        f'{ce("5384244502040975393", "⏳")} '
        f"<b>Заказ #{order_id} уже взят другим курьером.</b>"
    )


async def replace_courier_offer_with_taken(
    *,
    chat_id: int,
    message_id: int,
    order_id: int,
    caption_html: str = "",
    is_photo: bool = True,
    pickup_address: str = "",
    dropoff_address: str = "",
    fee: float | None = None,
) -> bool:
    """Меняет баннер 5a → 7a (как 2a → 3a при отмене рестораном)."""
    fields = order_taken_banner_fields(
        order_id,
        pickup_address=pickup_address,
        dropoff_address=dropoff_address,
        fee=fee,
        caption=caption_html,
    )
    new_caption = order_taken_caption(order_id)
    try:
        if is_photo:
            ok = await edit_banner_media(
                chat_id=chat_id,
                message_id=message_id,
                kind="order_taken_courier",
                fields=fields,
                caption=new_caption,
                keyboard=None,
            )
            if ok:
                await db.update_kind(order_id, chat_id, "taken")
            return ok
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=new_caption,
            reply_markup=None,
            parse_mode=ParseMode.HTML,
        )
        await db.update_kind(order_id, chat_id, "taken")
        return True
    except Exception as e:
        log.error("replace_courier_offer_with_taken failed: %s", e)
        return False


def _extract_dropoff_from_caption(html_text: str) -> str:
    """Достаёт адрес «Привезти» из HTML-caption карточки заказа."""
    if not html_text:
        return ""
    m = re.search(
        r"Привезти:</b>\s*(.+?)(?:\n|$)",
        html_text,
        flags=re.IGNORECASE,
    )
    if not m:
        m = re.search(r"Привезти:\s*(.+?)(?:\n|$)", html_text, flags=re.IGNORECASE)
    if not m:
        return ""
    return re.sub(r"<[^>]+>", "", m.group(1)).strip()


def courier_action_alert(
    action: str,
    order_id: int,
    *,
    dropoff: str = "",
    gateway_text: str = "",
) -> str:
    """Popup-текст статуса курьера (как show_alert у ресторана)."""
    if action == "accepted":
        return f"✅ Заказ принят! Направляйтесь в ресторан."
    if action == "arrived_restaurant":
        return f"📍 Статус обновлён. Заберите заказ #{order_id} у ресторана."
    if action == "picked_up":
        gt = (gateway_text or "").lower()
        if "еще не" in gt or "ещё не" in gt or "ожидайте" in gt:
            return gateway_text or "Ресторан еще не приготовил заказ. Ожидайте готовности!"
        addr = (dropoff or "").strip() or "адресу клиента"
        return f"🛍️ Заказ у вас. Везите по адресу: {addr}"
    if action == "completed":
        return (
            f"✅ Заказ #{order_id} доставлен! Баланс обновлён — проверьте раздел «Выплаты»."
        )
    if action == "rejected":
        return f"Заказ #{order_id} отклонён."
    if action == "arrived":
        return gateway_text or f"📍 Вы на месте у клиента по заказу #{order_id}."
    return gateway_text or "Успешно"


def keyboard_for_action(action: str, order_id: int) -> Optional[InlineKeyboardMarkup]:
    """Следующая зелёная кнопка статуса курьера."""
    btn = None
    if action == "arrived_restaurant":
        btn = InlineKeyboardButton(
            text="Я на месте",
            callback_data=f"mesti_arrived_restaurant_{order_id}",
            style=ButtonStyle.SUCCESS,
            icon_custom_emoji_id="5382351125838077755",
        )
    elif action == "picked_up":
        btn = InlineKeyboardButton(
            text="Забрал заказ",
            callback_data=f"mesti_picked_up_{order_id}",
            style=ButtonStyle.SUCCESS,
            icon_custom_emoji_id="5384312315279612142",
        )
    elif action in ("completed", "arrived"):
        # «arrived» у клиента больше не используем в UI — сразу «Заказ доставлен».
        btn = InlineKeyboardButton(
            text="Заказ доставлен",
            callback_data=f"mesti_completed_{order_id}",
            style=ButtonStyle.SUCCESS,
            icon_custom_emoji_id="5384518714227990146",
        )
    else:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


@router.callback_query(F.data.startswith("mesti_"))
async def on_mesti_callback(callback: CallbackQuery):
    data = callback.data
    action, order_id = decode_callback_data(data)
    if not action or not order_id:
        await callback.answer("⚠️ Неизвестное действие", show_alert=True)
        return

    telegram_id = callback.from_user.id

    log.info("Mesti callback: order_id=%d, action=%s, user_tg=%d", order_id, action, telegram_id)

    # Отказ от оффера — через confirm/reason (кнопка «Отказаться»), не сразу в gateway.
    if action == "rejected":
        try:
            await callback.message.edit_reply_markup(
                reply_markup=_courier_refuse_confirm_kb(order_id)
            )
        except Exception as e:
            log.warning("mesti_rejected → confirm kb failed: %s", e)
        await callback.answer(
            f"Отказаться от заказа #{order_id}?",
            show_alert=True,
        )
        return

    # Лоадер, чтобы избежать дабл-кликов
    original_kb = callback.message.reply_markup
    try:
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⏳ Обработка...", callback_data="ignore")
            ]])
        )
    except Exception:
        pass

    url = f"{BACKEND_URL}/api/v1/bot-callback"
    headers = {
        "Content-Type": "application/json",
        SECURITY_HEADER: SECURITY_TOKEN,
    }
    payload = {
        "order_id": order_id,
        "telegram_id": telegram_id,
        "action": action,
    }

    try:
        async with _aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=_aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.error("Gateway bot-callback failed for order %d status=%d body=%s", order_id, resp.status, body)

                    import json
                    err_msg = ""
                    try:
                        data = json.loads(body)
                        err_msg = data.get("error", "") or ""
                    except Exception:
                        err_msg = body or ""

                    low = err_msg.lower()
                    if (
                        "already assigned" in low
                        or "already taken" in low
                        or "not pending" in low
                        or "transition" in low
                    ):
                        await callback.answer("❌ Заказ уже принят или недоступен", show_alert=True)
                        cap = callback.message.html_text or callback.message.caption or ""
                        is_photo = bool(callback.message.photo)
                        replaced = await replace_courier_offer_with_taken(
                            chat_id=telegram_id,
                            message_id=callback.message.message_id,
                            order_id=order_id,
                            caption_html=cap,
                            is_photo=is_photo,
                        )
                        if not replaced:
                            try:
                                await callback.message.edit_caption(
                                    caption=order_taken_caption(order_id),
                                    reply_markup=None,
                                    parse_mode=ParseMode.HTML,
                                )
                            except Exception:
                                try:
                                    await callback.message.edit_reply_markup(reply_markup=None)
                                except Exception:
                                    pass
                    elif "courier not found" in low:
                        await callback.answer("❌ Вы не зарегистрированы как курьер. Введите /reset", show_alert=True)
                        try:
                            await callback.message.edit_reply_markup(reply_markup=original_kb)
                        except Exception:
                            pass
                    else:
                        await callback.answer("⚠️ Ошибка: " + (err_msg or "сервер"), show_alert=True)
                        try:
                            await callback.message.edit_reply_markup(reply_markup=original_kb)
                        except Exception:
                            pass
                    return
                resp_data = await resp.json()
    except Exception as e:
        log.error("Gateway bot-callback error: %s", e)
        await callback.answer("⚠️ Ошибка связи с сервером", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=original_kb)
        except Exception:
            pass
        return

    if not resp_data.get("success"):
        await callback.answer("⚠️ Ошибка выполнения операции", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=original_kb)
        except Exception:
            pass
        return

    gateway_text = resp_data.get("display_text", "") or ""
    next_action = resp_data.get("next_allowed_action", "") or ""
    dropoff = _extract_dropoff_from_caption(
        callback.message.html_text or callback.message.caption or ""
    )
    alert_text = courier_action_alert(
        action,
        order_id,
        dropoff=dropoff,
        gateway_text=gateway_text,
    )

    # Карточку не дописываем — только меняем кнопки (как у ресторана).
    kb = keyboard_for_action(next_action, order_id) if next_action else None
    # Если gateway вернул тот же шаг (заказ ещё не готов) — оставляем текущую кнопку.
    if action == "picked_up" and next_action == "picked_up":
        kb = keyboard_for_action("picked_up", order_id)

    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception as e:
        log.warning("Webhook: edit_reply_markup failed: %s", e)

    await callback.answer(alert_text, show_alert=True)

    if action != "rejected":
        await db.update_kind(order_id, telegram_id, "tracking")


# ─────────────────────────────────────────────
#  HTTP клиент → бэкенд
# ─────────────────────────────────────────────
import aiohttp as _aiohttp

async def ensure_courier_telegram_bound(telegram_id: int, username: Optional[str] = None) -> bool:
    """Гарантирует telegram_id курьера в auth.db (gateway шлёт broadcast только по нему).

    Без привязки курьер может быть online в bot_users, но пропадать из веера заказов.
    """
    if not username:
        user = await db.get_bot_user(telegram_id) or {}
        username = user.get("backend_username")
    if not username:
        log.warning("ensure_courier_telegram_bound: no username for tg=%s", telegram_id)
        return False

    tg_str = str(telegram_id)
    ok = False

    def _bind():
        nonlocal ok
        for path in BACKEND_DB_PATHS:
            if not os.path.exists(path):
                continue
            try:
                conn = connect_sqlite_wal(path)
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, role FROM admin_users WHERE username = ?",
                    (username,),
                )
                row = cur.fetchone()
                if not row or row[1] != "courier":
                    conn.close()
                    continue
                cur.execute(
                    "UPDATE admin_users SET telegram_id = NULL WHERE telegram_id = ?",
                    (tg_str,),
                )
                cur.execute(
                    "UPDATE admin_users SET telegram_id = ? WHERE id = ?",
                    (tg_str, int(row[0])),
                )
                conn.commit()
                conn.close()
                ok = True
                log.info(
                    "ensure_courier_telegram_bound: tg=%s → username=%s in %s",
                    tg_str, username, path,
                )
            except Exception as e:
                log.error("ensure_courier_telegram_bound failed %s: %s", path, e)
        return ok

    return await asyncio.to_thread(_bind)


async def update_courier_online_backend(telegram_id: int, action: str) -> bool:
    """Отправляет POST /api/v1/bot-callback (set_online/set_offline)."""
    # При выходе на линию фиксируем telegram_id в auth — иначе set_online/resolve молча no-op
    # и gateway не попадёт в список broadcast.
    if action == "set_online":
        await ensure_courier_telegram_bound(telegram_id)
        # Снимаем «на линии» с дублей того же логина (старые TG после смены аккаунта).
        try:
            user = await db.get_bot_user(telegram_id) or {}
            uname = user.get("backend_username")
            if uname:
                await db.offline_other_sessions(telegram_id, uname)
        except Exception as e:
            log.warning("offline_other_sessions failed tg=%s: %s", telegram_id, e)

    url = f"{BACKEND_URL}/api/v1/bot-callback"
    headers = {
        "Content-Type": "application/json",
        SECURITY_HEADER: SECURITY_TOKEN,
    }
    payload = {
        "order_id": 0,
        "telegram_id": telegram_id,
        "action": action,
    }
    try:
        async with _aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=_aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    log.info("Backend set courier %d %s", telegram_id, action)
                    return True
                else:
                    body = await resp.text()
                    log.error("Backend error %s: %s", action, body)
                    return False
    except Exception as e:
        log.error("Backend error %s: %s", action, e)
        return False


async def update_order_status_backend(order_id: int, status: str) -> bool:
    """Отправляет PATCH /api/v1/orders/{id}/status на бэкенд."""
    url = f"{BACKEND_URL}/api/v1/orders/{order_id}/status"
    headers = {
        "Content-Type": "application/json",
        SECURITY_HEADER: SECURITY_TOKEN,
    }
    payload = {"status": status}
    try:
        async with _aiohttp.ClientSession() as session:
            async with session.patch(url, json=payload, headers=headers, timeout=_aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    log.info("Backend updated order #%d -> %s", order_id, status)
                    return True
                else:
                    body = await resp.text()
                    log.warning("Backend PATCH order #%d status=%d body=%s", order_id, resp.status, body)
                    return False
    except Exception as e:
        log.error("update_order_status_backend error: %s", e)
        return False


# ─────────────────────────────────────────────
#  HTTP сервер — принимает уведомления от бэкенда
# ─────────────────────────────────────────────

def check_token(request: web.Request) -> bool:
    """Проверяет X-Bot-Security-Token в заголовке запроса."""
    if not SECURITY_TOKEN:
        log.error("SECURITY_TOKEN not configured!")
        return False
    return request.headers.get(SECURITY_HEADER) == SECURITY_TOKEN


async def handle_new_order(request: web.Request) -> web.Response:
    """
    POST /api/bot/v1/restaurant/new-order
    Принимает уведомление о новом заказе и шлёт его партнёру в Telegram.
    """
    if not check_token(request):
        log.warning("new-order: unauthorized from %s", request.remote)
        return web.Response(status=401, text="unauthorized")

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    order_id = data.get("order_id")
    if not order_id:
        return web.Response(status=400, text="order_id required")

    # Резолвим telegram_id
    telegram_id = data.get("restaurant_telegram_id")
    restaurant_id = data.get("restaurant_id")

    # Если telegram_id не передан, попробуем найти его через локальную БД по restaurant_id
    if not telegram_id and restaurant_id:
        partner = await db.get_partner_by_restaurant(restaurant_id)
        if partner:
            telegram_id = partner["telegram_id"]

    if not telegram_id:
        log.warning("new-order: telegram_id not resolved for order %s, restaurant %s", order_id, restaurant_id)
        return web.json_response(
            {"ok": False, "error": f"Telegram ID not resolved for restaurant '{restaurant_id}'"},
            status=404,
        )

    # Объединяем данные из вебхука
    items = data.get("items") or []
    items_total = 0.0
    for it in items:
        try:
            items_total += float(it.get("price") or 0) * int(it.get("quantity") or 1)
        except (TypeError, ValueError):
            continue

    formatted_data = {
        "order_id": order_id,
        "restaurant_id": restaurant_id or data.get("restaurant_id", ""),
        "total_amount": data.get("total_amount") or 0,
        "currency": data.get("currency") or "GEL",
        "customer_name": data.get("customer_name") or "Клиент",
        "phone": data.get("phone") or "—",
        "address": data.get("address") or "—",
        "comment": data.get("comment") or "",
        "items": items,
        "payment_method": data.get("payment_method") or "—",
        "delivery_fee": data.get("delivery_fee") or 0,
        "created_at": data.get("created_at") or data.get("createdAt"),
    }

    # Формируем и отправляем сообщение
    text = format_order_message(formatted_data)
    keyboard = make_order_keyboard(order_id)

    try:
        # Баннер 2a: items / ₾ total / таймер 5:00 (окно ресторана ~5 мин)
        msg = await send_banner_photo(
            chat_id=telegram_id,
            kind="order_new_restaurant",
            fields={
                "order_number": f"#{order_id}",
                "items": _format_banner_items(items),
                "order_total": f"₾ {items_total:.2f}",
                "accept_timer": f"{RESTAURANT_ACCEPT_MIN}:00",
            },
            keyboard=keyboard,
            caption=text,
        )
        log.info(
            "new-order: sent to restaurant %s tg=%d order_id=%s msg_id=%d",
            restaurant_id or "unknown", telegram_id, order_id, msg.message_id,
        )
        await db.save_order_message(order_id, telegram_id, msg.message_id)
        await db.save_message(order_id, telegram_id, msg.message_id, "restaurant", "new_order")
        return web.json_response({"ok": True, "message_id": msg.message_id})
    except Exception as e:
        log.error("new-order: telegram send failed: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=502)


def _fmt_money_amount(value) -> str:
    try:
        n = float(value)
        return f"{n:.0f}" if n == int(n) else f"{n:.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_banner_lari(value) -> str:
    """Сумма на баннере: «₾ 98.00»."""
    try:
        return f"₾ {float(value):.2f}"
    except (TypeError, ValueError):
        return f"₾ {value}"


def _items_food_total(items) -> float:
    total = 0.0
    for it in items or []:
        try:
            total += float(it.get("price") or 0) * int(it.get("quantity") or 1)
        except (TypeError, ValueError):
            continue
    return total


def format_broadcast_text(
    *,
    order_id: int | str,
    restaurant_name: str,
    pickup_address: str,
    delivery_address: str,
    fee: float,
    currency: str,
    created_at=None,
    comment: str = "",
    distance_km: float | str | None = None,
    tips: float = 0,
) -> str:
    """HTML-карточка нового заказа для курьера (как у ресторана: premium-emoji + <b>)."""
    created_hm, deadline_hm = _format_order_time(
        created_at, minutes=COURIER_ACCEPT_MIN
    )
    comment = _clean_order_comment(comment)
    currency = currency or "GEL"

    pickup_addr = (pickup_address or "").strip()
    rest_name = (restaurant_name or "").strip()
    if pickup_addr and rest_name and pickup_addr.lower() != rest_name.lower():
        pickup_line = f"{html.escape(pickup_addr)} | {html.escape(rest_name)}"
    else:
        pickup_line = html.escape(pickup_addr or rest_name or "—")

    dropoff_line = html.escape((delivery_address or "").strip() or "—")

    if distance_km is None or distance_km == "":
        distance_str = "1.5 км"
    else:
        try:
            distance_str = f"{float(distance_km):.1f} км"
        except (TypeError, ValueError):
            distance_str = str(distance_km)
            if "км" not in distance_str.lower():
                distance_str = f"{distance_str} км"

    fee_str = _fmt_money_amount(fee)
    try:
        tips_val = float(tips or 0)
    except (TypeError, ValueError):
        tips_val = 0.0

    parts = [
        f'{ce("5384244502040975393", "🔔")} <b>НОВЫЙ ЗАКАЗ #{order_id}</b>',
        f" <b>Создан:</b> {created_hm} · <b>Принять до:</b> {deadline_hm}"
        f" (обычно 5–10 мин, пока готовится)",
        "",
        f'{ce("5384312315279612142", "📍")} <b>Забрать:</b> {pickup_line}',
        f'{ce("5384312315279612142", "📍")} <b>Привезти:</b> {dropoff_line}',
        f'{ce("5382351125838077755", "📏")} <b>Расстояние:</b> {html.escape(distance_str)}',
        "",
        f'{ce("5384520939021048827", "💰")} <b>Доход:</b> {fee_str} {html.escape(currency)}',
    ]
    if tips_val > 0:
        tips_str = _fmt_money_amount(tips_val)
        parts.append(
            f'{ce("5384518714227990146", "✨")} <b>Чаевые:</b> {tips_str} {html.escape(currency)}'
        )
    if comment:
        parts.append(
            f'{ce("5382097310450753507", "💬")} <b>Комментарий:</b> {html.escape(comment)}'
        )
    return "\n".join(parts)


def make_broadcast_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура оффера курьеру: Принять / Отказаться + Подробности (WebApp)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Принять",
                    callback_data=f"mesti_accepted_{order_id}",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    text="Отказаться",
                    callback_data=f"cr_ask_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Открыть подробности",
                    web_app=WebAppInfo(url=f"{MINIAPP_DIRECT_URL}?order_id={order_id}"),
                    icon_custom_emoji_id="5384138412053796842",
                )
            ],
        ]
    )


def _courier_refuse_confirm_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, отказаться",
                    callback_data=f"cr_yes_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
                InlineKeyboardButton(
                    text="Нет, назад",
                    callback_data=f"cr_no_{order_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ]
        ]
    )


def _courier_refuse_reason_kb(order_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"cr_rs_{order_id}_{code}")]
        for code, (label, _) in COURIER_REFUSE_REASON_DEFS.items()
    ]
    rows.append(
        [InlineKeyboardButton(text="← Назад", callback_data=f"cr_ask_{order_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _courier_snooze_kb(order_id: int) -> InlineKeyboardMarkup:
    """Только +5 мин — максимум, как просил продукт."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Через {COURIER_SNOOZE_MIN} мин",
                    callback_data=f"cr_dl_{order_id}_{COURIER_SNOOZE_MIN}",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отказаться сейчас",
                    callback_data=f"cr_fx_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
            ],
            [
                InlineKeyboardButton(text="← Назад", callback_data=f"cr_yes_{order_id}"),
            ],
        ]
    )


def format_courier_refuse_caption(order_id: int | str, reason: str = "") -> str:
    icon = ce("5384244502040975393", "❌")
    parts = [f"{icon} <b>Вы отказались от заказа #{order_id}</b>"]
    reason = (reason or "").strip()
    if reason:
        parts.append("")
        parts.append(f"Причина · {html.escape(reason)}")
    return "\n".join(parts)


def format_courier_snooze_caption(order_id: int | str, until_hm: str) -> str:
    icon = ce("5382351125838077755", "⏳")
    return (
        f"{icon} <b>Напомним о заказе #{order_id}</b>\n"
        f"Вы на другом заказе — предложим снова в <b>{html.escape(until_hm)}</b> "
        f"(через {COURIER_SNOOZE_MIN} мин)."
    )


def cancel_courier_snooze(order_id: int, telegram_id: int) -> None:
    task = _COURIER_SNOOZE_TASKS.pop((int(order_id), int(telegram_id)), None)
    if task and not task.done():
        task.cancel()


async def _gateway_courier_rejected(order_id: int, telegram_id: int) -> bool:
    """Сообщает gateway, что этот курьер отказался (статус заказа не меняется)."""
    url = f"{BACKEND_URL}/api/v1/bot-callback"
    headers = {
        "Content-Type": "application/json",
        SECURITY_HEADER: SECURITY_TOKEN,
    }
    payload = {
        "order_id": int(order_id),
        "telegram_id": int(telegram_id),
        "action": "rejected",
    }
    try:
        async with _aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=_aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.warning(
                        "gateway rejected failed order=%s status=%s body=%s",
                        order_id, resp.status, body[:200],
                    )
                    return False
                data = await resp.json()
                return bool(data.get("success", True))
    except Exception as e:
        log.error("gateway rejected error: %s", e)
        return False


async def _finalize_courier_refuse(
    *,
    chat_id: int,
    message_id: int,
    order_id: int,
    reason_label: str,
    is_photo: bool,
) -> bool:
    """Финальный отказ: gateway rejected + UI без кнопок."""
    cancel_courier_snooze(order_id, chat_id)
    _COURIER_REFUSE_META.pop(int(order_id), None)
    ok = await _gateway_courier_rejected(order_id, chat_id)
    if not ok:
        return False
    caption = format_courier_refuse_caption(order_id, reason_label)
    try:
        if is_photo:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=caption,
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
        else:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=caption,
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        log.warning("finalize courier refuse UI failed: %s", e)
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except Exception:
            pass
    await db.update_kind(order_id, chat_id, "refused")
    return True


async def _courier_offer_still_open(order_id: int, telegram_id: int) -> bool:
    """True, если заказ ещё можно предложить этому курьеру."""
    try:
        msgs = await db.get_messages_for_order(order_id)
    except Exception:
        return False
    for m in msgs:
        kind = m.get("kind") or ""
        tid = m.get("telegram_id")
        if kind in ("tracking", "winner") and tid != telegram_id:
            return False
        if kind == "taken":
            return False
        if tid == telegram_id and kind in ("refused", "taken"):
            # свой отказ / taken — но после snooze kind=snooze, не refused
            if kind == "refused":
                return False
    # Есть ли ещё broadcast/snooze у этого курьера?
    mine = [m for m in msgs if m.get("telegram_id") == telegram_id]
    if not mine:
        return False
    return any((m.get("kind") or "") in ("broadcast", "snooze", "tracking") for m in mine)


async def _restore_courier_offer_after_snooze(
    order_id: int,
    telegram_id: int,
    message_id: int,
) -> None:
    """Через 5 мин: вернуть кнопки или показать 7a, если заказ уже ушёл."""
    key = (int(order_id), int(telegram_id))
    _COURIER_SNOOZE_TASKS.pop(key, None)

    try:
        msgs = await db.get_messages_for_order(order_id)
    except Exception:
        msgs = []

    # Если assign уже поставил taken — ничего не трогаем.
    for m in msgs:
        if m.get("telegram_id") == telegram_id and m.get("kind") == "taken":
            return
        if m.get("kind") in ("tracking", "winner") and m.get("telegram_id") != telegram_id:
            # заказ у другого — меняем на 7a
            await replace_courier_offer_with_taken(
                chat_id=telegram_id,
                message_id=message_id,
                order_id=order_id,
                is_photo=True,
            )
            return

    if not await _courier_offer_still_open(order_id, telegram_id):
        await replace_courier_offer_with_taken(
            chat_id=telegram_id,
            message_id=message_id,
            order_id=order_id,
            is_photo=True,
        )
        return

    cached = _COURIER_BROADCAST_FIELDS.get(int(order_id), {})
    fields = {
        "pickup_address": cached.get("pickup_address") or "—",
        "dropoff_address": cached.get("dropoff_address") or "—",
        "route_distance": "—",
        "courier_payout": cached.get("missed_payout")
        or (f"₾ {float(cached.get('fee') or 0):.2f}" if cached else "₾ 0.00"),
    }
    # Восстанавливаем баннер 5a + исходный caption-шаблон по возможности.
    fee = cached.get("fee") or 0
    try:
        fee = float(fee)
    except (TypeError, ValueError):
        fee = 0.0
    caption = format_broadcast_text(
        order_id=order_id,
        restaurant_name="",
        pickup_address=cached.get("pickup_address") or "",
        delivery_address=cached.get("dropoff_address") or "",
        fee=fee,
        currency="GEL",
        created_at=datetime.now(),
        comment="",
        distance_km=None,
    )
    try:
        await edit_banner_media(
            chat_id=telegram_id,
            message_id=message_id,
            kind="order_new_courier",
            fields=fields,
            caption=caption,
            keyboard=make_broadcast_keyboard(order_id),
        )
        await db.update_kind(order_id, telegram_id, "broadcast")
        await bot.send_message(
            chat_id=telegram_id,
            text=(
                f'{ce("5384244502040975393", "🔔")} '
                f"Напоминание: заказ <b>#{order_id}</b> ещё доступен — "
                f"можно принять."
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        log.warning("snooze restore failed order=%s tg=%s: %s", order_id, telegram_id, e)


def schedule_courier_snooze(
    order_id: int,
    telegram_id: int,
    message_id: int,
    *,
    delay_sec: int | None = None,
) -> None:
    cancel_courier_snooze(order_id, telegram_id)
    wait = int(delay_sec if delay_sec is not None else COURIER_SNOOZE_MIN * 60)

    async def _job() -> None:
        try:
            await asyncio.sleep(wait)
            await _restore_courier_offer_after_snooze(order_id, telegram_id, message_id)
        except asyncio.CancelledError:
            return
        except Exception as e:
            log.warning("courier snooze job failed: %s", e)

    _COURIER_SNOOZE_TASKS[(int(order_id), int(telegram_id))] = asyncio.create_task(_job())


async def handle_broadcast(request: web.Request) -> web.Response:
    """
    POST /api/bot/v1/couriers/broadcast
    """
    if not check_token(request):
        log.warning("broadcast: unauthorized from %s", request.remote)
        return web.Response(status=401, text="unauthorized")

    try:
        req = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    order_id = req.get("order_id")
    courier_ids = req.get("couriers_telegram_ids")
    if not order_id or not courier_ids:
        return web.Response(status=400, text="missing order_id or couriers")

    restaurant_name = req.get("restaurant_name", "")
    pickup_address = req.get("pickup_address", "")
    delivery_address = req.get("delivery_address", "")
    delivery_fee = req.get("delivery_fee", 0.0)
    tips = req.get("tips", 0.0)
    currency = req.get("currency", "GEL")
    created_at = req.get("created_at")
    comment = req.get("comment") or req.get("courier_comment") or ""
    distance_km = req.get("distance_km", req.get("route_distance", 1.5))

    # Баннер 5a: латиница «1.3 km» в одну строку (кириллица «км» рвала зону).
    distance_label = "1.5 km"
    try:
        distance_label = f"{float(distance_km):.1f} km"
    except (TypeError, ValueError):
        if distance_km:
            distance_label = str(distance_km).replace("км", "km").replace("КМ", "km")

    text = format_broadcast_text(
        order_id=order_id,
        restaurant_name=restaurant_name,
        pickup_address=pickup_address,
        delivery_address=delivery_address,
        fee=float(delivery_fee or 0),
        currency=currency,
        created_at=created_at,
        comment=comment,
        distance_km=distance_km,
        tips=float(tips or 0),
    )
    keyboard = make_broadcast_keyboard(int(order_id))

    _COURIER_BROADCAST_FIELDS[int(order_id)] = {
        "pickup_address": pickup_address or restaurant_name or "",
        "dropoff_address": delivery_address or "",
        "fee": float(delivery_fee or 0),
        "missed_payout": f"₾ {float(delivery_fee or 0):.2f}",
    }

    sent = 0
    failed = []
    for cid in courier_ids:
        if cid <= 0:
            continue
        try:
            msg = await send_banner_photo(
                chat_id=cid,
                kind="order_new_courier",
                fields={
                    "pickup_address": pickup_address or restaurant_name,
                    "dropoff_address": delivery_address,
                    "route_distance": distance_label,
                    "courier_payout": f"₾ {float(delivery_fee or 0):.2f}",
                },
                keyboard=keyboard,
                caption=text,
            )
            await db.save_message(order_id, cid, msg.message_id, "courier", "broadcast")
            sent += 1
        except Exception as e:
            log.warning("broadcast: send to courier %d failed: %s", cid, e)
            failed.append(cid)

    log.info("broadcast done: order_id=%d, sent=%d, failed=%d", order_id, sent, len(failed))
    return web.json_response({"ok": True, "sent": sent, "failed": failed})


async def handle_assign(request: web.Request) -> web.Response:
    """
    POST /api/bot/v1/couriers/assign-order
    Чистит UI проигравших курьеров; победителю — кнопка на broadcast-карточке
    (или запасное текстовое сообщение, если карточки нет).
    """
    if not check_token(request):
        log.warning("assign: unauthorized from %s", request.remote)
        return web.Response(status=401, text="unauthorized")

    try:
        req = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    order_id = req.get("order_id")
    winner_tg = req.get("winner_telegram_id")
    if not order_id or not winner_tg:
        return web.Response(status=400, text="missing order_id or winner_telegram_id")

    winner_keyboard = keyboard_for_action("arrived_restaurant", int(order_id))
    winner_message_id = None
    taken_caption = order_taken_caption(order_id)
    taken_fields = order_taken_banner_fields(int(order_id))

    # 1) Победитель: только edit карточки. Не слать второе сообщение —
    # accept-callback уже ставит кнопку; assign часто приходит после смены kind.
    try:
        all_msgs = await db.get_messages_for_order(order_id)
        winner_card = next(
            (
                m for m in all_msgs
                if m["telegram_id"] == winner_tg
                and m.get("kind") in ("broadcast", "tracking", "winner")
            ),
            None,
        )
        if winner_card:
            mid = winner_card["message_id"]
            try:
                await bot.edit_message_reply_markup(
                    chat_id=winner_tg,
                    message_id=mid,
                    reply_markup=winner_keyboard,
                )
            except Exception as e:
                err = str(e).lower()
                # Кнопку уже поставил accept-callback — это ок, дубль не шлём.
                if "not modified" not in err and "message is not modified" not in err:
                    log.warning("assign: edit winner markup failed: %s", e)
            winner_message_id = mid
            await db.update_kind(order_id, winner_tg, "tracking")
        else:
            log.warning(
                "assign: no card for winner tg=%s order=%s — skip duplicate text",
                winner_tg, order_id,
            )
    except Exception as e:
        log.error("assign: winner UI failed: %s", e)
        return web.Response(status=502, text="telegram send failed")

    # 2) Проигравшие: баннер 7a + снять кнопки
    losers = req.get("losers_telegram_ids")
    if not losers:
        losers = await db.get_broadcast_recipients(order_id)
        # Если winners уже tracking — добираем recipients из всех записей заказа.
        if not losers:
            losers = [
                m["telegram_id"] for m in (await db.get_messages_for_order(order_id))
                if m.get("role") == "courier"
            ]

    notified = 0
    try:
        msgs = await db.get_messages_for_order(order_id)
    except Exception:
        msgs = []

    for loser_id in losers:
        if loser_id == winner_tg:
            continue
        cancel_courier_snooze(int(order_id), int(loser_id))
        for m in msgs:
            if m["telegram_id"] != loser_id:
                continue
            if m.get("kind") not in ("broadcast", "tracking"):
                continue
            mid = m["message_id"]
            try:
                ok = await edit_banner_media(
                    chat_id=loser_id,
                    message_id=mid,
                    kind="order_taken_courier",
                    fields=taken_fields,
                    caption=taken_caption,
                    keyboard=None,
                )
                if ok:
                    await db.update_kind(order_id, loser_id, "taken")
                    notified += 1
                else:
                    raise RuntimeError("edit_banner_media returned False")
            except Exception:
                try:
                    await bot.edit_message_caption(
                        chat_id=loser_id,
                        message_id=mid,
                        caption=taken_caption,
                        reply_markup=None,
                        parse_mode=ParseMode.HTML,
                    )
                    await db.update_kind(order_id, loser_id, "taken")
                    notified += 1
                except Exception:
                    try:
                        await bot.edit_message_reply_markup(
                            chat_id=loser_id,
                            message_id=mid,
                            reply_markup=None,
                        )
                        notified += 1
                    except Exception as e2:
                        log.warning("assign: clear loser %d failed: %s", loser_id, e2)

    _COURIER_BROADCAST_FIELDS.pop(int(order_id), None)

    log.info(
        "assign done: order_id=%d, winner_tg=%d, losers_notified=%d",
        order_id, winner_tg, notified,
    )
    return web.json_response({"ok": True, "winner_message_id": winner_message_id, "losers_notified": notified})


async def handle_sync_state(request: web.Request) -> web.Response:
    """
    POST /api/bot/v1/orders/sync-state
    """
    if not check_token(request):
        log.warning("sync-state: unauthorized from %s", request.remote)
        return web.Response(status=401, text="unauthorized")

    try:
        req = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    order_id = req.get("order_id")
    user_tg = req.get("user_telegram_id")
    if not order_id or not user_tg:
        return web.Response(status=400, text="missing order_id or user_telegram_id")

    # Find live message: prefer kind='tracking', fallback to 'winner'
    msgs = await db.get_messages_for_order(order_id)
    target = None
    for m in msgs:
        if m["telegram_id"] == user_tg:
            if m["kind"] == "tracking":
                target = m
                break
            if m["kind"] == "winner" and target is None:
                target = m

    if not target:
        log.warning("sync-state: no live message found for order %d user %d", order_id, user_tg)
        return web.Response(status=404, text="no message to sync")

    display_text = req.get("display_text", "")
    next_action = req.get("next_allowed_action", "")
    kb = keyboard_for_action(next_action, order_id) if next_action else None

    # Не затираем карточку заказа — только обновляем кнопки (как у ресторана).
    try:
        await bot.edit_message_reply_markup(
            chat_id=user_tg,
            message_id=target["message_id"],
            reply_markup=kb,
        )
    except Exception as e:
        # Fallback: текстовое сообщение без photo-caption
        try:
            if display_text:
                await bot.edit_message_text(
                    chat_id=user_tg,
                    message_id=target["message_id"],
                    text=display_text,
                    reply_markup=kb,
                    parse_mode=ParseMode.HTML,
                )
            else:
                raise e
        except Exception as e2:
            log.error("sync-state: edit message failed: %s", e2)
            return web.Response(status=502, text="telegram edit failed")

    if target["kind"] != "tracking":
        await db.update_kind(order_id, user_tg, "tracking")

    log.info("sync-state applied: order_id=%d, user_tg=%d, next_action=%s", order_id, user_tg, next_action)
    return web.json_response({"ok": True})


async def handle_cancel(request: web.Request) -> web.Response:
    """
    POST /api/bot/v1/orders/cancel
    """
    if not check_token(request):
        log.warning("cancel: unauthorized from %s", request.remote)
        return web.Response(status=401, text="unauthorized")

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    order_id = data.get("order_id")
    total_amount = data.get("total_amount") or 0
    currency = data.get("currency") or "сом"
    items = data.get("items") or []
    if not order_id:
        return web.Response(status=400, text="order_id required")

    # Как на баннере нового заказа — сумма позиций (без доставки/сервиса).
    food_total = _items_food_total(items)
    if food_total > 0:
        cancel_amount = food_total
    else:
        try:
            raw_total = float(total_amount or 0)
        except (TypeError, ValueError):
            raw_total = 0.0
        try:
            fees = (
                float(data.get("delivery_fee") or 0)
                + float(data.get("service_fee") or 0)
                + float(data.get("tips") or 0)
            )
        except (TypeError, ValueError):
            fees = 0.0
        cancel_amount = max(0.0, raw_total - fees)
    cancel_total = _fmt_banner_lari(cancel_amount)
    cancel_time = datetime.now().strftime("%H:%M")

    # Если отмену инициировал ресторан — не подменяем текст «администратором».
    rest_meta = _RESTAURANT_CANCEL_META.pop(int(order_id), None)
    if rest_meta and not rest_meta.get("_pending_reason"):
        by_label = rest_meta.get("cancelled_by") or "Ресторан"
        reason = rest_meta.get("reason") or "Отклонён рестораном"
        cancel_total = rest_meta.get("cancel_total") or cancel_total
        cancel_time = rest_meta.get("cancel_time") or cancel_time
        new_caption = rest_meta.get("caption") or format_restaurant_cancel_caption(
            order_id, reason=reason, by="restaurant"
        )
        banner_reason = reason
        banner_by = by_label
        log.info("Order #%d cancel from restaurant reason=%s", order_id, reason)
    else:
        # Чистый admin/global cancel (или ещё не завершённый delayable-флоу).
        if rest_meta and rest_meta.get("_pending_reason"):
            # вернём pending — это не финальная отмена
            _RESTAURANT_CANCEL_META[int(order_id)] = rest_meta
        new_caption = format_restaurant_cancel_caption(order_id, by="admin")
        banner_reason = "Отменен администратором"
        banner_by = "Администратор"
        log.info("Order #%d cancelled globally (admin/service). Updating bot messages...", order_id)

    # Find all messages associated with this order
    msgs = await db.get_messages_for_order(order_id)
    if not msgs:
        log.warning("cancel: no bot messages found for order %d", order_id)
        return web.json_response({"ok": True, "count": 0})

    count = 0
    for m in msgs:
        chat_id = m["telegram_id"]
        msg_id = m["message_id"]
        role = m["role"]
        kind = m["kind"]

        try:
            if role == "restaurant":
                try:
                    await edit_banner_media(
                        chat_id=chat_id,
                        message_id=msg_id,
                        kind="order_cancelled_restaurant",
                        fields={
                            "order_number": f"#{order_id}",
                            "cancel_total": cancel_total,
                            "cancel_time": cancel_time,
                            "cancel_reason": banner_reason,
                            "cancelled_by": banner_by,
                        },
                        caption=new_caption,
                        keyboard=None,
                    )
                    count += 1
                except Exception as ex:
                    log.error("cancel restaurant msg %d failed: %s", msg_id, ex)
            elif role == "courier":
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=format_courier_cancel_caption(order_id),
                        reply_markup=None,
                        parse_mode=ParseMode.HTML,
                    )
                    count += 1
                except Exception as ex:
                    log.error("cancel courier msg %d failed: %s", msg_id, ex)
        except Exception as e:
            log.error("cancel failed for message %d: %s", msg_id, e)

    return web.json_response({"ok": True, "count": count})


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def handle_partners_list(request: web.Request) -> web.Response:
    """GET /api/bot/v1/partners — список зарегистрированных партнёров."""
    if not check_token(request):
        return web.Response(status=401, text="unauthorized")
    partners = await db.list_partners()
    return web.json_response(partners)


async def handle_courier_arrived(request: web.Request) -> web.Response:
    """
    POST /api/bot/v1/restaurant/courier-arrived
    Принимает уведомление о прибытии курьера в ресторан и шлёт его партнёру в Telegram.
    """
    if not check_token(request):
        log.warning("courier-arrived: unauthorized from %s", request.remote)
        return web.Response(status=401, text="unauthorized")

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    order_id = data.get("order_id")
    restaurant_telegram_id = data.get("restaurant_telegram_id")
    courier_name = data.get("courier_name") or "Курьер"

    if not order_id or not restaurant_telegram_id:
        return web.Response(status=400, text="order_id and restaurant_telegram_id required")

    log.info("Courier arrived: order_id=%d, restaurant_tg=%d, courier=%s", order_id, restaurant_telegram_id, courier_name)

    text = (
        f'{ce("5384312315279612142", "📍")} <b>Курьер на месте!</b>\n'
        f"Курьер <b>{html.escape(str(courier_name))}</b> прибыл в ресторан "
        f"за заказом <b>#{order_id}</b>."
    )
    try:
        await bot.send_message(
            chat_id=restaurant_telegram_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        log.warning("courier-arrived: failed to send telegram notification: %s", e)

    return web.json_response({"ok": True})


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/healthz", handle_health)
    app.router.add_post("/api/bot/v1/restaurant/new-order", handle_new_order)
    app.router.add_post("/api/bot/v1/restaurant/courier-arrived", handle_courier_arrived)
    app.router.add_post("/api/bot/v1/couriers/broadcast", handle_broadcast)
    app.router.add_post("/api/bot/v1/couriers/assign-order", handle_assign)
    app.router.add_post("/api/bot/v1/orders/sync-state", handle_sync_state)
    app.router.add_post("/api/bot/v1/orders/cancel", handle_cancel)
    app.router.add_get("/api/bot/v1/partners", handle_partners_list)
    return app


# ─────────────────────────────────────────────
#  Точка входа
# ─────────────────────────────────────────────

async def on_startup(bot: Bot, base_url: str):
    await bot.set_webhook(f"{base_url}/api/telegram-webhook")
    log.info(f"Webhook set to {base_url}/api/telegram-webhook")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    log.info("Webhook deleted")

async def main():
    global db, bot, BOT_PUBLIC_URL

    log.info("=" * 50)
    log.info("MestiDelivery Partners Bot starting...")
    log.info("HTTP server: %s:%d", HTTP_HOST, HTTP_PORT)
    log.info("Backend URL: %s", BACKEND_URL)
    log.info("=" * 50)

    # База данных
    db = Database(DB_PATH)
    await db.connect()

    # Сброс всех курьеров в офлайн убран, чтобы избежать рассинхронизации клавиатур
    # и статусов при перезапусках бота в процессе обновления.
    log.info("Courier status reset on startup bypassed")

    # Telegram бот
    import socket
    from aiogram.client.session.aiohttp import AiohttpSession
    class IPv4OnlyAiohttpSession(AiohttpSession):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._connector_init["family"] = socket.AF_INET

    session = IPv4OnlyAiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session, default=None)
    dp = Dispatcher(storage=MemoryStorage())

    # Set bot commands for the Menu button
    from aiogram.types import BotCommand
    try:
        await bot.set_my_commands([
            BotCommand.model_validate({
                "command": "start",
                "description": "Запустить бота / Главное меню",
                "icon_custom_emoji_id": "5384244502040975393",
            }),
            BotCommand.model_validate({
                "command": "reset",
                "description": "Сбросить профиль (Начать заново)",
                "icon_custom_emoji_id": "5384518714227990146",
            }),
        ])
        log.info("Bot commands set successfully")
    except Exception as e:
        log.warning("Failed to set bot commands: %s", e)

    # Регистрация хэндлеров
    dp.include_router(router)

    from admin_panel import register_admin_handlers, sla_watch_loop

    async def _open_admin_payouts(chat_id: int, message_id: int):
        await send_admin_payout_request(chat_id, message_id, 0)

    register_admin_handlers(
        router,
        get_db=lambda: db,
        get_bot=lambda: bot,
        admin_tg_id=ADMIN_TG_ID,
        order_db_paths=ORDER_DB_PATHS,
        catalog_db_paths=CATALOG_DB_PATHS,
        auth_db_paths=BACKEND_DB_PATHS,
        partners_db_path=DB_PATH,
        emoji=CUSTOM_EMOJI,
        open_payouts=_open_admin_payouts,
    )
    sla_stop = asyncio.Event()
    sla_task = asyncio.create_task(sla_watch_loop(sla_stop))
    log.info("Admin panel + SLA watcher registered")

    # Авто-подтягивание Webhook (ngrok)
    if not BOT_PUBLIC_URL:
        try:
            from pyngrok import ngrok
            http_tunnel = ngrok.connect(HTTP_PORT)
            BOT_PUBLIC_URL = http_tunnel.public_url
            log.info(f"ngrok tunnel created: {BOT_PUBLIC_URL}")
        except Exception as e:
            log.warning(f"ngrok failed to start or not installed: {e}. Falling back to long polling.")

    use_webhook = bool(BOT_PUBLIC_URL)

    if use_webhook:
        dp.startup.register(lambda bot: on_startup(bot, BOT_PUBLIC_URL))
        dp.shutdown.register(on_shutdown)
    else:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            log.info("Webhook deleted for polling fallback")
        except Exception:
            pass

    # HTTP сервер
    app = make_app()

    if use_webhook:
        # Интеграция aiogram вебхука в aiohttp сервер
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=SECURITY_TOKEN,
        )
        webhook_requests_handler.register(app, path="/api/telegram-webhook")
        setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HTTP_HOST, HTTP_PORT)
    await site.start()
    log.info("HTTP server started on %s:%d", HTTP_HOST, HTTP_PORT)

    try:
        if use_webhook:
            # Держим процесс aiohttp запущенным
            while True:
                await asyncio.sleep(3600)
        else:
            log.info("Starting Telegram polling...")
            await dp.start_polling(
                bot,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
            )
    finally:
        log.info("Shutting down...")
        sla_stop.set()
        try:
            await asyncio.wait_for(sla_task, timeout=3)
        except Exception:
            sla_task.cancel()
        await runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
