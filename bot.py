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
import base64
import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

GEORGIA_TZ = timezone(timedelta(hours=4))

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramRetryAfter
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
from partner_i18n import (
    COURIER_REFUSE_I18N_KEYS,
    REJECT_I18N_KEYS,
    ui_text,
)


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


# Data-dir бэкенда: на проде задаётся BACKEND_DATA_DIR (docker volume),
# локально — build/data. Без env на Linux путь Windows → баланс всегда 0.
_BACKEND_DATA = (
    os.getenv("BACKEND_DATA_DIR")
    or os.getenv("MESTIGO_DATA_DIR")
    or (r"c:\MestiDelivery\Backend GO\Backend\build\data" if os.name == "nt" else "/var/lib/docker/volumes/mestigo_sqlite_data/_data")
)
BACKEND_DB_PATHS = [os.path.join(_BACKEND_DATA, "auth.db")]
CATALOG_DB_PATHS = [os.path.join(_BACKEND_DATA, "catalog.db")]
ORDER_DB_PATHS = [os.path.join(_BACKEND_DATA, "order.db")]

# Доли от суммы позиций (items = total - delivery_fee - service_fee - tips) после delivered.
PLATFORM_ITEMS_COMMISSION = 0.10  # 10% сервису
RESTAURANT_ITEMS_SHARE = 0.90     # 90% ресторану
# delivery_fee → 100% курьеру; tips → 100% курьеру; service_fee → 100% сервису.

SECURITY_HEADER = "X-Bot-Security-Token"

# Telegram ID владельца — панель /admin только по этому ID
ADMIN_TG_ID: int = int(os.getenv("ADMIN_TELEGRAM_ID", "5564438585") or "5564438585")
if ADMIN_TG_ID <= 0:
    ADMIN_TG_ID = 5564438585

JWT_SECRET: str = os.getenv("JWT_SECRET", "super_secure_secret_change_me_in_production_12345")


def make_hs256_jwt(payload: dict, secret: str = JWT_SECRET) -> str:
    """Generates standard HS256 JWT access token compatible with Mestigo Gateway."""
    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = b64url(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def connect_sqlite_wal(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
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

CREATE TABLE IF NOT EXISTS courier_snooze_jobs (
    order_id     INTEGER NOT NULL,
    telegram_id  INTEGER NOT NULL,
    message_id   INTEGER NOT NULL,
    wake_at      REAL    NOT NULL,
    PRIMARY KEY (order_id, telegram_id)
);

CREATE TABLE IF NOT EXISTS courier_broadcast_cache (
    order_id   INTEGER PRIMARY KEY,
    payload    TEXT    NOT NULL,
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS courier_assign_reminders (
    order_id INTEGER NOT NULL,
    stage    INTEGER NOT NULL,
    wake_at  REAL    NOT NULL,
    PRIMARY KEY (order_id, stage)
);

CREATE TABLE IF NOT EXISTS courier_blocks (
    telegram_id INTEGER PRIMARY KEY,
    until_ts    REAL    NOT NULL,
    reason      TEXT    NOT NULL DEFAULT '',
    created_by  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS synced_orders (
    id              INTEGER PRIMARY KEY,
    restaurant_id   TEXT    NOT NULL DEFAULT '',
    courier_id      INTEGER NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'new',
    total           REAL    NOT NULL DEFAULT 0.0,
    delivery_fee    REAL    NOT NULL DEFAULT 0.0,
    customer_name   TEXT    NOT NULL DEFAULT '',
    phone           TEXT    NOT NULL DEFAULT '',
    address         TEXT    NOT NULL DEFAULT '',
    comment         TEXT    NOT NULL DEFAULT '',
    items_json      TEXT    NOT NULL DEFAULT '[]',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_synced_orders_rest ON synced_orders(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_synced_orders_cour ON synced_orders(courier_id);
CREATE INDEX IF NOT EXISTS idx_synced_orders_stat ON synced_orders(status);
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
        try:
            # Режим запары (rush mode): 0 = auto (18-22), 1 = forced on, -1 = forced off
            await self._db.execute("ALTER TABLE partners ADD COLUMN rush_mode INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            await self._db.execute("ALTER TABLE admin_sla_alerts ADD COLUMN message_id INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS courier_snooze_jobs (
                order_id     INTEGER NOT NULL,
                telegram_id  INTEGER NOT NULL,
                message_id   INTEGER NOT NULL,
                wake_at      REAL    NOT NULL,
                PRIMARY KEY (order_id, telegram_id)
            );
            CREATE TABLE IF NOT EXISTS courier_broadcast_cache (
                order_id   INTEGER PRIMARY KEY,
                payload    TEXT    NOT NULL,
                updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS courier_assign_reminders (
                order_id INTEGER NOT NULL,
                stage    INTEGER NOT NULL,
                wake_at  REAL    NOT NULL,
                PRIMARY KEY (order_id, stage)
            );
            CREATE TABLE IF NOT EXISTS courier_blocks (
                telegram_id INTEGER PRIMARY KEY,
                until_ts    REAL    NOT NULL,
                reason      TEXT    NOT NULL DEFAULT '',
                created_by  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
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
        rid = str(restaurant_id or "").strip()
        if not rid:
            return None
        async with self._db.execute(
            "SELECT * FROM partners WHERE restaurant_id = ?", (rid,)
        ) as cur:
            row = await cur.fetchone()
            if row and row["telegram_id"]:
                return dict(row)

        def _check_auth():
            for path in BACKEND_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    r = conn.execute(
                        "SELECT id, username, telegram_id, restaurant_id FROM admin_users "
                        "WHERE restaurant_id = ? AND telegram_id IS NOT NULL AND telegram_id != ''",
                        (rid,),
                    ).fetchone()
                    conn.close()
                    if r and r[2]:
                        return {"telegram_id": int(r[2]), "restaurant_id": rid, "restaurant_name": r[1]}
                except Exception:
                    pass
            return None

        auth_partner = await asyncio.to_thread(_check_auth)
        if auth_partner:
            try:
                await self.register_partner(
                    auth_partner["telegram_id"],
                    rid,
                    auth_partner.get("restaurant_name") or "",
                )
            except Exception:
                pass
            return auth_partner

        return None

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

    async def get_partner_rush_mode(self, restaurant_id: str) -> int:
        if not restaurant_id:
            return 0
        try:
            async with self._db.execute(
                "SELECT rush_mode FROM partners WHERE restaurant_id = ?", (str(restaurant_id),)
            ) as cur:
                row = await cur.fetchone()
                if row and row["rush_mode"] is not None:
                    return int(row["rush_mode"])
        except Exception as e:
            log.error("get_partner_rush_mode error: %s", e)
        return 0

    async def set_partner_rush_mode(self, restaurant_id: str, mode: int) -> bool:
        if not restaurant_id:
            return False
        try:
            await self._db.execute(
                "UPDATE partners SET rush_mode = ? WHERE restaurant_id = ?",
                (mode, str(restaurant_id)),
            )
            await self._db.commit()
            return True
        except Exception as e:
            log.error("set_partner_rush_mode error: %s", e)
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

    async def upsert_courier_broadcast_cache(self, order_id: int, payload: dict) -> None:
        try:
            await self._db.execute(
                """INSERT INTO courier_broadcast_cache (order_id, payload, updated_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(order_id) DO UPDATE SET
                     payload = excluded.payload,
                     updated_at = excluded.updated_at""",
                (int(order_id), json.dumps(payload, ensure_ascii=False, default=str)),
            )
            await self._db.commit()
        except Exception as e:
            log.error("upsert_courier_broadcast_cache error: %s", e)

    async def get_courier_broadcast_cache(self, order_id: int) -> dict:
        try:
            async with self._db.execute(
                "SELECT payload FROM courier_broadcast_cache WHERE order_id = ?",
                (int(order_id),),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return {}
            data = json.loads(row["payload"] or "{}")
            return data if isinstance(data, dict) else {}
        except Exception as e:
            log.error("get_courier_broadcast_cache error: %s", e)
            return {}

    async def delete_courier_broadcast_cache(self, order_id: int) -> None:
        try:
            await self._db.execute(
                "DELETE FROM courier_broadcast_cache WHERE order_id = ?",
                (int(order_id),),
            )
            await self._db.commit()
        except Exception as e:
            log.error("delete_courier_broadcast_cache error: %s", e)

    async def upsert_courier_snooze(
        self, order_id: int, telegram_id: int, message_id: int, wake_at: float
    ) -> None:
        try:
            await self._db.execute(
                """INSERT INTO courier_snooze_jobs (order_id, telegram_id, message_id, wake_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(order_id, telegram_id) DO UPDATE SET
                     message_id = excluded.message_id,
                     wake_at = excluded.wake_at""",
                (int(order_id), int(telegram_id), int(message_id), float(wake_at)),
            )
            await self._db.commit()
        except Exception as e:
            log.error("upsert_courier_snooze error: %s", e)

    async def delete_courier_snooze(self, order_id: int, telegram_id: int) -> None:
        try:
            await self._db.execute(
                "DELETE FROM courier_snooze_jobs WHERE order_id = ? AND telegram_id = ?",
                (int(order_id), int(telegram_id)),
            )
            await self._db.commit()
        except Exception as e:
            log.error("delete_courier_snooze error: %s", e)

    async def list_pending_courier_snoozes(self) -> list[dict]:
        try:
            async with self._db.execute(
                "SELECT order_id, telegram_id, message_id, wake_at FROM courier_snooze_jobs"
            ) as cur:
                rows = await cur.fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            log.error("list_pending_courier_snoozes error: %s", e)
            return []

    async def upsert_assign_reminder(self, order_id: int, stage: int, wake_at: float) -> None:
        try:
            await self._db.execute(
                """INSERT INTO courier_assign_reminders (order_id, stage, wake_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(order_id, stage) DO UPDATE SET wake_at = excluded.wake_at""",
                (int(order_id), int(stage), float(wake_at)),
            )
            await self._db.commit()
        except Exception as e:
            log.error("upsert_assign_reminder error: %s", e)

    async def delete_assign_reminders(self, order_id: int, stage: int | None = None) -> None:
        try:
            if stage is None:
                await self._db.execute(
                    "DELETE FROM courier_assign_reminders WHERE order_id = ?",
                    (int(order_id),),
                )
            else:
                await self._db.execute(
                    "DELETE FROM courier_assign_reminders WHERE order_id = ? AND stage = ?",
                    (int(order_id), int(stage)),
                )
            await self._db.commit()
        except Exception as e:
            log.error("delete_assign_reminders error: %s", e)

    async def list_assign_reminders(self) -> list[dict]:
        try:
            async with self._db.execute(
                "SELECT order_id, stage, wake_at FROM courier_assign_reminders"
            ) as cur:
                rows = await cur.fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            log.error("list_assign_reminders error: %s", e)
            return []

    async def sla_alert_sent(self, order_id: int, alert_type: str) -> bool:
        try:
            async with self._db.execute(
                "SELECT 1 FROM admin_sla_alerts WHERE order_id = ? AND alert_type = ?",
                (int(order_id), str(alert_type)),
            ) as cur:
                return await cur.fetchone() is not None
        except Exception as e:
            log.error("sla_alert_sent error: %s", e)
            return False

    async def mark_sla_alert(self, order_id: int, alert_type: str, message_id: int = 0) -> None:
        try:
            await self._db.execute(
                """INSERT INTO admin_sla_alerts (order_id, alert_type, message_id) VALUES (?, ?, ?)
                   ON CONFLICT(order_id, alert_type) DO UPDATE SET message_id = excluded.message_id""",
                (int(order_id), str(alert_type), int(message_id)),
            )
            await self._db.commit()
        except Exception as e:
            log.error("mark_sla_alert error: %s", e)

    async def get_sla_alerts(self, order_id: int) -> list[int]:
        try:
            async with self._db.execute(
                "SELECT message_id FROM admin_sla_alerts WHERE order_id = ? AND message_id > 0",
                (int(order_id),),
            ) as cur:
                rows = await cur.fetchall()
            return [int(r["message_id"]) for r in rows]
        except Exception as e:
            log.error("get_sla_alerts error: %s", e)
            return []

    async def get_courier_block(self, telegram_id: int) -> Optional[dict]:
        try:
            async with self._db.execute(
                "SELECT telegram_id, until_ts, reason, created_by, created_at "
                "FROM courier_blocks WHERE telegram_id = ?",
                (int(telegram_id),),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return None
            data = dict(row)
            if float(data.get("until_ts") or 0) <= time.time():
                await self.clear_courier_block(int(telegram_id))
                return None
            return data
        except Exception as e:
            log.error("get_courier_block error: %s", e)
            return None

    async def is_courier_blocked(self, telegram_id: int) -> bool:
        return (await self.get_courier_block(telegram_id)) is not None

    async def set_courier_block(
        self,
        telegram_id: int,
        *,
        until_ts: float,
        reason: str = "",
        created_by: int = 0,
    ) -> bool:
        try:
            await self._db.execute(
                """INSERT INTO courier_blocks (telegram_id, until_ts, reason, created_by, created_at)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(telegram_id) DO UPDATE SET
                     until_ts = excluded.until_ts,
                     reason = excluded.reason,
                     created_by = excluded.created_by,
                     created_at = excluded.created_at""",
                (int(telegram_id), float(until_ts), (reason or "")[:200], int(created_by)),
            )
            await self._db.commit()
            return True
        except Exception as e:
            log.error("set_courier_block error: %s", e)
            return False

    async def clear_courier_block(self, telegram_id: int) -> bool:
        try:
            await self._db.execute(
                "DELETE FROM courier_blocks WHERE telegram_id = ?",
                (int(telegram_id),),
            )
            await self._db.commit()
            return True
        except Exception as e:
            log.error("clear_courier_block error: %s", e)
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

    async def set_user_language(self, telegram_id: int, language: str) -> bool:
        try:
            await self._db.execute("UPDATE bot_users SET language = ? WHERE telegram_id = ?", (language, telegram_id))
            await self._db.commit()
            return True
        except Exception as e:
            log.error("set_user_language error: %s", e)
            return False

    async def get_all_bot_users(self) -> list[dict]:
        async with self._db.execute("SELECT * FROM bot_users") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def save_synced_order(self, order_data: dict) -> bool:
        try:
            oid = int(order_data.get("id") or order_data.get("order_id") or 0)
            if oid <= 0:
                return False
            rid = str(order_data.get("restaurant_id") or "")
            cid = int(order_data.get("courier_id") or 0)
            st = str(order_data.get("status") or "new")
            tot = float(order_data.get("total") or 0.0)
            fee = float(order_data.get("delivery_fee") or 0.0)
            cname = str(order_data.get("customer_name") or "")
            phone = str(order_data.get("phone") or "")
            addr = str(order_data.get("address") or "")
            comm = str(order_data.get("comment") or "")
            items = order_data.get("items") or []
            items_str = json.dumps(items, ensure_ascii=False) if not isinstance(items, str) else items
            c_at = str(order_data.get("created_at") or "")

            await self._db.execute(
                """INSERT INTO synced_orders (id, restaurant_id, courier_id, status, total, delivery_fee, customer_name, phone, address, comment, items_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(NULLIF(?, ''), datetime('now')), datetime('now'))
                   ON CONFLICT(id) DO UPDATE SET
                     restaurant_id = CASE WHEN excluded.restaurant_id != '' THEN excluded.restaurant_id ELSE synced_orders.restaurant_id END,
                     courier_id = CASE WHEN excluded.courier_id > 0 THEN excluded.courier_id ELSE synced_orders.courier_id END,
                     status = excluded.status,
                     total = CASE WHEN excluded.total > 0 THEN excluded.total ELSE synced_orders.total END,
                     delivery_fee = CASE WHEN excluded.delivery_fee > 0 THEN excluded.delivery_fee ELSE synced_orders.delivery_fee END,
                     customer_name = CASE WHEN excluded.customer_name != '' THEN excluded.customer_name ELSE synced_orders.customer_name END,
                     phone = CASE WHEN excluded.phone != '' THEN excluded.phone ELSE synced_orders.phone END,
                     address = CASE WHEN excluded.address != '' THEN excluded.address ELSE synced_orders.address END,
                     comment = CASE WHEN excluded.comment != '' THEN excluded.comment ELSE synced_orders.comment END,
                     items_json = CASE WHEN excluded.items_json != '[]' THEN excluded.items_json ELSE synced_orders.items_json END,
                     updated_at = datetime('now')""",
                (oid, rid, cid, st, tot, fee, cname, phone, addr, comm, items_str, c_at),
            )
            await self._db.commit()
            return True
        except Exception as e:
            log.error("save_synced_order error: %s", e)
            return False

    async def update_synced_order_status(self, order_id: int, status: str, courier_id: int = 0) -> bool:
        try:
            if courier_id > 0:
                await self._db.execute(
                    "UPDATE synced_orders SET status = ?, courier_id = ?, updated_at = datetime('now') WHERE id = ?",
                    (status, courier_id, int(order_id)),
                )
            else:
                await self._db.execute(
                    "UPDATE synced_orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
                    (status, int(order_id)),
                )
            await self._db.commit()
            return True
        except Exception as e:
            log.error("update_synced_order_status error: %s", e)
            return False

    async def get_synced_orders(self, restaurant_id: str = "", courier_id: int = 0, limit: int = 100) -> list[dict]:
        try:
            if restaurant_id:
                async with self._db.execute(
                    "SELECT * FROM synced_orders WHERE restaurant_id = ? ORDER BY id DESC LIMIT ?",
                    (restaurant_id, limit),
                ) as cur:
                    rows = await cur.fetchall()
                    return [dict(r) for r in rows]
            elif courier_id > 0:
                async with self._db.execute(
                    "SELECT * FROM synced_orders WHERE courier_id = ? OR (courier_id = 0 AND status IN ('confirmed', 'accepted', 'preparing', 'ready')) ORDER BY id DESC LIMIT ?",
                    (courier_id, limit),
                ) as cur:
                    rows = await cur.fetchall()
                    return [dict(r) for r in rows]
            else:
                async with self._db.execute(
                    "SELECT * FROM synced_orders ORDER BY id DESC LIMIT ?",
                    (limit,),
                ) as cur:
                    rows = await cur.fetchall()
                    return [dict(r) for r in rows]
        except Exception as e:
            log.error("get_synced_orders error: %s", e)
            return []

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
        """Все id курьера по TG во всех auth.db (с fallback по username из bot_users)."""
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
                except Exception as e:
                    log.error("Error get_courier_ids_by_telegram: %s", e)
            return ids

        ids = await asyncio.to_thread(_query)
        if not ids:
            # Fallback: поиск по backend_username курьера из bot_users
            user = await self.get_bot_user(telegram_id)
            if user and user.get("role") == "courier" and user.get("backend_username"):
                username = user["backend_username"]
                def _query_by_user():
                    u_ids: list[int] = []
                    for path in BACKEND_DB_PATHS:
                        if not os.path.exists(path):
                            continue
                        try:
                            conn = connect_sqlite_wal(path)
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT id FROM admin_users WHERE username = ? AND role = 'courier'",
                                (username,),
                            )
                            for row in cursor.fetchall():
                                cid = int(row[0])
                                if cid not in u_ids:
                                    u_ids.append(cid)
                            # Заодно привязываем telegram_id в auth.db
                            if u_ids:
                                cursor.execute(
                                    "UPDATE admin_users SET telegram_id = ? WHERE username = ?",
                                    (str(telegram_id), username),
                                )
                                conn.commit()
                            conn.close()
                        except Exception as e:
                            log.error("Error get_courier_ids fallback by username: %s", e)
                    return u_ids
                ids = await asyncio.to_thread(_query_by_user)
        return ids

    @staticmethod
    def _items_amount_sql() -> str:
        # items = total + discount - delivery - service - tips (скидку на доставку компенсирует сервис, курьер получает 100% базы)
        return (
            "MAX(0, COALESCE(total, 0) + COALESCE(discount, 0) - COALESCE(delivery_fee, 0) "
            "- COALESCE(service_fee, 0) - COALESCE(tips, 0))"
        )

    @staticmethod
    def _restaurant_income_expr() -> str:
        # ресторан получает 85% items (комиссия сервиса 15%)
        return f"SUM({RESTAURANT_ITEMS_SHARE} * {Database._items_amount_sql()})"

    @staticmethod
    def _courier_income_expr() -> str:
        # 100% delivery_fee + 100% tips (без комиссии сервиса)
        return "SUM(COALESCE(delivery_fee, 0) + COALESCE(tips, 0))"

    @staticmethod
    def _platform_income_expr() -> str:
        # 15% items + 100% service_fee
        return (
            f"SUM({PLATFORM_ITEMS_COMMISSION} * {Database._items_amount_sql()} "
            "+ COALESCE(service_fee, 0))"
        )

    @staticmethod
    def _delivered_status_sql() -> str:
        return "lower(status) = 'delivered'"

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
                        "WHERE restaurant_id = ? AND lower(status) = 'delivered' "
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
                        "WHERE restaurant_id = ? AND lower(status) = 'delivered'",
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
                        f"WHERE courier_id IN ({placeholders}) AND lower(status) = 'delivered' "
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
                        f"WHERE courier_id IN ({placeholders}) AND lower(status) = 'delivered'",
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
                        f"SELECT {expr} FROM orders WHERE lower(status) = 'delivered' "
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
                        f"SELECT {expr} FROM orders WHERE lower(status) = 'delivered'"
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

    async def create_payout_request(self, partner_id: str, role: str, amount: float) -> Optional[int]:
        try:
            cur = await self._db.execute(
                "INSERT INTO payout_requests (partner_id, role, amount) VALUES (?, ?, ?)",
                (str(partner_id), role, amount)
            )
            await self._db.commit()
            return cur.lastrowid
        except Exception as e:
            log.error(f"Error creating payout request: {e}")
            return None

    async def get_partner_pending_request(self, partner_id: str, role: str) -> Optional[dict]:
        try:
            async with self._db.execute(
                "SELECT id, amount, created_at FROM payout_requests WHERE partner_id = ? AND role = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
                (str(partner_id), role)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            log.error(f"Error getting pending payout request: {e}")
            return None

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


def make_order_keyboard(order_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для нового заказа: Принять / Отклонить + Подробности."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_accept"),
                    callback_data=f"accept_{order_id}",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_reject"),
                    callback_data=f"reject_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_open_details"),
                    web_app=WebAppInfo(url=miniapp_page_url(order_id=order_id)),
                    icon_custom_emoji_id="5384138412053796842",
                )
            ],
        ]
    )


# Окна принятия заказа (баннер + caption + SLA).
RESTAURANT_ACCEPT_MIN = 5   # ресторану ~5 минут
COURIER_ACCEPT_MIN = 5      # курьеру 5 минут на принятие оффера


def _format_georgia_time(value) -> str:
    """Форматирует timestamp / ISO / SQLite время в HH:MM по Грузии (UTC+4)."""
    now_geo = datetime.now(GEORGIA_TZ)
    if not value:
        return now_geo.strftime("%H:%M")
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(GEORGIA_TZ).strftime("%H:%M")
        except Exception:
            return now_geo.strftime("%H:%M")
    raw = str(value).strip()
    try:
        if "T" in raw or "+" in raw or "Z" in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(GEORGIA_TZ).strftime("%H:%M")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%H:%M"):
            try:
                dt = datetime.strptime(raw, fmt)
                if fmt == "%H:%M":
                    return raw
                dt = dt.replace(tzinfo=timezone.utc).astimezone(GEORGIA_TZ)
                return dt.strftime("%H:%M")
            except ValueError:
                continue
    except Exception:
        pass
    return now_geo.strftime("%H:%M")


def _format_order_time(value, *, minutes: int = RESTAURANT_ACCEPT_MIN) -> tuple[str, str]:
    """Возвращает (создан HH:MM, принять_до HH:MM) с учётом таймзоны Грузии (UTC+4)."""
    now_geo = datetime.now(GEORGIA_TZ)
    created_dt = now_geo
    if value:
        if isinstance(value, (int, float)):
            try:
                created_dt = datetime.fromtimestamp(value, tz=timezone.utc).astimezone(GEORGIA_TZ)
            except Exception:
                created_dt = now_geo
        else:
            raw = str(value).strip()
            try:
                if "T" in raw or "+" in raw or "Z" in raw:
                    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    created_dt = parsed.astimezone(GEORGIA_TZ)
                else:
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%H:%M"):
                        try:
                            parsed = datetime.strptime(raw, fmt)
                            if fmt == "%H:%M":
                                created_dt = now_geo.replace(
                                    hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0
                                )
                            else:
                                created_dt = parsed.replace(tzinfo=timezone.utc).astimezone(GEORGIA_TZ)
                            break
                        except ValueError:
                            continue
            except Exception:
                created_dt = now_geo
    deadline = created_dt + timedelta(minutes=minutes)
    return created_dt.strftime("%H:%M"), deadline.strftime("%H:%M")


def _localize_item_name(raw_name, lang: str = "ru") -> str:
    """Извлекает название блюда на выбранном языке без JSON-структур, кавычек и фигурных скобок."""
    if not raw_name:
        return ""
    if isinstance(raw_name, dict):
        val = raw_name.get(lang) or raw_name.get("ru") or raw_name.get("en") or raw_name.get("ka")
        if not val and raw_name:
            val = next(iter(raw_name.values()), "")
        return str(val or "").strip()
    if isinstance(raw_name, str):
        raw_str = raw_name.strip()
        if (raw_str.startswith("{") and raw_str.endswith("}")) or ("'ru':" in raw_str or '"ru":' in raw_str):
            try:
                import json
                parsed = json.loads(raw_str)
                if isinstance(parsed, dict):
                    val = parsed.get(lang) or parsed.get("ru") or parsed.get("en") or parsed.get("ka")
                    if not val and parsed:
                        val = next(iter(parsed.values()), "")
                    return str(val or "").strip()
            except Exception:
                pass
            try:
                import ast
                parsed = ast.literal_eval(raw_str)
                if isinstance(parsed, dict):
                    val = parsed.get(lang) or parsed.get("ru") or parsed.get("en") or parsed.get("ka")
                    if not val and parsed:
                        val = next(iter(parsed.values()), "")
                    return str(val or "").strip()
            except Exception:
                pass
        return raw_str
    return str(raw_name).strip()


def _format_banner_items(items: list, lang: str = "ru") -> str:
    """Формат зоны ITEMS на баннере 2a: «3 items · A, B, C»."""
    if not items:
        return "—"
    names: list[str] = []
    count = 0
    item_fallback = t(lang, "item_fallback") if "item_fallback" in I18N.get(lang, {}) else "Товар"
    for it in items:
        raw_name = it.get("name")
        name = _localize_item_name(raw_name, lang=lang) or item_fallback
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


def _lookup_order_cutlery(order_id) -> int:
    """Читает cutlery_count из order.db (если gateway не прислал в вебхуке)."""
    try:
        oid = int(order_id)
    except (TypeError, ValueError):
        return 0
    for path in ORDER_DB_PATHS:
        if not os.path.exists(path):
            continue
        try:
            conn = connect_sqlite_wal(path)
            try:
                row = conn.execute(
                    "SELECT cutlery_count FROM orders WHERE id = ?",
                    (oid,),
                ).fetchone()
            finally:
                conn.close()
            if row is not None and row[0] is not None:
                return max(0, int(row[0]))
        except Exception as e:
            log.debug("cutlery lookup failed order=%s path=%s: %s", order_id, path, e)
    return 0


def _fetch_order_fees_sync(order_id: int) -> tuple[float, float]:
    """Читает delivery_fee и tips из order.db (если gateway не прислал в вебхуке)."""
    try:
        oid = int(order_id)
    except (TypeError, ValueError):
        return 0.0, 0.0
    for path in ORDER_DB_PATHS:
        if not os.path.exists(path):
            continue
        try:
            conn = connect_sqlite_wal(path)
            try:
                row = conn.execute(
                    "SELECT delivery_fee, tips FROM orders WHERE id = ?",
                    (oid,),
                ).fetchone()
            finally:
                conn.close()
            if row is not None:
                fee = float(row[0] or 0.0)
                tips = float(row[1] or 0.0)
                return fee, tips
        except Exception as e:
            log.debug("fees lookup failed order=%s path=%s: %s", order_id, path, e)
    return 0.0, 0.0


def get_order_current_status(order_id: int) -> Optional[str]:
    """Возвращает статус заказа из order.db: pending, accepted, preparing, ready, delivering, delivered, cancelled."""
    for path in ORDER_DB_PATHS:
        if os.path.exists(path):
            try:
                conn = connect_sqlite_wal(path)
                row = conn.execute("SELECT status FROM orders WHERE id = ?", (int(order_id),)).fetchone()
                conn.close()
                if row and row[0]:
                    return str(row[0]).strip().lower()
            except Exception as e:
                log.warning("get_order_current_status failed order=%s path=%s: %s", order_id, path, e)
    return None


def _get_order_row(order_id: int) -> dict:
    """Загружает полную строку заказа из order.db (с распарсенными items)."""
    try:
        oid = int(order_id)
    except (TypeError, ValueError):
        return {}
    for path in ORDER_DB_PATHS:
        if not os.path.exists(path):
            continue
        try:
            conn = connect_sqlite_wal(path)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
            conn.close()
            if row:
                d = dict(row)
                raw_items = d.get("items")
                if isinstance(raw_items, str):
                    try:
                        d["items"] = json.loads(raw_items)
                    except Exception:
                        d["items"] = []
                d["order_id"] = oid
                return d
        except Exception as e:
            log.warning("_get_order_row failed order=%s path=%s: %s", order_id, path, e)
    return {}


SUNSET_RESTAURANT_IDS = {"rest-1785108442716453469", "sunset-restaurant"}
SUNSET_COMBINABLE_KEYWORDS = (
    "мწვადი", "шашлык", "barbecue", "mtsvadi",
    "კუბდარი", "кубдари", "kubdari",
    "ხაჭაპური", "хачапури", "khachapuri",
    "ჭვიშტარი", "чвиштари", "chvishtari",
    "ფრი", "фри", "fries",
    "პური", "хлеб", "bread",
    "ხინკალი", "хинкали", "khinkali",
)
SUNSET_FREE_KEYWORDS = (
    "borjomi", "боржоми", "coca", "кола", "вода", "water", "წყალი",
    "лимонад", "lemonade", "ლიმონათი", "чай", "tea", "ჩაი",
    "кофе", "coffee", "ყავა", "соус", "sauce", "სოუსი",
    "ткемали", "ტყემალი", "сацебели", "საწებელი", "баже", "ბაჟე",
    "кетчуп", "кетчупи", "сметана", "არაჟანი", "набеглави", "ნაბეღლავი",
    "ნაბეგლავი", "сок", "juice", "წვენი",
)


def is_sunset_restaurant(rest_id: str, rest_name: str = "") -> bool:
    rid = str(rest_id or "").strip().lower()
    rname = str(rest_name or "").strip().lower()
    return rid in SUNSET_RESTAURANT_IDS or "sunset" in rid or "sunset" in rname


def calculate_sunset_packaging(items: list) -> tuple[int, float]:
    """
    Правила упаковки для Sunset Restaurant:
    - Комбинируемые блюда (шашлык, кубдари, хачапури, чвиштари, фри, хлеб, хинкали) при повторе кладут в один бокс (1 бокс на строку позиции).
    - Напитки и соусы — бесплатно (0 боксов).
    - Остальные блюда (супы, соусные горячие блюда, салаты) — индивидуальный контейнер на каждую порцию (qty боксов).
    - Стоимость одного бокса: 2.0 GEL.
    """
    boxes = 0
    for it in items:
        name = str(it.get("name") or "").lower()
        qty = int(it.get("quantity") or 1)
        cat = str(it.get("category") or "").lower()
        if any(w in name for w in SUNSET_FREE_KEYWORDS) or cat in ("напитки", "соусы", "drinks", "sauces"):
            continue
        if any(kw in name for kw in SUNSET_COMBINABLE_KEYWORDS):
            boxes += 1
        else:
            boxes += qty
    fee = float(boxes * 2.0)
    return boxes, fee


def format_order_message(
    data: dict,
    lang: str = "ru",
    *,
    delivered: bool = False,
    status: str = "",
    ready_time: str = "",
) -> str:
    """HTML-карточка заказа ресторана: состав + приборы + сумма позиций."""
    order_id = data.get("order_id", "?")
    comment = _clean_order_comment(data.get("comment") or "")
    items = data.get("items") or []
    item_fallback = t(lang, "item_fallback")

    rest_id = str(data.get("restaurant_id") or "").strip()
    rest_name = str(data.get("restaurant_name") or "").strip()
    if not rest_id and order_id and str(order_id) != "?":
        ord_row = _get_order_row(order_id)
        if ord_row:
            rest_id = str(ord_row.get("restaurant_id") or "").strip()
            rest_name = str(ord_row.get("restaurant_name") or rest_name).strip()

    is_sunset = is_sunset_restaurant(rest_id, rest_name)
    packaging_boxes = 0
    packaging_fee = 0.0
    if is_sunset:
        packaging_boxes, packaging_fee = calculate_sunset_packaging(items)

    items_lines: list[str] = []
    food_total = 0.0
    for item in items:
        raw_name = item.get("name")
        name = html.escape(_localize_item_name(raw_name, lang=lang) or item_fallback)
        qty = int(item.get("quantity") or 1)
        unit = float(item.get("price") or 0)
        line_total = unit * qty
        food_total += line_total
        items_lines.append(f"<b>{qty}\u00A0×</b> {name} · {_fmt_caption_lari(line_total)}")

    if is_sunset and packaging_boxes > 0:
        food_total += packaging_fee
        if lang == "ka":
            items_lines.append(f"<b>შეფუთვა:</b> {packaging_boxes} ბოქსი · {_fmt_caption_lari(packaging_fee)}")
        elif lang == "ru":
            box_word = "бокс" if packaging_boxes == 1 else ("бокса" if 2 <= packaging_boxes % 10 <= 4 and not (11 <= packaging_boxes % 100 <= 14) else "боксов")
            items_lines.append(f"<b>Упаковка:</b> {packaging_boxes} {box_word} · {_fmt_caption_lari(packaging_fee)}")
        else:
            box_word = "box" if packaging_boxes == 1 else "boxes"
            items_lines.append(f"<b>Packaging:</b> {packaging_boxes} {box_word} · {_fmt_caption_lari(packaging_fee)}")

    items_block = "<blockquote>" + "\n".join(items_lines) + "</blockquote>" if items_lines else " —"

    if delivered:
        if lang == "ka":
            header = f'{ce("5384244502040975393", "✅")} <b>შეკვეთა #{order_id} დასრულებულია</b>'
        elif lang == "ru":
            header = f'{ce("5384244502040975393", "✅")} <b>ЗАКАЗ #{order_id} ЗАВЕРШЁН</b>'
        else:
            header = f'{ce("5384244502040975393", "✅")} <b>ORDER #{order_id} COMPLETED</b>'
    elif status == "ready":
        if lang == "ka":
            header = f'{ce("5384138412053796842", "📦")} <b>შეკვეთა #{order_id} მზადაა გასაცემად</b>'
        elif lang == "ru":
            header = f'{ce("5384138412053796842", "📦")} <b>ЗАКАЗ #{order_id} ГОТОВ К ВЫДАЧЕ</b>'
        else:
            header = f'{ce("5384138412053796842", "📦")} <b>ORDER #{order_id} READY FOR PICKUP</b>'
    elif status == "preparing" or ready_time:
        if ready_time:
            if lang == "ka":
                header = f'{ce("5384312315279612142", "👨‍🍳")} <b>შეკვეთა #{order_id} მზადდება · გაცემა {ready_time}-მდე</b>'
            elif lang == "ru":
                header = f'{ce("5384312315279612142", "👨‍🍳")} <b>ЗАКАЗ #{order_id} ГОТОВИТСЯ · Выдача до {ready_time}</b>'
            else:
                header = f'{ce("5384312315279612142", "👨‍🍳")} <b>ORDER #{order_id} PREPARING · Ready by {ready_time}</b>'
        else:
            if lang == "ka":
                header = f'{ce("5384312315279612142", "👨‍🍳")} <b>შეკვეთა #{order_id} მზადდება</b>'
            elif lang == "ru":
                header = f'{ce("5384312315279612142", "👨‍🍳")} <b>ЗАКАЗ #{order_id} ГОТОВИТСЯ</b>'
            else:
                header = f'{ce("5384312315279612142", "👨‍🍳")} <b>ORDER #{order_id} PREPARING</b>'
    else:
        header = f'{ce("5384244502040975393", "🔔")} <b>{t(lang, "rest_new_order_title", order_id=order_id)}</b>'

    parts = [
        header,
        "",
        f'{ce("5384312315279612142", "🛒")} <b>{t(lang, "rest_order_items")}</b>\n{items_block}',
    ]

    has_comment = bool(
        comment
        and comment.strip()
        and comment.strip().lower() not in ("нет", "none", "—", "-", "არ არის", "no")
    )
    if has_comment:
        parts.append(
            f'\n{ce("5382097310450753507", "💬")} <b>{t(lang, "rest_comment")}</b>\n<blockquote>{html.escape(comment.strip())}</blockquote>'
        )

    cutlery_val = data.get("cutlery_count")
    if cutlery_val is None:
        cutlery_val = data.get("cutlery")
    if cutlery_val is None and order_id and str(order_id) != "?":
        cutlery_val = _lookup_order_cutlery(order_id)
    try:
        cutlery_count = int(cutlery_val or 0)
    except (TypeError, ValueError):
        cutlery_count = 0

    if lang == "ka":
        cutlery_label = "დანა-ჩანგალი:"
        cutlery_str = f"{cutlery_count} ც." if cutlery_count > 0 else "არ არის საჭირო"
    elif lang == "ru":
        cutlery_label = "Приборы:"
        cutlery_str = f"{cutlery_count} шт." if cutlery_count > 0 else "не требуются"
    else:
        cutlery_label = "Cutlery:"
        cutlery_str = f"{cutlery_count} pcs" if cutlery_count > 0 else "not needed"

    bottom_lines = [
        f'{ce("5382351125838077755", "🍴")} <b>{cutlery_label}</b> <b>{cutlery_str}</b>',
        f'{ce("5384520939021048827", "💰")} <b>{t(lang, "rest_order_total")}</b> <b>{_fmt_caption_lari(food_total)}</b>',
    ]

    # Приборы, упаковка и сумма заказа в самом низу карточки — прямо перед кнопками
    parts.append("\n" + "\n".join(bottom_lines))

    return "\n".join(parts)


# ── Команды ───────────────────────────────────



CUSTOM_EMOJI = {
    "cutlery": "5382351125838077755",
    "welcome": "5384489194917765397",
    "point_down": "5382351125838077755",
    "profile_setup": "5384244502040975393",
    "success": "5384244502040975393",
    "logo": "5384244502040975393",
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
    "alert_red": "5348083587532994863",
    "alert_green": "5348348011489542390",
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
        "auth_fail": (
            f'{ce(CUSTOM_EMOJI["alert_red"], "🔴")} <b>Неверный логин или пароль</b>. '
            f"Пожалуйста, проверьте данные и введите логин заново."
        ),
        "role_courier": "Курьер",
        "role_rest": "Ресторатор",
        "menu_history": "📜 История заказов",
        "menu_profile": "Профиль",
        "menu_orders": "Заказы",
        "menu_menu": "Меню",
        "menu_shifts": "Инструкция",
        "menu_guide": "Инструкция",
        "menu_income": "Статистика",
        "menu_support": "Поддержка",
        "menu_courier_offline": "Выйти на линию",
        "menu_courier_online": "Сойти с линии",
        "status_online_now": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>Вы вышли на линию!</b> Теперь вы будете получать заказы.'
        ),
        "status_offline_now": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} <b>Вы не на линии.</b> Заказы не поступают.'
        ),
        "courier_offline_alert": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} <b>Не на линии.</b> Заказы не поступают.'
        ),
        "courier_online_alert": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>На линии!</b> Заказы будут поступать.'
        ),
        "courier_line_status_offline": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} <b>Не на линии.</b> Заказы не поступают.'
        ),
        "courier_line_status_online": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>На линии!</b> Заказы будут поступать.'
        ),
        "btn_call_client": "Позвонить",
        "btn_whatsapp_client": "WhatsApp",
        "btn_telegram_client": "Telegram",
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
        "auth_fail": (
            f'{ce(CUSTOM_EMOJI["alert_red"], "🔴")} <b>Invalid login or password</b>. '
            f"Please check your credentials and enter your login again."
        ),
        "role_courier": "Courier",
        "role_rest": "Restaurateur",
        "menu_history": "📜 Order History",
        "menu_profile": "Profile",
        "menu_orders": "Orders",
        "menu_menu": "Menu",
        "menu_shifts": "How it works",
        "menu_guide": "How it works",
        "menu_income": "Statistics",
        "menu_support": "Support",
        "menu_courier_offline": "Go online",
        "menu_courier_online": "Go offline",
        "status_online_now": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>You are online!</b> You will now receive orders.'
        ),
        "status_offline_now": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} <b>You are offline.</b> Orders are not incoming.'
        ),
        "courier_offline_alert": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} <b>Offline.</b> Orders are not incoming.'
        ),
        "courier_online_alert": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>Online!</b> Orders will be incoming.'
        ),
        "courier_line_status_offline": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} <b>Offline.</b> Orders are not incoming.'
        ),
        "courier_line_status_online": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>Online!</b> Orders will be incoming.'
        ),
        "btn_call_client": "Call client",
        "btn_whatsapp_client": "WhatsApp",
        "btn_telegram_client": "Telegram",
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
        "auth_fail": (
            f'{ce(CUSTOM_EMOJI["alert_red"], "🔴")} <b>არასწორი ლოგინი ან პაროლი</b>. '
            f"გთხოვთ შეამოწმოთ მონაცემები და ხელახლა შეიყვანოთ ლოგინი."
        ),
        "role_courier": "კურიერი",
        "role_rest": "რესტორატორი",
        "menu_history": "📜 შეკვეთების ისტორია",
        "menu_profile": "პროფილი",
        "menu_orders": "შეკვეთები",
        "menu_menu": "მენიუ",
        "menu_shifts": "ინსტრუქცია",
        "menu_guide": "ინსტრუქცია",
        "menu_income": "სტატისტიკა",
        "menu_support": "მხარდაჭერა",
        "menu_courier_online": "ხაზიდან გამოსვლა",
        "menu_courier_offline": "ხაზზე გასვლა",
        "status_online_now": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>თქვენ ხაზზე ხართ!</b> ახლა მიიღებთ შეკვეთებს.'
        ),
        "status_offline_now": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} <b>თქვენ ხაზგარეშე ხართ.</b> შეკვეთებს არ მიიღებთ.'
        ),
        "courier_offline_alert": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} <b>ხაზგარეშე.</b> შეკვეთებს არ მიიღებთ.'
        ),
        "courier_online_alert": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>ხაზზე!</b> შეკვეთები შემოვა.'
        ),
        "courier_line_status_offline": (
            f'{ce(CUSTOM_EMOJI["close_restaurant"], "🔴")} <b>ხაზგარეშე.</b> შეკვეთებს არ მიიღებთ.'
        ),
        "courier_line_status_online": (
            f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>ხაზზე!</b> შეკვეთები შემოვა.'
        ),
        "btn_call_client": "დარეკვა კლიენტთან",
        "btn_whatsapp_client": "WhatsApp",
        "btn_telegram_client": "Telegram",
    }
}

def get_text(lang: str, key: str, **kwargs) -> str:
    bucket = I18N.get(lang) or I18N["ru"]
    text = bucket.get(key)
    if text is None:
        text = I18N["ru"].get(key)
    if text is None:
        return ui_text(lang, key, **kwargs)
    return text.format(**kwargs) if kwargs else text


def t(lang: str, key: str, **kwargs) -> str:
    """UI string: base I18N first, then partner_i18n fallback."""
    bucket = I18N.get(lang) or I18N["ru"]
    if key in bucket or key in I18N["ru"]:
        return get_text(lang, key, **kwargs)
    return ui_text(lang, key, **kwargs)


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
CONTACT_EMOJI_WHATSAPP = "5334998226636390258"
CONTACT_EMOJI_TELEGRAM = "5330237710655306682"
CONTACT_EMOJI_PHONE = "5343657129813221401"

# Причины отклонения рестораном: code → (label RU fallback, предлагает_отложить)
REJECT_REASON_DEFS: dict[str, tuple[str, bool]] = {
    "ns": ("Нет продуктов", False),
    "kb": ("Завал на кухне", True),
    "lq": ("Большая очередь", True),
    "cl": ("Ресторан закрывается", False),
    "ot": ("Другая причина", False),
}

# Причины отказа курьера: code → (label RU fallback, предлагает_напомнить_через_5_мин)
COURIER_REFUSE_REASON_DEFS: dict[str, tuple[str, bool]] = {
    "ao": ("На другом заказе", True),
    "far": ("Не по пути / далеко", False),
    "busy": ("Сейчас не могу", False),
    "ot": ("Другая причина", False),
}


def reject_reason_label(code: str, lang: str = "ru") -> str:
    key = REJECT_I18N_KEYS.get(code)
    if key:
        return t(lang, key)
    return REJECT_REASON_DEFS.get(code, (t(lang, "reject_other"), False))[0]


def courier_refuse_reason_label(code: str, lang: str = "ru") -> str:
    key = COURIER_REFUSE_I18N_KEYS.get(code)
    if key:
        return t(lang, key)
    return COURIER_REFUSE_REASON_DEFS.get(code, (t(lang, "courier_refuse_other"), False))[0]


COURIER_SNOOZE_MIN = 5
# (order_id, telegram_id) → asyncio.Task отложенного напоминания
_COURIER_SNOOZE_TASKS: dict[tuple[int, int], asyncio.Task] = {}
# order_id → последняя выбранная причина (для финализации после delay)
_COURIER_REFUSE_META: dict[int, dict] = {}

# Напоминание: заказ ещё никто не взял (после broadcast)
COURIER_ASSIGN_REMIND_MIN = 5
COURIER_ASSIGN_REMIND2_MIN = 2
# (order_id, stage) → Task; stage = 5 | 7 (минуты от broadcast)
_COURIER_ASSIGN_REMIND_TASKS: dict[tuple[int, int], asyncio.Task] = {}


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


async def _send_courier_shift_summary(chat_id: int, tg: int, lang: str = "ru"):
    """Подсчитывает и отправляет итоги смены курьера за сегодня."""
    courier_ids = await db.get_courier_ids_by_telegram(tg)
    if not courier_ids:
        return

    def _query():
        count = 0
        fees = 0.0
        tips = 0.0
        for path in ORDER_DB_PATHS:
            if not os.path.exists(path):
                continue
            conn = None
            try:
                conn = connect_sqlite_wal(path)
                placeholders = ",".join("?" for _ in courier_ids)
                cur = conn.cursor()
                cur.execute(
                    f"SELECT count(*), coalesce(sum(delivery_fee), 0), coalesce(sum(tips), 0) "
                    f"FROM orders WHERE courier_id IN ({placeholders}) "
                    f"AND date(courier_taken_at) = date('now') "
                    f"AND status = 'delivered'",
                    tuple(courier_ids),
                )
                row = cur.fetchone()
                if row:
                    count += int(row[0] or 0)
                    fees += float(row[1] or 0.0)
                    tips += float(row[2] or 0.0)
                break
            except Exception as e:
                log.warning("Shift summary query failed: %s", e)
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
        return count, fees, tips

    count, fees, tips = await asyncio.to_thread(_query)
    if count > 0:
        total = fees + tips
        text = (
            f'{ce("5384244502040975393", "🏁")} {t(lang, "shift_summary_title")}\n\n'
            f'{ce("5384138412053796842", "📦")} {t(lang, "shift_summary_orders", n=count)}\n'
            f'{ce("5384520939021048827", "💰")} {t(lang, "shift_summary_income", amount=f"{fees:.2f}")}\n'
            f'{ce("5384518714227990146", "🎁")} {t(lang, "shift_summary_tips", amount=f"{tips:.2f}")}\n\n'
            f'{ce("5384518714227990146", "💵")} {t(lang, "shift_summary_total", amount=f"{total:.2f}")}'
        )
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        except Exception as e:
            log.warning("Failed to send shift summary to tg=%d: %s", tg, e)


async def toggle_courier_line_status(tg_id: int, chat_id: int, user: dict) -> int:
    """Переключает online/offline курьера. Возвращает новый статус 0/1."""
    cancel_scheduled_courier_line_status(chat_id)
    is_online = user.get("is_online", 0)
    new_status = 1 if is_online == 0 else 0
    if new_status == 1:
        block = await db.get_courier_block(int(tg_id))
        if block:
            await notify_courier_access_restricted(tg_id, float(block["until_ts"]))
            return int(is_online or 0)
    log.info(
        "Courier line toggle tg=%d chat=%d %d -> %d",
        tg_id,
        chat_id,
        is_online,
        new_status,
    )
    action = "set_online" if new_status == 1 else "set_offline"
    ok = await update_courier_online_backend(tg_id, action)
    if not ok:
        log.warning("Courier line toggle gateway failed tg=%d action=%s — keep local %s", tg_id, action, is_online)
        return int(is_online or 0)
    await db.set_courier_online_status(tg_id, new_status)
    lang = user.get("language", "ru")
    await set_courier_reply_kb(chat_id, lang, new_status == 1)
    if new_status == 0:
        await _send_courier_shift_summary(chat_id, tg_id, lang)
    return new_status


async def force_courier_online(tg_id: int, chat_id: int, user: dict) -> None:
    """Принудительно выводит курьера на линию (/line)."""
    cancel_scheduled_courier_line_status(chat_id)
    block = await db.get_courier_block(int(tg_id))
    if block:
        await notify_courier_access_restricted(tg_id, float(block["until_ts"]))
        return
    ok = await update_courier_online_backend(tg_id, "set_online")
    if not ok:
        log.warning("force_courier_online gateway failed tg=%d", tg_id)
        return
    await db.set_courier_online_status(tg_id, 1)
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


# Direct HTTPS URL for WebApp buttons (not t.me short link — that can point to stale Firebase).
_raw_miniapp = os.getenv("MINIAPP_URL", "https://partners.mestidelivery.com").rstrip("/")
if "partners." in _raw_miniapp:
    MINIAPP_DIRECT_URL = _raw_miniapp
else:
    MINIAPP_DIRECT_URL = _raw_miniapp + "/partners/"
# Deep-link short name (BotFather Direct Link); prefer HTTPS for actual WebApp opens.
MINIAPP_URL = "https://partners.mestidelivery.com"
SUPPORT_BOT_URL = "https://t.me/MestigoSupport_Bot"


def miniapp_page_url(page: str = "", order_id: int | None = None) -> str:
    """HTTPS Mini App URL with optional ?page= / ?order_id= for deep links."""
    base = MINIAPP_DIRECT_URL if MINIAPP_DIRECT_URL.endswith("/") else MINIAPP_DIRECT_URL + "/"
    q: list[str] = []
    if page:
        q.append(f"page={page}")
    if order_id is not None:
        q.append(f"order_id={int(order_id)}")
    return base + (("?" + "&".join(q)) if q else "")


def kb_support_inline(lang: str = "ru") -> InlineKeyboardMarkup:
    labels = {"ru": "Поддержка", "en": "Support", "ka": "მხარდაჭერა"}
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=labels.get(lang, "Support"),
                    url=SUPPORT_BOT_URL,
                    icon_custom_emoji_id=CUSTOM_EMOJI["btn_support"],
                )
            ]
        ]
    )


def format_access_restricted_html(until_hm: str, lang: str = "ru") -> str:
    red = ce(CUSTOM_EMOJI["alert_red"], "🔴")
    if lang == "en":
        return (
            f"{red} <b>System access is temporarily restricted</b> until {until_hm}. "
            f"If this restriction was applied by mistake, please contact support."
        )
    if lang == "ka":
        return (
            f"{red} <b>სისტემაზე წვდომა დროებით შეზღუდულია</b> {until_hm}-მდე. "
            f"თუ შეზღუდვა შეცდომითაა გამოყენებული, გთხოვთ მიმართოთ მხარდაჭერას."
        )
    return (
        f"{red} <b>Доступ к системе временно ограничен</b> до {until_hm}. "
        f"Если ограничение применено ошибочно, пожалуйста, обратитесь в службу поддержки."
    )


def format_access_restored_html(lang: str = "ru") -> str:
    green = ce(CUSTOM_EMOJI["alert_green"], "🟢")
    if lang == "en":
        return (
            f"{green} <b>Restrictions lifted.</b> "
            f"Access to orders is restored — you can go back online."
        )
    if lang == "ka":
        return (
            f"{green} <b>შეზღუდვები მოხსნილია.</b> "
            f"შეკვეთებზე წვდომა აღდგენილია — შეგიძლიათ კვლავ გახვიდეთ ხაზზე."
        )
    return (
        f"{green} <b>Ограничения сняты.</b> "
        f"Доступ к заказам восстановлен, вы можете возобновить работу на линии."
    )


async def notify_courier_access_restricted(telegram_id: int, until_ts: float) -> None:
    until_hm = datetime.fromtimestamp(float(until_ts)).strftime("%d.%m, %H:%M")
    user = await db.get_bot_user(int(telegram_id)) or {}
    lang = user.get("language", "ru")
    try:
        await bot.send_message(
            int(telegram_id),
            format_access_restricted_html(until_hm, lang),
            parse_mode=ParseMode.HTML,
            reply_markup=kb_support_inline(lang),
        )
    except Exception as e:
        log.warning("notify_courier_access_restricted failed tg=%s: %s", telegram_id, e)


async def notify_courier_access_restored(telegram_id: int) -> None:
    user = await db.get_bot_user(int(telegram_id)) or {}
    lang = user.get("language", "ru")
    try:
        await bot.send_message(
            int(telegram_id),
            format_access_restored_html(lang),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        log.warning("notify_courier_access_restored failed tg=%s: %s", telegram_id, e)


def get_main_inline_kb(lang: str, role: str = "") -> InlineKeyboardMarkup:
    """Генерирует инлайн-кнопки для главного меню под приветственным баннером."""
    lbl_profile = get_text(lang, "menu_profile")
    lbl_orders = get_text(lang, "menu_orders")
    lbl_stats = get_text(lang, "menu_income")
    lbl_menu = get_text(lang, "menu_menu")
    lbl_support = get_text(lang, "menu_support")
    if lang == "ru":
        lbl_history = "📜 История"
        lbl_schedule = "📅 График смен"
    elif lang == "en":
        lbl_history = "📜 History"
        lbl_schedule = "📅 Schedule"
    else:
        lbl_history = "📜 ისტორია"
        lbl_schedule = "📅 განრიგი"

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
                    web_app=WebAppInfo(url=miniapp_page_url("orders")),
                ),
                InlineKeyboardButton(
                    text=lbl_menu,
                    icon_custom_emoji_id=CUSTOM_EMOJI["btn_menu"],
                    web_app=WebAppInfo(url=miniapp_page_url("menu")),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=lbl_stats,
                    icon_custom_emoji_id=CUSTOM_EMOJI["btn_stats"],
                    web_app=WebAppInfo(url=miniapp_page_url("stats")),
                ),
                InlineKeyboardButton(
                    text=lbl_support,
                    icon_custom_emoji_id=CUSTOM_EMOJI["btn_support"],
                    url=SUPPORT_BOT_URL,
                ),
            ],
        ]
    else:
        # Курьер: Профиль → Заказы+Гайд → Статистика+Поддержка (как в миниаппе)
        lbl_guide = get_text(lang, "menu_guide")
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
                    web_app=WebAppInfo(url=miniapp_page_url("orders")),
                ),
                InlineKeyboardButton(
                    text=lbl_guide,
                    icon_custom_emoji_id="5384312315279612142",
                    web_app=WebAppInfo(url=miniapp_page_url("guide")),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=lbl_stats,
                    icon_custom_emoji_id="5384518714227990146",
                    web_app=WebAppInfo(url=miniapp_page_url("stats")),
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
                    text="ქართული",
                    icon_custom_emoji_id=CUSTOM_EMOJI["flag_ka"],
                    callback_data="lang_ka",
                ),
            ],
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
    kb_list.append([InlineKeyboardButton(text="← Панель", callback_data="admin_back_home")])
        
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
            partner = await db.get_partner_by_restaurant(partner_id)
            if partner:
                partner_chat_id = partner.get("telegram_id")
        else:
            try:
                partner_chat_id = int(partner_id)
            except Exception:
                pass
            
        if partner_chat_id:
            try:
                tg_user = await db.get_bot_user(partner_chat_id) or {}
                lang = tg_user.get("language", "ru")
                
                if lang == "ru":
                    notif = f'{ce("5384244502040975393", "✅")} <b>Ваша заявка на выплату {amount:.2f} ₾ одобрена!</b>\nСредства отправлены и зачислены по вашим реквизитам.'
                elif lang == "en":
                    notif = f'{ce("5384244502040975393", "✅")} <b>Your payout request for {amount:.2f} ₾ has been approved!</b>\nFunds have been sent and will be credited shortly.'
                else:
                    notif = f'{ce("5384244502040975393", "✅")} <b>თანხის გატანის მოთხოვნა {amount:.2f} ₾-ზე დამტკიცებულია!</b>\nთანხა გაგზავნილია და ჩაირიცხება უახლოეს დროში.'
                    
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
            partner = await db.get_partner_by_restaurant(partner_id)
            if partner:
                partner_chat_id = partner.get("telegram_id")
        else:
            try:
                partner_chat_id = int(partner_id)
            except Exception:
                pass
            
        if partner_chat_id:
            try:
                tg_user = await db.get_bot_user(partner_chat_id) or {}
                lang = tg_user.get("language", "ru")
                
                if lang == "ru":
                    notif = f'{ce("5348083587532994863", "❌")} <b>Ваша заявка на выплату {amount:.2f} ₾ отклонена.</b>\nСредства возвращены на ваш баланс в боте.'
                elif lang == "en":
                    notif = f'{ce("5348083587532994863", "❌")} <b>Your payout request for {amount:.2f} ₾ has been rejected.</b>\nThe amount has been returned to your balance.'
                else:
                    notif = f'{ce("5348083587532994863", "❌")} <b>თანხის გატანის მოთხოვნა {amount:.2f} ₾-ზე უარყოფილია.</b>\nთანხა დაბრუნებულია თქვენს ბალანსზე.'
                    
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


@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    await state.clear()
    tg = message.from_user.id
    user = await db.get_bot_user(tg) or {}
    if not user or not user.get("role"):
        await cmd_start(message, state)
        return
    await render_and_send_profile(message.chat.id, None, tg, user)


@router.message(Command("role"))
async def cmd_role_switch(message: Message, state: FSMContext):
    """Быстрое переключение роли аккаунта (ресторан / курьер) для тестов и основателя."""
    await state.clear()
    args = (message.text or "").split()
    target_role = args[1].lower() if len(args) > 1 else ""
    tg_id = message.from_user.id
    user = await db.get_bot_user(tg_id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь через /start")
        return

    current_role = user.get("role")
    if target_role in ("courier", "курьер"):
        new_role = "courier"
    elif target_role in ("restaurant", "restaurant_admin", "ресторан"):
        new_role = "restaurant_admin"
    else:
        new_role = "courier" if current_role == "restaurant_admin" else "restaurant_admin"

    async with aiosqlite.connect(db.path) as conn:
        await conn.execute("UPDATE bot_users SET role = ? WHERE telegram_id = ?", (new_role, tg_id))
        await conn.commit()

    role_label = "🛵 Курьер" if new_role == "courier" else "🏛️ Ресторан (Кухня)"
    await message.answer(
        f"✅ <b>Роль партнёра изменена на: {role_label}</b>\n\n"
        f"Откройте Mini App — интерфейс и данные полностью адаптированы под эту роль.",
        parse_mode=ParseMode.HTML
    )


@router.message(CommandStart())
@router.message(Command("menu"))
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
    await callback.answer()
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
    await callback.answer()
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
                # Удаляем фантомных курьеров, созданных шлюзом для этого telegram_id
                cursor.execute(
                    "DELETE FROM admin_users WHERE username = ? OR (username LIKE 'courier_%' AND telegram_id = ?)",
                    (f"courier_{tg_str}", tg_str),
                )
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
                log.info("Bound telegram_id=%s to username=%s in %s (cleaned phantoms)", tg_str, username, path)
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
        await message.answer(t(user.get("language", "ru"), "alert_couriers_only"))
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
        await message.answer(t(user.get("language", "ru"), "alert_couriers_only"))
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
def get_restaurant_profile_kb(is_open: bool, lang: str = "ru", restaurant_id: str = "", rush_mode: int = 0) -> InlineKeyboardMarkup:
    if lang == "en":
        toggle_text = "Close restaurant" if is_open else "Open restaurant"
        hours_text = "Working hours"
        payouts_text = "Payouts"
        stoplist_text = "Stop-list"
        lang_text = "Change language"
        back_text = "← Back"
        if rush_mode == 1:
            rush_text = "🔥 Rush mode: ON"
        elif rush_mode == -1:
            rush_text = "🔥 Rush mode: OFF"
        else:
            rush_text = "🔥 Rush mode: Auto (18–22)"
    elif lang == "ka":
        toggle_text = "რესტორნის დახურვა" if is_open else "რესტორნის გახსნა"
        hours_text = "სამუშაო საათები"
        payouts_text = "გადახდები"
        stoplist_text = "სტოპ-ლისტი"
        lang_text = "ენის შეცვლა"
        back_text = "← უკან"
        if rush_mode == 1:
            rush_text = "🔥 პიკის საათი: ჩართ."
        elif rush_mode == -1:
            rush_text = "🔥 პიკის საათი: გამორთ."
        else:
            rush_text = "🔥 პიკის საათი: ავტო (18–22)"
    else:
        toggle_text = "Закрыть ресторан" if is_open else "Открыть ресторан"
        hours_text = "Часы работы"
        payouts_text = "Выплаты"
        stoplist_text = "Стоп-лист"
        lang_text = "Сменить язык"
        back_text = "← Назад"
        if rush_mode == 1:
            rush_text = "🔥 Запара: ВКЛ"
        elif rush_mode == -1:
            rush_text = "🔥 Запара: ВЫКЛ"
        else:
            rush_text = "🔥 Запара: Авто (18–22)"

    toggle_emoji = CUSTOM_EMOJI["close_restaurant"] if is_open else CUSTOM_EMOJI["open_restaurant"]
    lang_emoji = "5384222159621102491"

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
                    text=rush_text,
                    callback_data="profile_toggle_rush",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=stoplist_text,
                    icon_custom_emoji_id="5384312315279612142",
                    callback_data=f"stoplist_open_{restaurant_id}",
                ),
                InlineKeyboardButton(
                    text=hours_text,
                    icon_custom_emoji_id=CUSTOM_EMOJI["hours"],
                    callback_data="profile_hours",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=payouts_text,
                    icon_custom_emoji_id=CUSTOM_EMOJI["payouts"],
                    callback_data="profile_payouts",
                ),
                InlineKeyboardButton(
                    text=lang_text,
                    icon_custom_emoji_id=lang_emoji,
                    callback_data="profile_change_language",
                ),
            ],
            [
                InlineKeyboardButton(text=back_text, callback_data="profile_back"),
            ],
        ]
    )

def get_courier_profile_kb(is_online: bool, lang: str = "ru") -> InlineKeyboardMarkup:
    toggle_text = t(
        lang,
        "profile_courier_online" if is_online else "profile_courier_offline",
    )
    toggle_icon = (
        CUSTOM_EMOJI["open_restaurant"] if is_online else CUSTOM_EMOJI["close_restaurant"]
    )
    lang_text = "ენის შეცვლა" if lang == "ka" else ("Change language" if lang == "en" else "Сменить язык")
    lang_emoji = "5384222159621102491"
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
                    text=t(lang, "profile_payouts"),
                    callback_data="profile_payouts",
                    icon_custom_emoji_id="5384518714227990146",
                ),
                InlineKeyboardButton(
                    text=lang_text,
                    icon_custom_emoji_id=lang_emoji,
                    callback_data="profile_change_language",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "profile_back"),
                    callback_data="profile_back",
                ),
            ],
        ]
    )

def get_language_switcher_kb(lang: str = "ru", back_callback: str = "profile_back") -> InlineKeyboardMarkup:
    if lang == "ka":
        back_text = "← უკან"
    elif lang == "en":
        back_text = "← Back"
    else:
        back_text = "← Назад"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ქართული",
                    icon_custom_emoji_id=CUSTOM_EMOJI["flag_ka"],
                    callback_data="set_user_lang_ka",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Русский",
                    icon_custom_emoji_id=CUSTOM_EMOJI["flag_ru"],
                    callback_data="set_user_lang_ru",
                ),
                InlineKeyboardButton(
                    text="English",
                    icon_custom_emoji_id=CUSTOM_EMOJI["flag_en"],
                    callback_data="set_user_lang_en",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=back_text,
                    callback_data=back_callback,
                ),
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

        rush_mode = await db.get_partner_rush_mode(restaurant_id)
        kb = get_restaurant_profile_kb(is_open, lang, restaurant_id, rush_mode)
        
        fields = {
            "restaurant_name": name,
            "rating": "4.9",
            "status_badge": status_badge,
            "active_orders": f"{active_n} active orders",
            "payout": _fmt_banner_lari(int(round(balance))),
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
            
        kb = get_courier_profile_kb(is_online, lang=lang)
        
        fields = {
            "courier_name": name,
            "rating": "5.0",
            # ON LINE запечён в Banner-6a для online; offline — через conditional.
            "status_badge": "online" if is_online else "offline",
            "deliveries_count": f"{deliveries_n} {'delivery' if deliveries_n == 1 else 'deliveries'}",
            "earnings": _fmt_banner_lari(int(round(balance))),
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
        last_payout_text = t(lang, "comment_none_short")

    pending_req = await db.get_partner_pending_request(partner_id, role)
    pending_line = ""
    if pending_req:
        p_amt = float(pending_req["amount"])
        p_date = (pending_req.get("created_at") or "").split()[0]
        p_id = pending_req.get("id")
        if lang == "ru":
            pending_line = f'\n{ce("5382351125838077755", "⏳")} <b>В обработке:</b> {p_amt:.2f} ₾ <i>(Заявка #{p_id} от {p_date})</i>'
        elif lang == "en":
            pending_line = f'\n{ce("5382351125838077755", "⏳")} <b>In processing:</b> {p_amt:.2f} ₾ <i>(Request #{p_id} from {p_date})</i>'
        else:
            pending_line = f'\n{ce("5382351125838077755", "⏳")} <b>დამუშავებაშია:</b> {p_amt:.2f} ₾ <i>(მოთხოვნა #{p_id})</i>'
        
    if lang == "ru":
        text = (
            f'{ce(CUSTOM_EMOJI["payouts"], "💳")} <b>Выплаты</b>\n\n'
            f'{ce(CUSTOM_EMOJI["balance"], "💰")} <b>Доступно к выводу:</b> {balance:.2f} ₾'
            f'{pending_line}\n'
            f'{ce(CUSTOM_EMOJI["hours"], "🕒")} <b>Последняя выплата:</b> {last_payout_text}'
        )
        btn_request = "Запросить выплату"
        btn_back = t(lang, "profile_back")
    elif lang == "en":
        text = (
            f'{ce(CUSTOM_EMOJI["payouts"], "💳")} <b>Payouts</b>\n\n'
            f'{ce(CUSTOM_EMOJI["balance"], "💰")} <b>Available for withdrawal:</b> {balance:.2f} ₾'
            f'{pending_line}\n'
            f'{ce(CUSTOM_EMOJI["hours"], "🕒")} <b>Last payout:</b> {last_payout_text}'
        )
        btn_request = "Request payout"
        btn_back = t(lang, "profile_back")
    else:
        text = (
            f'{ce(CUSTOM_EMOJI["payouts"], "💳")} <b>გადახდები</b>\n\n'
            f'{ce(CUSTOM_EMOJI["balance"], "💰")} <b>გასატანად ხელმისაწვდომია:</b> {balance:.2f} ₾'
            f'{pending_line}\n'
            f'{ce(CUSTOM_EMOJI["hours"], "🕒")} <b>ბოლო გადახდა:</b> {last_payout_text}'
        )
        btn_request = "თანხის გატანის მოთხოვნა"
        btn_back = t(lang, "profile_back")
        
    buttons = []
    if balance > 0 and not pending_req:
        buttons.append([
            InlineKeyboardButton(
                text=btn_request,
                icon_custom_emoji_id="5384520939021048827",
                callback_data="payout_request_action",
            )
        ])
    elif pending_req:
        p_label = {
            "ru": f"Заявка #{pending_req['id']} в обработке",
            "en": f"Request #{pending_req['id']} pending",
            "ka": f"მოთხოვნა #{pending_req['id']} მუშავდება",
        }.get(lang, "Заявка в обработке")
        buttons.append([
            InlineKeyboardButton(
                text=p_label,
                icon_custom_emoji_id="5382351125838077755",
                callback_data="payout_pending_info",
            )
        ])
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


@router.message(Command("lang"))
@router.message(Command("language"))
async def cmd_language(message: Message, state: FSMContext):
    await state.clear()
    lang = await user_lang(message.from_user.id)
    kb = get_language_switcher_kb(lang=lang, back_callback="nav_profile")
    if lang == "ka":
        title = "აირჩიეთ ინტერფეისის ენა:"
    elif lang == "en":
        title = "Choose interface language:"
    else:
        title = "Выберите язык интерфейса:"
    text = f'{ce("5384222159621102491", "🌐")} <b>{title}</b>'
    await message.answer(
        text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "profile_change_language")
async def on_profile_change_language(callback: CallbackQuery):
    lang = await user_lang(callback.from_user.id)
    kb = get_language_switcher_kb(lang=lang, back_callback="nav_profile")
    if lang == "ka":
        title = "აირჩიეთ ინტერფეისის ენა:"
    elif lang == "en":
        title = "Choose interface language:"
    else:
        title = "Выберите язык интерфейса:"
    text = f'{ce("5384222159621102491", "🌐")} <b>{title}</b>'
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        else:
            await callback.message.edit_text(
                text=text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        try:
            await callback.message.edit_text(
                text=text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await callback.message.answer(
                text=text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
    await callback.answer()


@router.callback_query(F.data.startswith("set_user_lang_"))
async def on_set_user_language(callback: CallbackQuery, state: FSMContext):
    new_lang = callback.data.split("_")[-1]  # ka, ru, en
    tg_id = callback.from_user.id
    await db.set_user_language(tg_id, new_lang)
    await state.update_data(language=new_lang)

    user = await db.get_bot_user(tg_id) or {}
    role = user.get("role", "")

    if role == "courier":
        is_online = user.get("is_online", 0) == 1
        await set_courier_reply_kb(tg_id, new_lang, is_online)

    lang_names = {"ka": "ქართული", "ru": "Русский", "en": "English"}
    alert_msgs = {
        "ka": f"ენა შეიცვალა: {lang_names.get(new_lang, new_lang)}",
        "ru": f"Язык изменён: {lang_names.get(new_lang, new_lang)}",
        "en": f"Language changed: {lang_names.get(new_lang, new_lang)}",
    }
    await callback.answer(alert_msgs.get(new_lang, f"Язык: {new_lang}"), show_alert=True)

    user["language"] = new_lang
    if role:
        await render_and_send_profile(callback.message.chat.id, callback.message.message_id, tg_id, user)
    else:
        await callback.message.edit_text(
            get_text(new_lang, "choose_role"),
            reply_markup=get_role_kb(new_lang),
            parse_mode=ParseMode.HTML,
        )


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
        # Soft-block: нельзя выйти на линию
        if user.get("is_online", 0) != 1:
            block = await db.get_courier_block(tg)
            if block:
                until_hm = datetime.fromtimestamp(float(block["until_ts"])).strftime("%d.%m, %H:%M")
                await callback.answer(
                    f"Доступ временно ограничен до {until_hm}",
                    show_alert=True,
                )
                return
        is_online = user.get("is_online", 0) == 1
        new_status = 0 if is_online else 1
        action = "set_online" if new_status == 1 else "set_offline"
        ok = await update_courier_online_backend(tg, action)
        if not ok:
            await callback.answer(
                "⚠️ Не удалось синхронизировать статус с сервером. Повторите.",
                show_alert=True,
            )
            return
        await db.set_courier_online_status(tg, new_status)
        
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


@router.callback_query(F.data == "profile_toggle_rush")
async def on_profile_toggle_rush(callback: CallbackQuery):
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    role = user.get("role", "")
    lang = user.get("language", "ru")

    if role != "restaurant_admin":
        await callback.answer()
        return

    partner = (
        await db.get_partner_by_telegram(callback.message.chat.id)
        or await db.get_partner_by_telegram(tg)
        or {}
    )
    restaurant_id = partner.get("restaurant_id", "")
    if not restaurant_id:
        await callback.answer("Ресторан не найден", show_alert=True)
        return

    current_mode = await db.get_partner_rush_mode(restaurant_id)
    # Cycle: 0 (Auto) -> 1 (ON) -> -1 (OFF) -> 0 (Auto)
    if current_mode == 0:
        new_mode = 1
        msg = (
            "🔥 Режим запары включён!\nНа странице оформления установлено время 45–65 мин и баннер часа пик."
            if lang == "ru"
            else (
                "🔥 Rush mode ON!\nDelivery time set to 45–65 min with rush notice."
                if lang == "en"
                else "🔥 პიკის საათი ჩართულია!\nმიტანის დროა 45–65 წთ."
            )
        )
    elif current_mode == 1:
        new_mode = -1
        msg = (
            "Режим запары принудительно выключен (стандартное время 25–40 мин)."
            if lang == "ru"
            else (
                "Rush mode forced OFF (standard 25–40 min)."
                if lang == "en"
                else "პიკის საათი გამორთულია (სტანდარტული 25–40 წთ)."
            )
        )
    else:
        new_mode = 0
        msg = (
            "Режим запары переведён в Авто (активен в вечерний час пик 18:00–22:00)."
            if lang == "ru"
            else (
                "Rush mode set to Auto (active 18:00–22:00)."
                if lang == "en"
                else "პიკის საათი ავტო რეჟიმშია (18:00–22:00)."
            )
        )

    await db.set_partner_rush_mode(restaurant_id, new_mode)
    await callback.answer(msg, show_alert=True)
    await render_and_send_profile(callback.message.chat.id, callback.message.message_id, tg, user)


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
        await callback.answer(t(lang, "alert_balance_zero"), show_alert=True)
        return

    # Защита от дублирования заявок (debounce / pending check)
    pending = await db.get_pending_payout_requests()
    if any(str(r.get("partner_id")) == str(partner_id) for r in pending):
        dup_msg = {
            "ru": "У вас уже есть активная заявка на вывод в обработке.",
            "en": "You already have an active withdrawal request pending.",
            "ka": "თქვენ უკვე გაქვთ აქტიური მოთხოვნა დამუშავების პროცესში.",
        }.get(lang, "Заявка уже на рассмотрении.")
        await callback.answer(dup_msg, show_alert=True)
        return

    req_id = await db.create_payout_request(partner_id, role, balance)
    if req_id:
        pname = ""
        role_label = ""
        if role == "restaurant_admin":
            partner = (
                await db.get_partner_by_telegram(callback.message.chat.id)
                or await db.get_partner_by_telegram(tg)
                or await db.get_partner_by_restaurant(partner_id)
                or {}
            )
            pname = partner.get("restaurant_name") or user.get("backend_username") or partner_id
            role_label = "Ресторан"
        else:
            pname = user.get("backend_username") or callback.from_user.full_name or f"Курьер {tg}"
            role_label = "Курьер"

        if ADMIN_TG_ID:
            try:
                from datetime import datetime as _dt
                now_str = _dt.now().strftime("%d.%m.%Y %H:%M")
                username_str = f"@{callback.from_user.username}" if callback.from_user.username else f"id: {tg}"
                
                admin_text = (
                    f'{ce("5384520939021048827", "💰")} <b>Новая заявка на выплату #{req_id}!</b>\n\n'
                    f'• <b>Партнёр:</b> {html.escape(str(pname))} ({role_label})\n'
                    f'• <b>Сумма к выплате:</b> <code>{balance:.2f} ₾</code>\n'
                    f'• <b>Telegram:</b> {username_str} (<code>{tg}</code>)\n'
                    f'• <b>Дата:</b> {now_str}'
                )
                
                admin_kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=f"✅ Одобрить {balance:.2f} ₾",
                                callback_data=f"admin_payout_direct_approve_{req_id}",
                            ),
                            InlineKeyboardButton(
                                text="❌ Отклонить",
                                callback_data=f"admin_payout_direct_reject_{req_id}",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                text="Все заявки в панели",
                                icon_custom_emoji_id="5384222159621102491",
                                callback_data="admin_payouts",
                            ),
                        ],
                    ]
                )
                
                await bot.send_message(
                    chat_id=int(ADMIN_TG_ID),
                    text=admin_text,
                    reply_markup=admin_kb,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                log.warning("Notify admin payout request failed: %s", e)

        # 1. Popup alert
        if lang == "ru":
            alert_msg = f"✅ Заявка #{req_id} на {balance:.2f} ₾ принята!\nМы обработаем её в ближайшее время."
        elif lang == "en":
            alert_msg = f"✅ Request #{req_id} for {balance:.2f} ₾ accepted!\nWe will process it shortly."
        else:
            alert_msg = f"✅ მოთხოვნა #{req_id} ({balance:.2f} ₾) მიღებულია!\nდამუშავდება უახლოეს დროში."

        await callback.answer(alert_msg, show_alert=True)

        # 2. Confirmation message in partner's chat
        try:
            if lang == "ru":
                conf_text = (
                    f'{ce("5384244502040975393", "✅")} <b>Заявка на выплату #{req_id} отправлена!</b>\n\n'
                    f'• <b>Сумма:</b> {balance:.2f} ₾\n'
                    f'• <b>Статус:</b> В обработке\n\n'
                    f'<i>Администратор уже получил уведомление. Обычно выплата занимает от 15 минут до нескольких часов. '
                    f'Как только средства будут переведены, вы получите подтверждение здесь.</i>'
                )
            elif lang == "en":
                conf_text = (
                    f'{ce("5384244502040975393", "✅")} <b>Payout request #{req_id} sent!</b>\n\n'
                    f'• <b>Amount:</b> {balance:.2f} ₾\n'
                    f'• <b>Status:</b> In processing\n\n'
                    f'<i>The administrator has received your request. You will be notified as soon as the funds are transferred.</i>'
                )
            else:
                conf_text = (
                    f'{ce("5384244502040975393", "✅")} <b>თანხის გატანის მოთხოვნა #{req_id} გაგზავნილია!</b>\n\n'
                    f'• <b>თანხა:</b> {balance:.2f} ₾\n'
                    f'• <b>სტატუსი:</b> დამუშავებაშია\n\n'
                    f'<i>ადმინისტრატორს უკვე გაეგზავნა შეტყობინება. თანხის ჩარიცხვისთანავე მიიღებთ შეტყობინებას.</i>'
                )
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=conf_text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            log.warning("Sending partner payout confirmation message failed: %s", e)

        await render_payouts_screen(callback.message.chat.id, callback.message.message_id, tg, user)
    else:
        await callback.answer(t(lang, "alert_payout_error"), show_alert=True)


@router.callback_query(F.data == "payout_pending_info")
async def payout_pending_info(callback: CallbackQuery):
    lang = await user_lang(callback.from_user.id)
    msg = {
        "ru": "Ваша заявка на выплату находится на рассмотрении у администратора. Средства поступят в ближайшее время.",
        "en": "Your payout request is under review by the administrator. Funds will arrive shortly.",
        "ka": "თქვენი მოთხოვნა განხილვის პროცესშია. თანხა ჩაირიცხება უახლოეს დროში.",
    }.get(lang, "Заявка на рассмотрении.")
    await callback.answer(msg, show_alert=True)


@router.callback_query(F.data.startswith("admin_payout_direct_approve_"))
async def admin_payout_direct_approve_callback(callback: CallbackQuery):
    is_admin = (callback.from_user.id == ADMIN_TG_ID) or (await db.is_super_admin(callback.from_user.id))
    if not is_admin:
        await callback.answer("Доступ запрещен", show_alert=True)
        return

    req_id = int(callback.data.split("_")[-1])
    req = await db.get_payout_request_by_id(req_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if req.get("status") != "pending":
        st = "одобрена" if req.get("status") == "approved" else "отклонена"
        await callback.answer(f"Заявка #{req_id} уже была {st}!", show_alert=True)
        return

    success = await db.approve_payout_request(req_id)
    if success:
        await callback.answer(f"Заявка #{req_id} успешно одобрена!", show_alert=True)
        
        partner_id = req["partner_id"]
        role = req["role"]
        amount = req["amount"]
        
        partner_chat_id = None
        pname = partner_id
        if role == "restaurant_admin":
            partner = await db.get_partner_by_restaurant(partner_id)
            if partner:
                partner_chat_id = partner.get("telegram_id")
                pname = partner.get("restaurant_name") or partner_id
        else:
            try:
                partner_chat_id = int(partner_id)
                tg_user = await db.get_bot_user(partner_chat_id) or {}
                pname = tg_user.get("backend_username") or f"Курьер {partner_id}"
            except Exception:
                pass
            
        if partner_chat_id:
            try:
                tg_user = await db.get_bot_user(partner_chat_id) or {}
                lang = tg_user.get("language", "ru")
                if lang == "ru":
                    notif = (
                        f'{ce("5384244502040975393", "✅")} <b>Выплата #{req_id} на сумму {amount:.2f} ₾ одобрена!</b>\n\n'
                        f'Средства отправлены и зачислены по вашим платёжным реквизитам. Спасибо за работу!'
                    )
                elif lang == "en":
                    notif = (
                        f'{ce("5384244502040975393", "✅")} <b>Payout #{req_id} for {amount:.2f} ₾ approved!</b>\n\n'
                        f'Funds have been sent to your account. Thank you!'
                    )
                else:
                    notif = (
                        f'{ce("5384244502040975393", "✅")} <b>გადახდა #{req_id} ({amount:.2f} ₾) დამტკიცებულია!</b>\n\n'
                        f'თანხა ჩარიცხულია თქვენს ანგარიშზე. მადლობა თანამშრომლობისთვის!'
                    )
                await bot.send_message(chat_id=partner_chat_id, text=notif, parse_mode=ParseMode.HTML)
            except Exception as e:
                log.warning(f"Failed sending payout approval notification to {partner_chat_id}: {e}")

        from datetime import datetime as _dt
        now_str = _dt.now().strftime("%d.%m.%Y %H:%M")
        who = f"@{callback.from_user.username}" if callback.from_user.username else f"ID {callback.from_user.id}"
        updated_text = (
            f'{ce("5384244502040975393", "✅")} <b>Заявка на выплату #{req_id} ОДОБРЕНА!</b>\n\n'
            f'• <b>Партнёр:</b> {html.escape(str(pname))}\n'
            f'• <b>Сумма:</b> <code>{amount:.2f} ₾</code>\n'
            f'• <b>Одобрил:</b> {who} ({now_str})\n'
            f'• <b>Статус:</b> Выплачено ✅'
        )
        try:
            await callback.message.edit_text(
                text=updated_text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="Все заявки в панели", icon_custom_emoji_id="5384222159621102491", callback_data="admin_payouts")]]
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    else:
        await callback.answer("Ошибка при одобрении заявки", show_alert=True)


@router.callback_query(F.data.startswith("admin_payout_direct_reject_"))
async def admin_payout_direct_reject_callback(callback: CallbackQuery):
    is_admin = (callback.from_user.id == ADMIN_TG_ID) or (await db.is_super_admin(callback.from_user.id))
    if not is_admin:
        await callback.answer("Доступ запрещен", show_alert=True)
        return

    req_id = int(callback.data.split("_")[-1])
    req = await db.get_payout_request_by_id(req_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if req.get("status") != "pending":
        st = "одобрена" if req.get("status") == "approved" else "отклонена"
        await callback.answer(f"Заявка #{req_id} уже была {st}!", show_alert=True)
        return

    success = await db.reject_payout_request(req_id)
    if success:
        await callback.answer(f"Заявка #{req_id} отклонена.", show_alert=True)
        
        partner_id = req["partner_id"]
        role = req["role"]
        amount = req["amount"]
        
        partner_chat_id = None
        pname = partner_id
        if role == "restaurant_admin":
            partner = await db.get_partner_by_restaurant(partner_id)
            if partner:
                partner_chat_id = partner.get("telegram_id")
                pname = partner.get("restaurant_name") or partner_id
        else:
            try:
                partner_chat_id = int(partner_id)
                tg_user = await db.get_bot_user(partner_chat_id) or {}
                pname = tg_user.get("backend_username") or f"Курьер {partner_id}"
            except Exception:
                pass
            
        if partner_chat_id:
            try:
                tg_user = await db.get_bot_user(partner_chat_id) or {}
                lang = tg_user.get("language", "ru")
                if lang == "ru":
                    notif = (
                        f'{ce("5348083587532994863", "❌")} <b>Заявка на выплату #{req_id} ({amount:.2f} ₾) отклонена.</b>\n\n'
                        f'Средства возвращены на ваш баланс в боте. Если у вас возникли вопросы, свяжитесь с поддержкой.'
                    )
                elif lang == "en":
                    notif = (
                        f'{ce("5348083587532994863", "❌")} <b>Payout request #{req_id} ({amount:.2f} ₾) was rejected.</b>\n\n'
                        f'The amount has been returned to your balance. Please contact support if you have questions.'
                    )
                else:
                    notif = (
                        f'{ce("5348083587532994863", "❌")} <b>მოთხოვნა #{req_id} ({amount:.2f} ₾) უარყოფილია.</b>\n\n'
                        f'თანხა დაბრუნებულია თქვენს ბალანსზე. კითხვების შემთხვევაში მიმართეთ ადმინისტრაციას.'
                    )
                await bot.send_message(chat_id=partner_chat_id, text=notif, parse_mode=ParseMode.HTML)
            except Exception as e:
                log.warning(f"Failed sending payout reject notification to {partner_chat_id}: {e}")

        from datetime import datetime as _dt
        now_str = _dt.now().strftime("%d.%m.%Y %H:%M")
        who = f"@{callback.from_user.username}" if callback.from_user.username else f"ID {callback.from_user.id}"
        updated_text = (
            f'{ce("5348083587532994863", "❌")} <b>Заявка на выплату #{req_id} ОТКЛОНЕНА</b>\n\n'
            f'• <b>Партнёр:</b> {html.escape(str(pname))}\n'
            f'• <b>Сумма:</b> <code>{amount:.2f} ₾</code>\n'
            f'• <b>Отклонил:</b> {who} ({now_str})\n'
            f'• <b>Статус:</b> Отклонено (баланс возвращён партнёру)'
        )
        try:
            await callback.message.edit_text(
                text=updated_text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="Все заявки в панели", icon_custom_emoji_id="5384222159621102491", callback_data="admin_payouts")]]
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    else:
        await callback.answer("Ошибка при отклонении заявки", show_alert=True)


async def send_stoplist_menu(chat_id: int, restaurant_id: str, lang: str = "ru", message_id: int | None = None):
    """Меню быстрого стоп-листа для ресторана."""
    def _fetch_dishes():
        dishes = []
        for path in CATALOG_DB_PATHS:
            if not os.path.exists(path):
                continue
            conn = None
            try:
                conn = connect_sqlite_wal(path)
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, name, is_available FROM products WHERE restaurant_id = ? ORDER BY name ASC LIMIT 40",
                    (restaurant_id,),
                )
                dishes = cur.fetchall()
                break
            except Exception as e:
                log.warning("Fetch dishes failed: %s", e)
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
        return dishes

    dishes = await asyncio.to_thread(_fetch_dishes)
    if not dishes:
        text = "ℹ️ В меню ресторана пока нет добавленных блюд."
        if message_id:
            try:
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(lang, "profile_back"), callback_data="profile_back")]]),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                await bot.send_message(chat_id=chat_id, text=text)
        else:
            await bot.send_message(chat_id=chat_id, text=text)
        return

    text = f'{ce("5384312315279612142", "🍽")} {t(lang, "stoplist_title")}'
    buttons = []
    for dish_id, raw_name, is_avail in dishes:
        name = _localize_item_name(raw_name, lang=lang) or "Блюдо"
        emoji_id = "5348348011489542390" if is_avail == 1 else "5348083587532994863"
        btn_text = name[:28]
        buttons.append([
            InlineKeyboardButton(
                text=btn_text,
                icon_custom_emoji_id=emoji_id,
                callback_data=f"toggle_dish:{dish_id}:{restaurant_id}",
            )
        ])

    buttons.append([InlineKeyboardButton(text=t(lang, "profile_back"), callback_data="profile_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if message_id:
        try:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=kb,
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.message(Command("stoplist"))
async def cmd_stoplist(message: Message):
    tg = message.from_user.id
    user = await db.get_bot_user(tg) or {}
    lang = user.get("language", "ru")
    partner = (
        await db.get_partner_by_telegram(message.chat.id)
        or await db.get_partner_by_telegram(tg)
        or {}
    )
    rest_id = partner.get("restaurant_id", "")
    if not rest_id:
        await message.answer("⚠️ Команда доступна только для ресторанов.")
        return
    await send_stoplist_menu(message.chat.id, rest_id, lang)


@router.callback_query(F.data.startswith("stoplist_open_"))
async def on_stoplist_open(callback: CallbackQuery):
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    if user.get("role") not in ("restaurant_admin", "admin") and not await db.is_super_admin(tg):
        await callback.answer("⛔ Доступ разрешён только рестораторам.", show_alert=True)
        return

    await callback.answer()
    rest_id = callback.data.replace("stoplist_open_", "")
    lang = user.get("language", "ru")
    if not rest_id:
        partner = (
            await db.get_partner_by_telegram(callback.message.chat.id)
            or await db.get_partner_by_telegram(tg)
            or {}
        )
        rest_id = partner.get("restaurant_id", "")
    await send_stoplist_menu(callback.message.chat.id, rest_id, lang, message_id=callback.message.message_id)


@router.callback_query(F.data.startswith("toggle_dish:"))
async def on_toggle_dish(callback: CallbackQuery):
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    if user.get("role") not in ("restaurant_admin", "admin") and not await db.is_super_admin(tg):
        await callback.answer("⛔ Доступ разрешён только рестораторам.", show_alert=True)
        return

    parts = callback.data.split(":")
    dish_id = parts[1]
    rest_id = parts[2]
    lang = await user_lang(tg)

    def _toggle():
        new_val = 0
        dname = ""
        for path in CATALOG_DB_PATHS:
            if not os.path.exists(path):
                continue
            conn = None
            try:
                conn = connect_sqlite_wal(path)
                cur = conn.cursor()
                cur.execute("SELECT name, is_available FROM products WHERE id = ?", (dish_id,))
                row = cur.fetchone()
                if row:
                    dname = row[0]
                    new_val = 0 if row[1] == 1 else 1
                    cur.execute("UPDATE products SET is_available = ? WHERE id = ?", (new_val, dish_id))
                    conn.commit()
                break
            except Exception as e:
                log.warning("Toggle dish failed: %s", e)
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
        return new_val, dname

    new_val, raw_name = await asyncio.to_thread(_toggle)
    name = _localize_item_name(raw_name, lang=lang) or "Блюдо"
    if new_val == 1:
        alert = t(lang, "alert_dish_available", name=name)
    else:
        alert = t(lang, "alert_dish_stopped", name=name)

    await callback.answer(alert, show_alert=False)
    await send_stoplist_menu(callback.message.chat.id, rest_id, lang, message_id=callback.message.message_id)

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
        prompt = f'{ce("5384244502040975393", "📝")} <b>Введите новое название ресторана:</b>'
    elif lang == "en":
        prompt = f'{ce("5384244502040975393", "📝")} <b>Enter new restaurant name:</b>'
    else:
        prompt = f'{ce("5384244502040975393", "📝")} <b>შეიყვანეთ რესტორნის ახალი სახელი:</b>'
        
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
        prompt = f'{ce("5384138412053796842", "📋")} <b>Введите новое описание ресторана:</b>'
    elif lang == "en":
        prompt = f'{ce("5384138412053796842", "📋")} <b>Enter new restaurant description:</b>'
    else:
        prompt = f'{ce("5384138412053796842", "📋")} <b>შეიყვანეთ რესტორნის ახალი აღწერა:</b>'
        
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
        prompt = f'{ce("5384312315279612142", "🖼")} <b>Отправьте новую фотографию для ресторана (одним сообщением):</b>'
    elif lang == "en":
        prompt = f'{ce("5384312315279612142", "🖼")} <b>Send a new photo for the restaurant (single message):</b>'
    else:
        prompt = f'{ce("5384312315279612142", "🖼")} <b>გამოაგზავნეთ რესტორნის ახალი ფოტო (ერთი შეტყობინებით):</b>'
        
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
    tg_user = await db.get_bot_user(callback.from_user.id) or {}
    if tg_user.get("role") not in ("restaurant_admin", "admin") and not await db.is_super_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ разрешён только рестораторам.", show_alert=True)
        return

    order_id = int(callback.data.split("_", 1)[1])
    telegram_id = callback.message.chat.id
    lang = await user_lang(telegram_id)

    log.info("Order #%d accepted by partner tg=%d", order_id, telegram_id)
    cancel_restaurant_accept_reminders(order_id)

    # Обновляем бэкенд
    success = await update_order_status_backend(order_id, "accepted")

    if success:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_prep_10"),
                    callback_data=f"prep_time:10:{order_id}",
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_prep_15"),
                    callback_data=f"prep_time:15:{order_id}",
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_prep_20"),
                    callback_data=f"prep_time:20:{order_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_start_cooking"),
                    callback_data=f"prepare_{order_id}",
                    style=ButtonStyle.SUCCESS,
                    icon_custom_emoji_id="5382351125838077755",
                ),
            ]
        ])
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer(t(lang, "alert_rest_accepted"), show_alert=True)
        await db.update_order_status(order_id, telegram_id, "accepted")
    else:
        await callback.answer(
            t(lang, "alert_status_update_err"),
            show_alert=True,
        )

@router.callback_query(F.data.startswith("prep_time:"))
async def on_prep_time(callback: CallbackQuery):
    tg_user = await db.get_bot_user(callback.from_user.id) or {}
    if tg_user.get("role") not in ("restaurant_admin", "admin") and not await db.is_super_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ разрешён только рестораторам.", show_alert=True)
        return

    parts = callback.data.split(":")
    minutes = int(parts[1])
    order_id = int(parts[2])
    telegram_id = callback.message.chat.id
    lang = await user_lang(telegram_id)

    log.info("Order #%d prep time set to %d min by partner tg=%d", order_id, minutes, telegram_id)
    cancel_restaurant_accept_reminders(order_id)

    # Сохраняем delay_minutes в order.db
    for path in ORDER_DB_PATHS:
        if os.path.exists(path):
            try:
                conn = connect_sqlite_wal(path)
                conn.execute(
                    "UPDATE orders SET delay_minutes = ? WHERE id = ?",
                    (minutes, order_id),
                )
                conn.commit()
                conn.close()
                break
            except Exception as e:
                log.warning("Save prep time failed order=%d: %s", order_id, e)

    await update_order_status_backend(order_id, "preparing")
    await db.update_order_status(order_id, telegram_id, "preparing")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t(lang, "btn_ready_for_pickup"),
                callback_data=f"ready_{order_id}",
                style=ButtonStyle.SUCCESS,
                icon_custom_emoji_id="5384312315279612142",
            ),
        ],
        [
            InlineKeyboardButton(
                text=t(lang, "btn_open_details"),
                web_app=WebAppInfo(url=miniapp_page_url(order_id=order_id)),
                icon_custom_emoji_id="5384138412053796842",
            ),
        ],
    ])

    # Обновляем заголовок карточки с таймингом готовности (UTC+4 Тбилиси)
    now_tb = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=4)
    ready_time = (now_tb + datetime.timedelta(minutes=minutes)).strftime("%H:%M")
    order_row = _get_order_row(order_id)
    prep_caption = format_order_message(
        order_row or {"order_id": order_id},
        lang=lang,
        status="preparing",
        ready_time=ready_time,
    )
    try:
        await callback.message.edit_caption(
            caption=prep_caption,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e_edit:
        log.warning("edit caption on_prep_time failed order=%s: %s", order_id, e_edit)
        await callback.message.edit_reply_markup(reply_markup=keyboard)

    await callback.answer(t(lang, "alert_prep_time_set", n=minutes), show_alert=True)

@router.callback_query(F.data.startswith("prepare_"))
async def on_prepare(callback: CallbackQuery):
    tg_user = await db.get_bot_user(callback.from_user.id) or {}
    if tg_user.get("role") not in ("restaurant_admin", "admin") and not await db.is_super_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ разрешён только рестораторам.", show_alert=True)
        return

    order_id = int(callback.data.split("_", 1)[1])
    telegram_id = callback.message.chat.id
    lang = await user_lang(telegram_id)

    log.info("Order #%d preparation started by partner tg=%d", order_id, telegram_id)
    cancel_restaurant_accept_reminders(order_id)

    success = await update_order_status_backend(order_id, "preparing")

    if success:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_ready_for_pickup"),
                    callback_data=f"ready_{order_id}",
                    style=ButtonStyle.SUCCESS,
                    icon_custom_emoji_id="5384312315279612142",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_open_details"),
                    web_app=WebAppInfo(url=miniapp_page_url(order_id=order_id)),
                    icon_custom_emoji_id="5384138412053796842",
                ),
            ],
        ])
        order_row = _get_order_row(order_id)
        prep_caption = format_order_message(
            order_row or {"order_id": order_id},
            lang=lang,
            status="preparing",
        )
        try:
            await callback.message.edit_caption(
                caption=prep_caption,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer(t(lang, "alert_rest_preparing"), show_alert=True)
        await db.update_order_status(order_id, telegram_id, "preparing")
    else:
        await callback.answer(t(lang, "alert_status_update_err"), show_alert=True)

@router.callback_query(F.data.startswith("ready_"))
async def on_ready(callback: CallbackQuery):
    order_id = int(callback.data.split("_", 1)[1])
    telegram_id = callback.message.chat.id
    lang = await user_lang(telegram_id)

    log.info("Order #%d ready by partner tg=%d", order_id, telegram_id)
    cancel_restaurant_accept_reminders(order_id)

    success = await update_order_status_backend(order_id, "ready")

    if success:
        ready_details_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=t(lang, "btn_open_details"),
                web_app=WebAppInfo(url=miniapp_page_url(order_id=order_id)),
                icon_custom_emoji_id="5384138412053796842",
            ),
        ]])
        order_row = _get_order_row(order_id)
        ready_caption = format_order_message(
            order_row or {"order_id": order_id},
            lang=lang,
            status="ready",
        )
        try:
            await callback.message.edit_caption(
                caption=ready_caption,
                reply_markup=ready_details_kb,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await callback.message.edit_reply_markup(reply_markup=ready_details_kb)
        await callback.answer(t(lang, "alert_rest_ready"), show_alert=True)
        await db.update_order_status(order_id, telegram_id, "ready")
        # Подсказка назначенному курьеру: можно забирать.
        try:
            msgs = await db.get_messages_for_order(order_id)
            for m in msgs:
                if (m.get("kind") or "") not in ("tracking", "winner"):
                    continue
                if (m.get("role") or "") != "courier":
                    continue
                cid = int(m.get("telegram_id") or 0)
                mid = int(m.get("message_id") or 0)
                if not cid:
                    continue
                try:
                    clang = await user_lang(cid)
                    await bot.send_message(
                        chat_id=cid,
                        text=(
                            f'{ce("5384518714227990146", "✅")} '
                            f"<b>{t(clang, 'courier_ready_notify', order_id=order_id)}</b>"
                        ),
                        parse_mode=ParseMode.HTML,
                        reply_to_message_id=mid or None,
                    )
                except Exception as e:
                    log.warning("ready→courier notify failed order=%d tg=%d: %s", order_id, cid, e)
                break
        except Exception as e:
            log.warning("ready→courier notify outer failed order=%d: %s", order_id, e)
    else:
        await callback.answer(
            t(lang, "alert_status_update_err"),
            show_alert=True,
        )


def _parse_cancel_total_from_caption(caption: str) -> str:
    """Достаёт сумму позиций из caption заказа → «₾ N.NN»."""
    if not caption:
        return _fmt_banner_lari(0)
    match = re.search(
        r"(?:Сумма заказа|Order total|შეკვეთის თანხა)\s*:</?b>?\s*([\d.,]+)"
        r"|(?:Сумма заказа|Order total|შეკვეთის თანხა):.*?(?:<b>)?([\d.,]+)",
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


async def user_lang(telegram_id: int) -> str:
    user = await db.get_bot_user(int(telegram_id)) or {}
    return user.get("language", "ka") or "ka"


def _reject_confirm_kb(order_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_reject_yes"),
                    callback_data=f"rj_yes_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_reject_no"),
                    callback_data=f"rj_no_{order_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ]
        ]
    )


def _reject_reason_kb(order_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=reject_reason_label(code, lang),
            callback_data=f"rj_rs_{order_id}_{code}",
        )]
        for code in REJECT_REASON_DEFS
    ]
    rows.append(
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=f"rj_no_{order_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _reject_delay_kb(order_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_delay_min", n=10),
                    callback_data=f"rj_dl_{order_id}_10",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_delay_min", n=15),
                    callback_data=f"rj_dl_{order_id}_15",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_delay_min", n=20),
                    callback_data=f"rj_dl_{order_id}_20",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_reject_anyway"),
                    callback_data=f"rj_fx_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
            ],
            [
                InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=f"rj_yes_{order_id}"),
            ],
        ]
    )


def _apply_process_until_caption(
    html_text: str, extra_min: int, lang: str = "ru"
) -> tuple[str, str]:
    """Меняет дедлайн на «Обработать до / Process by / დაამუშავეთ სანამ»."""
    deadline = datetime.now() + timedelta(minutes=extra_min)
    new_hm = deadline.strftime("%H:%M")
    text = html_text or ""
    process_label = t(lang, "label_process_by")
    created_label = t(lang, "label_created")

    text = re.sub(
        r"\n?\s*⏱?\s*(?:Ресторан запросил|Restaurant requested|რესტორანმა მოითხოვა)"
        r"\s*\+\d+\s*(?:мин|min|წთ|წუთ)[^\n]*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # RU / EN / KA deadline markers in one pass
    accept_or_process = (
        r"(?:Принять до|Обработать до|Accept by|Process by|"
        r"მიიღეთ სანამ|დაამუშავეთ სანამ)"
    )
    created_marker = (
        r"(?:Создан|Created|შექმნილია)"
    )

    updated, n = re.subn(
        rf"((?:{created_marker}</b>\s*:\s*|{created_marker}\s*:\s*)\d{{1,2}}:\d{{2}}\s*·\s*)"
        rf"(?:<b>)?{accept_or_process}(?:</b>)?\s*:\s*"
        rf"\d{{1,2}}:\d{{2}}(?:\s*\(~?\d+\s*(?:мин|min|წთ|წუთ)\))?",
        rf"\1<b>{process_label}</b>: {new_hm}",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    if not n:
        updated, n = re.subn(
            rf"(?:<b>)?{accept_or_process}(?:</b>)?\s*:\s*"
            rf"\d{{1,2}}:\d{{2}}(?:\s*\(~?\d+\s*(?:мин|min|წთ|წუთ)\))?",
            f"<b>{process_label}</b>: {new_hm}",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    if not n:
        updated = text.rstrip() + f"\n <b>{process_label}</b>: {new_hm}"

    # Keep created label consistent with partner language when we rewrote the line
    if n and created_label:
        updated = re.sub(
            rf"(?:Создан|Created|შექმნილია)(?=</b>\s*:|\s*:)",
            created_label,
            updated,
            count=1,
            flags=re.IGNORECASE,
        )

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
    lang: str = "ru",
) -> str:
    """Caption под баннером 3a: иконка + заголовок, причина отдельной мягкой строкой."""
    icon = ce("5384244502040975393", "❌")
    if by == "admin":
        return f"{icon} <b>{t(lang, 'caption_rest_rejected_admin', order_id=order_id)}</b>"
    reason = (reason or "").strip()
    parts = [f"{icon} <b>{t(lang, 'caption_rest_rejected', order_id=order_id)}</b>"]
    if reason:
        parts.append("")
        parts.append(t(lang, "caption_rest_reason", reason=html.escape(reason)))
    else:
        parts.append(t(lang, "caption_rest_refused"))
    return "\n".join(parts)


def format_courier_cancel_caption(order_id: int | str, lang: str = "ru") -> str:
    return (
        f'{ce("5384244502040975393", "❌")} '
        f"<b>{t(lang, 'caption_courier_cancelled', order_id=order_id)}</b>"
    )


async def _finalize_restaurant_reject(
    *,
    chat_id: int,
    message_id: int,
    order_id: int,
    caption_html: str,
    is_photo: bool,
    reason_label: str,
    lang: str = "ru",
) -> bool:
    """Отмена рестораном: banner + caption, затем PATCH cancelled."""
    cancel_total = _parse_cancel_total_from_caption(caption_html or "")
    cancel_time = datetime.now().strftime("%H:%M")
    cancelled_by = t(lang, "cancelled_by_restaurant")
    new_caption = format_restaurant_cancel_caption(
        order_id, reason=reason_label, by="restaurant", lang=lang
    )
    meta = {
        "reason": reason_label,
        "cancelled_by": cancelled_by,
        "cancel_total": cancel_total,
        "cancel_time": cancel_time,
        "caption": new_caption,
        "lang": lang,
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
        "cancelled_by": cancelled_by,
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
    lang = await user_lang(callback.from_user.id)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_reject_confirm_kb(order_id, lang=lang)
        )
    except Exception as e:
        log.warning("reject confirm kb failed: %s", e)
    await callback.answer(
        t(lang, "alert_reject_confirm", order_id=order_id),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("rj_no_"))
async def on_reject_cancel(callback: CallbackQuery):
    """Отмена флоу отклонения — вернуть Accept/Reject."""
    order_id = int(callback.data.split("_", 2)[2])
    lang = await user_lang(callback.from_user.id)
    await callback.answer(t(lang, "alert_reject_cancelled"))
    try:
        await callback.message.edit_reply_markup(
            reply_markup=make_order_keyboard(order_id, lang=lang)
        )
    except Exception as e:
        log.warning("rj_no restore kb failed: %s", e)


@router.callback_query(F.data.startswith("rj_yes_"))
async def on_reject_yes(callback: CallbackQuery):
    """Шаг 2: выбор причины."""
    order_id = int(callback.data.split("_", 2)[2])
    lang = await user_lang(callback.from_user.id)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_reject_reason_kb(order_id, lang=lang)
        )
    except Exception as e:
        log.warning("rj_yes reason kb failed: %s", e)
    await callback.answer(t(lang, "alert_pick_reject_reason"))


@router.callback_query(F.data.startswith("rj_rs_"))
async def on_reject_reason(callback: CallbackQuery):
    """Шаг 3: причина → отложить или финализировать."""
    # rj_rs_{order_id}_{code}
    parts = callback.data.split("_")
    lang = await user_lang(callback.from_user.id)
    if len(parts) < 4:
        await callback.answer(t(lang, "alert_data_error"), show_alert=True)
        return
    order_id = int(parts[2])
    code = parts[3]
    info = REJECT_REASON_DEFS.get(code)
    if not info:
        await callback.answer(t(lang, "alert_unknown_reason"), show_alert=True)
        return
    _, delayable = info
    label = reject_reason_label(code, lang)

    if delayable:
        _RESTAURANT_CANCEL_META[int(order_id)] = {
            "_pending_reason": label,
            "_pending_code": code,
        }
        try:
            await callback.message.edit_reply_markup(
                reply_markup=_reject_delay_kb(order_id, lang=lang)
            )
        except Exception as e:
            log.warning("rj_rs delay kb failed: %s", e)
        await callback.answer(
            t(lang, "alert_delay_or_reject", label=label),
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
        lang=lang,
    )
    if ok:
        await callback.answer(t(lang, "alert_rest_rejected"))
    else:
        await callback.answer(t(lang, "alert_status_update_err"), show_alert=True)


@router.callback_query(F.data.startswith("rj_dl_"))
async def on_reject_delay(callback: CallbackQuery):
    """Задержка = авто-принятие заказа + сдвиг «Обработать до»."""
    parts = callback.data.split("_")
    lang = await user_lang(callback.from_user.id)
    if len(parts) < 4:
        await callback.answer(t(lang, "alert_data_error"), show_alert=True)
        return
    order_id = int(parts[2])
    extra_min = int(parts[3])
    chat_id = callback.message.chat.id
    _RESTAURANT_CANCEL_META.pop(int(order_id), None)

    # При информе о задержке заказ принимается автоматически.
    success = await update_order_status_backend(order_id, "accepted")
    if not success:
        await callback.answer(t(lang, "alert_status_update_err"), show_alert=True)
        return

    html_text = callback.message.html_text or callback.message.caption or ""
    new_caption, until_hm = _apply_process_until_caption(html_text, extra_min, lang=lang)
    timer_label = f"{extra_min}:00"
    fields = _banner_fields_from_order_caption(order_id, html_text, timer_label)
    prepare_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_start_cooking"),
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
        t(lang, "alert_accepted_with_delay", n=extra_min, t=until_hm),
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
    lang = await user_lang(callback.from_user.id)
    meta = _RESTAURANT_CANCEL_META.get(int(order_id)) or {}
    code = meta.get("_pending_code") or "kb"
    label = meta.get("_pending_reason") or reject_reason_label(code, lang)
    ok = await _finalize_restaurant_reject(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        order_id=order_id,
        caption_html=callback.message.html_text or callback.message.caption or "",
        is_photo=bool(callback.message.photo or callback.message.document),
        reason_label=label,
        lang=lang,
    )
    if ok:
        await callback.answer(t(lang, "alert_rest_rejected"))
    else:
        await callback.answer(t(lang, "alert_status_update_err"), show_alert=True)


# ─── Отказ курьера от оффера (как reject у ресторана) ─────────────────────────

@router.callback_query(F.data.startswith("cr_call_"))
async def on_courier_call_client(callback: CallbackQuery):
    """Грузинский номер — карточка контакта с кнопкой набора."""
    lang = await user_lang(callback.from_user.id)
    try:
        order_id = int(callback.data.removeprefix("cr_call_"))
    except ValueError:
        await callback.answer(t(lang, "alert_generic_error"), show_alert=True)
        return
    phone = await resolve_courier_contact_phone(order_id)
    e164 = format_phone_e164(phone)
    if not e164:
        await callback.answer(t(lang, "alert_phone_unavailable"), show_alert=True)
        return
    customer_name = await asyncio.to_thread(
        _fetch_order_customer_name_sync, int(order_id)
    )
    await callback.answer()
    try:
        await bot.send_contact(
            chat_id=callback.message.chat.id,
            phone_number=e164,
            first_name=(customer_name[:64] or t(lang, "default_customer_name")),
        )
    except Exception as e:
        log.warning("send_contact failed order=%s phone=%s: %s", order_id, e164, e)
        hint = t(lang, "hint_tap_to_call")
        await callback.message.answer(
            f"<code>{html.escape(phone)}</code>\n{html.escape(hint)}",
            parse_mode=ParseMode.HTML,
        )


@router.callback_query(F.data.startswith("cr_ask_"))
async def on_courier_refuse_ask(callback: CallbackQuery):
    """Шаг 1: подтверждение отказа."""
    order_id = int(callback.data.rsplit("_", 1)[-1])
    lang = await user_lang(callback.from_user.id)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_courier_refuse_confirm_kb(order_id, lang=lang)
        )
    except Exception as e:
        log.warning("cr_ask confirm kb failed: %s", e)
    await callback.answer(
        t(lang, "alert_refuse_confirm", order_id=order_id),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("cr_no_"))
async def on_courier_refuse_no(callback: CallbackQuery):
    """Отмена флоу — вернуть Принять / Отказаться."""
    order_id = int(callback.data.rsplit("_", 1)[-1])
    lang = await user_lang(callback.from_user.id)
    await callback.answer(t(lang, "alert_refuse_cancelled"))
    try:
        await callback.message.edit_reply_markup(
            reply_markup=make_broadcast_keyboard(order_id, lang=lang)
        )
    except Exception as e:
        log.warning("cr_no restore kb failed: %s", e)


@router.callback_query(F.data.startswith("cr_yes_"))
async def on_courier_refuse_yes(callback: CallbackQuery):
    """Шаг 2: выбор причины."""
    order_id = int(callback.data.rsplit("_", 1)[-1])
    lang = await user_lang(callback.from_user.id)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_courier_refuse_reason_kb(order_id, lang=lang)
        )
    except Exception as e:
        log.warning("cr_yes reason kb failed: %s", e)
    await callback.answer(t(lang, "alert_pick_refuse_reason"))


@router.callback_query(F.data.startswith("cr_rs_"))
async def on_courier_refuse_reason(callback: CallbackQuery):
    """Шаг 3: причина → snooze 5 мин или финальный отказ."""
    # cr_rs_{order_id}_{code}
    parts = callback.data.split("_")
    lang = await user_lang(callback.from_user.id)
    if len(parts) < 4:
        await callback.answer(t(lang, "alert_data_error"), show_alert=True)
        return
    order_id = int(parts[2])
    code = parts[3]
    info = COURIER_REFUSE_REASON_DEFS.get(code)
    if not info:
        await callback.answer(t(lang, "alert_unknown_reason"), show_alert=True)
        return
    _, snoozeable = info
    label = courier_refuse_reason_label(code, lang)

    if snoozeable:
        _COURIER_REFUSE_META[int(order_id)] = {
            "_pending_reason": label,
            "_pending_code": code,
        }
        try:
            await callback.message.edit_reply_markup(
                reply_markup=_courier_snooze_kb(order_id, lang=lang)
            )
        except Exception as e:
            log.warning("cr_rs snooze kb failed: %s", e)
        await callback.answer(
            t(lang, "alert_snooze_or_refuse", label=label, n=COURIER_SNOOZE_MIN),
            show_alert=True,
        )
        return

    # Сразу финальный отказ
    ok = await _finalize_courier_refuse(
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        order_id=order_id,
        reason_label=label,
        is_photo=bool(callback.message.photo or callback.message.document),
        lang=lang,
    )
    if ok:
        await callback.answer(t(lang, "alert_refused_ok"), show_alert=True)
    else:
        try:
            await callback.message.edit_reply_markup(
                reply_markup=make_broadcast_keyboard(order_id, lang=lang)
            )
        except Exception:
            pass
        await callback.answer(t(lang, "alert_server_error"), show_alert=True)


@router.callback_query(F.data.startswith("cr_dl_"))
async def on_courier_refuse_snooze(callback: CallbackQuery):
    """Отложить предложение на 5 минут (только если на другом заказе)."""
    parts = callback.data.split("_")
    lang = await user_lang(callback.from_user.id)
    if len(parts) < 4:
        await callback.answer(t(lang, "alert_data_error"), show_alert=True)
        return
    order_id = int(parts[2])
    extra_min = int(parts[3])
    if extra_min > COURIER_SNOOZE_MIN:
        extra_min = COURIER_SNOOZE_MIN
    telegram_id = callback.from_user.id
    until_hm = (datetime.now() + timedelta(minutes=extra_min)).strftime("%H:%M")
    caption = format_courier_snooze_caption(order_id, until_hm, lang=lang)

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
        t(lang, "alert_snooze_ok", t=until_hm, n=extra_min),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("cr_fx_"))
async def on_courier_refuse_force(callback: CallbackQuery):
    """Отказаться сразу после delayable-причины."""
    order_id = int(callback.data.rsplit("_", 1)[-1])
    lang = await user_lang(callback.from_user.id)
    meta = _COURIER_REFUSE_META.get(int(order_id)) or {}
    code = meta.get("_pending_code") or "ao"
    label = meta.get("_pending_reason") or courier_refuse_reason_label(code, lang)
    ok = await _finalize_courier_refuse(
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        order_id=order_id,
        reason_label=label,
        is_photo=bool(callback.message.photo or callback.message.document),
        lang=lang,
    )
    if ok:
        await callback.answer(t(lang, "alert_refused_ok"))
    else:
        await callback.answer(t(lang, "alert_server_error"), show_alert=True)


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
    income_re = re.compile(r"(Доход:|Earnings:|შემოსავალი:)", re.I)
    tips_re = re.compile(r"(чаевые:|Tips:|ტიპსი:|ჩაი:)", re.I)
    for i, line in enumerate(lines):
        cleaned_lines.append(line)
        if income_re.search(line):
            # Строка чаевых идёт сразу под доходом — оставляем её тоже.
            if i + 1 < len(lines) and tips_re.search(lines[i + 1]):
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
    pickup_lbl = r"(?:Забрать|Pickup|წასაღები)"
    dropoff_lbl = r"(?:Привезти|Deliver to|მისატანი)"
    income_lbl = r"(?:Доход|Earnings|შემოსავალი)"

    m = re.search(
        rf"{pickup_lbl}:</b>\s*(.+?)(?:\n|$)",
        raw,
        flags=re.IGNORECASE,
    ) or re.search(rf"{pickup_lbl}:\s*(.+?)(?:\n|$)", plain, flags=re.IGNORECASE)
    if m:
        pickup = _strip_html(m.group(1))

    m = re.search(
        rf"{dropoff_lbl}:</b>\s*(.+?)(?:\n|$)",
        raw,
        flags=re.IGNORECASE,
    ) or re.search(rf"{dropoff_lbl}:\s*(.+?)(?:\n|$)", plain, flags=re.IGNORECASE)
    if m:
        dropoff = _strip_html(m.group(1))

    m = re.search(
        rf"{income_lbl}:</b>\s*([0-9]+(?:[.,][0-9]+)?)",
        raw,
        flags=re.IGNORECASE,
    ) or re.search(
        rf"{income_lbl}:\s*([0-9]+(?:[.,][0-9]+)?)",
        plain,
        flags=re.IGNORECASE,
    )
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
    tips_val = cached.get("tips", 0)
    # В блоке YOUR PAYOUT / missed — полная сумма: delivery + tips
    if cached.get("missed_payout") and fee is None and parsed.get("fee") is None:
        missed = cached["missed_payout"]
    else:
        try:
            missed = _fmt_banner_lari(_courier_payout_total(fee_val or 0, tips_val))
        except (TypeError, ValueError):
            missed = cached.get("missed_payout") or _fmt_banner_lari(0)

    return {
        "pickup_address": pickup,
        "dropoff_address": dropoff,
        "order_number": f"#{order_id}",
        "event_time": event_time or datetime.now().strftime("%H:%M"),
        "missed_payout": missed,
    }


def order_taken_caption(order_id: int | str, lang: str = "ru") -> str:
    return (
        f'{ce("5384244502040975393", "⏳")} '
        f"<b>{t(lang, 'caption_order_taken', order_id=order_id)}</b>"
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
    lang: str = "ru",
) -> bool:
    """Меняет баннер 5a → 7a (как 2a → 3a при отмене рестораном)."""
    fields = order_taken_banner_fields(
        order_id,
        pickup_address=pickup_address,
        dropoff_address=dropoff_address,
        fee=fee,
        caption=caption_html,
    )
    new_caption = order_taken_caption(order_id, lang=lang)
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
    """Достаёт адрес доставки из HTML-caption карточки заказа (ru/en/ka)."""
    if not html_text:
        return ""
    lbl = r"(?:Привезти|Deliver to|მისატანი)"
    m = re.search(
        rf"{lbl}:</b>\s*(.+?)(?:\n|$)",
        html_text,
        flags=re.IGNORECASE,
    )
    if not m:
        m = re.search(rf"{lbl}:\s*(.+?)(?:\n|$)", html_text, flags=re.IGNORECASE)
    if not m:
        return ""
    return re.sub(r"<[^>]+>", "", m.group(1)).strip()


def courier_action_alert(
    action: str,
    order_id: int,
    *,
    dropoff: str = "",
    gateway_text: str = "",
    lang: str = "ru",
) -> str:
    """Popup-текст статуса курьера (как show_alert у ресторана)."""
    if action == "accepted":
        return t(lang, "alert_courier_accepted")
    if action == "arrived_restaurant":
        return t(lang, "alert_courier_at_restaurant", order_id=order_id)
    if action == "picked_up":
        gt = (gateway_text or "").lower()
        not_ready = (
            "еще не" in gt
            or "ещё не" in gt
            or "ожидайте" in gt
            or "not ready" in gt
            or "wait" in gt
            or "ჯერ არ" in gt
            or "არ არის მზად" in gt
            or "მოიცადეთ" in gt
            or "დაელოდეთ" in gt
        )
        if not_ready:
            return gateway_text or t(lang, "alert_success")
        addr = (dropoff or "").strip() or t(lang, "alert_courier_dropoff_fallback")
        return t(lang, "alert_courier_picked_up", addr=addr)
    if action == "completed":
        return t(lang, "alert_courier_completed", order_id=order_id)
    if action == "rejected":
        return t(lang, "alert_courier_rejected", order_id=order_id)
    if action == "arrived":
        return gateway_text or t(lang, "alert_courier_at_client", order_id=order_id)
    return gateway_text or t(lang, "alert_success")


def normalize_phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def format_phone_e164(phone: str) -> str:
    digits = normalize_phone_digits(phone)
    return f"+{digits}" if digits else ""


def _coerce_coord(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    return v


def maps_nav_url(
    *,
    lat: float | None = None,
    lng: float | None = None,
    address: str = "",
) -> str | None:
    """Ссылка навигации Google Maps по адресу с гео-привязкой к Местии."""
    if lat is not None and lng is not None:
        try:
            flat, flng = float(lat), float(lng)
            if abs(flat) > 0.1 and abs(flng) > 0.1:
                return f"https://maps.google.com/?q={flat:.6f},{flng:.6f}"
        except (TypeError, ValueError):
            pass
    addr = (address or "").strip()
    if not addr or addr == "—":
        return None
    # Добавляем Mestia для 100% точного геопозиционирования в картах
    if "mestia" not in addr.lower() and "მესტია" not in addr:
        addr = f"{addr}, Mestia"
    return f"https://www.google.com/maps/dir/?api=1&destination={quote(addr)}"


def html_maps_link(
    text: str,
    *,
    lat: float | None = None,
    lng: float | None = None,
    address: str = "",
    search_query: str = "",
) -> str:
    """Текст адреса как кликабельная ссылка на карты; без URL — обычный escape."""
    label = (text or "").strip() or "—"
    safe = html.escape(label)
    query = search_query or address or label
    url = maps_nav_url(lat=lat, lng=lng, address=query)
    if not url:
        return safe
    return f'<a href="{html.escape(url, quote=True)}">{safe}</a>'


# Локализация адресов Местии для курьеров: EN (ru/en) или KA.
# Паттерны применяются по очереди (длинные — раньше).
_ADDRESS_LOCALE_RULES: list[tuple[re.Pattern[str], dict[str, str]]] = [
    (
        re.compile(r"пл(?:ощад[ьи])?\.?\s*сети|площадь\s+сети|seti\s+square|seti\s+sq\.?", re.I),
        {"en": "Seti Square", "ka": "სეტის მოედანი"},
    ),
    (
        re.compile(
            r"(\d+)[\-\s]*й?\s*переулок\s+сети|seti\s+(\d+)(?:st|nd|rd|th)?\s*(?:lane|alley|side\s*street)",
            re.I,
        ),
        {"en": "Seti {n} Lane", "ka": "სეტის მე-{n} შესახვევი"},
    ),
    (
        re.compile(r"переулок\s+сети|seti\s+(?:lane|alley)", re.I),
        {"en": "Seti Lane", "ka": "სეტის შესახვევი"},
    ),
    (
        re.compile(
            r"ул\.?\s*тамар[аы]\s*мепе|тамар[аы]\s*мепе|tamar(?:a)?\s*mepe|queen\s+tamar(?:a)?(?:\s+st(?:reet)?)?",
            re.I,
        ),
        {"en": "Tamar Mepe St", "ka": "თამარ მეფის ქუჩა"},
    ),
    (
        re.compile(
            r"ул\.?\s*витт?орио\s*селл[аы]|витт?орио\s*селл[аы]|vittorio\s*sella",
            re.I,
        ),
        {"en": "Vittorio Sella St", "ka": "ვიტორიო სელას ქუჩა"},
    ),
    (
        re.compile(r"ул\.?\s*бетлеми|бетлеми|betlemi|bethlehem", re.I),
        {"en": "Betlemi St", "ka": "ბეთლემის ქუჩა"},
    ),
    (
        re.compile(
            r"ул\.?\s*(?:зураб[аы]?\s*)?церетели|(?:зураб[аы]?\s*)?церетели|zurab\s*tsereteli|tsereteli",
            re.I,
        ),
        {"en": "Zurab Tsereteli St", "ka": "ზურაბ წერეთლის ქუჩა"},
    ),
    (
        re.compile(
            r"ул\.?\s*(?:борис[аы]?\s*)?кахиани|(?:борис[аы]?\s*)?кахиани|kakhiani",
            re.I,
        ),
        {"en": "Boris Kakhiani St", "ka": "ბორის კახიანის ქუჩა"},
    ),
    (
        re.compile(
            r"ул\.?\s*(?:шота\s*)?руставели|(?:шота\s*)?руставели|rustaveli",
            re.I,
        ),
        {"en": "Rustaveli St", "ka": "რუსთაველის ქუჩა"},
    ),
    (
        re.compile(
            r"ул\.?\s*(?:михеил[аы]?\s*|михаил[аы]?\s*)?хергиани|хергиани|khergiani",
            re.I,
        ),
        {"en": "Mikheil Khergiani St", "ka": "მიხეილ ხერგიანის ქუჩა"},
    ),
    (
        re.compile(r"ул\.?\s*ланчвали|ланчвали|lanchvali", re.I),
        {"en": "Lanchvali St", "ka": "ლანჩვალის ქუჩა"},
    ),
    (
        re.compile(r"ул\.?\s*лехтаги|лехтаги|lekhtagi", re.I),
        {"en": "Lekhtagi St", "ka": "ლეხთაგის ქუჩა"},
    ),
    (
        re.compile(r"ул\.?\s*лагами|лагами|laghami", re.I),
        {"en": "Laghami St", "ka": "ლაღამის ქუჩა"},
    ),
    (
        re.compile(
            r"ул\.?\s*(?:мераб[аы]?\s*)?костава|костава|kostava",
            re.I,
        ),
        {"en": "Kostava St", "ka": "კოსტავას ქუჩა"},
    ),
    (
        re.compile(
            r"ул\.?\s*(?:илья?\s*)?чавчавадзе|чавчавадзе|chavchavadze",
            re.I,
        ),
        {"en": "Chavchavadze St", "ka": "ჭავჭავაძის ქუჩა"},
    ),
    (
        re.compile(r"ул\.?\s*арах?ишвили|арах?ишвили|arakhishvili", re.I),
        {"en": "Arakhishvili St", "ka": "არახიშვილის ქუჩა"},
    ),
    (
        re.compile(r"ул\.?\s*лестничн\w*|лестничн\w*\s*ул\.?|ladder\s*st", re.I),
        {"en": "Ladder St", "ka": "კიბეების ქუჩა"},
    ),
    (
        re.compile(r"\bместия\b|\bmestia\b|\bმესტია\b", re.I),
        {"en": "Mestia", "ka": "მესტია"},
    ),
    (
        re.compile(r"\bэт\.?\s*(\d+)|\bэтаж\s*(\d+)|\bfloor\s*(\d+)|\bfl\.?\s*(\d+)|სართ\.?\s*(\d+)", re.I),
        {"en": "fl. {n}", "ka": "სართ. {n}"},
    ),
    (
        re.compile(r"\bкв\.?\s*(\d+)|\bквартира\s*(\d+)|\bapt\.?\s*(\d+)|\bapartment\s*(\d+)|ბინა\s*(\d+)", re.I),
        {"en": "apt {n}", "ka": "ბინა {n}"},
    ),
    (
        re.compile(r"\bподъезд\s*(\d+)|\bentrance\s*(\d+)|სადარბაზო\s*(\d+)", re.I),
        {"en": "entrance {n}", "ka": "სადარბაზო {n}"},
    ),
    (
        re.compile(r"\bд\.?\s*(\d+)\b|\bдом\s*(\d+)|\bhouse\s*(\d+)", re.I),
        {"en": "{n}", "ka": "{n}"},
    ),
    (
        re.compile(r"\bпер\.?\s*", re.I),
        {"en": "Lane ", "ka": "შესახვევი "},
    ),
    (
        re.compile(r"\bпереулок\b", re.I),
        {"en": "Lane", "ka": "შესახვევი"},
    ),
    (
        re.compile(r"\bпр(?:оспект)?\.?\s+|\bпр-т\.?\s*", re.I),
        {"en": "Ave ", "ka": "გამზირი "},
    ),
    (
        re.compile(r"\bул\.?\s*", re.I),
        {"en": "", "ka": ""},
    ),
    (
        re.compile(r"\bулица\b", re.I),
        {"en": "St", "ka": "ქუჩა"},
    ),
]

# Общие RU→EN/KA токены для остатков адреса после именованных правил.
_ADDRESS_TOKEN_MAP: list[tuple[re.Pattern[str], dict[str, str]]] = [
    (re.compile(r"\bнабережн\w*\b", re.I), {"en": "embankment", "ka": "სანაპირო"}),
    (re.compile(r"\bшоссе\b", re.I), {"en": "highway", "ka": "გზატკეცილი"}),
    (re.compile(r"\bплощад[ьи]\b", re.I), {"en": "square", "ka": "მოედანი"}),
    (re.compile(r"\bцентр\b", re.I), {"en": "center", "ka": "ცენტრი"}),
]

_CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
    'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
    'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
}


def _address_locale_key(lang: str) -> str:
    return "ka" if (lang or "").startswith("ka") else "en"


def localize_address_for_courier(address: str, lang: str = "ru") -> str:
    """Адрес для курьера: английский (ru/en) или грузинский (ka)."""
    text = (address or "").strip()
    if not text or text == "—":
        return text or "—"
    loc = _address_locale_key(lang)
    out = text
    for pat, forms in _ADDRESS_LOCALE_RULES:
        def _repl(m: re.Match, forms=forms, loc=loc) -> str:
            tpl = forms.get(loc) or forms["en"]
            nums = [g for g in m.groups() if g]
            if "{n}" in tpl:
                n = nums[0] if nums else ""
                return tpl.replace("{n}", n)
            return tpl

        out = pat.sub(_repl, out)
    for pat, forms in _ADDRESS_TOKEN_MAP:
        out = pat.sub(forms.get(loc) or forms["en"], out)
    # Транслитерация оставшейся кириллицы при переводе на английский
    if loc == "en" and re.search(r"[а-яА-ЯёЁ]", out):
        out = "".join(_CYRILLIC_TO_LATIN.get(c, c) for c in out)
    # подчистить двойные пробелы/запятые после замен
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s*,\s*,+", ", ", out)
    out = re.sub(r"^\s*,\s*|\s*,\s*$", "", out)
    return out.strip() or text


def _fetch_order_phone_sync(order_id: int) -> str:
    for path in ORDER_DB_PATHS:
        if not os.path.exists(path):
            continue
        try:
            conn = connect_sqlite_wal(path)
            cur = conn.cursor()
            cur.execute("SELECT phone FROM orders WHERE id = ?", (int(order_id),))
            row = cur.fetchone()
            conn.close()
            if row and row[0]:
                return str(row[0]).strip()
        except Exception as e:
            log.warning("fetch order phone failed order=%s path=%s: %s", order_id, path, e)
    return ""


def _fetch_order_map_points_sync(order_id: int) -> dict:
    """pickup/dropoff coords + addresses from order.db + catalog.db."""
    out = {
        "pickup_address": "",
        "dropoff_address": "",
        "pickup_lat": None,
        "pickup_lng": None,
        "dropoff_lat": None,
        "dropoff_lng": None,
        "restaurant_id": "",
        "restaurant_name": "",
        "restaurant_address": "",
    }
    restaurant_id = ""
    for path in ORDER_DB_PATHS:
        if not os.path.exists(path):
            continue
        try:
            conn = connect_sqlite_wal(path)
            cur = conn.cursor()
            cur.execute(
                "SELECT address, delivery_lat, delivery_lng, restaurant_id "
                "FROM orders WHERE id = ?",
                (int(order_id),),
            )
            row = cur.fetchone()
            conn.close()
            if not row:
                continue
            out["dropoff_address"] = (str(row[0] or "")).strip()
            out["dropoff_lat"] = _coerce_coord(row[1])
            out["dropoff_lng"] = _coerce_coord(row[2])
            restaurant_id = (str(row[3] or "")).strip()
            out["restaurant_id"] = restaurant_id
            break
        except Exception as e:
            log.warning("fetch order map points failed order=%s path=%s: %s", order_id, path, e)

    if restaurant_id:
        for path in CATALOG_DB_PATHS:
            if not os.path.exists(path):
                continue
            try:
                conn = connect_sqlite_wal(path)
                cur = conn.cursor()
                cur.execute(
                    "SELECT address, latitude, longitude, name FROM restaurants WHERE id = ?",
                    (restaurant_id,),
                )
                row = cur.fetchone()
                conn.close()
                if not row:
                    continue
                addr = (str(row[0] or "")).strip()
                name = (str(row[3] or "")).strip()
                out["restaurant_name"] = name
                out["restaurant_address"] = addr
                out["pickup_address"] = addr or name
                out["pickup_lat"] = _coerce_coord(row[1])
                out["pickup_lng"] = _coerce_coord(row[2])
                break
            except Exception as e:
                log.warning(
                    "fetch restaurant map points failed rest=%s path=%s: %s",
                    restaurant_id, path, e,
                )
    return out


def _fetch_order_customer_name_sync(order_id: int) -> str:
    for path in ORDER_DB_PATHS:
        if not os.path.exists(path):
            continue
        try:
            conn = connect_sqlite_wal(path)
            cur = conn.cursor()
            cur.execute(
                "SELECT customer_name FROM orders WHERE id = ?",
                (int(order_id),),
            )
            row = cur.fetchone()
            conn.close()
            if row and row[0]:
                name = str(row[0]).strip()
                if name:
                    return name
        except Exception as e:
            log.warning(
                "fetch order customer_name failed order=%s path=%s: %s",
                order_id, path, e,
            )
    return "Клиент"


async def courier_order_phone(order_id: int, phone: str = "") -> str:
    """Телефон клиента: аргумент → кэш broadcast → order.db."""
    resolved = (phone or "").strip()
    if resolved:
        return resolved
    cached = _COURIER_BROADCAST_FIELDS.get(int(order_id), {})
    resolved = (cached.get("phone") or "").strip()
    if resolved:
        return resolved
    resolved = await asyncio.to_thread(_fetch_order_phone_sync, int(order_id))
    if resolved:
        entry = dict(_COURIER_BROADCAST_FIELDS.get(int(order_id), {}))
        entry["phone"] = resolved
        _COURIER_BROADCAST_FIELDS[int(order_id)] = entry
    return resolved


async def resolve_courier_contact_phone(order_id: int, phone: str = "") -> str:
    """Телефон клиента с коротким retry — assign и accept часто гоняются."""
    resolved = await courier_order_phone(order_id, phone)
    if resolved:
        return resolved
    await asyncio.sleep(0.25)
    return await courier_order_phone(order_id, phone)


def cache_courier_order_phone(order_id: int, phone: str) -> None:
    phone = (phone or "").strip()
    if not phone:
        return
    entry = dict(_COURIER_BROADCAST_FIELDS.get(int(order_id), {}))
    entry["phone"] = phone
    _COURIER_BROADCAST_FIELDS[int(order_id)] = entry


def is_georgian_phone(phone: str) -> bool:
    raw = (phone or "").strip()
    digits = normalize_phone_digits(raw)
    if not digits:
        return False
    if raw.startswith("+995") or raw.startswith("995"):
        return True
    return digits.startswith("995") and len(digits) >= 11


def _courier_contact_row(phone: str, lang: str, order_id: int) -> list[InlineKeyboardButton] | None:
    """Кнопки связи с клиентом (Звонок / WhatsApp)."""
    digits = normalize_phone_digits(phone)
    buttons: list[InlineKeyboardButton] = []

    if digits:
        call_text = get_text(lang, "btn_call_client") or "Позвонить"
        if is_georgian_phone(phone):
            buttons.append(
                InlineKeyboardButton(
                    text=call_text,
                    callback_data=f"cr_call_{order_id}",
                    icon_custom_emoji_id=CONTACT_EMOJI_PHONE,
                )
            )
            buttons.append(
                InlineKeyboardButton(
                    text=get_text(lang, "btn_whatsapp_client"),
                    url=f"https://wa.me/{digits}",
                    icon_custom_emoji_id=CONTACT_EMOJI_WHATSAPP,
                )
            )
        else:
            buttons.append(
                InlineKeyboardButton(
                    text=get_text(lang, "btn_whatsapp_client"),
                    url=f"https://wa.me/{digits}",
                    icon_custom_emoji_id=CONTACT_EMOJI_WHATSAPP,
                )
            )
            buttons.append(
                InlineKeyboardButton(
                    text=get_text(lang, "btn_telegram_client"),
                    url=f"tg://resolve?phone={digits}",
                    icon_custom_emoji_id=CONTACT_EMOJI_TELEGRAM,
                )
            )
    return buttons if buttons else None


def _courier_status_button(action: str, order_id: int, lang: str = "ru") -> InlineKeyboardButton | None:
    if action in ("arrived_restaurant", "accepted"):
        return InlineKeyboardButton(
            text=t(lang, "btn_courier_arrived_rest"),
            callback_data=f"mesti_arrived_restaurant_{order_id}",
            style=ButtonStyle.SUCCESS,
            icon_custom_emoji_id="5382351125838077755",
        )
    if action == "picked_up":
        return InlineKeyboardButton(
            text=t(lang, "btn_courier_picked_up"),
            callback_data=f"mesti_picked_up_{order_id}",
            style=ButtonStyle.SUCCESS,
            icon_custom_emoji_id="5384312315279612142",
        )
    if action in ("completed", "arrived", "delivering"):
        return InlineKeyboardButton(
            text=t(lang, "btn_courier_delivered"),
            callback_data=f"mesti_completed_{order_id}",
            style=ButtonStyle.SUCCESS,
            icon_custom_emoji_id="5384518714227990146",
        )
    return None


def build_courier_tracking_keyboard(
    action: str,
    order_id: int,
    *,
    phone: str = "",
    lang: str = "ru",
    show_contact: bool = True,
) -> InlineKeyboardMarkup | None:
    """Зелёная кнопка статуса сверху; контакт клиента — строкой ниже; кнопка Подробнее."""
    status_btn = _courier_status_button(action, order_id, lang=lang)
    rows: list[list[InlineKeyboardButton]] = []
    if status_btn:
        rows.append([status_btn])

    if show_contact and phone.strip():
        try:
            contact_row = _courier_contact_row(phone, lang, order_id)
            if contact_row:
                rows.append(contact_row)
        except Exception as e:
            log.warning("courier contact row failed order=%s: %s", order_id, e)

    rows.append([
        InlineKeyboardButton(
            text=t(lang, "btn_open_details"),
            web_app=WebAppInfo(url=miniapp_page_url(order_id=order_id)),
            icon_custom_emoji_id="5384138412053796842",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def apply_courier_tracking_keyboard(
    message=None,
    *,
    chat_id: int | None = None,
    message_id: int | None = None,
    action: str,
    order_id: int,
    phone: str = "",
    lang: str = "ru",
    fallback_markup=None,
) -> bool:
    """Ставит tracking-клавиатуру с контактом; не снимает контакт, если телефон уже есть."""
    if message is not None:
        chat_id = message.chat.id
        message_id = message.message_id
    if chat_id is None or message_id is None:
        return False

    phone = await resolve_courier_contact_phone(order_id, phone)
    if phone:
        cache_courier_order_phone(order_id, phone)

    kb = build_courier_tracking_keyboard(
        action, order_id, phone=phone, lang=lang
    )
    for attempt in range(2):
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=kb,
            )
            return True
        except Exception as e:
            err = str(e).lower()
            if "not modified" in err or "message is not modified" in err:
                return True
            if attempt == 0:
                phone = await resolve_courier_contact_phone(order_id, phone)
                if phone:
                    cache_courier_order_phone(order_id, phone)
                kb = build_courier_tracking_keyboard(
                    action, order_id, phone=phone, lang=lang
                )
                await asyncio.sleep(0.15)
                continue
            log.warning(
                "apply_courier_tracking_keyboard failed order=%s action=%s: %s",
                order_id, action, e,
            )

    if phone.strip():
        return False

    kb_status = keyboard_for_action(action, order_id, lang=lang)
    if kb_status:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=kb_status,
            )
            return True
        except Exception as e2:
            log.warning(
                "apply_courier_tracking_keyboard status-only failed order=%s: %s",
                order_id, e2,
            )
    if fallback_markup is not None:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=fallback_markup,
            )
            return True
        except Exception:
            pass
    return False


def keyboard_for_action(action: str, order_id: int, lang: str = "ru") -> Optional[InlineKeyboardMarkup]:
    """Следующая зелёная кнопка статуса курьера (без контакта — legacy/sync)."""
    btn = _courier_status_button(action, order_id, lang=lang)
    if not btn:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


@router.callback_query(F.data == "ignore")
async def on_ignore_callback(callback: CallbackQuery):
    """Заглушка для кнопки «Обработка...» — глушим повторные клики."""
    await callback.answer()


async def get_order_complete_fields(order_id: int) -> dict:
    """Гарантированно возвращает полные данные заказа (ресторан, адреса, тарифы)."""
    fields = dict(await load_courier_broadcast_fields(int(order_id)))

    need_restaurant = not fields.get("restaurant_name") or not fields.get("pickup_address")
    need_dropoff = not (fields.get("dropoff_address") or fields.get("delivery_address"))
    need_financials = not fields.get("fee")
    need_accepted = not fields.get("accepted_at")

    if need_restaurant or need_dropoff or need_financials or need_accepted:
        def _read_dbs():
            res = {}
            for p in ORDER_DB_PATHS:
                if not os.path.exists(p):
                    continue
                try:
                    conn = connect_sqlite_wal(p)
                    conn.row_factory = sqlite3.Row
                    r = conn.execute("SELECT * FROM orders WHERE id = ?", (int(order_id),)).fetchone()
                    conn.close()
                    if r:
                        row_d = dict(r)
                        addr = row_d.get("address") or ""
                        res["dropoff_address"] = addr
                        res["delivery_address"] = addr
                        res["fee"] = float(row_d.get("delivery_fee") or 0.0)
                        res["tips"] = float(row_d.get("tips") or 0.0)
                        res["comment"] = row_d.get("comment") or ""
                        res["currency"] = "GEL"
                        res["created_at"] = row_d.get("created_at")
                        res["accepted_at"] = row_d.get("courier_taken_at") or row_d.get("courier_confirmed_at")
                        res["courier_taken_at"] = row_d.get("courier_taken_at")
                        res["dropoff_lat"] = row_d.get("delivery_lat")
                        res["dropoff_lng"] = row_d.get("delivery_lng")
                        res["restaurant_id"] = str(row_d.get("restaurant_id") or "")
                        break
                except Exception as ex:
                    log.warning("get_order_complete_fields order.db err: %s", ex)

            rest_id = res.get("restaurant_id")
            if rest_id:
                for cp in CATALOG_DB_PATHS:
                    if not os.path.exists(cp):
                        continue
                    try:
                        conn = connect_sqlite_wal(cp)
                        conn.row_factory = sqlite3.Row
                        r = conn.execute("SELECT name, address, latitude, longitude FROM restaurants WHERE id = ?", (str(rest_id),)).fetchone()
                        conn.close()
                        if r:
                            res["restaurant_name"] = r["name"] or ""
                            res["pickup_address"] = r["address"] or ""
                            res["pickup_lat"] = r["latitude"]
                            res["pickup_lng"] = r["longitude"]
                            break
                    except Exception as ex:
                        log.warning("get_order_complete_fields catalog.db err: %s", ex)

            if not res.get("distance_km") and res.get("pickup_lat") and res.get("dropoff_lat"):
                try:
                    import math
                    R = 6371.0
                    dlat = math.radians(res["dropoff_lat"] - res["pickup_lat"])
                    dlng = math.radians(res["dropoff_lng"] - res["pickup_lng"])
                    a = math.sin(dlat / 2)**2 + math.cos(math.radians(res["pickup_lat"])) * math.cos(math.radians(res["dropoff_lat"])) * math.sin(dlng / 2)**2
                    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                    res["distance_km"] = round(R * c * 1.25, 1)
                except Exception:
                    pass
            return res

        db_fields = await asyncio.to_thread(_read_dbs)
        for k, v in db_fields.items():
            if not fields.get(k) and v:
                fields[k] = v

    return fields


@router.callback_query(F.data.startswith("mesti_"))
async def on_mesti_callback(callback: CallbackQuery):
    data = callback.data
    action, order_id = decode_callback_data(data)
    telegram_id = callback.from_user.id
    lang = await user_lang(telegram_id)
    if not action or not order_id:
        await callback.answer(t(lang, "alert_unknown_action"), show_alert=True)
        return

    log.info("Mesti callback: order_id=%d, action=%s, user_tg=%d", order_id, action, telegram_id)

    # Отказ от оффера — через confirm/reason (кнопка «Отказаться»), не сразу в gateway.
    if action == "rejected":
        try:
            await callback.message.edit_reply_markup(
                reply_markup=_courier_refuse_confirm_kb(order_id, lang=lang)
            )
        except Exception as e:
            log.warning("mesti_rejected → confirm kb failed: %s", e)
        await callback.answer(
            t(lang, "alert_refuse_confirm", order_id=order_id),
            show_alert=True,
        )
        return

    # Проверка статуса заказа в базе: если уже доставлен или уже в доставке
    cur_status = get_order_current_status(int(order_id))
    if cur_status in ("delivered", "completed"):
        await callback.answer(
            t(lang, "alert_order_already_delivered", order_id=order_id),
            show_alert=True,
        )
        done_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=t(lang, "btn_open_details"),
                web_app=WebAppInfo(url=miniapp_page_url(order_id=order_id)),
                icon_custom_emoji_id="5384138412053796842",
            )
        ]])
        try:
            await callback.message.edit_reply_markup(reply_markup=done_kb)
        except Exception:
            pass
        return

    if action == "arrived_restaurant" and cur_status == "delivering":
        await callback.answer(
            t(lang, "alert_already_picked_up", order_id=order_id),
            show_alert=True,
        )
        cached = _COURIER_BROADCAST_FIELDS.get(int(order_id), {})
        phone = await resolve_courier_contact_phone(int(order_id), cached.get("phone") or "")
        delivering_kb = build_courier_tracking_keyboard("completed", order_id, phone=phone, lang=lang)
        try:
            await callback.message.edit_reply_markup(reply_markup=delivering_kb)
        except Exception:
            pass
        return

    # Лоадер, чтобы избежать дабл-кликов
    original_kb = callback.message.reply_markup
    try:
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(lang, "btn_processing"), callback_data="ignore")
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
                        await callback.answer(t(lang, "alert_order_unavailable"), show_alert=True)
                        cap = callback.message.html_text or callback.message.caption or ""
                        is_photo = bool(callback.message.photo)
                        replaced = await replace_courier_offer_with_taken(
                            chat_id=telegram_id,
                            message_id=callback.message.message_id,
                            order_id=order_id,
                            caption_html=cap,
                            is_photo=is_photo,
                            lang=lang,
                        )
                        if not replaced:
                            try:
                                await callback.message.edit_caption(
                                    caption=order_taken_caption(order_id, lang=lang),
                                    reply_markup=None,
                                    parse_mode=ParseMode.HTML,
                                )
                            except Exception:
                                try:
                                    await callback.message.edit_reply_markup(reply_markup=None)
                                except Exception:
                                    pass
                    elif "courier not found" in low:
                        await callback.answer(t(lang, "alert_not_courier"), show_alert=True)
                        try:
                            await callback.message.edit_reply_markup(reply_markup=original_kb)
                        except Exception:
                            pass
                    else:
                        await callback.answer(
                            t(lang, "alert_server_err_detail", err=(err_msg or "server")),
                            show_alert=True,
                        )
                        try:
                            await callback.message.edit_reply_markup(reply_markup=original_kb)
                        except Exception:
                            pass
                    return
                resp_data = await resp.json()
    except Exception as e:
        log.error("Gateway bot-callback error: %s", e)
        await callback.answer(t(lang, "alert_server_error"), show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=original_kb)
        except Exception:
            pass
        return

    if not resp_data.get("success"):
        await callback.answer(t(lang, "alert_op_failed"), show_alert=True)
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
        lang=lang,
    )

    # Карточку не дописываем — только меняем кнопки (как у ресторана).
    cached = _COURIER_BROADCAST_FIELDS.get(int(order_id), {})
    phone = await resolve_courier_contact_phone(
        int(order_id), cached.get("phone") or ""
    )
    if phone:
        cache_courier_order_phone(order_id, phone)
    next_kb_action = next_action
    if action == "picked_up" and next_action == "picked_up":
        next_kb_action = "picked_up"
    kb = (
        build_courier_tracking_keyboard(
            next_kb_action, order_id, phone=phone, lang=lang
        )
        if next_kb_action
        else None
    )

    # Отменяем напоминания SLA для курьера при принятии/продвижении заказа
    cancel_courier_assign_reminders(int(order_id))

    if action == "accepted":
        now_geo = datetime.now(GEORGIA_TZ).isoformat()
        _COURIER_BROADCAST_FIELDS.setdefault(int(order_id), {})["accepted_at"] = now_geo
        if db is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    db.upsert_courier_broadcast_cache(
                        int(order_id), _COURIER_BROADCAST_FIELDS[int(order_id)]
                    )
                )
            except Exception:
                pass

    next_kb_action = next_action
    if action == "accepted" and not next_kb_action:
        next_kb_action = "arrived_restaurant"
    elif action == "arrived_restaurant" and not next_kb_action:
        next_kb_action = "picked_up"
    elif action == "picked_up" and not next_kb_action:
        next_kb_action = "completed"

    if next_kb_action:
        await apply_courier_tracking_keyboard(
            callback.message,
            action=next_kb_action,
            order_id=order_id,
            phone=phone,
            lang=lang,
            fallback_markup=original_kb,
        )
    else:
        # Заказ доставлен — переводим карточку в статус завершённого и убираем кнопки действий
        done_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=t(lang, "btn_open_details"),
                web_app=WebAppInfo(url=miniapp_page_url(order_id=order_id)),
                icon_custom_emoji_id="5384138412053796842",
            )
        ]])

        cached_fields = await get_order_complete_fields(int(order_id))
        accepted_at_val = cached_fields.get("accepted_at") or cached_fields.get("courier_taken_at")
        accepted_hm = _format_georgia_time(accepted_at_val or cached_fields.get("created_at"))

        if lang == "ka":
            header_line = f'{ce("5384244502040975393", "✅")} <b>შეკვეთა #{order_id} დასრულებულია</b>'
        elif lang == "ru":
            header_line = f'{ce("5384244502040975393", "✅")} <b>ЗАКАЗ #{order_id} ЗАВЕРШЁН</b>'
        else:
            header_line = f'{ce("5384244502040975393", "✅")} <b>ORDER #{order_id} COMPLETED</b>'

        # Формируем карточку курьера с полным набором фирменных tg-emoji
        new_caption = format_broadcast_text(
            order_id=order_id,
            restaurant_name=cached_fields.get("restaurant_name") or "",
            pickup_address=cached_fields.get("pickup_address") or "",
            delivery_address=cached_fields.get("delivery_address") or cached_fields.get("dropoff_address") or "",
            fee=float(cached_fields.get("fee") or cached_fields.get("delivery_fee") or 0),
            currency=cached_fields.get("currency") or "GEL",
            created_at=cached_fields.get("created_at"),
            comment=cached_fields.get("comment") or "",
            distance_km=cached_fields.get("distance_km"),
            tips=float(cached_fields.get("tips") or 0),
            pickup_lat=cached_fields.get("pickup_lat"),
            pickup_lng=cached_fields.get("pickup_lng"),
            dropoff_lat=cached_fields.get("dropoff_lat") or cached_fields.get("delivery_lat"),
            dropoff_lng=cached_fields.get("dropoff_lng") or cached_fields.get("delivery_lng"),
            lang=lang,
            delivered=True,
            accepted_at=accepted_at_val,
        )

        try:
            await callback.message.edit_caption(
                caption=new_caption,
                reply_markup=done_kb,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e_edit:
            log.warning("edit delivered caption failed order=%s: %s", order_id, e_edit)
            try:
                await callback.message.edit_reply_markup(reply_markup=done_kb)
            except Exception:
                pass

        # Отправляем курьеру подтверждение завершения и начисления
        try:
            total_fee = float(cached_fields.get("fee") or cached_fields.get("delivery_fee") or 0)
            total_tips = float(cached_fields.get("tips") or 0)
            total_payout = total_fee + total_tips
            payout_str = _fmt_caption_lari(total_payout) if total_payout > 0 else ""
            tips_str = _fmt_caption_lari(total_tips) if total_tips > 0 else ""

            if lang == "ru":
                tips_line = f'\n{ce(CUSTOM_EMOJI["income_today"], "🎁")} Включая чаевые: <b>{tips_str}</b>' if total_tips > 0 else ""
                finish_text = (
                    f'{ce(CUSTOM_EMOJI["success"], "✅")} <b>Заказ #{order_id} успешно доставлен!</b>\n\n'
                    f'{ce(CUSTOM_EMOJI["balance"], "💰")} Начислено на баланс: <b>{payout_str}</b>{tips_line}\n\n'
                    f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>Вы на линии</b> — ожидайте новые заказы.'
                )
            elif lang == "ka":
                tips_line = f'\n{ce(CUSTOM_EMOJI["income_today"], "🎁")} მათ შორის ჩაი: <b>{tips_str}</b>' if total_tips > 0 else ""
                finish_text = (
                    f'{ce(CUSTOM_EMOJI["success"], "✅")} <b>შეკვეთა #{order_id} წარმატებით დასრულდა!</b>\n\n'
                    f'{ce(CUSTOM_EMOJI["balance"], "💰")} ბალანსზე დარიცხულია: <b>{payout_str}</b>{tips_line}\n\n'
                    f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>ხაზზე ხართ</b> — დაელოდეთ ახალ შეკვეთებს.'
                )
            else:
                tips_line = f'\n{ce(CUSTOM_EMOJI["income_today"], "🎁")} Including tips: <b>{tips_str}</b>' if total_tips > 0 else ""
                finish_text = (
                    f'{ce(CUSTOM_EMOJI["success"], "✅")} <b>Order #{order_id} successfully delivered!</b>\n\n'
                    f'{ce(CUSTOM_EMOJI["balance"], "💰")} Credited to balance: <b>{payout_str}</b>{tips_line}\n\n'
                    f'{ce(CUSTOM_EMOJI["open_restaurant"], "🟢")} <b>You are online</b> — waiting for new orders.'
                )
            await bot.send_message(
                chat_id=telegram_id,
                text=finish_text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            log.warning("finish order notification failed order=%s tg=%s: %s", order_id, telegram_id, e)

        # Уведомляем ресторан и переводим карточку ресторана в статус завершённой
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(notify_restaurant_order_delivered(int(order_id)))
        except Exception as e_rn:
            log.warning("schedule notify_restaurant_order_delivered failed order=%s: %s", order_id, e_rn)

    await callback.answer(alert_text, show_alert=True)

    if action != "rejected":
        await db.update_kind(order_id, telegram_id, "tracking")


async def notify_restaurant_order_delivered(order_id: int) -> None:
    """Обновляет карточку заказа ресторана (первая строка → ЗАКАЗ #ID ЗАВЕРШЁН) и шлёт отчёт."""
    # Загружаем данные заказа из order.db
    order_data = {}
    for p in ORDER_DB_PATHS:
        if not os.path.exists(p):
            continue
        try:
            conn = connect_sqlite_wal(p)
            conn.row_factory = sqlite3.Row
            r = conn.execute("SELECT * FROM orders WHERE id = ?", (int(order_id),)).fetchone()
            conn.close()
            if r:
                order_data = dict(r)
                break
        except Exception as ex:
            log.warning("notify_restaurant_delivered order.db err: %s", ex)

    try:
        msgs = await db.get_messages_for_order(int(order_id))
    except Exception:
        msgs = []

    rest_msgs = [m for m in msgs if (m.get("role") or "") == "restaurant"]

    # Резервный поиск карточки ресторана: order.db -> partners -> order_messages
    if not rest_msgs and order_data.get("restaurant_id"):
        try:
            rest_id = str(order_data["restaurant_id"])
            partner = await db.get_partner_by_restaurant_id(rest_id)
            if partner and partner.get("telegram_id"):
                r_tg = int(partner["telegram_id"])
                om = await db.get_order_message(int(order_id), r_tg)
                if om and om.get("message_id"):
                    rest_msgs.append({
                        "telegram_id": r_tg,
                        "message_id": int(om["message_id"]),
                        "role": "restaurant",
                    })
        except Exception as e_fb:
            log.warning("notify_restaurant_delivered fallback err: %s", e_fb)

    if not rest_msgs:
        log.info("notify_restaurant_delivered: no restaurant messages for order %s", order_id)
        return

    import json
    items = []
    raw_items = order_data.get("items")
    if raw_items:
        try:
            if isinstance(raw_items, str):
                items = json.loads(raw_items)
            elif isinstance(raw_items, list):
                items = raw_items
        except Exception:
            items = []

    total_val = float(order_data.get("total") or 0.0)
    del_fee = float(order_data.get("delivery_fee") or 0.0)
    serv_fee = float(order_data.get("service_fee") or 0.0)
    tips_val = float(order_data.get("tips") or 0.0)
    food_amount = max(0.0, total_val - del_fee - serv_fee - tips_val)
    if not food_amount and items:
        for it in items:
            try:
                food_amount += float(it.get("price") or 0) * int(it.get("quantity") or 1)
            except Exception:
                pass

    rest_income = round(food_amount * RESTAURANT_ITEMS_SHARE, 2)
    food_str = _fmt_caption_lari(food_amount)
    income_str = _fmt_caption_lari(rest_income)

    seen_tg = set()
    for m in rest_msgs:
        tg_id = int(m.get("telegram_id") or 0)
        mid = int(m.get("message_id") or 0)
        if tg_id <= 0 or tg_id in seen_tg:
            continue
        seen_tg.add(tg_id)

        user = await db.get_bot_user(tg_id) or {}
        lang = user.get("language", "ru")

        details_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=t(lang, "btn_open_details"),
                web_app=WebAppInfo(url=miniapp_page_url(order_id=order_id)),
                icon_custom_emoji_id="5384138412053796842",
            )
        ]])

        # 1. Обновление карточки заказа ресторана: меняется только первая строка на ЗАКАЗ #ID ЗАВЕРШЁН
        order_row = _get_order_row(int(order_id)) or {}
        card_data = dict(order_row)
        card_data.update(order_data)
        card_data["order_id"] = order_id
        if items:
            card_data["items"] = items
        card_caption = format_order_message(
            card_data,
            lang=lang,
            delivered=True,
        )

        try:
            await bot.edit_message_caption(
                chat_id=tg_id,
                message_id=mid,
                caption=card_caption,
                reply_markup=details_kb,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e_cap:
            log.warning("edit restaurant card caption failed order=%s tg=%s: %s", order_id, tg_id, e_cap)
            try:
                await bot.edit_message_text(
                    chat_id=tg_id,
                    message_id=mid,
                    text=card_caption,
                    reply_markup=details_kb,
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                try:
                    await bot.edit_message_reply_markup(chat_id=tg_id, message_id=mid, reply_markup=details_kb)
                except Exception:
                    pass

        # 2. Отдельное сообщение ресторану о завершении заказа
        if lang == "ka":
            finish_msg = (
                f'{ce(CUSTOM_EMOJI["success"], "✅")} <b>შეკვეთა #{order_id} წარმატებით მიწოდებულია!</b>\n\n'
                f'{ce(CUSTOM_EMOJI["balance"], "💰")} შეკვეთის თანხა: <b>{food_str}</b>\n'
                f'{ce(CUSTOM_EMOJI["income_today"], "💵")} რესტორნის დარიცხვა: <b>{income_str}</b>\n\n'
                f'თანხა ჩაირიცხა რესტორნის ბალანსზე.'
            )
        elif lang == "ru":
            finish_msg = (
                f'{ce(CUSTOM_EMOJI["success"], "✅")} <b>Заказ #{order_id} успешно доставлен!</b>\n\n'
                f'{ce(CUSTOM_EMOJI["balance"], "💰")} Сумма заказа: <b>{food_str}</b>\n'
                f'{ce(CUSTOM_EMOJI["income_today"], "💵")} Начислено заведению: <b>{income_str}</b>\n\n'
                f'Средства зачислены на баланс ресторана.'
            )
        else:
            finish_msg = (
                f'{ce(CUSTOM_EMOJI["success"], "✅")} <b>Order #{order_id} successfully delivered!</b>\n\n'
                f'{ce(CUSTOM_EMOJI["balance"], "💰")} Order amount: <b>{food_str}</b>\n'
                f'{ce(CUSTOM_EMOJI["income_today"], "💵")} Credited to restaurant: <b>{income_str}</b>\n\n'
                f'Funds have been credited to the restaurant balance.'
            )

        try:
            await bot.send_message(
                chat_id=tg_id,
                text=finish_msg,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e_send:
            log.warning("send restaurant delivered message failed order=%s tg=%s: %s", order_id, tg_id, e_send)


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
    """Отправляет PATCH /api/v1/orders/{id}/status на бэкенд (bot token auth)."""
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
    """Проверяет X-Bot-Security-Token в заголовке запроса с защитой от timing attack."""
    if not SECURITY_TOKEN:
        log.error("SECURITY_TOKEN not configured!")
        return False
    header_token = request.headers.get(SECURITY_HEADER, "")
    return hmac.compare_digest(header_token, SECURITY_TOKEN)


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

    cutlery_count = data.get("cutlery_count")
    if cutlery_count is None:
        cutlery_count = data.get("cutlery")
    try:
        cutlery_count = int(cutlery_count or 0)
    except (TypeError, ValueError):
        cutlery_count = 0
    if cutlery_count <= 0:
        # Fallback: в вебхуке gateway раньше не слал cutlery_count — читаем order.db
        cutlery_count = _lookup_order_cutlery(order_id)

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
        "cutlery_count": cutlery_count,
    }

    # Формируем и отправляем сообщение
    rest_user = await db.get_bot_user(int(telegram_id)) or {}
    rest_lang = rest_user.get("language", "ru") or "ru"
    text = format_order_message(formatted_data, lang=rest_lang)
    keyboard = make_order_keyboard(order_id, lang=rest_lang)

    if is_sunset_restaurant(restaurant_id or data.get("restaurant_id", "")):
        _b, _f = calculate_sunset_packaging(items)
        items_total += _f

    try:
        # Баннер 2a: items / ₾ total / таймер 5:00 (окно ресторана ~5 мин)
        msg = await send_banner_photo(
            chat_id=telegram_id,
            kind="order_new_restaurant",
            fields={
                "order_number": f"#{order_id}",
                "items": _format_banner_items(items, lang=rest_lang),
                "order_total": _fmt_banner_lari(items_total),
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
        schedule_restaurant_accept_reminder(int(order_id), int(telegram_id), msg.message_id, delay_sec=150)
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
    """Сумма на PNG-баннере: «98.00 GEL» / «1,240 GEL» (число, потом код).

    Символ ₾ в Archivo даёт «закорючку» — на баннерах только латиница GEL.
    В Telegram-caption по-прежнему ₾.
    """
    try:
        n = float(value)
    except (TypeError, ValueError):
        return f"{value} GEL"
    if n == int(n):
        iv = int(n)
        if abs(iv) >= 1000:
            return f"{iv:,} GEL"
        return f"{iv} GEL"
    return f"{n:.2f} GEL"


def _courier_payout_total(delivery_fee=0, tips=0) -> float:
    """Полный доход курьера по заказу: delivery_fee + tips."""
    try:
        fee = float(delivery_fee or 0)
    except (TypeError, ValueError):
        fee = 0.0
    try:
        tip = float(tips or 0)
    except (TypeError, ValueError):
        tip = 0.0
    return fee + tip


def _fmt_caption_lari(value) -> str:
    """Сумма в HTML-подписи Telegram: «98.00 ₾» (число, потом неразрывный пробел и символ)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return f"{value}\u00A0₾"
    if n == int(n):
        iv = int(n)
        if abs(iv) >= 1000:
            return f"{iv:,}\u00A0₾"
        return f"{iv}\u00A0₾"
    return f"{n:.2f}\u00A0₾"


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
    pickup_lat: float | None = None,
    pickup_lng: float | None = None,
    dropoff_lat: float | None = None,
    dropoff_lng: float | None = None,
    lang: str = "ru",
    delivered: bool = False,
    accepted_at=None,
    customer_name: str = "",
) -> str:
    """HTML-карточка заказа для курьера (фирменные tg-emoji + компактный маршрут без лишних отступов)."""
    created_hm, deadline_hm = _format_order_time(
        created_at, minutes=COURIER_ACCEPT_MIN
    )
    comment = _clean_order_comment(comment)
    currency = currency or "GEL"

    target_addr_lang = "ka" if (lang or "").startswith("ka") else "en"
    pickup_addr_en = localize_address_for_courier(pickup_address, target_addr_lang)
    pickup_addr_ka = localize_address_for_courier(pickup_address, "ka")

    dropoff_addr_en = localize_address_for_courier(delivery_address, target_addr_lang)
    dropoff_addr_ka = localize_address_for_courier(delivery_address, "ka")

    rest_name = (restaurant_name or "").strip()
    if not rest_name or not pickup_address:
        try:
            pts = _fetch_order_map_points_sync(int(order_id))
            if not rest_name:
                rest_name = (pts.get("restaurant_name") or "").strip()
            if not pickup_address:
                pickup_address = (pts.get("pickup_address") or "").strip()
        except Exception:
            pass

    accept_label = t(lang, "label_accept_by")
    if lang == "ru":
        addr_label = "Адрес:"
        client_label = "Клиент"
    elif lang == "ka":
        addr_label = "მისამართი:"
        client_label = "კლიენტი"
    else:
        addr_label = "Address:"
        client_label = "Client"

    # Ссылки на карты с точным поиском на грузинском / Mestia
    pickup_link = html_maps_link(
        pickup_addr_en or rest_name or "—",
        lat=pickup_lat,
        lng=pickup_lng,
        search_query=pickup_addr_ka or pickup_address or rest_name,
    )
    dropoff_link = html_maps_link(
        dropoff_addr_en or "—",
        lat=dropoff_lat,
        lng=dropoff_lng,
        search_query=dropoff_addr_ka or delivery_address,
    )

    # 1. Заведение: первым название с фирменным эмодзи (пакет/ресторан), ниже адрес без эмодзи
    restaurant_block = (
        f'{ce("5384312315279612142", "🛍️")} <b>{html.escape(rest_name or "Ресторан")}</b>\n'
        f'{addr_label} {pickup_link}'
    )

    # 2. Доставка: первым Клиент с фирменным эмодзи (метка), ниже адрес доставки без эмодзи
    cust_name = (customer_name or "").strip()
    if not cust_name and order_id:
        try:
            cust_name = _fetch_order_customer_name_sync(int(order_id))
        except Exception:
            pass

    if cust_name:
        client_title = f"{client_label} {cust_name}"
    else:
        client_title = client_label

    client_block = (
        f'{ce("5382351125838077755", "📍")} <b>{html.escape(client_title)}</b>\n'
        f'{addr_label} {dropoff_link}'
    )

    try:
        tips_val = float(tips or 0)
    except (TypeError, ValueError):
        tips_val = 0.0

    # Доход и чаевые в одной строке
    total_payout = float(fee or 0) + tips_val
    income_label = t(lang, "courier_income")
    if tips_val > 0:
        if lang == "ru":
            income_val = f"{_fmt_caption_lari(total_payout)} ({_fmt_caption_lari(tips_val)} чаевые)"
        elif lang == "ka":
            income_val = f"{_fmt_caption_lari(total_payout)} ({_fmt_caption_lari(tips_val)} ჩაი)"
        else:
            income_val = f"{_fmt_caption_lari(total_payout)} ({_fmt_caption_lari(tips_val)} tips)"
    else:
        income_val = _fmt_caption_lari(total_payout)

    # Дистанция маршрута с пометками дальности по Местии
    dist_val = None
    if distance_km not in (None, "", "—"):
        try:
            dist_val = float(str(distance_km).replace("km", "").replace("км", "").strip())
        except (TypeError, ValueError):
            pass
    if dist_val is None and pickup_lat and pickup_lng and dropoff_lat and dropoff_lng:
        try:
            import math
            R = 6371.0
            dlat = math.radians(dropoff_lat - pickup_lat)
            dlng = math.radians(dropoff_lng - pickup_lng)
            a = math.sin(dlat / 2)**2 + math.cos(math.radians(pickup_lat)) * math.cos(math.radians(dropoff_lat)) * math.sin(dlng / 2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            dist_val = round(R * c * 1.25, 1)
        except Exception:
            pass

    distance_line = ""
    if dist_val and dist_val > 0:
        if lang == "ru":
            zone_note = " (центр)" if dist_val <= 0.8 else (" (дальний район)" if dist_val >= 2.5 else "")
            distance_line = f'{ce("5382248944271140910", "🗺️")} <b>Расстояние:</b> ~{dist_val:.1f} км{zone_note}'
        elif lang == "ka":
            zone_note = " (ცენტრი)" if dist_val <= 0.8 else ""
            distance_line = f'{ce("5382248944271140910", "🗺️")} <b>მანძილი:</b> ~{dist_val:.1f} კმ{zone_note}'
        else:
            zone_note = " (center)" if dist_val <= 0.8 else ""
            distance_line = f'{ce("5382248944271140910", "🗺️")} <b>Distance:</b> ~{dist_val:.1f} km{zone_note}'

    # Заголовок
    if delivered:
        if lang == "ka":
            header_line = f'{ce("5384244502040975393", "✅")} <b>შეკვეთა #{order_id} დასრულებულია</b>'
        elif lang == "ru":
            header_line = f'{ce("5384244502040975393", "✅")} <b>ЗАКАЗ #{order_id} ЗАВЕРШЁН</b>'
        else:
            header_line = f'{ce("5384244502040975393", "✅")} <b>ORDER #{order_id} COMPLETED</b>'
        parts = [header_line, ""]
    else:
        parts = [
            f'{ce("5384244502040975393", "🟢")} <b>{t(lang, "courier_new_order_title", order_id=order_id)}</b>',
            "",
        ]

    # Маршрут: ресторан с адресом, отступ, затем клиент с адресом и расстоянием
    client_section = client_block
    if distance_line:
        client_section = f"{client_block}\n{distance_line}"

    parts.append(restaurant_block)
    parts.append("")
    parts.append(client_section)
    parts.append("")

    # Доход и комментарий
    parts.append(f'{ce("5384520939021048827", "💰")} <b>{income_label}</b> {income_val}')
    comment_text = html.escape(comment) if comment else t(lang, "comment_none")
    parts.append(
        f'{ce("5382097310450753507", "💬")} <b>{t(lang, "courier_comment")}</b> {comment_text}'
    )
    return "\n".join(parts)


def courier_phase_key(
    *,
    next_action: str = "",
    last_action: str = "",
    current_status: str = "",
) -> str:
    """Phase line keys aligned with Mini App stepper copy."""
    na = (next_action or "").strip().lower()
    la = (last_action or "").strip().lower()
    st = (current_status or "").strip().lower()
    if la == "completed" or st in ("delivered", "completed") or (not na and st == "delivered"):
        return "courier_phase_done"
    if na in ("completed", "arrived") or st == "delivering" or la == "picked_up":
        return "courier_phase_delivering"
    if na == "picked_up":
        if st == "ready":
            return "courier_phase_pickup"
        if st == "preparing":
            return "courier_phase_wait"
        if la == "arrived_restaurant":
            return "courier_phase_at_rest"
        return "courier_phase_at_rest"
    if na == "arrived_restaurant" or la in ("accepted", ""):
        return "courier_phase_to_rest"
    return "courier_phase_to_rest"


def format_courier_active_caption(
    *,
    order_id: int | str,
    fields: dict | None,
    lang: str,
    phase_key: str,
) -> str | None:
    """Rebuild broadcast caption + phase line from cached order fields."""
    cached = dict(fields or {})
    if not cached:
        return None
    try:
        fee = float(cached.get("fee") or cached.get("delivery_fee") or 0)
    except (TypeError, ValueError):
        fee = 0.0
    try:
        tips = float(cached.get("tips") or 0)
    except (TypeError, ValueError):
        tips = 0.0
    base = format_broadcast_text(
        order_id=order_id,
        restaurant_name=cached.get("restaurant_name") or "",
        pickup_address=cached.get("pickup_address") or "",
        delivery_address=cached.get("delivery_address") or cached.get("dropoff_address") or "",
        fee=fee,
        currency=cached.get("currency") or "GEL",
        created_at=cached.get("created_at"),
        comment=cached.get("comment") or "",
        distance_km=cached.get("distance_km"),
        tips=tips,
        pickup_lat=cached.get("pickup_lat"),
        pickup_lng=cached.get("pickup_lng"),
        dropoff_lat=cached.get("dropoff_lat"),
        dropoff_lng=cached.get("dropoff_lng"),
        lang=lang,
        customer_name=cached.get("customer_name") or "",
    )
    return base


async def edit_courier_tracking_caption(
    *,
    chat_id: int,
    message_id: int,
    order_id: int,
    lang: str,
    next_action: str = "",
    last_action: str = "",
    current_status: str = "",
) -> bool:
    """NO-OP: карточку заказа курьера не меняем (как у ресторана), меняются только статус-кнопки."""
    return True


def make_broadcast_keyboard(order_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура оффера курьеру: Принять / Отказаться + Подробности (WebApp)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_accept"),
                    callback_data=f"mesti_accepted_{order_id}",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_courier_refuse"),
                    callback_data=f"cr_ask_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_open_details"),
                    web_app=WebAppInfo(url=miniapp_page_url(order_id=order_id)),
                    icon_custom_emoji_id="5384138412053796842",
                )
            ],
        ]
    )


def _courier_refuse_confirm_kb(order_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_refuse_yes"),
                    callback_data=f"cr_yes_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_refuse_no"),
                    callback_data=f"cr_no_{order_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ]
        ]
    )


def _courier_refuse_reason_kb(order_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=courier_refuse_reason_label(code, lang),
            callback_data=f"cr_rs_{order_id}_{code}",
        )]
        for code in COURIER_REFUSE_REASON_DEFS
    ]
    rows.append(
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=f"cr_ask_{order_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _courier_snooze_kb(order_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Только +5 мин — максимум, как просил продукт."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_snooze_in", n=COURIER_SNOOZE_MIN),
                    callback_data=f"cr_dl_{order_id}_{COURIER_SNOOZE_MIN}",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_refuse_now"),
                    callback_data=f"cr_fx_{order_id}",
                    style=ButtonStyle.DANGER,
                ),
            ],
            [
                InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=f"cr_yes_{order_id}"),
            ],
        ]
    )


def format_courier_refuse_caption(order_id: int | str, reason: str = "", lang: str = "ru") -> str:
    icon = ce("5384244502040975393", "❌")
    parts = [f"{icon} <b>{t(lang, 'caption_courier_refused', order_id=order_id)}</b>"]
    reason = (reason or "").strip()
    if reason:
        parts.append("")
        parts.append(t(lang, "caption_reason_line", reason=html.escape(reason)))
    return "\n".join(parts)


def format_courier_snooze_caption(order_id: int | str, until_hm: str, lang: str = "ru") -> str:
    icon = ce("5382351125838077755", "⏳")
    return (
        f"{icon} <b>{t(lang, 'caption_courier_snooze', order_id=order_id, n=COURIER_SNOOZE_MIN, t=html.escape(until_hm))}</b>"
    )


def cancel_courier_snooze(
    order_id: int, telegram_id: int, *, persist: bool = True
) -> None:
    task = _COURIER_SNOOZE_TASKS.pop((int(order_id), int(telegram_id)), None)
    if task and not task.done():
        task.cancel()
    if persist and db is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(db.delete_courier_snooze(int(order_id), int(telegram_id)))
        except RuntimeError:
            pass


async def remember_courier_broadcast_fields(order_id: int, fields: dict) -> None:
    payload = dict(fields or {})
    if len(_COURIER_BROADCAST_FIELDS) > 300:
        for k in list(_COURIER_BROADCAST_FIELDS.keys())[:-200]:
            _COURIER_BROADCAST_FIELDS.pop(k, None)
    _COURIER_BROADCAST_FIELDS[int(order_id)] = payload
    if db is not None:
        await db.upsert_courier_broadcast_cache(int(order_id), payload)


async def load_courier_broadcast_fields(order_id: int) -> dict:
    cached = _COURIER_BROADCAST_FIELDS.get(int(order_id))
    if cached:
        return cached
    if db is None:
        return {}
    data = await db.get_courier_broadcast_cache(int(order_id))
    if data:
        _COURIER_BROADCAST_FIELDS[int(order_id)] = data
    return data or {}


async def forget_courier_broadcast_fields(order_id: int) -> None:
    _COURIER_BROADCAST_FIELDS.pop(int(order_id), None)
    if db is not None:
        await db.delete_courier_broadcast_cache(int(order_id))


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
    lang: str = "ru",
) -> bool:
    """Финальный отказ: gateway rejected + UI без кнопок."""
    cancel_courier_snooze(order_id, chat_id)
    _COURIER_REFUSE_META.pop(int(order_id), None)
    ok = await _gateway_courier_rejected(order_id, chat_id)
    if not ok:
        return False
    caption = format_courier_refuse_caption(order_id, reason_label, lang=lang)
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
    if db is not None:
        await db.delete_courier_snooze(int(order_id), int(telegram_id))

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
                lang=(await db.get_bot_user(telegram_id) or {}).get("language", "ru"),
            )
            return

    if not await _courier_offer_still_open(order_id, telegram_id):
        await replace_courier_offer_with_taken(
            chat_id=telegram_id,
            message_id=message_id,
            order_id=order_id,
            is_photo=True,
            lang=(await db.get_bot_user(telegram_id) or {}).get("language", "ru"),
        )
        return

    cached = await load_courier_broadcast_fields(int(order_id))
    user = await db.get_bot_user(int(telegram_id)) or {}
    lang = user.get("language", "ru")
    distance_km = cached.get("distance_km")
    route_distance = "—"
    try:
        if distance_km not in (None, ""):
            route_distance = f"{float(distance_km):.1f} km"
    except (TypeError, ValueError):
        if distance_km:
            route_distance = str(distance_km).replace("км", "km").replace("КМ", "km")
    try:
        tips_val = float(cached.get("tips") or 0)
    except (TypeError, ValueError):
        tips_val = 0.0
    banner_lang = "ka" if lang.startswith("ka") else "en"
    fields = {
        "pickup_address": localize_address_for_courier(
            cached.get("pickup_address") or "—", banner_lang
        ),
        "dropoff_address": localize_address_for_courier(
            cached.get("dropoff_address") or "—", banner_lang
        ),
        "route_distance": "",
        "courier_payout": cached.get("missed_payout")
        or (_fmt_banner_lari(cached.get("fee") or 0) if cached else _fmt_banner_lari(0)),
    }
    # Восстанавливаем баннер 5a + исходный caption-шаблон по возможности.
    fee = cached.get("fee") or 0
    try:
        fee = float(fee)
    except (TypeError, ValueError):
        fee = 0.0
    caption = format_broadcast_text(
        order_id=order_id,
        restaurant_name=cached.get("restaurant_name") or "",
        pickup_address=cached.get("pickup_address") or "",
        delivery_address=cached.get("dropoff_address") or "",
        fee=fee,
        currency=cached.get("currency") or "GEL",
        created_at=cached.get("created_at"),
        comment=cached.get("comment") or "",
        distance_km=distance_km,
        tips=tips_val,
        lang=lang,
    )
    try:
        await edit_banner_media(
            chat_id=telegram_id,
            message_id=message_id,
            kind="order_new_courier",
            fields=fields,
            caption=caption,
            keyboard=make_broadcast_keyboard(order_id, lang=lang),
        )
        await db.update_kind(order_id, telegram_id, "broadcast")
        await bot.send_message(
            chat_id=telegram_id,
            text=(
                f'{ce("5384244502040975393", "🔔")} '
                f"{t(lang, 'snooze_reminder', order_id=order_id)}"
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
    cancel_courier_snooze(order_id, telegram_id, persist=False)
    wait = int(delay_sec if delay_sec is not None else COURIER_SNOOZE_MIN * 60)
    wake_at = time.time() + wait
    if db is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                db.upsert_courier_snooze(
                    int(order_id), int(telegram_id), int(message_id), wake_at
                )
            )
        except RuntimeError:
            pass

    async def _job() -> None:
        try:
            await asyncio.sleep(wait)
            await _restore_courier_offer_after_snooze(order_id, telegram_id, message_id)
        except asyncio.CancelledError:
            return
        except Exception as e:
            log.warning("courier snooze job failed: %s", e)

    _COURIER_SNOOZE_TASKS[(int(order_id), int(telegram_id))] = asyncio.create_task(_job())


async def restore_pending_courier_snoozes() -> None:
    """После рестарта: поднять snooze-таймеры из SQLite."""
    if db is None:
        return
    rows = await db.list_pending_courier_snoozes()
    if not rows:
        return
    now = time.time()
    restored = 0
    for row in rows:
        order_id = int(row["order_id"])
        telegram_id = int(row["telegram_id"])
        message_id = int(row["message_id"])
        wake_at = float(row.get("wake_at") or 0)
        delay = max(0, int(wake_at - now))
        # Не зовём cancel_courier_snooze — иначе сразу удалит строку из БД.
        old = _COURIER_SNOOZE_TASKS.pop((order_id, telegram_id), None)
        if old and not old.done():
            old.cancel()

        async def _job(
            oid=order_id, tid=telegram_id, mid=message_id, wait=delay
        ) -> None:
            try:
                if wait > 0:
                    await asyncio.sleep(wait)
                await _restore_courier_offer_after_snooze(oid, tid, mid)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.warning("restored snooze job failed: %s", e)

        _COURIER_SNOOZE_TASKS[(order_id, telegram_id)] = asyncio.create_task(_job())
        restored += 1
    log.info("Restored %d courier snooze job(s) from DB", restored)


_REST_ACCEPT_REMIND_TASKS: dict[int, asyncio.Task] = {}
_REST_ACCEPT_REMIND_MSGS: dict[int, list[tuple[int, int]]] = {}


def cancel_restaurant_accept_reminders(order_id: int) -> None:
    """Отменяет таймер напоминания ресторану и удаляет отправленные сообщения-напоминания из чата."""
    oid = int(order_id)
    task = _REST_ACCEPT_REMIND_TASKS.pop(oid, None)
    if task and not task.done():
        task.cancel()
    pings = _REST_ACCEPT_REMIND_MSGS.pop(oid, [])
    if pings:
        async def _del_pings():
            for tid, mid in pings:
                try:
                    await bot.delete_message(chat_id=tid, message_id=mid)
                except Exception:
                    pass
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_del_pings())
        except RuntimeError:
            pass


async def _fire_restaurant_accept_reminder(order_id: int, telegram_id: int, reply_to_mid: int) -> None:
    oid = int(order_id)
    _REST_ACCEPT_REMIND_TASKS.pop(oid, None)
    st = get_order_current_status(oid)
    if st and st != "pending":
        return

    user = await db.get_bot_user(int(telegram_id)) or {}
    lang = user.get("language", "ru")
    if lang == "ka":
        text = (
            f'{ce("5384244502040975393", "🟢")} <b>ყურადღება:</b> შეკვეთა <b>#{oid}</b> ელოდება დადასტურებას. მისაღებად გამოიყენეთ ზემოთ მოცემული ბარათი.'
        )
    elif lang == "ru":
        text = (
            f'{ce("5384244502040975393", "🟢")} <b>Внимание:</b> Заказ <b>#{oid}</b> ожидает подтверждения. Для принятия в работу используйте карточку заказа выше.'
        )
    else:
        text = (
            f'{ce("5384244502040975393", "🟢")} <b>Attention:</b> Order <b>#{oid}</b> is awaiting confirmation. Use the order card above to accept it.'
        )

    try:
        sent_msg = await bot.send_message(
            chat_id=int(telegram_id),
            text=text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=int(reply_to_mid) if reply_to_mid else None,
        )
        if sent_msg and hasattr(sent_msg, "message_id"):
            _REST_ACCEPT_REMIND_MSGS.setdefault(oid, []).append((int(telegram_id), sent_msg.message_id))
            log.info("restaurant accept reminder sent order=%s tg=%s msg_id=%s", oid, telegram_id, sent_msg.message_id)
    except Exception as e:
        log.warning("restaurant reminder send failed order=%s tg=%s: %s", oid, telegram_id, e)


def schedule_restaurant_accept_reminder(
    order_id: int, telegram_id: int, message_id: int, delay_sec: int = 150
) -> None:
    """Планирует напоминание ресторану, если через delay_sec заказ всё ещё pending."""
    cancel_restaurant_accept_reminders(order_id)
    oid = int(order_id)
    tid = int(telegram_id)
    mid = int(message_id)

    async def _job():
        try:
            await asyncio.sleep(delay_sec)
            await _fire_restaurant_accept_reminder(oid, tid, mid)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.warning("restaurant accept reminder job failed order=%s: %s", oid, e)

    _REST_ACCEPT_REMIND_TASKS[oid] = asyncio.create_task(_job())
    log.info("restaurant accept reminder scheduled order=%s in %ds", oid, delay_sec)


_COURIER_ASSIGN_REMIND_MSGS: dict[int, list[tuple[int, int]]] = {}


def cancel_courier_assign_reminders(order_id: int, *, persist: bool = True) -> None:
    oid = int(order_id)
    for stage in (COURIER_ASSIGN_REMIND_MIN, COURIER_ASSIGN_REMIND_MIN + COURIER_ASSIGN_REMIND2_MIN):
        task = _COURIER_ASSIGN_REMIND_TASKS.pop((oid, stage), None)
        if task and not task.done():
            task.cancel()
    # Удаляем отправленные напоминания из чата курьера, чтобы они не висели под карточкой
    pings = _COURIER_ASSIGN_REMIND_MSGS.pop(oid, [])
    if pings:
        for tid, mid in pings:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(bot.delete_message(chat_id=tid, message_id=mid))
            except Exception:
                pass
    # Также удаляем сохранённые в БД напоминания и SLA-алерты
    try:
        loop = asyncio.get_running_loop()
        async def _del_saved_reminders():
            if db is not None:
                try:
                    for rm in await db.get_messages_for_order_kind(oid, "assign_reminder"):
                        try:
                            await bot.delete_message(chat_id=rm["telegram_id"], message_id=rm["message_id"])
                        except Exception:
                            pass
                    for sm in await db.get_messages_for_order_kind(oid, "sla_alert"):
                        try:
                            await bot.delete_message(chat_id=sm["telegram_id"], message_id=sm["message_id"])
                        except Exception:
                            pass
                    for mid_sla in await db.get_sla_alerts(oid):
                        try:
                            await bot.delete_message(chat_id=ADMIN_TG_ID, message_id=mid_sla)
                        except Exception:
                            pass
                except Exception:
                    pass
        loop.create_task(_del_saved_reminders())
    except Exception:
        pass

    if persist and db is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(db.delete_assign_reminders(oid))
        except RuntimeError:
            pass


async def _order_still_needs_courier(order_id: int) -> bool:
    """True, пока никто не стал winner/tracking по этому офферу."""
    try:
        msgs = await db.get_messages_for_order(int(order_id))
    except Exception:
        return False
    if not msgs:
        return False
    for m in msgs:
        if (m.get("role") or "") != "courier":
            continue
        kind = m.get("kind") or ""
        if kind in ("tracking", "winner"):
            return False
    # Есть хоть какая-то courier-карточка по заказу (broadcast/snooze/refused/taken)
    return any((m.get("role") or "") == "courier" for m in msgs)


async def _ping_online_couriers_unassigned(order_id: int, *, urgent: bool = False) -> int:
    """Reply-пинг online-курьерам с открытой карточкой. Возвращает число отправок."""
    try:
        msgs = await db.get_messages_for_order(int(order_id))
    except Exception:
        msgs = []
    online = set(await db.get_online_courier_ids())
    key = "courier_assign_reminder_urgent" if urgent else "courier_assign_reminder"
    sent = 0
    seen: set[int] = set()
    for m in msgs:
        if (m.get("role") or "") != "courier":
            continue
        if (m.get("kind") or "") not in ("broadcast", "snooze"):
            continue
        tid = int(m.get("telegram_id") or 0)
        mid = int(m.get("message_id") or 0)
        if tid <= 0 or tid in seen or tid not in online:
            continue
        seen.add(tid)
        user = await db.get_bot_user(tid) or {}
        lang = user.get("language", "ru")
        text = t(lang, key, order_id=order_id)
        try:
            sent_msg = await bot.send_message(
                chat_id=tid,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=mid or None,
            )
            if sent_msg and hasattr(sent_msg, "message_id"):
                _COURIER_ASSIGN_REMIND_MSGS.setdefault(int(order_id), []).append((tid, sent_msg.message_id))
                await db.save_message(int(order_id), tid, sent_msg.message_id, "courier", "assign_reminder")
            sent += 1
        except Exception as e:
            log.warning(
                "assign-remind ping failed order=%s tg=%s: %s", order_id, tid, e
            )
            try:
                sent_msg = await bot.send_message(chat_id=tid, text=text, parse_mode=ParseMode.HTML)
                if sent_msg and hasattr(sent_msg, "message_id"):
                    _COURIER_ASSIGN_REMIND_MSGS.setdefault(int(order_id), []).append((tid, sent_msg.message_id))
                    await db.save_message(int(order_id), tid, sent_msg.message_id, "courier", "assign_reminder")
                sent += 1
            except Exception as e2:
                log.warning(
                    "assign-remind ping fallback failed order=%s tg=%s: %s",
                    order_id, tid, e2,
                )
    return sent


async def _notify_admin_unassigned(order_id: int, *, stage: int) -> None:
    alert_type = f"assign{stage}"
    if await db.sla_alert_sent(int(order_id), alert_type):
        return
    cached = await load_courier_broadcast_fields(int(order_id))
    restaurant = html.escape(
        (cached.get("restaurant_name") or "").strip() or "—"
    )
    urgent = stage >= (COURIER_ASSIGN_REMIND_MIN + COURIER_ASSIGN_REMIND2_MIN)
    key = "admin_assign_alert_urgent" if urgent else "admin_assign_alert"
    text = t("ru", key, order_id=order_id, restaurant=restaurant, n=stage)
    try:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"Открыть #{order_id}",
                        icon_custom_emoji_id="5384138412053796842",
                        callback_data=f"admin_order_{order_id}",
                    )
                ]
            ]
        )
        sent_msg = await bot.send_message(
            ADMIN_TG_ID, text, parse_mode=ParseMode.HTML, reply_markup=kb
        )
        mid = sent_msg.message_id if sent_msg and hasattr(sent_msg, "message_id") else 0
        await db.mark_sla_alert(int(order_id), alert_type, message_id=mid)
        if mid > 0:
            await db.save_message(int(order_id), ADMIN_TG_ID, mid, "admin", "sla_alert")
        if stage == COURIER_ASSIGN_REMIND_MIN:
            await db.mark_sla_alert(int(order_id), "assign", message_id=mid)
    except Exception as e:
        log.warning("assign-remind admin notify failed order=%s: %s", order_id, e)


async def _fire_courier_assign_reminder(order_id: int, stage: int) -> None:
    key = (int(order_id), int(stage))
    _COURIER_ASSIGN_REMIND_TASKS.pop(key, None)
    if db is not None:
        await db.delete_assign_reminders(int(order_id), int(stage))

    if not await _order_still_needs_courier(int(order_id)):
        cancel_courier_assign_reminders(int(order_id))
        log.info("assign-remind skip order=%s stage=%s (already taken)", order_id, stage)
        return

    urgent = int(stage) >= (COURIER_ASSIGN_REMIND_MIN + COURIER_ASSIGN_REMIND2_MIN)
    pinged = await _ping_online_couriers_unassigned(int(order_id), urgent=urgent)
    await _notify_admin_unassigned(int(order_id), stage=int(stage))
    log.info(
        "assign-remind fired order=%s stage=%s pinged=%s urgent=%s",
        order_id, stage, pinged, urgent,
    )


def schedule_courier_assign_reminders(order_id: int) -> None:
    """После broadcast: T+5 мин и T+7 мин (ещё +2)."""
    cancel_courier_assign_reminders(order_id, persist=False)
    oid = int(order_id)
    now = time.time()
    stages = (
        COURIER_ASSIGN_REMIND_MIN,
        COURIER_ASSIGN_REMIND_MIN + COURIER_ASSIGN_REMIND2_MIN,
    )
    for stage in stages:
        wake_at = now + stage * 60
        wait = max(0, int(wake_at - now))
        if db is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(db.upsert_assign_reminder(oid, stage, wake_at))
            except RuntimeError:
                pass

        async def _job(oid_=oid, stage_=stage, wait_=wait) -> None:
            try:
                if wait_ > 0:
                    await asyncio.sleep(wait_)
                await _fire_courier_assign_reminder(oid_, stage_)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.warning("assign-remind job failed order=%s stage=%s: %s", oid_, stage_, e)

        _COURIER_ASSIGN_REMIND_TASKS[(oid, stage)] = asyncio.create_task(_job())
    log.info(
        "assign-remind scheduled order=%s at +%s/+%s min",
        oid, stages[0], stages[1],
    )


async def restore_pending_courier_assign_reminders() -> None:
    if db is None:
        return
    rows = await db.list_assign_reminders()
    if not rows:
        return
    now = time.time()
    restored = 0
    for row in rows:
        order_id = int(row["order_id"])
        stage = int(row["stage"])
        wake_at = float(row.get("wake_at") or 0)
        delay = max(0, int(wake_at - now))
        old = _COURIER_ASSIGN_REMIND_TASKS.pop((order_id, stage), None)
        if old and not old.done():
            old.cancel()

        async def _job(oid=order_id, st=stage, wait=delay) -> None:
            try:
                if wait > 0:
                    await asyncio.sleep(wait)
                await _fire_courier_assign_reminder(oid, st)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.warning("restored assign-remind failed: %s", e)

        _COURIER_ASSIGN_REMIND_TASKS[(order_id, stage)] = asyncio.create_task(_job())
        restored += 1
    log.info("Restored %d courier assign-remind job(s) from DB", restored)


async def broadcast_order_to_couriers(
    order_id: int,
    courier_ids: list[int],
    *,
    restaurant_name: str = "",
    pickup_address: str = "",
    delivery_address: str = "",
    phone: str = "",
    delivery_fee: float = 0.0,
    tips: float = 0.0,
    currency: str = "GEL",
    created_at=None,
    comment: str = "",
    distance_km=1.5,
    schedule_reminders: bool = True,
    skip_blocked: bool = True,
    customer_name: str = "",
) -> dict:
    """Шлёт оффер курьерам. Возвращает {sent, failed, skipped_blocked}."""
    oid = int(order_id)
    distance_label = "1.5 km"
    try:
        distance_label = f"{float(distance_km):.1f} km"
    except (TypeError, ValueError):
        if distance_km:
            distance_label = str(distance_km).replace("км", "km").replace("КМ", "km")

    if not customer_name:
        try:
            customer_name = await asyncio.to_thread(_fetch_order_customer_name_sync, oid)
        except Exception:
            pass

    fee_num = float(delivery_fee or 0)
    tips_num = float(tips or 0)
    if fee_num <= 0:
        db_fee, db_tips = await asyncio.to_thread(_fetch_order_fees_sync, oid)
        if db_fee > 0:
            fee_num = db_fee
        if db_tips > 0 and tips_num <= 0:
            tips_num = db_tips
    if fee_num <= 0:
        fee_num = 8.0  # Базовый тариф доставки в Местии

    delivery_fee = fee_num
    tips = tips_num
    payout_total = _courier_payout_total(delivery_fee, tips)
    await remember_courier_broadcast_fields(
        oid,
        {
            "pickup_address": pickup_address or restaurant_name or "",
            "dropoff_address": delivery_address or "",
            "fee": float(delivery_fee or 0),
            "tips": float(tips or 0),
            "missed_payout": _fmt_banner_lari(payout_total),
            "phone": phone or "",
            "restaurant_name": restaurant_name or "",
            "customer_name": customer_name or "",
            "created_at": created_at,
            "comment": comment or "",
            "distance_km": distance_km,
            "currency": currency or "GEL",
            "route_distance": distance_label,
        },
    )

    sent = 0
    failed: list[int] = []
    skipped_blocked: list[int] = []
    for cid in courier_ids:
        if int(cid) <= 0:
            continue
        if skip_blocked and await db.is_courier_blocked(int(cid)):
            skipped_blocked.append(int(cid))
            continue
        try:
            user = await db.get_bot_user(int(cid)) or {}
            lang = user.get("language", "ru")
            text = format_broadcast_text(
                order_id=oid,
                restaurant_name=restaurant_name,
                pickup_address=pickup_address,
                delivery_address=delivery_address,
                fee=float(delivery_fee or 0),
                currency=currency or "GEL",
                created_at=created_at,
                comment=comment or "",
                distance_km=distance_km,
                tips=float(tips or 0),
                lang=lang,
                customer_name=customer_name or "",
            )
            banner_lang = "ka" if lang.startswith("ka") else "en"
            banner_pickup = localize_address_for_courier(
                pickup_address or restaurant_name, banner_lang
            )
            banner_dropoff = localize_address_for_courier(delivery_address, banner_lang)
            msg = await send_banner_photo(
                chat_id=int(cid),
                kind="order_new_courier",
                fields={
                    "pickup_address": banner_pickup or restaurant_name,
                    "dropoff_address": banner_dropoff,
                    "route_distance": "",
                    "courier_payout": _fmt_banner_lari(payout_total),
                },
                keyboard=make_broadcast_keyboard(oid, lang=lang),
                caption=text,
            )
            await db.save_message(oid, int(cid), msg.message_id, "courier", "broadcast")
            sent += 1
        except Exception as e:
            log.warning("broadcast: send to courier %d failed: %s", cid, e)
            failed.append(int(cid))

    if schedule_reminders and sent > 0:
        schedule_courier_assign_reminders(oid)
    return {"sent": sent, "failed": failed, "skipped_blocked": skipped_blocked}


async def admin_rebroadcast_order(order_id: int) -> tuple[bool, str]:
    """Реброадкаст online-курьерам из кэша / order.db."""
    oid = int(order_id)
    cached = await load_courier_broadcast_fields(oid)
    if not cached.get("pickup_address") and not cached.get("dropoff_address"):
        points = await asyncio.to_thread(_fetch_order_map_points_sync, oid)
        phone = await asyncio.to_thread(_fetch_order_phone_sync, oid)
        cached = {
            **cached,
            "pickup_address": points.get("pickup_address") or "",
            "dropoff_address": points.get("dropoff_address") or "",
            "phone": phone or cached.get("phone") or "",
            "fee": cached.get("fee") or 0,
            "tips": cached.get("tips") or 0,
            "currency": cached.get("currency") or "GEL",
            "distance_km": cached.get("distance_km") or 1.5,
            "restaurant_name": cached.get("restaurant_name") or "",
        }
    online = await db.get_online_courier_ids()
    if not online:
        return False, "Нет курьеров на линии"
    result = await broadcast_order_to_couriers(
        oid,
        online,
        restaurant_name=cached.get("restaurant_name") or "",
        pickup_address=cached.get("pickup_address") or "",
        delivery_address=cached.get("dropoff_address") or "",
        phone=cached.get("phone") or "",
        delivery_fee=float(cached.get("fee") or 0),
        tips=float(cached.get("tips") or 0),
        currency=cached.get("currency") or "GEL",
        created_at=cached.get("created_at"),
        comment=cached.get("comment") or "",
        distance_km=cached.get("distance_km") or 1.5,
        schedule_reminders=True,
    )
    return True, f"Отправлено: {result['sent']}, ошибок: {len(result['failed'])}"


async def admin_assign_courier(order_id: int, courier_tg: int) -> tuple[bool, str]:
    """Принудительно назначает курьера на заказ через gateway и базу."""
    oid = int(order_id)
    tg = int(courier_tg)

    # 1. Resolve courier backend_id
    courier_backend_id = 0
    for path in BACKEND_DB_PATHS:
        if os.path.exists(path):
            try:
                conn = connect_sqlite_wal(path)
                row = conn.execute(
                    "SELECT id FROM admin_users WHERE telegram_id = ? AND role = 'courier'",
                    (str(tg),),
                ).fetchone()
                conn.close()
                if row:
                    courier_backend_id = int(row[0])
                    break
            except Exception:
                pass

    # 2. Update order.db
    for path in ORDER_DB_PATHS:
        if os.path.exists(path):
            try:
                conn = connect_sqlite_wal(path)
                conn.execute(
                    "UPDATE orders SET courier_id = ?, courier_taken_at = datetime('now'), "
                    "status = CASE WHEN lower(status) = 'pending' THEN 'accepted' ELSE status END WHERE id = ?",
                    (courier_backend_id, oid),
                )
                conn.commit()
                conn.close()
                break
            except Exception as e:
                log.warning("admin_assign_courier update db failed: %s", e)

    # 3. Notify gateway / backend
    url = f"{BACKEND_URL}/api/v1/bot-callback"
    headers = {
        "Content-Type": "application/json",
        SECURITY_HEADER: SECURITY_TOKEN,
    }
    payload = {
        "order_id": oid,
        "telegram_id": tg,
        "action": "accepted",
    }
    try:
        async with _aiohttp.ClientSession() as session:
            await session.post(url, json=payload, headers=headers, timeout=_aiohttp.ClientTimeout(total=5))
    except Exception as e:
        log.warning("admin_assign_courier gateway notify failed: %s", e)

    # 4. Send tracking card to courier
    cached = await load_courier_broadcast_fields(oid)
    phone = await resolve_courier_contact_phone(oid, cached.get("phone") or "")
    user = await db.get_bot_user(tg) or {}
    lang = user.get("language", "ru")

    try:
        all_msgs = await db.get_messages_for_order(oid)
        courier_msg = next((m for m in all_msgs if m["telegram_id"] == tg), None)
        if courier_msg:
            await apply_courier_tracking_keyboard(
                chat_id=tg,
                message_id=int(courier_msg["message_id"]),
                action="arrived_restaurant",
                order_id=oid,
                phone=phone,
                lang=lang,
            )
        else:
            text = (
                f'{ce("5384138412053796842", "📦")} <b>Вам назначен заказ #{oid}!</b>\n\n'
                f'{ce("5384312315279612142", "🍽")} <b>Ресторан:</b> {html.escape(cached.get("restaurant_name") or "—")}\n'
                f'{ce("5382248944271140910", "📍")} <b>Куда:</b> {html.escape(cached.get("dropoff_address") or "—")}\n'
                f'{ce("5384520939021048827", "💰")} <b>Оплата:</b> {_fmt_caption_lari(cached.get("fee") or 8.0)}'
            )
            kb = build_courier_tracking_keyboard(
                action="arrived_restaurant",
                order_id=oid,
                phone=phone,
                lang=lang,
            )
            sent_msg = await bot.send_message(tg, text, reply_markup=kb, parse_mode=ParseMode.HTML)
            await db.save_order_message(oid, tg, sent_msg.message_id)
            await db.save_message(oid, tg, sent_msg.message_id, "courier", "winner")
    except Exception as e:
        log.warning("admin_assign_courier notify courier failed: %s", e)

    cancel_courier_assign_reminders(oid)
    return True, f"Курьер успешно назначен на заказ #{oid}!"


async def cleanup_order_everywhere(order_id: int, *, delete_from_db: bool = True) -> tuple[bool, str]:
    oid = int(order_id)
    deleted_msgs = 0

    # 1. Снимаем таймеры напоминаний в памяти
    cancel_courier_assign_reminders(oid)
    _REST_ACCEPT_REMIND_TASKS.pop(oid, None)

    # 2. Удаляем все сообщения по заказу из bot_messages (рассылка курьерам, напоминания, победитель, алерты)
    try:
        b_msgs = await db.get_messages_for_order(oid)
        for m in b_msgs:
            tid = int(m.get("telegram_id") or 0)
            mid = int(m.get("message_id") or 0)
            if tid > 0 and mid > 0:
                try:
                    await bot.delete_message(chat_id=tid, message_id=mid)
                    deleted_msgs += 1
                except Exception:
                    pass
    except Exception as e:
        log.warning("cleanup_order bot_messages error: %s", e)

    # 3. Удаляем сообщения ресторану из order_messages
    try:
        async with db._db.execute("SELECT telegram_id, message_id FROM order_messages WHERE order_id = ?", (oid,)) as cur:
            o_rows = await cur.fetchall()
            for r in o_rows:
                tid = int(r["telegram_id"] or 0)
                mid = int(r["message_id"] or 0)
                if tid > 0 and mid > 0:
                    try:
                        await bot.delete_message(chat_id=tid, message_id=mid)
                        deleted_msgs += 1
                    except Exception:
                        pass
    except Exception as e:
        log.warning("cleanup_order order_messages error: %s", e)

    # 4. Удаляем админские SLA-алерты
    try:
        for mid in await db.get_sla_alerts(oid):
            if mid > 0:
                try:
                    await bot.delete_message(chat_id=ADMIN_TG_ID, message_id=mid)
                    deleted_msgs += 1
                except Exception:
                    pass
    except Exception as e:
        log.warning("cleanup_order sla_alerts error: %s", e)

    # 5. Очищаем таблицы бота
    try:
        await db._db.execute("DELETE FROM courier_assign_reminders WHERE order_id = ?", (oid,))
        await db._db.execute("DELETE FROM courier_broadcast_cache WHERE order_id = ?", (oid,))
        await db._db.execute("DELETE FROM courier_snooze_jobs WHERE order_id = ?", (oid,))
        await db._db.execute("DELETE FROM bot_messages WHERE order_id = ?", (oid,))
        await db._db.execute("DELETE FROM order_messages WHERE order_id = ?", (oid,))
        await db._db.execute("DELETE FROM admin_sla_alerts WHERE order_id = ?", (oid,))
        await db._db.commit()
    except Exception as e:
        log.warning("cleanup_order bot DB error: %s", e)

    await forget_courier_broadcast_fields(oid)

    # 6. Удаляем или отменяем заказ в order.db
    if delete_from_db:
        for p in ORDER_DB_PATHS:
            if os.path.exists(p):
                try:
                    conn = sqlite3.connect(p)
                    conn.execute("DELETE FROM order_items WHERE order_id = ?", (oid,))
                    conn.execute("DELETE FROM order_status_history WHERE order_id = ?", (oid,))
                    conn.execute("DELETE FROM orders WHERE id = ?", (oid,))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    log.warning("cleanup_order delete order.db error: %s", e)
        return True, f"Заказ #{oid} полностью удалён. Сообщений удалено: {deleted_msgs}"
    else:
        await update_order_status_backend(oid, "cancelled")
        return True, f"Заказ #{oid} отменён. Сообщений удалено: {deleted_msgs}"


async def admin_delete_order(order_id: int) -> tuple[bool, str]:
    return await cleanup_order_everywhere(int(order_id), delete_from_db=True)


async def admin_cancel_order(order_id: int) -> tuple[bool, str]:
    return await cleanup_order_everywhere(int(order_id), delete_from_db=False)


async def admin_bulk_delete_orders(mode: str) -> tuple[bool, str]:
    path = None
    for p in ORDER_DB_PATHS:
        if os.path.exists(p):
            path = p
            break
    if not path:
        return False, "База order.db не найдена"

    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        if mode == "test":
            cur.execute(
                "SELECT id FROM orders WHERE restaurant_id IN ('test_rest_01', 'demo') OR address LIKE '%тест%' OR comment LIKE '%тест%'"
            )
        elif mode == "1h":
            cur.execute(
                "SELECT id FROM orders WHERE created_at >= datetime('now', '-1 hour')"
            )
        elif mode == "cancelled":
            cur.execute(
                "SELECT id FROM orders WHERE status IN ('cancelled', 'canceled')"
            )
        else:
            conn.close()
            return False, f"Неизвестный режим: {mode}"

        rows = cur.fetchall()
        oids = [int(r[0]) for r in rows]
        conn.close()
    except Exception as e:
        return False, f"Ошибка выборки: {e}"

    if not oids:
        return True, "Нет подходящих заказов для удаления"

    deleted_count = 0
    for oid in oids:
        ok, msg = await cleanup_order_everywhere(oid, delete_from_db=True)
        if ok:
            deleted_count += 1

    return True, f"Успешно удалено заказов: {deleted_count}. Все связанные сообщения стёрты."


async def admin_ping_order_couriers(order_id: int) -> tuple[bool, str]:
    n = await _ping_online_couriers_unassigned(int(order_id), urgent=True)
    return True, f"Пинг отправлен: {n}"


async def admin_force_courier_offline(telegram_id: int) -> tuple[bool, str]:
    tg = int(telegram_id)
    ok = await update_courier_online_backend(tg, "set_offline")
    await db.set_courier_online_status(tg, 0)
    try:
        user = await db.get_bot_user(tg) or {}
        await set_courier_reply_kb(tg, user.get("language", "ru"), False)
    except Exception:
        pass
    if ok:
        return True, "Курьер снят с линии"
    return True, "Снят локально (backend sync failed)"


async def admin_block_courier(
    telegram_id: int, hours: int, *, admin_id: int = 0, reason: str = ""
) -> tuple[bool, str]:
    tg = int(telegram_id)
    until_ts = time.time() + max(1, int(hours)) * 3600
    ok = await db.set_courier_block(
        tg, until_ts=until_ts, reason=reason or f"{hours}h", created_by=admin_id
    )
    await admin_force_courier_offline(tg)
    until_hm = datetime.fromtimestamp(until_ts).strftime("%d.%m, %H:%M")
    await notify_courier_access_restricted(tg, until_ts)
    if ok:
        return True, f"Блок до {until_hm}"
    return False, "Не удалось сохранить блок"


async def admin_unblock_courier(telegram_id: int) -> tuple[bool, str]:
    ok = await db.clear_courier_block(int(telegram_id))
    if ok:
        await notify_courier_access_restored(int(telegram_id))
        return True, "Блок снят"
    return False, "Ошибка снятия блока"


async def admin_set_restaurant_open(restaurant_id: str, want_open: bool) -> tuple[bool, str]:
    rid = str(restaurant_id)
    ok_cat = await db.update_restaurant_status(rid, 1 if want_open else 0)
    await db.set_partner_ui_open(rid, 1 if want_open else 0)
    partner = await db.get_partner_by_restaurant(rid) or {}
    tg = int(partner.get("telegram_id") or 0)
    if tg > 0:
        try:
            if want_open:
                text = (
                    f'{ce(CUSTOM_EMOJI["alert_green"], "🟢")} '
                    f"Ресторан открыт администратором."
                )
            else:
                text = (
                    f'{ce(CUSTOM_EMOJI["alert_red"], "🔴")} '
                    f"Ресторан закрыт администратором."
                )
            await bot.send_message(tg, text, parse_mode=ParseMode.HTML)
        except Exception:
            pass
    if ok_cat:
        return True, ("Открыт" if want_open else "Закрыт")
    return False, "Каталог не обновлён"


async def admin_send_partner_message(telegram_id: int, text: str, msg_type: str = "general") -> tuple[bool, str]:
    body = (text or "").strip()
    if not body:
        return False, "Пустое сообщение"
    try:
        user = await db.get_bot_user(int(telegram_id)) or {}
        lang = user.get("language", "ru")
        icon_emoji = ce("5384244502040975393", "🟢")
        if msg_type == "tech":
            if lang == "ka":
                header = f"{icon_emoji} <b>ტექნიკური შეტყობინება:</b>"
            elif lang == "en":
                header = f"{icon_emoji} <b>System Maintenance Notice:</b>"
            else:
                header = f"{icon_emoji} <b>Техническое уведомление:</b>"
        else:
            if lang == "ka":
                header = f"{icon_emoji} <b>შეტყობინება პლატფორმისგან:</b>"
            elif lang == "en":
                header = f"{icon_emoji} <b>Platform Message:</b>"
            else:
                header = f"{icon_emoji} <b>Сообщение от платформы:</b>"

        msg_text = f"{header}\n\n{body}"
        try:
            await bot.send_message(
                int(telegram_id),
                msg_text,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await bot.send_message(
                int(telegram_id),
                f"{header}\n\n{html.escape(body)}",
                parse_mode=ParseMode.HTML,
            )
        return True, "Отправлено"
    except Exception as e:
        return False, f"Не доставлено: {e}"


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
    rest_id = str(req.get("restaurant_id") or "").lower()
    r_name_lower = str(restaurant_name or "").lower()
    if "test_rest" in rest_id or "тест" in r_name_lower or "test" in r_name_lower:
        log.info("broadcast: suppressed test order #%s (%s / %s) to couriers", order_id, rest_id, restaurant_name)
        return web.json_response({"ok": True, "skipped": True, "reason": "test_order_suppressed"})
    pickup_address = req.get("pickup_address", "")
    delivery_address = req.get("delivery_address", "")
    phone = (req.get("phone") or req.get("customer_phone") or "").strip()
    if not phone:
        phone = await asyncio.to_thread(_fetch_order_phone_sync, int(order_id))

    pickup_lat = _coerce_coord(req.get("pickup_lat", req.get("restaurant_lat")))
    pickup_lng = _coerce_coord(req.get("pickup_lng", req.get("restaurant_lng")))
    dropoff_lat = _coerce_coord(req.get("delivery_lat", req.get("dropoff_lat")))
    dropoff_lng = _coerce_coord(req.get("delivery_lng", req.get("dropoff_lng")))
    if (
        pickup_lat is None
        or pickup_lng is None
        or dropoff_lat is None
        or dropoff_lng is None
        or not pickup_address
        or not delivery_address
    ):
        points = await asyncio.to_thread(_fetch_order_map_points_sync, int(order_id))
        if not pickup_address:
            pickup_address = points.get("pickup_address") or pickup_address
        if not delivery_address:
            delivery_address = points.get("dropoff_address") or delivery_address
        if pickup_lat is None:
            pickup_lat = points.get("pickup_lat")
        if pickup_lng is None:
            pickup_lng = points.get("pickup_lng")
        if dropoff_lat is None:
            dropoff_lat = points.get("dropoff_lat")
        if dropoff_lng is None:
            dropoff_lng = points.get("dropoff_lng")

    delivery_fee = req.get("delivery_fee")
    if delivery_fee is None:
        delivery_fee = req.get("courier_fee") or req.get("deliveryFee") or req.get("fee") or 0.0
    tips = req.get("tips")
    if tips is None:
        tips = req.get("tip") or 0.0
    currency = req.get("currency", "GEL")
    created_at = req.get("created_at")
    comment = req.get("comment") or req.get("courier_comment") or ""
    distance_km = req.get("distance_km", req.get("route_distance", 1.5))
    customer_name = (req.get("customer_name") or req.get("customer") or "").strip()
    if not customer_name:
        try:
            customer_name = await asyncio.to_thread(_fetch_order_customer_name_sync, int(order_id))
        except Exception:
            pass

    result = await broadcast_order_to_couriers(
        int(order_id),
        [int(c) for c in courier_ids],
        restaurant_name=restaurant_name,
        pickup_address=pickup_address,
        delivery_address=delivery_address,
        phone=phone,
        delivery_fee=float(delivery_fee or 0),
        tips=float(tips or 0),
        currency=currency,
        created_at=created_at,
        comment=comment,
        distance_km=distance_km,
        schedule_reminders=True,
        skip_blocked=True,
        customer_name=customer_name,
    )
    sent = result["sent"]
    failed = result["failed"]

    log.info(
        "broadcast done: order_id=%d, sent=%d, failed=%d, blocked=%d",
        order_id, sent, len(failed), len(result.get("skipped_blocked") or []),
    )
    return web.json_response({"ok": True, "sent": sent, "failed": failed})


def _resolve_courier_details_sync(winner_tg: int, winner_user: dict | None = None) -> tuple[str, str]:
    """
    Возвращает (имя, телефон) курьера для уведомления заведения.
    Ищет по цепочке: bot_users -> auth.db admin_users -> tg chat info.
    Ни при каких обстоятельствах не подтягивает телефон клиента!
    """
    c_name = ""
    c_phone = ""
    tg_int = int(winner_tg)

    # 1) bot_users в partners_bot.db
    pdb = DB_PATH if "DB_PATH" in globals() else "partners_bot.db"
    if os.path.exists(pdb):
        try:
            conn = connect_sqlite_wal(pdb)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT name, phone, backend_username FROM bot_users WHERE telegram_id = ?",
                (tg_int,),
            ).fetchone()
            conn.close()
            if row:
                keys = row.keys()
                if "phone" in keys and row["phone"]:
                    c_phone = str(row["phone"]).strip()
                if "name" in keys and row["name"]:
                    c_name = str(row["name"]).strip()
                if not c_name and row["backend_username"]:
                    c_name = str(row["backend_username"]).strip()
        except Exception as e:
            log.warning("resolve courier bot_users failed: %s", e)

    # 2) auth.db admin_users
    for path in BACKEND_DB_PATHS if "BACKEND_DB_PATHS" in globals() else []:
        if not os.path.exists(path):
            continue
        try:
            conn = connect_sqlite_wal(path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT full_name, phone, username FROM admin_users WHERE telegram_id = ? AND role = 'courier'",
                (str(tg_int),),
            ).fetchone()
            conn.close()
            if row:
                keys = row.keys()
                if not c_phone and "phone" in keys and row["phone"]:
                    c_phone = str(row["phone"]).strip()
                if not c_name and "full_name" in keys and row["full_name"]:
                    c_name = str(row["full_name"]).strip()
                if not c_name and row["username"]:
                    c_name = str(row["username"]).strip()
                break
        except Exception as e:
            log.warning("resolve courier auth.db failed: %s", e)

    # 3) winner_user из кэша aiogram
    if winner_user:
        if not c_name:
            c_name = (
                winner_user.get("name")
                or winner_user.get("full_name")
                or winner_user.get("first_name")
                or winner_user.get("backend_username")
                or ""
            ).strip()
        if not c_phone and winner_user.get("phone"):
            c_phone = str(winner_user["phone"]).strip()

    if not c_name:
        c_name = f"Курьер (ID: {tg_int})"

    return c_name, c_phone


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

    cached = _COURIER_BROADCAST_FIELDS.get(int(order_id), {})
    phone = await resolve_courier_contact_phone(
        int(order_id),
        (req.get("phone") or cached.get("phone") or ""),
    )
    if phone:
        cache_courier_order_phone(int(order_id), phone)
    winner_user = await db.get_bot_user(int(winner_tg)) or {}
    winner_lang = winner_user.get("language", "ru")
    winner_message_id = None
    taken_fields = order_taken_banner_fields(int(order_id))

    # 1) Победитель: только edit карточки. Не слать второе сообщение —
    # accept-callback уже ставит кнопку; assign часто приходит после смены kind.
    try:
        all_msgs = await db.get_messages_for_order(order_id)
        winner_cards = [
            m for m in all_msgs
            if m["telegram_id"] == winner_tg
            and m.get("kind") in ("broadcast", "tracking", "winner")
        ]
        if winner_cards:
            primary_card = winner_cards[0]
            mid = primary_card["message_id"]
            applied = await apply_courier_tracking_keyboard(
                chat_id=int(winner_tg),
                message_id=int(mid),
                action="arrived_restaurant",
                order_id=int(order_id),
                phone=phone,
                lang=winner_lang,
            )
            if not applied:
                log.warning(
                    "assign: winner keyboard with contact not applied order=%s tg=%s",
                    order_id, winner_tg,
                )
            winner_message_id = mid
            await db.update_kind(order_id, winner_tg, "tracking")
            cancel_courier_assign_reminders(int(order_id))

            # Убираем кнопки действий со всех вторичных/дублирующих карточек у курьера
            extra_details_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=t(winner_lang, "btn_open_details"),
                    web_app=WebAppInfo(url=miniapp_page_url(order_id=order_id)),
                    icon_custom_emoji_id="5384138412053796842",
                )
            ]])
            for extra_card in winner_cards[1:]:
                try:
                    await bot.edit_message_reply_markup(
                        chat_id=int(winner_tg),
                        message_id=int(extra_card["message_id"]),
                        reply_markup=extra_details_kb,
                    )
                except Exception:
                    pass
        else:
            log.warning(
                "assign: no card for winner tg=%s order=%s — skip duplicate text",
                winner_tg, order_id,
            )

        # 1.1) Уведомление ресторану о назначенном курьере (сообщение с именем и телефоном)
        try:
            courier_name, courier_phone = _resolve_courier_details_sync(int(winner_tg), winner_user)
            if req.get("courier_name"):
                courier_name = str(req["courier_name"]).strip()
            if not courier_name or courier_name.lower().startswith("курьер"):
                try:
                    tg_chat = await bot.get_chat(int(winner_tg))
                    courier_name = tg_chat.full_name or tg_chat.first_name or tg_chat.username or courier_name
                except Exception:
                    pass

            rest_cards = [m for m in all_msgs if (m.get("role") or "") == "restaurant"]
            rest_tg = rest_cards[0]["telegram_id"] if rest_cards else None
            if not rest_tg:
                order_row = _get_order_row(int(order_id))
                rest_id = order_row.get("restaurant_id")
                if rest_id:
                    p = await db.get_partner_by_restaurant(rest_id)
                    if p:
                        rest_tg = p.get("telegram_id")

            already_notified = any(m.get("kind") == "courier_assigned_notify" for m in all_msgs)
            if rest_tg and not already_notified:
                rest_user = await db.get_bot_user(int(rest_tg)) or {}
                rlang = rest_user.get("language", "ru")

                clean_digits = re.sub(r'\D', '', courier_phone or "")
                if clean_digits and len(clean_digits) >= 6:
                    tel_prefix = "+" if not courier_phone.startswith("+") and len(clean_digits) >= 10 else ("+" if courier_phone.startswith("+") else "")
                    phone_display = f'<a href="tel:{tel_prefix}{clean_digits}">{html.escape(courier_phone)}</a>'
                elif courier_phone and courier_phone not in ("—", "-"):
                    phone_display = html.escape(courier_phone)
                else:
                    phone_display = "неизвестен" if rlang == "ru" else ("უცნობია" if rlang == "ka" else "unknown")

                if rlang == "ka":
                    notify_text = (
                        f'{ce("5384244502040975393", "🟢")} <b>კურიერი დაინიშნა შეკვეთაზე <b>#{order_id}</b>!</b>\n\n'
                        f'{ce("5381848533060067195", "👤")} სახელი: <b>{html.escape(courier_name)}</b>\n'
                        f'📞 ტელეფონი: <b>{phone_display}</b>'
                    )
                elif rlang == "ru":
                    notify_text = (
                        f'{ce("5384244502040975393", "🟢")} <b>Курьер назначен на заказ <b>#{order_id}</b>!</b>\n\n'
                        f'{ce("5381848533060067195", "👤")} Имя: <b>{html.escape(courier_name)}</b>\n'
                        f'📞 Телефон: <b>{phone_display}</b>'
                    )
                else:
                    notify_text = (
                        f'{ce("5384244502040975393", "🟢")} <b>Courier assigned to order <b>#{order_id}</b>!</b>\n\n'
                        f'{ce("5381848533060067195", "👤")} Name: <b>{html.escape(courier_name)}</b>\n'
                        f'📞 Phone: <b>{phone_display}</b>'
                    )
                rest_mid = rest_cards[0]["message_id"] if rest_cards else None
                sent_notify = await bot.send_message(
                    chat_id=int(rest_tg),
                    text=notify_text,
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=rest_mid or None,
                )
                await db.save_message(order_id, rest_tg, sent_notify.message_id, "restaurant", "courier_assigned_notify")
                log.info("Notified restaurant %s about courier assign order=%s", rest_tg, order_id)
        except Exception as e_rest_notif:
            log.warning("Notify restaurant of courier assign failed order=%s: %s", order_id, e_rest_notif)

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
        loser_user = await db.get_bot_user(int(loser_id)) or {}
        loser_lang = loser_user.get("language", "ru")
        taken_caption = order_taken_caption(order_id, lang=loser_lang)
        for m in msgs:
            if m["telegram_id"] != loser_id:
                continue
            if m.get("kind") not in ("broadcast", "tracking", "snooze", "winner"):
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

    await forget_courier_broadcast_fields(int(order_id))
    cancel_courier_assign_reminders(int(order_id))

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
    cached = _COURIER_BROADCAST_FIELDS.get(int(order_id), {})
    phone = await resolve_courier_contact_phone(
        int(order_id),
        (req.get("phone") or cached.get("phone") or ""),
    )
    if phone:
        cache_courier_order_phone(int(order_id), phone)
    sync_user = await db.get_bot_user(int(user_tg)) or {}
    sync_lang = sync_user.get("language", "ru")
    if next_action:
        applied = await apply_courier_tracking_keyboard(
            chat_id=int(user_tg),
            message_id=int(target["message_id"]),
            action=next_action,
            order_id=int(order_id),
            phone=phone,
            lang=sync_lang,
        )
        if not applied:
            log.warning(
                "sync-state: keyboard not applied order=%s tg=%s action=%s",
                order_id, user_tg, next_action,
            )
    curr_st = str(req.get("current_status") or "").lower()
    if not next_action:
        if curr_st in ("delivered", "completed"):
            done_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=t(sync_lang, "btn_open_details"),
                    web_app=WebAppInfo(url=miniapp_page_url(order_id=order_id)),
                    icon_custom_emoji_id="5384138412053796842",
                )
            ]])
            try:
                await bot.edit_message_reply_markup(
                    chat_id=user_tg,
                    message_id=target["message_id"],
                    reply_markup=done_kb,
                )
            except Exception:
                pass
            try:
                asyncio.create_task(notify_restaurant_order_delivered(int(order_id)))
            except Exception as e_rn:
                log.warning("sync-state notify_restaurant_delivered failed: %s", e_rn)
        else:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=user_tg,
                    message_id=target["message_id"],
                    reply_markup=None,
                )
            except Exception as e:
                log.error("sync-state: clear markup failed: %s", e)
                return web.Response(status=502, text="telegram edit failed")

    await edit_courier_tracking_caption(
        chat_id=int(user_tg),
        message_id=int(target["message_id"]),
        order_id=int(order_id),
        lang=sync_lang,
        next_action=next_action or "",
        current_status=str(req.get("current_status") or ""),
    )

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
        by_label = rest_meta.get("cancelled_by") or t("ru", "cancelled_by_restaurant")
        reason = rest_meta.get("reason") or t("ru", "cancel_reason_rest")
        cancel_total = rest_meta.get("cancel_total") or cancel_total
        cancel_time = rest_meta.get("cancel_time") or cancel_time
        rest_lang = rest_meta.get("lang") or "ru"
        new_caption = rest_meta.get("caption") or format_restaurant_cancel_caption(
            order_id, reason=reason, by="restaurant", lang=rest_lang
        )
        banner_reason = reason
        banner_by = by_label
        log.info("Order #%d cancel from restaurant reason=%s", order_id, reason)
    else:
        # Чистый admin/global cancel (или ещё не завершённый delayable-флоу).
        if rest_meta and rest_meta.get("_pending_reason"):
            # вернём pending — это не финальная отмена
            _RESTAURANT_CANCEL_META[int(order_id)] = rest_meta
        new_caption = None  # per-recipient below
        banner_reason = t("ru", "cancel_reason_admin")
        banner_by = t("ru", "cancelled_by_admin")
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
        recip = await db.get_bot_user(int(chat_id)) or {}
        recip_lang = recip.get("language", "ru")
        if role == "restaurant":
            caption = new_caption or format_restaurant_cancel_caption(
                order_id, by="admin", lang=recip_lang
            )
            # Localize banner labels for this restaurant
            local_by = banner_by
            local_reason = banner_reason
            if not (rest_meta and not rest_meta.get("_pending_reason")):
                local_by = t(recip_lang, "cancelled_by_admin")
                local_reason = t(recip_lang, "cancel_reason_admin")
            try:
                try:
                    await edit_banner_media(
                        chat_id=chat_id,
                        message_id=msg_id,
                        kind="order_cancelled_restaurant",
                        fields={
                            "order_number": f"#{order_id}",
                            "cancel_total": cancel_total,
                            "cancel_time": cancel_time,
                            "cancel_reason": local_reason,
                            "cancelled_by": local_by,
                        },
                        caption=caption,
                        keyboard=None,
                    )
                    count += 1
                except Exception as ex:
                    log.error("cancel restaurant msg %d failed: %s", msg_id, ex)
                    try:
                        await bot.edit_message_reply_markup(
                            chat_id=chat_id, message_id=msg_id, reply_markup=None
                        )
                    except Exception:
                        pass
            except Exception:
                pass
        elif role == "courier":
            cancel_courier_snooze(int(order_id), int(chat_id))
            courier_caption = format_courier_cancel_caption(order_id, lang=recip_lang)
            cancel_fields = order_taken_banner_fields(int(order_id))
            try:
                ok = await edit_banner_media(
                    chat_id=chat_id,
                    message_id=msg_id,
                    kind="order_taken_courier",
                    fields=cancel_fields,
                    caption=courier_caption,
                    keyboard=None,
                )
                if ok:
                    await db.update_kind(order_id, chat_id, "cancelled")
                    count += 1
                else:
                    raise RuntimeError("edit_banner_media returned False")
            except Exception:
                try:
                    # Офферы — photo-баннеры: caption, не text.
                    await bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=msg_id,
                        caption=courier_caption,
                        reply_markup=None,
                        parse_mode=ParseMode.HTML,
                    )
                    await db.update_kind(order_id, chat_id, "cancelled")
                    count += 1
                except Exception:
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=msg_id,
                            text=courier_caption,
                            reply_markup=None,
                            parse_mode=ParseMode.HTML,
                        )
                        await db.update_kind(order_id, chat_id, "cancelled")
                        count += 1
                    except Exception:
                        try:
                            await bot.edit_message_reply_markup(
                                chat_id=chat_id, message_id=msg_id, reply_markup=None
                            )
                            await db.update_kind(order_id, chat_id, "cancelled")
                            count += 1
                        except Exception as ex:
                            log.error("cancel courier msg %d failed: %s", msg_id, ex)

    await forget_courier_broadcast_fields(int(order_id))
    cancel_courier_assign_reminders(int(order_id))
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
    Курьер нажал «Я на месте» — ресторан получает оповещение + кнопка «Готов к выдаче»,
    если заказ ещё готовится.
    """
    if not check_token(request):
        log.warning("courier-arrived: unauthorized from %s", request.remote)
        return web.Response(status=401, text="unauthorized")

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    order_id = data.get("order_id")
    restaurant_telegram_id = int(data.get("restaurant_telegram_id") or 0)
    restaurant_id = (data.get("restaurant_id") or "").strip()
    courier_name = data.get("courier_name") or ""

    if not order_id:
        return web.Response(status=400, text="order_id required")

    # Fallback: resolve restaurant TG from local partners DB (gateway may send 0).
    if restaurant_telegram_id <= 0 and restaurant_id:
        partner = await db.get_partner_by_restaurant(restaurant_id) or {}
        restaurant_telegram_id = int(partner.get("telegram_id") or 0)
    if restaurant_telegram_id <= 0:
        # Last resort: telegram_id from order_messages for this order.
        msgs = await db.get_messages_for_order(int(order_id))
        for m in msgs:
            if (m.get("role") or "") == "restaurant" and m.get("telegram_id"):
                restaurant_telegram_id = int(m["telegram_id"])
                break

    if restaurant_telegram_id <= 0:
        log.warning(
            "courier-arrived: no restaurant telegram for order=%s restaurant_id=%s",
            order_id,
            restaurant_id,
        )
        return web.json_response({"ok": False, "error": "restaurant telegram not found"}, status=404)

    order_status = get_order_current_status(int(order_id))
    # If order is already picked up, delivering, delivered, or cancelled, do not notify restaurant!
    if order_status in ("delivering", "delivered", "completed", "cancelled"):
        log.info("courier-arrived: skipped notification because order #%s status is %s", order_id, order_status)
        return web.json_response({"ok": True, "skipped": True, "status": order_status})

    rest_user = await db.get_bot_user(int(restaurant_telegram_id)) or {}
    lang = rest_user.get("language", "ru")
    name = (courier_name or "").strip() or t(lang, "default_courier_name")

    log.info(
        "Courier arrived: order_id=%s, restaurant_tg=%d, courier=%s, status=%s (restaurant message suppressed)",
        order_id,
        restaurant_telegram_id,
        name,
        order_status,
    )

    # Уведомление ресторану «Курьер на месте» отключено по запросу пользователя для исключения спама в чате
    return web.json_response({"ok": True, "skipped": True, "reason": "suppressed_by_user_request"})


async def handle_order_review(request: web.Request) -> web.Response:
    """
    POST /api/bot/v1/orders/review
    Новый отзыв о заказе от клиента:
      - Ресторану уходит ТОЛЬКО оценка кухни и отзыв о блюдах
      - Курьеру уходит ТОЛЬКО оценка доставки и отзыв о курьере
    """
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    order_id = data.get("order_id")
    if not order_id:
        return web.Response(status=400, text="order_id required")

    rest_rating = int(data.get("restaurant_rating") or 0)
    rest_tags = data.get("restaurant_tags") or []
    rest_comment = (data.get("restaurant_comment") or "").strip()

    courier_rating = int(data.get("courier_rating") or 0)
    courier_tags = data.get("courier_tags") or []
    courier_comment = (data.get("courier_comment") or "").strip()

    msgs = await db.get_messages_for_order(int(order_id))

    # 1. Отправка отзыва РЕСТОРАНУ (ТОЛЬКО кухня/блюда)
    if rest_rating > 0:
        restaurant_telegram_id = 0
        for m in msgs:
            if (m.get("role") or "") == "restaurant" and m.get("telegram_id"):
                restaurant_telegram_id = int(m["telegram_id"])
                break

        if restaurant_telegram_id <= 0:
            try:
                conn = connect_sqlite_wal(ORDER_DB_PATHS[0])
                cur = conn.cursor()
                cur.execute("SELECT restaurant_id FROM orders WHERE id = ?", (int(order_id),))
                row = cur.fetchone()
                if row and row[0]:
                    partner = await db.get_partner_by_restaurant(row[0]) or {}
                    restaurant_telegram_id = int(partner.get("telegram_id") or 0)
                conn.close()
            except Exception:
                pass

        if restaurant_telegram_id > 0:
            stars_str = "⭐" * rest_rating
            lines = [
                f'{ce("5384244502040975393", "⭐️")} <b>Новый отзыв по заказу <b>#{order_id}</b></b>\n',
                f"<b>Оценка кухни:</b> {stars_str} ({rest_rating}/5)",
            ]
            if rest_tags:
                lines.append(f"<b>Отмечено:</b> {', '.join(rest_tags)}")
            if rest_comment:
                lines.append(f"<b>Отзыв:</b> <i>«{html.escape(rest_comment)}»</i>")

            text = "\n".join(lines)
            try:
                await bot.send_message(
                    chat_id=restaurant_telegram_id,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
                log.info("Restaurant review sent to TG=%d for order #%s", restaurant_telegram_id, order_id)
            except Exception as e:
                log.warning("Failed to send restaurant review: %s", e)

    # 2. Отправка отзыва КУРЬЕРУ (ТОЛЬКО доставка/курьер)
    if courier_rating > 0:
        courier_telegram_id = 0
        for m in msgs:
            if (m.get("role") or "") == "courier" and m.get("kind") in ("winner", "tracking", "new_order"):
                courier_telegram_id = int(m["telegram_id"])
                break

        if courier_telegram_id <= 0:
            for m in msgs:
                if (m.get("role") or "") == "courier" and m.get("telegram_id"):
                    courier_telegram_id = int(m["telegram_id"])
                    break

        if courier_telegram_id > 0:
            c_stars = "⭐" * courier_rating
            lines = [
                f'{ce("5384520939021048827", "🛵")} <b>Отзыв о доставке заказа <b>#{order_id}</b></b>\n',
                f"<b>Оценка доставки:</b> {c_stars} ({courier_rating}/5)",
            ]
            if courier_tags:
                lines.append(f"<b>Отмечено клиентом:</b> {', '.join(courier_tags)}")
            if courier_comment:
                lines.append(f"<b>Комментарий:</b> <i>«{html.escape(courier_comment)}»</i>")

            tips_amount = float(data.get("tips") or 0)
            if tips_amount > 0:
                lines.append(f'\n{ce("5384518714227990146", "💸")} <b>Чаевые:</b> {tips_amount:.2f} ₾')

            text = "\n".join(lines)
            try:
                await bot.send_message(
                    chat_id=courier_telegram_id,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
                log.info("Courier review sent to TG=%d for order #%s", courier_telegram_id, order_id)
            except Exception as e:
                log.warning("Failed to send courier review: %s", e)

    return web.json_response({"ok": True, "order_id": order_id})


async def handle_order_tips(request: web.Request) -> web.Response:
    """
    POST /api/bot/v1/orders/tips
    Отправка прямого уведомления курьеру о начислении чаевых.
    """
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    order_id = data.get("order_id")
    tips_amount = float(data.get("tips") or 0)
    if not order_id or tips_amount <= 0:
        return web.Response(status=400, text="order_id and positive tips required")

    msgs = await db.get_messages_for_order(int(order_id))
    courier_telegram_id = 0
    for m in msgs:
        if (m.get("role") or "") == "courier" and m.get("kind") in ("winner", "tracking", "new_order"):
            courier_telegram_id = int(m["telegram_id"])
            break

    if courier_telegram_id <= 0:
        for m in msgs:
            if (m.get("role") or "") == "courier" and m.get("telegram_id"):
                courier_telegram_id = int(m["telegram_id"])
                break

    if courier_telegram_id > 0:
        text = (
            f'{ce("5384518714227990146", "💸")} <b>Вам начислены чаевые по заказу <b>#{order_id}</b>!</b>\n\n'
            f"<b>Сумма:</b> {tips_amount:.2f} ₾\n"
            f"Клиент поблагодарил вас за отличную доставку!"
        )
        try:
            await bot.send_message(
                chat_id=courier_telegram_id,
                text=text,
                parse_mode=ParseMode.HTML
            )
            log.info("Courier tips notification sent to TG=%d for order #%s (%s GEL)", courier_telegram_id, order_id, tips_amount)
        except Exception as e:
            log.warning("Failed to send tips notification to courier: %s", e)

    return web.json_response({"ok": True, "order_id": order_id, "tips": tips_amount})


async def sync_all_bot_users_to_backend():
    """Синхронизирует всех пользователей бота с admin_users в auth.db, удаляет фантомных курьеров."""
    def _sync():
        bot_users = []
        try:
            conn_p = connect_sqlite_wal(DB_PATH)
            cur_p = conn_p.cursor()
            cur_p.execute("SELECT telegram_id, language, role, backend_username FROM bot_users")
            bot_users = cur_p.fetchall()
            cur_p.execute("SELECT restaurant_id, telegram_id, restaurant_name FROM partners")
            partners = cur_p.fetchall()
            conn_p.close()
        except Exception as e:
            log.error("sync_all_bot_users_to_backend read bot db failed: %s", e)
            return

        partners_by_tg = {int(p[1]): {"restaurant_id": p[0], "restaurant_name": p[2]} for p in partners if p[1]}

        for path in BACKEND_DB_PATHS:
            if not os.path.exists(path):
                continue
            try:
                conn_a = connect_sqlite_wal(path)
                cur_a = conn_a.cursor()
                for u in bot_users:
                    tg_id = int(u[0])
                    tg_str = str(tg_id)
                    role = u[2]
                    username = u[3]
                    # Удаляем созданных шлюзом фантомных курьеров courier_<tg_id>
                    cur_a.execute(
                        "DELETE FROM admin_users WHERE username = ? OR (username LIKE 'courier_%' AND telegram_id = ?)",
                        (f"courier_{tg_str}", tg_str),
                    )
                    if username:
                        cur_a.execute(
                            "UPDATE admin_users SET telegram_id = ? WHERE username = ?",
                            (tg_str, username),
                        )
                        if role == "restaurant_admin" and tg_id in partners_by_tg:
                            rid = partners_by_tg[tg_id]["restaurant_id"]
                            cur_a.execute(
                                "UPDATE admin_users SET restaurant_id = ? WHERE username = ?",
                                (rid, username),
                            )
                for rid, tg_id, rname in partners:
                    if tg_id:
                        cur_a.execute(
                            "UPDATE admin_users SET telegram_id = ? WHERE restaurant_id = ?",
                            (str(tg_id), rid),
                        )
                conn_a.commit()
                conn_a.close()
                log.info("sync_all_bot_users_to_backend successfully synced users to %s", path)
            except Exception as e:
                log.error("sync_all_bot_users_to_backend failed for %s: %s", path, e)

        # Предварительная синхронизация заказов из order.db в synced_orders
        for opath in ORDER_DB_PATHS:
            if not os.path.exists(opath):
                continue
            try:
                conn_o = connect_sqlite_wal(opath)
                cur_o = conn_o.cursor()
                cur_o.execute("""
                    SELECT id, restaurant_id, courier_id, status, total, delivery_fee, customer_name, phone, address, comment, items, created_at
                    FROM orders ORDER BY id DESC LIMIT 500
                """)
                orders = cur_o.fetchall()
                conn_o.close()

                conn_p = connect_sqlite_wal(DB_PATH)
                cur_p = conn_p.cursor()
                for o in orders:
                    oid, rid, cid, st, tot, fee, cname, phone, addr, comm, items, c_at = o
                    cur_p.execute(
                        """INSERT INTO synced_orders (id, restaurant_id, courier_id, status, total, delivery_fee, customer_name, phone, address, comment, items_json, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(NULLIF(?, ''), datetime('now')), datetime('now'))
                           ON CONFLICT(id) DO UPDATE SET
                             restaurant_id = CASE WHEN excluded.restaurant_id != '' THEN excluded.restaurant_id ELSE synced_orders.restaurant_id END,
                             courier_id = CASE WHEN excluded.courier_id > 0 THEN excluded.courier_id ELSE synced_orders.courier_id END,
                             status = excluded.status,
                             total = CASE WHEN excluded.total > 0 THEN excluded.total ELSE synced_orders.total END,
                             delivery_fee = CASE WHEN excluded.delivery_fee > 0 THEN excluded.delivery_fee ELSE synced_orders.delivery_fee END,
                             customer_name = CASE WHEN excluded.customer_name != '' THEN excluded.customer_name ELSE synced_orders.customer_name END,
                             phone = CASE WHEN excluded.phone != '' THEN excluded.phone ELSE synced_orders.phone END,
                             address = CASE WHEN excluded.address != '' THEN excluded.address ELSE synced_orders.address END,
                             comment = CASE WHEN excluded.comment != '' THEN excluded.comment ELSE synced_orders.comment END,
                             items_json = CASE WHEN excluded.items_json != '[]' THEN excluded.items_json ELSE synced_orders.items_json END,
                             updated_at = datetime('now')""",
                        (oid, rid or '', cid or 0, st or 'new', tot or 0.0, fee or 0.0, cname or '', phone or '', addr or '', comm or '', items or '[]', c_at or ''),
                    )
                conn_p.commit()
                conn_p.close()
                log.info("sync_all_bot_users_to_backend pre-synced %d orders from %s", len(orders), opath)
            except Exception as e:
                log.error("sync_all_bot_users_to_backend orders pre-sync failed for %s: %s", opath, e)

    await asyncio.to_thread(_sync)


async def handle_auth_session(request: web.Request) -> web.Response:
    """Аутентификация пользователя Telegram для Mini App."""
    try:
        data = await request.json()
    except Exception:
        data = {}

    tg_id_raw = data.get("telegram_id") or request.query.get("telegram_id")
    if not tg_id_raw:
        return web.json_response({"ok": False, "error": "telegram_id required"}, status=400)

    try:
        telegram_id = int(tg_id_raw)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "invalid telegram_id"}, status=400)

    user = await db.get_bot_user(telegram_id)
    partner = await db.get_partner_by_telegram(telegram_id)

    # Если в bot_users не найден, проверим в auth.db по telegram_id
    if not user:
        for path in BACKEND_DB_PATHS:
            if not os.path.exists(path):
                continue
            try:
                conn = connect_sqlite_wal(path)
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, username, role, restaurant_id FROM admin_users WHERE telegram_id = ? AND username NOT LIKE 'courier_%'",
                    (str(telegram_id),),
                )
                row = cur.fetchone()
                conn.close()
                if row:
                    u_role = row[2]
                    u_name = row[1]
                    await db.save_bot_user(telegram_id, "ru", u_role, u_name)
                    if u_role == "restaurant_admin" and row[3]:
                        await db.register_partner(telegram_id, row[3], u_name)
                    user = await db.get_bot_user(telegram_id)
                    partner = await db.get_partner_by_telegram(telegram_id)
                    break
            except Exception as e:
                log.error("handle_auth_session auth check failed: %s", e)

    if not user:
        # Пользователь не зарегистрирован в боте
        return web.json_response({
            "ok": False,
            "registered": False,
            "error": "not_registered",
            "bot_username": "MestiDelivery_Partners_Bot",
            "message": "Пользователь не зарегистрирован в Telegram-боте партнёров",
        }, status=200)

    role = user.get("role") or ""
    username = user.get("backend_username") or ""
    language = user.get("language") or "ru"
    restaurant_id = ""
    restaurant_name = ""

    if role == "restaurant_admin":
        if partner:
            restaurant_id = partner.get("restaurant_id") or ""
            restaurant_name = partner.get("restaurant_name") or ""
        if not restaurant_id:
            # Попробуем найти в auth.db
            for path in BACKEND_DB_PATHS:
                if not os.path.exists(path):
                    continue
                try:
                    conn = connect_sqlite_wal(path)
                    cur = conn.cursor()
                    cur.execute("SELECT restaurant_id FROM admin_users WHERE username = ?", (username,))
                    r = cur.fetchone()
                    conn.close()
                    if r and r[0]:
                        restaurant_id = r[0]
                        restaurant_name = r[0]
                        await db.register_partner(telegram_id, restaurant_id, restaurant_name)
                        break
                except Exception:
                    pass

    # Находим user_id из admin_users
    admin_user_id = None
    for path in BACKEND_DB_PATHS:
        if not os.path.exists(path):
            continue
        try:
            conn = connect_sqlite_wal(path)
            cur = conn.cursor()
            # Удаляем созданных шлюзом фантомов для этого TG
            cur.execute(
                "DELETE FROM admin_users WHERE username = ? OR (username LIKE 'courier_%' AND telegram_id = ?)",
                (f"courier_{telegram_id}", str(telegram_id)),
            )
            # Привязываем telegram_id к настоящему пользователю
            if username:
                cur.execute("UPDATE admin_users SET telegram_id = ? WHERE username = ?", (str(telegram_id), username))
                cur.execute("SELECT id FROM admin_users WHERE username = ?", (username,))
                r = cur.fetchone()
                if r:
                    admin_user_id = r[0]
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("handle_auth_session clean phantom failed: %s", e)

    if not admin_user_id:
        admin_user_id = telegram_id % 10000000

    now = int(time.time())
    jwt_claims = {
        "user_id": int(admin_user_id),
        "username": username or f"user_{telegram_id}",
        "role": role,
        "restaurant_id": restaurant_id,
        "typ": "access",
        "iat": now,
        "nbf": now,
        "exp": now + 86400 * 30,  # 30 дней
    }
    token = make_hs256_jwt(jwt_claims)

    photo_url = (data.get("photo_url") or "").strip()
    if photo_url:
        COURIER_AVATAR_CACHE[telegram_id] = photo_url
        if admin_user_id:
            COURIER_AVATAR_CACHE[admin_user_id] = photo_url
        if username:
            COURIER_AVATAR_CACHE[username] = photo_url

    log.info("Auth session generated for TG=%d, role=%s, user=%s, rest=%s, photo=%s", telegram_id, role, username, restaurant_id, bool(photo_url))

    return web.json_response({
        "ok": True,
        "registered": True,
        "token": token,
        "user": {
            "id": telegram_id,
            "admin_user_id": admin_user_id,
            "username": username,
            "role": role,
            "restaurant_id": restaurant_id,
            "restaurant_name": restaurant_name,
            "language": language,
            "photo_url": photo_url or COURIER_AVATAR_CACHE.get(telegram_id) or COURIER_AVATAR_CACHE.get(admin_user_id) or "",
            "is_online": bool(user.get("is_online", 0)),
        },
    })


async def handle_gateway_webhook(request: web.Request) -> web.Response:
    """Прием входящих вебхуков от бэкенда (order.created, order.status_changed)."""
    try:
        payload = await request.json()
    except Exception as e:
        log.warning("handle_gateway_webhook invalid json: %s", e)
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    event = payload.get("event") or request.headers.get("X-Event-Type") or ""
    order_data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

    order_id = order_data.get("order_id") or order_data.get("id")
    if not order_id:
        order_id = payload.get("order_id") or payload.get("id")

    log.info("Gateway webhook received: event=%s, order_id=%s", event, order_id)

    if not order_id:
        return web.json_response({"ok": True, "note": "ignored, no order_id"})

    try:
        oid = int(order_id)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "invalid order_id"}, status=400)

    if event == "order.status_changed":
        new_status = str(order_data.get("status") or payload.get("status") or "").lower()
        if new_status:
            cid = int(order_data.get("courier_id") or payload.get("courier_id") or 0)
            await db.update_synced_order_status(oid, new_status, courier_id=cid)
            log.info("Webhook updated status: order #%d -> %s (courier: %d)", oid, new_status, cid)
    else:
        to_save = {
            "id": oid,
            "restaurant_id": str(order_data.get("restaurant_id") or payload.get("restaurant_id") or ""),
            "courier_id": int(order_data.get("courier_id") or payload.get("courier_id") or 0),
            "status": str(order_data.get("status") or payload.get("status") or "new"),
            "total": float(order_data.get("total") or payload.get("total") or 0.0),
            "delivery_fee": float(order_data.get("delivery_fee") or payload.get("delivery_fee") or 0.0),
            "customer_name": str(order_data.get("customer_name") or payload.get("customer_name") or ""),
            "phone": str(order_data.get("phone") or payload.get("phone") or ""),
            "address": str(order_data.get("address") or payload.get("address") or ""),
            "comment": str(order_data.get("comment") or payload.get("comment") or ""),
            "items": order_data.get("items") or payload.get("items") or [],
            "created_at": str(order_data.get("created_at") or payload.get("created_at") or ""),
        }
        await db.save_synced_order(to_save)
        log.info("Webhook saved order #%d (rest: %s, total: %.2f)", oid, to_save["restaurant_id"], to_save["total"])

    return web.json_response({"ok": True, "order_id": oid})


COURIER_AVATAR_CACHE: dict = {}
AVATARS_DIR = "/var/www/partners-app/avatars"

def _resolve_courier_by_id_or_tg_fast(courier_id: int = 0, courier_tg: int = 0) -> tuple[str, str, str]:
    """
    Возвращает (имя, телефон, фото) курьера для карточки заказа заведения.
    Ни при каких обстоятельствах не возвращает данные клиента!
    """
    if not courier_id and not courier_tg:
        return "", "", ""
    c_name = ""
    c_phone = ""
    c_photo = ""
    found_tg = courier_tg

    if courier_id and courier_id in COURIER_AVATAR_CACHE:
        c_photo = COURIER_AVATAR_CACHE[courier_id]
    elif found_tg and found_tg in COURIER_AVATAR_CACHE:
        c_photo = COURIER_AVATAR_CACHE[found_tg]

    # 1. auth.db (admin_users)
    for p in BACKEND_DB_PATHS if "BACKEND_DB_PATHS" in globals() else []:
        if not os.path.exists(p):
            continue
        try:
            conn = connect_sqlite_wal(p)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, full_name, phone, username, telegram_id FROM admin_users WHERE id = ? OR telegram_id = ?",
                (courier_id, str(courier_tg or courier_id))
            ).fetchone()
            conn.close()
            if row:
                c_name = (row["full_name"] or "").strip() or (row["username"] or "").strip()
                c_phone = (row["phone"] or "").strip()
                if row["telegram_id"]:
                    try:
                        found_tg = int(row["telegram_id"])
                    except Exception:
                        pass
                break
        except Exception:
            pass

    # 2. partners_bot.db (bot_users)
    pdb = DB_PATH if "DB_PATH" in globals() else "partners_bot.db"
    if os.path.exists(pdb) and (found_tg or not c_name or not c_phone):
        try:
            conn = connect_sqlite_wal(pdb)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT name, phone FROM bot_users WHERE telegram_id = ? OR telegram_id = ?",
                (found_tg or courier_id, courier_id)
            ).fetchone()
            conn.close()
            if row:
                if not c_name and row["name"]:
                    c_name = row["name"].strip()
                if not c_phone and row["phone"]:
                    c_phone = row["phone"].strip()
        except Exception:
            pass

    # Avatar file resolution from static avatars folder
    if not c_photo and found_tg:
        p_tg = os.path.join(AVATARS_DIR, f"{found_tg}.jpg")
        if os.path.exists(p_tg) and os.path.getsize(p_tg) > 100:
            c_photo = f"/avatars/{found_tg}.jpg"

    if not c_photo and courier_id:
        p_cid = os.path.join(AVATARS_DIR, f"{courier_id}.jpg")
        if os.path.exists(p_cid) and os.path.getsize(p_cid) > 100:
            c_photo = f"/avatars/{courier_id}.jpg"

    if not c_photo and c_name:
        if c_name in COURIER_AVATAR_CACHE:
            c_photo = COURIER_AVATAR_CACHE[c_name]
        else:
            p_name = os.path.join(AVATARS_DIR, f"{c_name.lower()}.jpg")
            if os.path.exists(p_name) and os.path.getsize(p_name) > 100:
                c_photo = f"/avatars/{c_name.lower()}.jpg"

    return c_name, c_phone, c_photo


async def handle_partner_orders(request: web.Request) -> web.Response:
    """Возвращает синхронизированные заказы для ресторана или курьера в Mini App."""
    restaurant_id = (request.query.get("restaurant_id") or "").strip()
    courier_id_raw = (request.query.get("courier_id") or "0").strip()
    try:
        courier_id = int(courier_id_raw)
    except ValueError:
        courier_id = 0

    limit = 100
    try:
        limit = min(int(request.query.get("limit") or 100), 200)
    except ValueError:
        pass

    orders = await db.get_synced_orders(restaurant_id=restaurant_id, courier_id=courier_id, limit=limit)

    def _read_from_order_db():
        for opath in ORDER_DB_PATHS:
            if not os.path.exists(opath):
                continue
            try:
                conn = connect_sqlite_wal(opath)
                cur = conn.cursor()
                if restaurant_id:
                    cur.execute("""
                        SELECT id, restaurant_id, courier_id, status, total, delivery_fee, customer_name, phone, address, comment, items, created_at
                        FROM orders WHERE restaurant_id = ? ORDER BY id DESC LIMIT ?
                    """, (restaurant_id, limit))
                elif courier_id > 0:
                    cur.execute("""
                        SELECT id, restaurant_id, courier_id, status, total, delivery_fee, customer_name, phone, address, comment, items, created_at
                        FROM orders WHERE courier_id = ? OR (courier_id = 0 AND status IN ('confirmed', 'accepted', 'preparing', 'ready'))
                        ORDER BY id DESC LIMIT ?
                    """, (courier_id, limit))
                else:
                    cur.execute("""
                        SELECT id, restaurant_id, courier_id, status, total, delivery_fee, customer_name, phone, address, comment, items, created_at
                        FROM orders ORDER BY id DESC LIMIT ?
                    """, (limit,))
                rows = cur.fetchall()
                conn.close()
                res = []
                for r in rows:
                    items_val = []
                    try:
                        items_val = json.loads(r[10]) if r[10] else []
                    except Exception:
                        pass
                    res.append({
                        "id": r[0],
                        "order_id": r[0],
                        "restaurant_id": r[1],
                        "courier_id": r[2] or 0,
                        "status": r[3],
                        "total": r[4],
                        "delivery_fee": r[5],
                        "customer_name": r[6],
                        "phone": r[7],
                        "address": r[8],
                        "comment": r[9],
                        "items": items_val,
                        "created_at": r[11],
                    })
                return res
            except Exception as e:
                log.error("handle_partner_orders read order.db failed: %s", e)
        return []

    order_db_items = await asyncio.to_thread(_read_from_order_db)

    combined = {}
    for o in order_db_items:
        combined[o["id"]] = o

    for so in orders:
        oid = so["id"]
        if oid in combined:
            c = combined[oid]
            if not c.get("courier_id") and so.get("courier_id"):
                c["courier_id"] = so["courier_id"]
            if not c.get("items") and so.get("items_json"):
                try:
                    c["items"] = json.loads(so["items_json"])
                except Exception:
                    pass
            continue

        items_val = []
        try:
            items_val = json.loads(so.get("items_json") or "[]")
        except Exception:
            pass
        item = {
            "id": oid,
            "order_id": oid,
            "restaurant_id": so.get("restaurant_id") or "",
            "courier_id": so.get("courier_id") or 0,
            "status": so.get("status") or "new",
            "total": so.get("total") or 0.0,
            "delivery_fee": so.get("delivery_fee") or 0.0,
            "customer_name": so.get("customer_name") or "",
            "phone": so.get("phone") or "",
            "address": so.get("address") or "",
            "comment": so.get("comment") or "",
            "items": items_val,
            "created_at": so.get("created_at") or "",
        }
        combined[oid] = item

    result_list = sorted(combined.values(), key=lambda x: x["id"], reverse=True)[:limit]

    # Resolve courier name, phone & photo, and enforce customer privacy for restaurant
    courier_cache = {}
    for item in result_list:
        cid = item.get("courier_id") or 0
        c_name = ""
        c_phone = ""
        c_photo = ""
        if cid:
            if cid not in courier_cache:
                courier_cache[cid] = _resolve_courier_by_id_or_tg_fast(courier_id=cid)
            c_name, c_phone, c_photo = courier_cache[cid]
        item["courier_name"] = c_name
        item["courier_phone"] = c_phone
        item["courier_photo"] = c_photo
        item["courier_assigned"] = bool(cid and (c_name or c_phone))

        # PRIVACY SANITIZATION:
        # Ресторан не должен видеть никаких данных клиента (ни имя, ни телефон, ни адрес)
        if restaurant_id:
            item["customer_name"] = ""
            item["phone"] = ""
            item["address"] = ""

    return web.json_response({
        "ok": True,
        "orders": result_list,
        "count": len(result_list),
    })


async def handle_update_partner_order_status(request: web.Request) -> web.Response:
    """Обновляет статус заказа от имени кухни или курьера в Mini App."""
    order_id_raw = request.match_info.get("id") or request.query.get("id") or "0"
    try:
        order_id = int(order_id_raw)
    except ValueError:
        return web.json_response({"ok": False, "error": "Invalid order id"}, status=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    new_status = (body.get("status") or "").strip().lower()
    courier_id = int(body.get("courier_id") or 0)
    courier_photo = (body.get("courier_photo") or "").strip()
    if courier_photo and courier_id:
        COURIER_AVATAR_CACHE[courier_id] = courier_photo

    if not new_status:
        return web.json_response({"ok": False, "error": "Missing status"}, status=400)

    log.info("handle_update_partner_order_status: order_id=%d status=%s courier_id=%d photo=%s", order_id, new_status, courier_id, bool(courier_photo))

    # 1. Update in synced_orders
    await db.update_synced_order_status(order_id, new_status, courier_id)

    # 2. Update directly in order.db if available
    db_status = "accepted" if new_status in ("confirmed", "accepted") else new_status
    for opath in ORDER_DB_PATHS:
        if not os.path.exists(opath):
            continue
        try:
            conn = connect_sqlite_wal(opath)
            cur = conn.cursor()
            if courier_id > 0:
                cur.execute("UPDATE orders SET status = ?, courier_id = ?, updated_at = datetime('now') WHERE id = ?", (db_status, courier_id, order_id))
            else:
                cur.execute("UPDATE orders SET status = ?, updated_at = datetime('now') WHERE id = ?", (db_status, order_id))
            conn.commit()
            conn.close()
            log.info("Updated order.db directly for order %d -> %s", order_id, db_status)
        except Exception as e:
            log.error("Failed to update order.db directly: %s", e)

    # 3. Call backend orders service PATCH if available
    try:
        timeout = aiohttp.ClientTimeout(total=3.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            patch_url = f"{BACKEND_URL}/api/orders/{order_id}/status"
            await session.patch(patch_url, json={"status": db_status})
    except Exception as e:
        log.debug("Backend PATCH status forward note: %s", e)

    return web.json_response({"ok": True, "order_id": order_id, "status": new_status, "courier_id": courier_id})


async def handle_partner_menu(request: web.Request) -> web.Response:
    """Возвращает полноценное меню ресторана из catalog.db."""
    restaurant_id = (request.query.get("restaurant_id") or "").strip()
    if not restaurant_id:
        restaurant_id = "test_rest_01"

    def _get_menu():
        for cpath in CATALOG_DB_PATHS:
            if not os.path.exists(cpath):
                continue
            try:
                conn = connect_sqlite_wal(cpath)
                cur = conn.cursor()
                
                # Проверим количество блюд; если пусто или мало, скопируем демо-набор из других заведений
                cur.execute("SELECT count(*) FROM products WHERE restaurant_id = ?", (restaurant_id,))
                cnt = cur.fetchone()[0]
                if cnt < 5 and restaurant_id in ("test_rest_01", "test_rest"):
                    cur.execute("""
                        INSERT OR IGNORE INTO products (id, restaurant_id, name, description, price, img, category, weight, calories, proteins, fats, carbs, ingredients, is_available)
                        SELECT 'demo-' || id, ?, name, description, price, img, category, weight, calories, proteins, fats, carbs, ingredients, 1
                        FROM products WHERE restaurant_id != ? AND category IN ('Салаты', 'Выпечка', 'Сванские блюда', 'Десерты', 'Горячее', 'Супы', 'Напитки', 'Бургеры', 'Пицца')
                        GROUP BY category LIMIT 14
                    """, (restaurant_id, restaurant_id))
                    conn.commit()

                cur.execute("""
                    SELECT id, name, description, price, img, category, weight, calories, proteins, fats, carbs, ingredients, is_available
                    FROM products WHERE restaurant_id = ? ORDER BY category, id
                """, (restaurant_id,))
                rows = cur.fetchall()
                conn.close()

                dishes = []
                categories = set()
                for r in rows:
                    cat = r[5] or "Общее"
                    categories.add(cat)
                    dishes.append({
                        "id": r[0],
                        "name": r[1],
                        "description": r[2],
                        "price": float(r[3] or 0),
                        "img": r[4] or "",
                        "category": cat,
                        "weight": r[6] or "",
                        "calories": r[7] or "",
                        "proteins": r[8] or "",
                        "fats": r[9] or "",
                        "carbs": r[10] or "",
                        "ingredients": r[11] or "",
                        "is_available": bool(r[12]),
                    })
                return {"categories": sorted(list(categories)), "dishes": dishes}
            except Exception as e:
                log.error("handle_partner_menu error: %s", e)
        return {"categories": [], "dishes": []}

    res = await asyncio.to_thread(_get_menu)
    return web.json_response({"ok": True, "restaurant_id": restaurant_id, **res})


async def handle_partner_dish_toggle(request: web.Request) -> web.Response:
    """Переключает статус доступности блюда (стоп-лист)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    dish_id = str(body.get("dish_id") or "").strip()
    is_available = bool(body.get("is_available"))
    if not dish_id:
        return web.json_response({"ok": False, "error": "dish_id required"}, status=400)

    def _toggle():
        for cpath in CATALOG_DB_PATHS:
            if not os.path.exists(cpath):
                continue
            try:
                conn = connect_sqlite_wal(cpath)
                cur = conn.cursor()
                cur.execute("UPDATE products SET is_available = ? WHERE id = ?", (1 if is_available else 0, dish_id))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                log.error("handle_partner_dish_toggle failed: %s", e)
        return False

    ok = await asyncio.to_thread(_toggle)
    return web.json_response({"ok": ok, "dish_id": dish_id, "is_available": is_available})


async def handle_partner_dish_update(request: web.Request) -> web.Response:
    """Обновляет цену, граммовку, описание и категорию блюда в catalog.db."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    dish_id = str(body.get("id") or body.get("dish_id") or "").strip()
    if not dish_id:
        return web.json_response({"ok": False, "error": "dish_id required"}, status=400)

    price = float(body.get("price") or 0)
    weight = str(body.get("weight") or "").strip()
    category = str(body.get("category") or "").strip()
    name = body.get("name")
    description = body.get("description")
    is_available = 1 if body.get("is_available", True) else 0

    def _update():
        for cpath in CATALOG_DB_PATHS:
            if not os.path.exists(cpath):
                continue
            try:
                conn = connect_sqlite_wal(cpath)
                cur = conn.cursor()
                name_str = json.dumps(name, ensure_ascii=False) if isinstance(name, dict) else str(name or "")
                desc_str = json.dumps(description, ensure_ascii=False) if isinstance(description, dict) else str(description or "")

                cur.execute("""
                    UPDATE products SET
                        price = CASE WHEN ? > 0 THEN ? ELSE price END,
                        weight = CASE WHEN ? != '' THEN ? ELSE weight END,
                        category = CASE WHEN ? != '' THEN ? ELSE category END,
                        name = CASE WHEN ? != '' THEN ? ELSE name END,
                        description = CASE WHEN ? != '' THEN ? ELSE description END,
                        is_available = ?
                    WHERE id = ?
                """, (price, price, weight, weight, category, category, name_str, name_str, desc_str, desc_str, is_available, dish_id))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                log.error("handle_partner_dish_update failed: %s", e)
        return False

    ok = await asyncio.to_thread(_update)
    return web.json_response({"ok": ok, "dish_id": dish_id})


async def handle_partner_dish_create(request: web.Request) -> web.Response:
    """Создает новое блюдо в catalog.db."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    restaurant_id = str(body.get("restaurant_id") or "test_rest_01").strip()
    name = body.get("name") or "Новое блюдо"
    price = float(body.get("price") or 0.0)
    category = str(body.get("category") or "Основные").strip()
    weight = str(body.get("weight") or "").strip()
    description = body.get("description") or ""
    img = str(body.get("img") or "/uploads/ed63010fa7fe49e7b6d09a5e7a990577.jpg").strip()

    import random
    dish_id = f"prod-{int(time.time())}-{random.randint(100, 999)}"

    def _create():
        for cpath in CATALOG_DB_PATHS:
            if not os.path.exists(cpath):
                continue
            try:
                conn = connect_sqlite_wal(cpath)
                cur = conn.cursor()
                name_str = json.dumps(name, ensure_ascii=False) if isinstance(name, dict) else json.dumps({"ru": str(name), "en": str(name), "ka": str(name)}, ensure_ascii=False)
                desc_str = json.dumps(description, ensure_ascii=False) if isinstance(description, dict) else json.dumps({"ru": str(description), "en": str(description), "ka": str(description)}, ensure_ascii=False)
                cur.execute("""
                    INSERT INTO products (id, restaurant_id, name, description, price, img, category, weight, is_available)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (dish_id, restaurant_id, name_str, desc_str, price, img, category, weight))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                log.error("handle_partner_dish_create failed: %s", e)
        return False

    ok = await asyncio.to_thread(_create)
    return web.json_response({"ok": ok, "dish_id": dish_id})


async def handle_partner_stats(request: web.Request) -> web.Response:
    """Возвращает детальную статистику и аналитику по заказам."""
    restaurant_id = (request.query.get("restaurant_id") or "").strip()
    courier_id_raw = (request.query.get("courier_id") or "0").strip()
    period = (request.query.get("period") or "week").strip()
    try:
        courier_id = int(courier_id_raw)
    except ValueError:
        courier_id = 0

    def _calc_stats():
        for opath in ORDER_DB_PATHS:
            if not os.path.exists(opath):
                continue
            try:
                conn = connect_sqlite_wal(opath)
                cur = conn.cursor()

                where_clauses = []
                params = []
                if restaurant_id:
                    where_clauses.append("restaurant_id = ?")
                    params.append(restaurant_id)
                elif courier_id > 0:
                    where_clauses.append("courier_id = ?")
                    params.append(courier_id)

                if period == "today":
                    where_clauses.append("date(created_at) = date('now')")
                elif period == "week":
                    where_clauses.append("datetime(created_at) >= datetime('now', '-7 days')")
                elif period == "month":
                    where_clauses.append("datetime(created_at) >= datetime('now', '-30 days')")

                where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

                cur.execute(f"""
                    SELECT id, status, total, delivery_fee, tips, created_at, items
                    FROM orders {where_sql} ORDER BY id DESC
                """, tuple(params))
                orders = cur.fetchall()

                # Fallback: если фильтр пуст, заберем все заказы, чтобы не показывать пустой экран
                if not orders and period != "all":
                    fallback_where = f"WHERE {'restaurant_id = ?' if restaurant_id else 'courier_id = ?'}" if (restaurant_id or courier_id > 0) else ""
                    cur.execute(f"SELECT id, status, total, delivery_fee, tips, created_at, items FROM orders {fallback_where} ORDER BY id DESC", tuple(params))
                    orders = cur.fetchall()

                conn.close()

                total_revenue = 0.0
                delivered_count = 0
                active_count = 0
                cancelled_count = 0
                dish_counts = {}
                daily_map = {}
                courier_earnings = 0.0
                tips_total = 0.0
                delivery_trips = []

                import datetime
                for i in range(6, -1, -1):
                    d = datetime.date.today() - datetime.timedelta(days=i)
                    d_str = d.strftime("%Y-%m-%d")
                    day_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][d.weekday()]
                    daily_map[d_str] = {"date": d_str, "day": f"{day_ru} {d.strftime('%d.%m')}", "revenue": 0.0, "count": 0}

                for o in orders:
                    oid, st, tot, d_fee, tips_val, c_at, items_json = o
                    tot = float(tot or 0.0)
                    d_fee_f = float(d_fee or 8.0)
                    tips_f = float(tips_val or 0.0)
                    st = (st or "new").lower()
                    if st == "delivered":
                        delivered_count += 1
                        total_revenue += tot
                        courier_earnings += (d_fee_f + tips_f)
                        tips_total += tips_f
                        delivery_trips.append({
                            "id": oid,
                            "delivery_fee": d_fee_f,
                            "tips": tips_f,
                            "created_at": c_at,
                        })

                        c_date = (c_at or "")[:10]
                        if c_date in daily_map:
                            daily_map[c_date]["revenue"] += tot
                            daily_map[c_date]["count"] += 1

                        if items_json:
                            try:
                                items = json.loads(items_json) if isinstance(items_json, str) else items_json
                                for it in items:
                                    name_val = it.get("name") or it.get("title") or "Блюдо"
                                    name_str = name_val if isinstance(name_val, str) else name_val.get("ru") or str(name_val)
                                    qty = int(it.get("quantity") or 1)
                                    price = float(it.get("price") or 0.0)
                                    if name_str not in dish_counts:
                                        dish_counts[name_str] = {"name": name_str, "count": 0, "revenue": 0.0}
                                    dish_counts[name_str]["count"] += qty
                                    dish_counts[name_str]["revenue"] += price * qty
                            except Exception:
                                pass
                    elif st in ("new", "pending", "confirmed", "accepted", "preparing", "ready", "delivering", "on_the_way"):
                        active_count += 1
                    elif st == "cancelled":
                        cancelled_count += 1

                avg_check = round(total_revenue / delivered_count, 1) if delivered_count > 0 else 0.0
                rest_net = round(total_revenue * 0.9, 1)
                platform_fee = round(total_revenue * 0.1, 1)

                top_dishes = sorted(dish_counts.values(), key=lambda x: x["count"], reverse=True)[:5]
                chart_data = list(daily_map.values())

                return {
                    "revenue": round(total_revenue, 1),
                    "courier_earnings": round(courier_earnings, 1),
                    "tips_total": round(tips_total, 1),
                    "delivery_trips": delivery_trips,
                    "delivered_count": delivered_count,
                    "active_count": active_count,
                    "cancelled_count": cancelled_count,
                    "total_orders": len(orders),
                    "avg_check": avg_check,
                    "restaurant_net": rest_net,
                    "platform_fee": platform_fee,
                    "top_dishes": top_dishes,
                    "daily_chart": chart_data,
                }
            except Exception as e:
                log.error("handle_partner_stats error: %s", e)
        return {"revenue": 0.0, "delivered_count": 0, "active_count": 0, "cancelled_count": 0, "total_orders": 0, "avg_check": 0.0, "top_dishes": [], "daily_chart": []}

    res = await asyncio.to_thread(_calc_stats)
    return web.json_response({"ok": True, "period": period, "stats": res})


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=200)
    else:
        resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, PATCH, DELETE"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Bot-Security-Token"
    return resp


async def handle_rush_status(request: web.Request) -> web.Response:
    restaurant_id = request.query.get("restaurant_id", "").strip()
    rush_mode = 0
    if restaurant_id and db:
        rush_mode = await db.get_partner_rush_mode(restaurant_id)

    now_geo = datetime.now(GEORGIA_TZ)
    hour = now_geo.hour
    is_evening_schedule = (18 <= hour < 22)

    if rush_mode == 1:
        is_rush = True
        reason = "manual_on"
    elif rush_mode == -1:
        is_rush = False
        reason = "manual_off"
    else:
        is_rush = is_evening_schedule
        reason = "evening_rush" if is_evening_schedule else "normal"

    data = {
        "is_rush": is_rush,
        "reason": reason,
        "rush_mode": rush_mode,
        "current_hour": hour,
        "tbilisi_time": now_geo.strftime("%Y-%m-%d %H:%M:%S"),
        "delivery_min": 45 if is_rush else 25,
        "delivery_max": 65 if is_rush else 40,
    }
    return web.json_response(data, headers={"Access-Control-Allow-Origin": "*"})


def make_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/healthz", handle_health)
    app.router.add_get("/api/bot/v1/rush-status", handle_rush_status)
    app.router.add_post("/api/bot/v1/restaurant/new-order", handle_new_order)
    app.router.add_post("/api/bot/v1/restaurant/courier-arrived", handle_courier_arrived)
    app.router.add_post("/api/bot/v1/couriers/broadcast", handle_broadcast)
    app.router.add_post("/api/bot/v1/couriers/assign-order", handle_assign)
    app.router.add_post("/api/bot/v1/orders/sync-state", handle_sync_state)
    app.router.add_post("/api/bot/v1/orders/cancel", handle_cancel)
    app.router.add_post("/api/bot/v1/orders/review", handle_order_review)
    app.router.add_post("/api/bot/v1/orders/tips", handle_order_tips)
    app.router.add_get("/api/bot/v1/partners", handle_partners_list)
    # Новые эндпоинты для интеграции Mini App и вебхуков бэкенда
    app.router.add_post("/api/bot/v1/auth/session", handle_auth_session)
    app.router.add_post("/api/bot/v1/webhook/orders", handle_gateway_webhook)
    app.router.add_get("/api/bot/v1/partner/orders", handle_partner_orders)
    app.router.add_post("/api/bot/v1/partner/order/{id}/status", handle_update_partner_order_status)
    app.router.add_patch("/api/bot/v1/partner/order/{id}/status", handle_update_partner_order_status)
    # Эндпоинты для полноценного меню и аналитики
    app.router.add_get("/api/bot/v1/partner/menu", handle_partner_menu)
    app.router.add_post("/api/bot/v1/partner/menu/toggle", handle_partner_dish_toggle)
    app.router.add_post("/api/bot/v1/partner/menu/update", handle_partner_dish_update)
    app.router.add_post("/api/bot/v1/partner/menu/create", handle_partner_dish_create)
    app.router.add_get("/api/bot/v1/partner/stats", handle_partner_stats)
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
    log.info("Backend data dir: %s", _BACKEND_DATA)
    for label, paths in (
        ("order", ORDER_DB_PATHS),
        ("auth", BACKEND_DB_PATHS),
        ("catalog", CATALOG_DB_PATHS),
    ):
        for p in paths:
            log.info("  %s.db: %s (%s)", label, p, "OK" if os.path.exists(p) else "MISSING")
    log.info(
        "Commission: restaurant=%.0f%% items, platform=%.0f%% items, courier=100%% delivery+tips",
        RESTAURANT_ITEMS_SHARE * 100,
        PLATFORM_ITEMS_COMMISSION * 100,
    )
    log.info("=" * 50)

    # База данных
    db = Database(DB_PATH)
    await db.connect()

    # Синхронизация существующих пользователей бота в бэкенд и удаление фантомных курьеров
    try:
        await sync_all_bot_users_to_backend()
    except Exception as e_sync:
        log.error("Failed startup sync_all_bot_users_to_backend: %s", e_sync)

    # Сброс всех курьеров в офлайн убран, чтобы избежать рассинхронизации клавиатур
    # и статусов при перезапусках бота в процессе обновления.
    log.info("Courier status reset on startup bypassed")
    await restore_pending_courier_snoozes()
    await restore_pending_courier_assign_reminders()

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
                "description": "Запустить бота",
                "icon_custom_emoji_id": "5384244502040975393",
            }),
            BotCommand.model_validate({
                "command": "menu",
                "description": "Главное меню",
                "icon_custom_emoji_id": "5384222159621102491",
            }),
            BotCommand.model_validate({
                "command": "profile",
                "description": "Мой профиль",
                "icon_custom_emoji_id": "5381848533060067195",
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

    # Menu button "Open" → partners SPA on mestidelivery.com (not Firebase)
    try:
        from aiogram.types import MenuButtonWebApp, WebAppInfo as _WebAppInfo

        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Open",
                web_app=_WebAppInfo(url=MINIAPP_DIRECT_URL),
            )
        )
        log.info("Chat menu button WebApp set to %s", MINIAPP_DIRECT_URL)
    except Exception as e:
        log.warning("Failed to set chat menu button: %s", e)

    # Main Mini App / Direct Link live only in @BotFather (not Bot API).
    # If they still point at mestidelivery.web.app, Telegram shows Firebase 404
    # even while menu button + HTTPS WebApp buttons are correct.
    try:
        me = await bot.get_me()
        if getattr(me, "has_main_web_app", False):
            log.warning(
                "Bot has Main Mini App (BotFather). Ensure its URL is %s — "
                "stale Firebase/web.app URLs cannot be fixed via Bot API.",
                MINIAPP_DIRECT_URL,
            )
    except Exception as e:
        log.debug("Main Mini App check skipped: %s", e)

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
        is_super_admin=db.is_super_admin,
        ops={
            "assign_courier": admin_assign_courier,
            "cancel_order": admin_cancel_order,
            "delete_order": admin_delete_order,
            "bulk_delete_orders": admin_bulk_delete_orders,
            "ping_couriers": admin_ping_order_couriers,
            "rebroadcast": admin_rebroadcast_order,
            "force_offline": admin_force_courier_offline,
            "block_courier": admin_block_courier,
            "unblock_courier": admin_unblock_courier,
            "set_restaurant_open": admin_set_restaurant_open,
            "send_message": admin_send_partner_message,
            "get_courier_block": db.get_courier_block,
        },
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
