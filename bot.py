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
import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Optional

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from dotenv import load_dotenv
import bcrypt


# ─────────────────────────────────────────────
#  Конфигурация
# ─────────────────────────────────────────────
load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "7850991424:AAGHGIOHv2Zn-M4moa-5X_oVaypMlp2SXuw")
SECURITY_TOKEN: str = os.getenv("BOT_SECURITY_TOKEN", "MestiSecurePassphrase_23wdq432hj")
HTTP_HOST: str = os.getenv("PARTNERS_HTTP_HOST", "0.0.0.0")
HTTP_PORT: int = int(os.getenv("PARTNERS_HTTP_PORT", "50061"))
BACKEND_URL: str = os.getenv("MAIN_BACKEND_URL", "http://localhost:8080")
BOT_PUBLIC_URL: str = os.getenv("BOT_PUBLIC_URL", "")  # URL для Telegram Webhook
DB_PATH: str = os.getenv("PARTNERS_DB_PATH", "partners_bot.db")


BACKEND_DB_PATHS = [
    r"c:\MestiDelivery\Backend GO\Backend\data\auth.db",
    r"c:\MestiDelivery\Backend GO\Backend\build\data\auth.db"
]
CATALOG_DB_PATHS = [
    r"c:\MestiDelivery\Backend GO\Backend\data\catalog.db",
    r"c:\MestiDelivery\Backend GO\Backend\build\data\catalog.db"
]

SECURITY_HEADER = "X-Bot-Security-Token"

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

CREATE INDEX IF NOT EXISTS idx_partners_tid   ON partners(telegram_id);
CREATE INDEX IF NOT EXISTS idx_partners_rid   ON partners(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_order_messages ON order_messages(order_id);
CREATE INDEX IF NOT EXISTS idx_bot_messages_order  ON bot_messages(order_id);
CREATE INDEX IF NOT EXISTS idx_bot_messages_lookup ON bot_messages(order_id, telegram_id, kind);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        try:
            await self._db.execute("ALTER TABLE bot_users ADD COLUMN is_online INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        await self._db.commit()
        log.info("Database connected: %s", self.path)

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

    async def get_online_couriers(self) -> list[int]:
        async with self._db.execute("SELECT telegram_id FROM bot_users WHERE role = 'courier' AND is_online = 1") as cur:
            rows = await cur.fetchall()
            return [r["telegram_id"] for r in rows]


# ─────────────────────────────────────────────
#  Telegram Bot — роутер
# ─────────────────────────────────────────────
router = Router()
db: Optional[Database] = None
bot: Optional[Bot] = None


def make_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для нового заказа: Принять / Отклонить."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять",
                    callback_data=f"accept_{order_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject_{order_id}",
                ),
            ]
        ]
    )


def format_order_message(data: dict) -> str:
    """Форматирует красивое HTML-сообщение о новом заказе."""
    order_id = data.get("order_id", "?")
    total = data.get("total_amount", 0)
    currency = data.get("currency", "сом")
    customer = data.get("customer_name", "Клиент")
    phone = data.get("phone", "—")
    address = data.get("address", "—")
    comment = data.get("comment", "")
    items = data.get("items", [])
    payment = data.get("payment_method", "—")
    delivery_fee = data.get("delivery_fee", 0)
    created_at = data.get("created_at", datetime.now().strftime("%H:%M"))

    # Позиции заказа
    items_text = ""
    if items:
        for item in items:
            name = item.get("name", "Товар")
            qty = item.get("quantity", 1)
            price = item.get("price", 0)
            items_text += f"  • {name} × {qty} — {price:.0f} {currency}\n"
    else:
        items_text = "  —\n"

    comment_block = f"\n💬 <b>Комментарий:</b> {comment}" if comment else ""

    return (
        f"🔔 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n"
        f"🕐 {created_at}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Клиент:</b> {customer}\n"
        f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
        f"📍 <b>Адрес:</b> {address}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛒 <b>Состав заказа:</b>\n"
        f"{items_text}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>Оплата:</b> {payment}\n"
        f"🚚 <b>Доставка:</b> {delivery_fee:.0f} {currency}\n"
        f"💰 <b>Итого:</b> <b>{total:.0f} {currency}</b>"
        f"{comment_block}"
    )


# ── Команды ───────────────────────────────────



I18N = {
    "ru": {
        "welcome": "👋 Добро пожаловать, {first_name}!\n\n💼 Это бот для партнеров MestiDelivery. Здесь вы сможете получать уведомления о заказах и управлять доставкой.\nЧтобы продолжить, выберите язык 👇",
        "choose_role": "👤 Пожалуйста, выберите вашу роль:",
        "enter_login": "🔑 Введите ваш <b>логин</b> из личного кабинета (/partners):",
        "enter_password": "🔒 Теперь введите ваш <b>пароль</b>:",
        "checking_data": "⏳ Проверяем данные...",
        "auth_success_rest": "✅ <b>Авторизация успешна!</b>\nВы вошли как Ресторатор для ресторана <b>{rest_name}</b>.",
        "auth_success_courier": "✅ <b>Авторизация успешна!</b>\nВы вошли как Курьер.",
        "auth_fail": "❌ <b>Неверный логин или пароль</b>. Пожалуйста, проверьте данные и введите логин заново.",
        "role_courier": "🚚 Курьер",
        "role_rest": "🏪 Ресторатор",
        "menu_history": "📜 История заказов",
        "menu_profile": "👤 Профиль",
        "menu_income": "💰 Доход"
    },
    "en": {
        "welcome": "👋 Welcome, {first_name}!\n\n💼 This is the MestiDelivery partners bot. Here you can receive order notifications and manage deliveries.\nTo continue, please select a language 👇",
        "choose_role": "👤 Please choose your role:",
        "enter_login": "🔑 Enter your <b>login</b> from the dashboard (/partners):",
        "enter_password": "🔒 Now enter your <b>password</b>:",
        "checking_data": "⏳ Checking credentials...",
        "auth_success_rest": "✅ <b>Authorization successful!</b>\nYou logged in as Restaurateur for <b>{rest_name}</b>.",
        "auth_success_courier": "✅ <b>Authorization successful!</b>\nYou logged in as Courier.",
        "auth_fail": "❌ <b>Invalid login or password</b>. Please check your credentials and enter your login again.",
        "role_courier": "🚚 Courier",
        "role_rest": "🏪 Restaurateur",
        "menu_history": "📜 Order History",
        "menu_profile": "👤 Profile",
        "menu_income": "💰 Income"
    },
    "ka": {
        "welcome": "👋 მოგესალმებით, {first_name}!\n\n💼 ეს არის MestiDelivery-ის პარტნიორების ბოტი. აქ შეგიძლიათ მიიღოთ შეტყობინებები შეკვეთების შესახებ და მართოთ მიწოდება.\nგაგრძელებისთვის, გთხოვთ აირჩიოთ ენა 👇",
        "choose_role": "👤 გთხოვთ აირჩიოთ თქვენი როლი:",
        "enter_login": "🔑 შეიყვანეთ თქვენი <b>ლოგინი</b> პირადი კაბინეტიდან (/partners):",
        "enter_password": "🔒 ახლა შეიყვანეთ თქვენი <b>პაროლი</b>:",
        "checking_data": "⏳ მონაცემების შემოწმება...",
        "auth_success_rest": "✅ <b>ავტორიზაცია წარმატებულია!</b>\nთქვენ შეხვედით როგორც რესტორატორი <b>{rest_name}</b>-სთვის.",
        "auth_success_courier": "✅ <b>ავტორიზაცია წარმატებულია!</b>\nთქვენ შეხვედით როგორც კურიერი.",
        "auth_fail": "❌ <b>არასწორი ლოგინი ან პაროლი</b>. გთხოვთ შეამოწმოთ მონაცემები და ხელახლა შეიყვანოთ ლოგინი.",
        "role_courier": "🚚 კურიერი",
        "role_rest": "🏪 რესტორატორი",
        "menu_history": "📜 შეკვეთების ისტორია",
        "menu_profile": "👤 პროფილი",
        "menu_income": "💰 შემოსავალი"
    }
}

def get_text(lang: str, key: str, **kwargs) -> str:
    text = I18N.get(lang, I18N["ru"]).get(key, I18N["ru"][key])
    return text.format(**kwargs) if kwargs else text

class RegistrationFlow(StatesGroup):

    language = State()
    role = State()
    username = State()
    password = State()


from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_kb(lang: str, role: str = "", is_online: int = 0) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=get_text(lang, "menu_history"))],
        [KeyboardButton(text=get_text(lang, "menu_profile")), KeyboardButton(text=get_text(lang, "menu_income"))]
    ]
    if role == "courier":
        if is_online == 1:
            keyboard.insert(0, [KeyboardButton(text="🔴 Уйти с линии")])
        else:
            keyboard.insert(0, [KeyboardButton(text="🟢 Выйти на линию")])
            
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_language_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"), InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton(text="🇬🇪 ქართული", callback_data="lang_ka")]
        ]
    )

def get_role_kb(lang: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_text(lang, "role_courier"), callback_data="role_courier")],
            [InlineKeyboardButton(text=get_text(lang, "role_rest"), callback_data="role_restaurant_admin")]
        ]
    )

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    first_name = message.from_user.first_name or message.from_user.username or "affiliate sxclipse"
    
    # User hasn't selected language yet, use Russian by default for welcome, 
    # but since it's the language selection step, they will read the text and pick language.
    # The language selection buttons are universally understandable.
    # Wait, maybe use user's telegram language code if available?
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
        reply_markup=get_role_kb(lang)
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
    await state.set_state(RegistrationFlow.username)

@router.message(RegistrationFlow.username)
async def process_username(message: Message, state: FSMContext):
    username = message.text.strip()
    await state.update_data(username=username)
    data = await state.get_data()
    lang = data.get("language", "ru")
    await message.answer(get_text(lang, "enter_password"), parse_mode=ParseMode.HTML)
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
        
    await message.answer(get_text(language, "checking_data"))
    
    import sqlite3
    import bcrypt
    
    auth_success = False
    backend_user_id = None
    restaurant_id = None
    
    for path in BACKEND_DB_PATHS:
        try:
            if not os.path.exists(path):
                continue
            conn = sqlite3.connect(path)
            cursor = conn.cursor()
            cursor.execute("SELECT id, password_hash, role, restaurant_id FROM admin_users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                hashed = row[1]
                if bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8')):
                    user_role = row[2]
                    if user_role == role or user_role == "super_admin":
                        backend_user_id = row[0]
                        restaurant_id = row[3]
                        cursor.execute("UPDATE admin_users SET telegram_id = NULL WHERE telegram_id = ?", (str(message.from_user.id),))
                        cursor.execute("UPDATE admin_users SET telegram_id = ? WHERE id = ?", (str(message.from_user.id), backend_user_id))
                        conn.commit()
                        auth_success = True
                        break
            conn.close()
        except Exception as e:
            log.error(f"Error checking auth.db: {e}")
            if 'conn' in locals():
                conn.close()
            log.error(f"Error checking auth.db: {e}")
            
    if auth_success:
        await db.save_bot_user(message.from_user.id, language, role, username)
        
        if role == "restaurant_admin" and restaurant_id:
            rest_name = restaurant_id
            for cpath in CATALOG_DB_PATHS:
                try:
                    if not os.path.exists(cpath):
                        continue
                    cconn = sqlite3.connect(cpath)
                    ccur = cconn.cursor()
                    ccur.execute("SELECT name FROM restaurants WHERE id = ?", (restaurant_id,))
                    r = ccur.fetchone()
                    if r:
                        rest_name = r[0]
                    cconn.close()
                except Exception:
                    pass
            await db.register_partner(message.from_user.id, restaurant_id, rest_name)
            
            await message.answer(get_text(language, "auth_success_rest", rest_name=rest_name), parse_mode=ParseMode.HTML, reply_markup=get_main_kb(language, role="restaurant_admin"))
        else:
            await message.answer(get_text(language, "auth_success_courier"), parse_mode=ParseMode.HTML, reply_markup=get_main_kb(language, role="courier", is_online=0))
            
        await state.clear()
    else:
        await message.answer(get_text(language, "auth_fail"), parse_mode=ParseMode.HTML)
        await state.set_state(RegistrationFlow.username)

@router.message(Command("help"))

async def cmd_help(message: Message):
    await message.answer(
        "📋 <b>Команды партнёрского бота</b>\n\n"
        "/start — приветствие\n"
        "/register &lt;ID&gt; — привязать ресторан к этому чату\n"
        "/status — проверить статус подключения\n"
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
            conn = sqlite3.connect(path)
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
            conn = sqlite3.connect(path)
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
                        cconn = sqlite3.connect(cpath)
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
            conn = sqlite3.connect(path)
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


@router.message(F.text == "🟢 Выйти на линию")
async def process_go_online(message: Message):
    user = await db.get_bot_user(message.from_user.id)
    if user and user["role"] == "courier":
        await db.set_courier_online_status(message.from_user.id, 1)
        await message.answer("🟢 Вы вышли на линию! Теперь вы будете получать новые заказы.", reply_markup=get_main_kb(user["language"], role="courier", is_online=1))

@router.message(F.text == "🔴 Уйти с линии")
async def process_go_offline(message: Message):
    user = await db.get_bot_user(message.from_user.id)
    if user and user["role"] == "courier":
        await db.set_courier_online_status(message.from_user.id, 0)
        await message.answer("🔴 Вы ушли с линии. Заказы временно не будут вам поступать.", reply_markup=get_main_kb(user["language"], role="courier", is_online=0))

# ── Callback-кнопки ───────────────────────────

@router.callback_query(F.data.startswith("accept_"))
async def on_accept(callback: CallbackQuery):
    order_id = int(callback.data.split("_", 1)[1])
    telegram_id = callback.message.chat.id

    log.info("Order #%d accepted by partner tg=%d", order_id, telegram_id)

    # Обновляем бэкенд
    success = await update_order_status_backend(order_id, "accepted")

    if success:
        # Редактируем сообщение — добавляем новые кнопки
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🍳 Начать готовить", callback_data=f"prepare_{order_id}"),
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"reject_{order_id}"),
            ]
        ])
        await callback.message.edit_text(
            callback.message.html_text + "\n\n"
            "✅ <b>Заказ принят!</b> Вы можете начать готовить его прямо сейчас.",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer("✅ Заказ принят!", show_alert=False)
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
                InlineKeyboardButton(text="✅ Готово к выдаче", callback_data=f"ready_{order_id}"),
            ]
        ])
        await callback.message.edit_text(
            callback.message.html_text + "\n\n"
            "🍳 <b>Заказ готовится.</b> Нажмите 'Готово к выдаче', когда курьер сможет его забрать. Курьеры уже начали получать уведомления!",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer("🍳 Заказ готовится", show_alert=False)
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
        await callback.message.edit_text(
            callback.message.html_text + "\n\n"
            "✅ <b>Заказ готов к выдаче!</b> Ожидайте курьера.",
            reply_markup=None,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer("✅ Заказ готов", show_alert=False)
        await db.update_order_status(order_id, telegram_id, "ready")
    else:
        await callback.answer("⚠️ Ошибка обновления статуса.", show_alert=True)


@router.callback_query(F.data.startswith("reject_"))
async def on_reject(callback: CallbackQuery):
    order_id = int(callback.data.split("_", 1)[1])
    telegram_id = callback.message.chat.id

    log.info("Order #%d rejected by partner tg=%d", order_id, telegram_id)

    success = await update_order_status_backend(order_id, "cancelled")

    if success:
        await callback.message.edit_text(
            callback.message.html_text + "\n\n"
            "❌ <b>Заказ отклонён.</b>",
            reply_markup=None,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer("❌ Заказ отклонён.", show_alert=False)
        await db.update_order_status(order_id, telegram_id, "cancelled")
    else:
        await callback.answer(
            "⚠️ Ошибка обновления статуса на сервере.",
            show_alert=True,
        )
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


@router.callback_query(F.data.startswith("mesti_"))
async def on_mesti_callback(callback: CallbackQuery):
    data = callback.data
    action, order_id = decode_callback_data(data)
    if not action or not order_id:
        await callback.answer("⚠️ Неизвестное действие", show_alert=True)
        return

    telegram_id = callback.from_user.id
    chat_id = callback.message.chat.id

    log.info("Mesti callback: order_id=%d, action=%s, user_tg=%d", order_id, action, telegram_id)

    # Меняем кнопку на лоадер, чтобы избежать дабл-кликов
    original_kb = callback.message.reply_markup
    try:
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⏳ Обработка...", callback_data="ignore")
            ]])
        )
    except Exception:
        pass

    # Call gateway bot-callback
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
                    await callback.answer("⚠️ Ошибка связи с сервером", show_alert=True)
                    # Восстанавливаем оригинальную клавиатуру при ошибке сети
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

    # Check gateway response success
    if not resp_data.get("success"):
        await callback.answer("⚠️ Ошибка выполнения операции", show_alert=True)
        display_text = resp_data.get("display_text")
        if display_text:
            try:
                await callback.message.edit_text(text=display_text, reply_markup=None, parse_mode=ParseMode.HTML)
            except Exception:
                pass
        else:
            try:
                await callback.message.edit_reply_markup(reply_markup=original_kb)
            except Exception:
                pass
        return

    # Update message text and keyboard
    display_text = resp_data.get("display_text", "")
    next_action = resp_data.get("next_allowed_action", "")
    kb = keyboard_for_action(next_action, order_id)

    try:
        await callback.message.edit_text(
            text=display_text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        log.warning("Webhook: edit message failed: %s", e)

    await callback.answer("Успешно", show_alert=False)

    # Re-tag message kind to tracking in database
    await db.update_kind(order_id, telegram_id, "tracking")


# ─────────────────────────────────────────────
#  HTTP клиент → бэкенд
# ─────────────────────────────────────────────
import aiohttp as _aiohttp


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

    # Запрашиваем детали заказа с бэкенда для отображения подробного состава заказа
    full_order = {}
    try:
        url = f"{BACKEND_URL}/api/v1/orders/{order_id}"
        async with _aiohttp.ClientSession() as session:
            async with session.get(url, timeout=_aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    full_order = await resp.json()
                    if not restaurant_id:
                        restaurant_id = full_order.get("restaurant_id")
                else:
                    log.warning("Failed to fetch full order details from backend status=%d", resp.status)
    except Exception as e:
        log.error("Error fetching order details from backend: %s", e)

    # Если все еще нет telegram_id, попробуем поискать по разрешенному restaurant_id
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

    # Объединяем данные из вебхука и детального запроса
    formatted_data = {
        "order_id": order_id,
        "restaurant_id": restaurant_id or full_order.get("restaurant_id", ""),
        "total_amount": full_order.get("total") or data.get("total_amount") or 0,
        "currency": data.get("currency") or "сом",
        "customer_name": full_order.get("customer_name") or "Клиент",
        "phone": full_order.get("phone") or "—",
        "address": full_order.get("address") or "—",
        "comment": full_order.get("comment") or "",
        "items": full_order.get("items") or [],
        "payment_method": full_order.get("payment_method") or "—",
        "delivery_fee": full_order.get("delivery_fee") or 0,
    }

    # Формируем и отправляем сообщение
    text = format_order_message(formatted_data)
    keyboard = make_order_keyboard(order_id)

    try:
        msg = await bot.send_message(
            chat_id=telegram_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
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


def format_broadcast_text(restaurant: str, pickup: str, delivery: str, fee: float, currency: str) -> str:
    return (
        f"🛵 <b>Новый заказ из ресторана {restaurant}!</b>\n"
        f"Забрать: {pickup}\n"
        f"Привезти: {delivery}\n"
        f"Доход: {fee:.2f} {currency}"
    )


def make_broadcast_keyboard(order_id: int, mini_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", web_app=WebAppInfo(url=mini_app_url)),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"mesti_rejected_{order_id}"),
            ]
        ]
    )


def keyboard_for_action(action: str, order_id: int) -> Optional[InlineKeyboardMarkup]:
    if action == "picked_up":
        btn = InlineKeyboardButton(text="📦 Забрал заказ", callback_data=f"mesti_picked_up_{order_id}")
    elif action == "arrived":
        btn = InlineKeyboardButton(text="📍 Прибыл на место", callback_data=f"mesti_arrived_{order_id}")
    elif action == "completed":
        btn = InlineKeyboardButton(text="✅ Заказ передан (Завершить)", callback_data=f"mesti_completed_{order_id}")
    else:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


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
    currency = req.get("currency", "сом")
    mini_app_url = req.get("mini_app_url", "")
    # Формируем нужную ссылку для Mini App
    mini_app_url = f"https://mestidelivery.web.app/partners/order{order_id}"

    text = format_broadcast_text(restaurant_name, pickup_address, delivery_address, delivery_fee, currency)
    keyboard = make_broadcast_keyboard(order_id, mini_app_url)

    online_couriers = await db.get_online_couriers()

    sent = 0
    failed = []
    for cid in courier_ids:
        if cid <= 0 or cid not in online_couriers:
            continue
        try:
            msg = await bot.send_message(
                chat_id=cid,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
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

    # 1. Winner message
    winner_text = f"✅ Вы приняли заказ #{order_id}. Ресторан готовит. Направляйтесь на место."
    winner_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📦 Забрал заказ",
                    callback_data=f"mesti_picked_up_{order_id}",
                )
            ]
        ]
    )

    try:
        winner_msg = await bot.send_message(
            chat_id=winner_tg,
            text=winner_text,
            reply_markup=winner_keyboard,
            parse_mode=ParseMode.HTML,
        )
        await db.save_message(order_id, winner_tg, winner_msg.message_id, "courier", "winner")
    except Exception as e:
        log.error("assign: send winner message failed: %s", e)
        return web.Response(status=502, text="telegram send failed")

    # 2. Losers set
    losers = req.get("losers_telegram_ids")
    if not losers:
        # DB lookup
        losers = await db.get_broadcast_recipients(order_id)

    notified = 0
    for loser_id in losers:
        if loser_id == winner_tg:
            continue
        try:
            # Look up broadcast message id for this loser
            msgs = await db.get_messages_for_order_kind(order_id, "broadcast")
            for m in msgs:
                if m["telegram_id"] == loser_id:
                    await bot.edit_message_text(
                        chat_id=loser_id,
                        message_id=m["message_id"],
                        text=f"Заказ #{order_id} уже взят другим курьером.",
                        reply_markup=None,
                    )
                    notified += 1
        except Exception as e:
            log.warning("assign: edit loser %d message failed: %s", loser_id, e)

    log.info("assign done: order_id=%d, winner_tg=%d, losers_notified=%d", order_id, winner_tg, notified)
    return web.json_response({"ok": True, "winner_message_id": winner_msg.message_id, "losers_notified": notified})


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
    kb = keyboard_for_action(next_action, order_id)

    try:
        await bot.edit_message_text(
            chat_id=user_tg,
            message_id=target["message_id"],
            text=display_text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        log.error("sync-state: edit message failed: %s", e)
        return web.Response(status=502, text="telegram edit failed")

    if target["kind"] != "tracking":
        await db.update_kind(order_id, user_tg, "tracking")

    log.info("sync-state applied: order_id=%d, user_tg=%d, next_action=%s", order_id, user_tg, next_action)
    return web.json_response({"ok": True})


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def handle_partners_list(request: web.Request) -> web.Response:
    """GET /api/bot/v1/partners — список зарегистрированных партнёров."""
    if not check_token(request):
        return web.Response(status=401, text="unauthorized")
    partners = await db.list_partners()
    return web.json_response(partners)


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/healthz", handle_health)
    app.router.add_post("/api/bot/v1/restaurant/new-order", handle_new_order)
    app.router.add_post("/api/bot/v1/couriers/broadcast", handle_broadcast)
    app.router.add_post("/api/bot/v1/couriers/assign-order", handle_assign)
    app.router.add_post("/api/bot/v1/orders/sync-state", handle_sync_state)
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

    # Telegram бот
    bot = Bot(token=BOT_TOKEN, default=None)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

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
        await runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
