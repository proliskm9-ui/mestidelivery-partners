"""
Админ-панель Partners Bot: одно редактируемое сообщение + SLA-алерты.
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

log = logging.getLogger("partners_bot.admin")

ADMIN_ORDERS_PAGE = 8
SLA_ACCEPT_MIN = 5  # ресторан ~5 мин на принятие
SLA_ASSIGN_MIN = 5  # заказ без курьера
SLA_READY_MIN = 15
SLA_DELIVER_MIN = 10
SLA_POLL_SEC = 90


class AdminMessageState(StatesGroup):
    waiting_text = State()

ACTIVE_STATUSES = ("pending", "accepted", "preparing", "ready", "delivering")
DONE_STATUSES = ("delivered", "cancelled")

STATUS_RU = {
    "pending": "Ожидает",
    "accepted": "Принят",
    "preparing": "Готовится",
    "ready": "Готов",
    "delivering": "В пути",
    "delivered": "Доставлен",
    "cancelled": "Отменён",
}

# deps injected at register time
_deps: dict[str, Any] = {}


def _ce(emoji_id: str, alt: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{alt}</tg-emoji>'


def _E() -> dict:
    return _deps["emoji"]


def _db():
    return _deps["get_db"]()


def _bot():
    return _deps["get_bot"]()


def _admin_id() -> int:
    return int(_deps["admin_tg_id"])


def _order_paths() -> list[str]:
    return _deps["order_db_paths"]


def _catalog_paths() -> list[str]:
    return _deps["catalog_db_paths"]


def _auth_paths() -> list[str]:
    return _deps["auth_db_paths"]


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn


def _first_existing(paths: list[str]) -> Optional[str]:
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip().replace("T", " ").replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s[:26], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _age_minutes(ts: Optional[datetime], now: Optional[datetime] = None) -> Optional[float]:
    if not ts:
        return None
    now = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (now - ts).total_seconds() / 60.0)


def _fmt_money(v) -> str:
    try:
        n = float(v or 0)
        return f"{n:.0f}" if n == int(n) else f"{n:.2f}"
    except (TypeError, ValueError):
        return str(v)


def _status_label(status: str) -> str:
    return STATUS_RU.get(status or "", status or "—")


def _overdue_label(flags: list[str]) -> str:
    if not flags:
        return ""
    m = {
        "accept": "не принят",
        "assign": "нет курьера",
        "ready": "не готов",
        "deliver": "не доставлен",
    }
    parts = [m[f] for f in flags if f in m]
    return "⚠️ " + ", ".join(parts) if parts else "⚠️"


def _clip(text: str, limit: int = 3900) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n…(обрезано)"


# Владелец панели — только эти Telegram ID (не роль из auth.db)
ADMIN_IDS = {5564438585}


def _is_admin(tg_id: int) -> bool:
    tid = int(tg_id or 0)
    return tid == _admin_id() or tid in ADMIN_IDS


async def _is_admin_async(tg_id: int) -> bool:
    return _is_admin(tg_id)


def _ops():
    return _deps.get("ops") or {}


def _orders_where(filter_key: str) -> str:
    if filter_key == "active":
        return f"status IN ({','.join(repr(s) for s in ACTIVE_STATUSES)})"
    if filter_key == "done":
        return f"status IN ({','.join(repr(s) for s in DONE_STATUSES)})"
    return "1=1"


def _count_orders(filter_key: str) -> int:
    path = _first_existing(_order_paths())
    if not path:
        return 0
    where = _orders_where(filter_key)
    conn = _connect(path)
    n = int(conn.execute(f"SELECT COUNT(*) AS c FROM orders WHERE {where}").fetchone()["c"])
    conn.close()
    return n


def _count_overdue_active() -> int:
    path = _first_existing(_order_paths())
    if not path:
        return 0
    now = datetime.now(timezone.utc)
    conn = _connect(path)
    rows = conn.execute(
        f"""
        SELECT status, created_at, restaurant_confirmed_at, courier_taken_at, courier_id
        FROM orders
        WHERE status IN ({','.join(repr(s) for s in ACTIVE_STATUSES)})
        """
    ).fetchall()
    conn.close()
    return sum(1 for r in rows if _order_overdue_flags(r, now))


# ── SQL / data ───────────────────────────────────────────────


def _row_val(row: sqlite3.Row, key: str, default=None):
    """Безопасный доступ к sqlite3.Row (IndexError при отсутствии ключа)."""
    try:
        if key in row.keys():
            return row[key]
    except Exception:
        pass
    return default


def _order_overdue_flags(row: sqlite3.Row, now: datetime) -> list[str]:
    """Какие SLA-флаги горят для строки заказа."""
    flags: list[str] = []
    st = (str(_row_val(row, "status") or "")).lower()
    created = _parse_ts(_row_val(row, "created_at"))
    confirmed = _parse_ts(_row_val(row, "restaurant_confirmed_at"))
    taken = _parse_ts(_row_val(row, "courier_taken_at"))

    if st == "pending":
        age = _age_minutes(created, now)
        if age is not None and age >= SLA_ACCEPT_MIN:
            flags.append("accept")
    if st in ("accepted", "preparing", "ready"):
        try:
            cid = int(_row_val(row, "courier_id") or 0)
        except (TypeError, ValueError):
            cid = 0
        if cid <= 0:
            base = confirmed or created
            age = _age_minutes(base, now)
            if age is not None and age >= SLA_ASSIGN_MIN:
                flags.append("assign")
    if st in ("accepted", "preparing"):
        # Готовность считаем только от подтверждения рестораном.
        if confirmed is None:
            pass
        else:
            age = _age_minutes(confirmed, now)
            if age is not None and age >= SLA_READY_MIN:
                flags.append("ready")
    if st == "delivering":
        # Доставка — только от момента назначения курьера.
        if taken is None:
            pass
        else:
            age = _age_minutes(taken, now)
            if age is not None and age >= SLA_DELIVER_MIN:
                flags.append("deliver")
    return flags


def _load_restaurant_names() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in _catalog_paths():
        if not os.path.exists(path):
            continue
        try:
            conn = _connect(path)
            for r in conn.execute("SELECT id, name FROM restaurants"):
                if r["id"] and r["id"] not in out:
                    out[str(r["id"])] = r["name"] or str(r["id"])
            conn.close()
        except Exception as e:
            log.warning("catalog names: %s", e)
    return out


def _load_courier_names() -> dict[int, str]:
    """backend courier_id → username."""
    out: dict[int, str] = {}
    for path in _auth_paths():
        if not os.path.exists(path):
            continue
        try:
            conn = _connect(path)
            for r in conn.execute(
                "SELECT id, username, telegram_id FROM admin_users WHERE role = 'courier'"
            ):
                cid = int(r["id"])
                if cid not in out:
                    out[cid] = r["username"] or f"#{cid}"
            conn.close()
            break
        except Exception as e:
            log.warning("auth couriers: %s", e)
    return out


def _query_orders(filter_key: str, page: int) -> tuple[list[dict], int]:
    path = _first_existing(_order_paths())
    if not path:
        return [], 0
    names = _load_restaurant_names()
    couriers = _load_courier_names()
    now = datetime.now(timezone.utc)
    where = _orders_where(filter_key)

    conn = _connect(path)
    total = conn.execute(f"SELECT COUNT(*) AS c FROM orders WHERE {where}").fetchone()["c"]
    offset = max(0, page) * ADMIN_ORDERS_PAGE
    rows = conn.execute(
        f"""
        SELECT id, restaurant_id, status, total, address, courier_id,
               created_at, restaurant_confirmed_at, courier_taken_at, tips,
               delivery_fee, service_fee, phone, customer_name, payment_method
        FROM orders WHERE {where}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (ADMIN_ORDERS_PAGE, offset),
    ).fetchall()
    conn.close()

    items = []
    for r in rows:
        flags = _order_overdue_flags(r, now)
        cid = int(r["courier_id"] or 0)
        items.append(
            {
                "id": int(r["id"]),
                "restaurant_id": str(r["restaurant_id"] or ""),
                "restaurant": names.get(str(r["restaurant_id"] or ""), str(r["restaurant_id"] or "—")),
                "address": (r["address"] or "—").strip() or "—",
                "total": float(r["total"] or 0),
                "status": r["status"] or "",
                "courier": couriers.get(cid, "—") if cid else "—",
                "courier_id": cid,
                "overdue": flags,
                "tips": float(r["tips"] or 0) if "tips" in r.keys() else 0.0,
                "delivery_fee": float(r["delivery_fee"] or 0) if "delivery_fee" in r.keys() else 0.0,
                "service_fee": float(r["service_fee"] or 0) if "service_fee" in r.keys() else 0.0,
                "phone": (r["phone"] or "—") if "phone" in r.keys() else "—",
                "customer_name": (r["customer_name"] or "—") if "customer_name" in r.keys() else "—",
                "payment_method": (r["payment_method"] or "—") if "payment_method" in r.keys() else "—",
                "created_at": r["created_at"],
            }
        )
    return items, int(total)


def _query_order_card(order_id: int) -> Optional[dict]:
    path = _first_existing(_order_paths())
    if not path:
        return None
    names = _load_restaurant_names()
    couriers = _load_courier_names()
    now = datetime.now(timezone.utc)
    conn = _connect(path)
    r = conn.execute(
        """
        SELECT id, restaurant_id, status, total, address, courier_id,
               created_at, restaurant_confirmed_at, courier_taken_at, tips,
               delivery_fee, service_fee, phone, customer_name, payment_method, comment
        FROM orders WHERE id = ?
        """,
        (order_id,),
    ).fetchone()
    conn.close()
    if not r:
        return None
    cid = int(r["courier_id"] or 0)
    flags = _order_overdue_flags(r, now)
    return {
        "id": int(r["id"]),
        "restaurant_id": str(r["restaurant_id"] or ""),
        "restaurant": names.get(str(r["restaurant_id"] or ""), str(r["restaurant_id"] or "—")),
        "address": (r["address"] or "—").strip() or "—",
        "total": float(r["total"] or 0),
        "status": r["status"] or "",
        "courier": couriers.get(cid, "—") if cid else "—",
        "courier_id": cid,
        "overdue": flags,
        "tips": float(r["tips"] or 0),
        "delivery_fee": float(r["delivery_fee"] or 0),
        "service_fee": float(r["service_fee"] or 0),
        "phone": r["phone"] or "—",
        "customer_name": r["customer_name"] or "—",
        "payment_method": r["payment_method"] or "—",
        "comment": (r["comment"] or "").strip(),
        "created_at": r["created_at"],
        "courier_taken_at": r["courier_taken_at"],
    }


def _query_restaurants() -> list[dict]:
    path_c = _first_existing(_catalog_paths())
    path_o = _first_existing(_order_paths())
    if not path_c:
        return []

    active_counts: dict[str, int] = {}
    if path_o:
        conn = _connect(path_o)
        placeholders = ",".join("?" * len(ACTIVE_STATUSES))
        for r in conn.execute(
            f"""
            SELECT restaurant_id, COUNT(*) AS c FROM orders
            WHERE status IN ({placeholders})
            GROUP BY restaurant_id
            """,
            ACTIVE_STATUSES,
        ):
            active_counts[str(r["restaurant_id"])] = int(r["c"])
        conn.close()

    conn = _connect(path_c)
    rows = conn.execute(
        "SELECT id, name, is_active, rating FROM restaurants ORDER BY name COLLATE NOCASE"
    ).fetchall()
    conn.close()

    # ui_is_open из partners (если есть)
    ui_open: dict[str, Optional[int]] = {}
    try:
        # sync read через sqlite partners_bot — путь из deps
        pdb = _deps.get("partners_db_path")
        if pdb and os.path.exists(pdb):
            pc = _connect(pdb)
            for r in pc.execute("SELECT restaurant_id, ui_is_open FROM partners"):
                ui_open[str(r["restaurant_id"])] = r["ui_is_open"]
            pc.close()
    except Exception:
        pass

    out = []
    for r in rows:
        rid = str(r["id"])
        catalog_open = int(r["is_active"] or 0) == 1
        ui = ui_open.get(rid)
        is_open = catalog_open if ui is None else int(ui) == 1
        out.append(
            {
                "id": rid,
                "name": r["name"] or rid,
                "is_open": is_open,
                "rating": r["rating"] or "—",
                "active_orders": active_counts.get(rid, 0),
            }
        )
    return out


def _query_restaurant_card(restaurant_id: str) -> dict:
    rests = {r["id"]: r for r in _query_restaurants()}
    base = rests.get(restaurant_id, {"id": restaurant_id, "name": restaurant_id, "is_open": False, "rating": "—", "active_orders": 0})
    path = _first_existing(_order_paths())
    active = []
    today_count = 0
    today_sum = 0.0
    if path:
        conn = _connect(path)
        placeholders = ",".join("?" * len(ACTIVE_STATUSES))
        for r in conn.execute(
            f"""
            SELECT id, total, status FROM orders
            WHERE restaurant_id = ? AND status IN ({placeholders})
            ORDER BY id DESC LIMIT 12
            """,
            (restaurant_id, *ACTIVE_STATUSES),
        ):
            active.append({"id": int(r["id"]), "total": float(r["total"] or 0), "status": r["status"]})
        row = conn.execute(
            """
            SELECT COUNT(*) AS c, COALESCE(SUM(total), 0) AS s FROM orders
            WHERE restaurant_id = ?
              AND date(replace(substr(created_at, 1, 10), 'T', ' ')) = date('now')
              AND status != 'cancelled'
            """,
            (restaurant_id,),
        ).fetchone()
        today_count = int(row["c"] or 0)
        today_sum = float(row["s"] or 0)
        conn.close()
    base = dict(base)
    base["active_list"] = active
    base["today_count"] = today_count
    base["today_sum"] = today_sum
    return base


def _query_couriers() -> list[dict]:
    """Список из bot_users + активный заказ из order.db."""
    couriers_auth = {}
    for path in _auth_paths():
        if not os.path.exists(path):
            continue
        try:
            conn = _connect(path)
            for r in conn.execute(
                "SELECT id, username, telegram_id FROM admin_users WHERE role = 'courier'"
            ):
                tg = r["telegram_id"]
                key = str(tg) if tg else f"id:{r['id']}"
                couriers_auth[key] = {"backend_id": int(r["id"]), "username": r["username"], "telegram_id": int(tg) if tg else None}
            conn.close()
            break
        except Exception as e:
            log.warning("couriers auth: %s", e)

    # статусы online из partners bot_users
    online_map: dict[int, int] = {}
    names: dict[int, str] = {}
    pdb = _deps.get("partners_db_path")
    if pdb and os.path.exists(pdb):
        pc = _connect(pdb)
        for r in pc.execute(
            "SELECT telegram_id, backend_username, is_online FROM bot_users WHERE role = 'courier'"
        ):
            online_map[int(r["telegram_id"])] = int(r["is_online"] or 0)
            names[int(r["telegram_id"])] = r["backend_username"] or str(r["telegram_id"])
        pc.close()

    # активные заказы по courier_id
    active_by_courier: dict[int, dict] = {}
    path = _first_existing(_order_paths())
    if path:
        conn = _connect(path)
        ph = ",".join("?" * len(ACTIVE_STATUSES))
        for r in conn.execute(
            f"""
            SELECT id, courier_id, total, status, address FROM orders
            WHERE courier_id IS NOT NULL AND courier_id != 0 AND status IN ({ph})
            ORDER BY id DESC
            """,
            ACTIVE_STATUSES,
        ):
            cid = int(r["courier_id"])
            if cid not in active_by_courier:
                active_by_courier[cid] = {
                    "id": int(r["id"]),
                    "total": float(r["total"] or 0),
                    "status": r["status"],
                    "address": r["address"] or "—",
                }
        conn.close()

    # собираем уникальных курьеров: кто есть в auth и/или bot_users
    seen_tg: set[int] = set()
    out = []
    for meta in couriers_auth.values():
        tg = meta["telegram_id"]
        if not tg or tg in seen_tg:
            continue
        seen_tg.add(tg)
        bid = meta["backend_id"]
        out.append(
            {
                "telegram_id": tg,
                "backend_id": bid,
                "name": names.get(tg) or meta["username"] or f"tg:{tg}",
                "is_online": online_map.get(tg, 0) == 1,
                "active_order": active_by_courier.get(bid),
            }
        )
    for tg, name in names.items():
        if tg in seen_tg:
            continue
        out.append(
            {
                "telegram_id": tg,
                "backend_id": None,
                "name": name,
                "is_online": online_map.get(tg, 0) == 1,
                "active_order": None,
            }
        )
    out.sort(key=lambda x: (not x["is_online"], x["name"].lower()))
    return out


def _query_courier_card(telegram_id: int) -> dict:
    lst = {c["telegram_id"]: c for c in _query_couriers()}
    base = lst.get(
        telegram_id,
        {"telegram_id": telegram_id, "backend_id": None, "name": f"tg:{telegram_id}", "is_online": False, "active_order": None},
    )
    base = dict(base)
    backend_ids = []
    if base.get("backend_id"):
        backend_ids.append(int(base["backend_id"]))
    # подтянуть все id из auth по telegram
    for path in _auth_paths():
        if not os.path.exists(path):
            continue
        try:
            conn = _connect(path)
            for r in conn.execute(
                "SELECT id FROM admin_users WHERE telegram_id = ? AND role = 'courier'",
                (str(telegram_id),),
            ):
                backend_ids.append(int(r["id"]))
            conn.close()
        except Exception:
            pass
    backend_ids = list(dict.fromkeys(backend_ids))

    today_count = 0
    today_income = 0.0
    history = []
    path = _first_existing(_order_paths())
    if path and backend_ids:
        ph = ",".join("?" * len(backend_ids))
        conn = _connect(path)
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS c,
                   COALESCE(SUM(COALESCE(delivery_fee,0)+COALESCE(tips,0)),0) AS inc
            FROM orders
            WHERE courier_id IN ({ph}) AND status = 'delivered'
              AND date(replace(substr(created_at, 1, 10), 'T', ' ')) = date('now')
            """,
            tuple(backend_ids),
        ).fetchone()
        today_count = int(row["c"] or 0)
        today_income = float(row["inc"] or 0)
        for r in conn.execute(
            f"""
            SELECT id, total, status, delivery_fee, tips, address
            FROM orders
            WHERE courier_id IN ({ph})
              AND date(replace(substr(created_at, 1, 10), 'T', ' ')) = date('now')
            ORDER BY id DESC LIMIT 10
            """,
            tuple(backend_ids),
        ):
            history.append(
                {
                    "id": int(r["id"]),
                    "total": float(r["total"] or 0),
                    "status": r["status"],
                    "earn": float(r["delivery_fee"] or 0) + float(r["tips"] or 0),
                    "address": r["address"] or "—",
                }
            )
        # refresh active
        act_ph = ",".join("?" * len(ACTIVE_STATUSES))
        act = conn.execute(
            f"""
            SELECT id, total, status, address FROM orders
            WHERE courier_id IN ({ph}) AND status IN ({act_ph})
            ORDER BY id DESC LIMIT 1
            """,
            (*backend_ids, *ACTIVE_STATUSES),
        ).fetchone()
        if act:
            base["active_order"] = {
                "id": int(act["id"]),
                "total": float(act["total"] or 0),
                "status": act["status"],
                "address": act["address"] or "—",
            }
        conn.close()
    base["today_count"] = today_count
    base["today_income"] = today_income
    base["history"] = history
    return base


# ── UI builders ──────────────────────────────────────────────


def kb_home(*, pending_payouts: int = 0, overdue_n: int = 0) -> InlineKeyboardMarkup:
    payout_label = "💳 Выплаты" if pending_payouts == 0 else f"💳 Выплаты ({pending_payouts})"
    overdue_label = "⚠️ Внимание" if overdue_n == 0 else f"⚠️ Внимание ({overdue_n})"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_refresh")],
            [InlineKeyboardButton(text=overdue_label, callback_data="admin_overdue")],
            [
                InlineKeyboardButton(text="📦 Заказы", callback_data="admin_orders"),
                InlineKeyboardButton(text="🍽 Рестораны", callback_data="admin_restaurants"),
            ],
            [
                InlineKeyboardButton(text="🛵 Курьеры", callback_data="admin_couriers"),
                InlineKeyboardButton(text=payout_label, callback_data="admin_payouts"),
            ],
        ]
    )


def kb_orders(filter_key: str, page: int, total: int, items: list[dict]) -> InlineKeyboardMarkup:
    pages = max(1, (total + ADMIN_ORDERS_PAGE - 1) // ADMIN_ORDERS_PAGE)
    page = max(0, min(page, pages - 1))
    n_active = _count_orders("active")
    n_done = _count_orders("done")
    n_all = _count_orders("all")

    def _flt(key: str, label: str, n: int) -> InlineKeyboardButton:
        mark = "• " if filter_key == key else ""
        return InlineKeyboardButton(
            text=f"{mark}{label} {n}",
            callback_data=f"admin_orders_f_{key}_0",
        )

    filters = [
        _flt("active", "Акт.", n_active),
        _flt("done", "Готово", n_done),
        _flt("all", "Все", n_all),
    ]
    rows: list[list[InlineKeyboardButton]] = [filters]

    # Тапы по заказам текущей страницы (по 2 в ряд)
    pair: list[InlineKeyboardButton] = []
    for it in items:
        warn = "⚠" if it.get("overdue") else "#"
        pair.append(
            InlineKeyboardButton(
                text=f"{warn}{it['id']}",
                callback_data=f"admin_order_{it['id']}",
            )
        )
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀️", callback_data=f"admin_orders_f_{filter_key}_{page - 1}")
        )
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="admin_noop"))
    if page < pages - 1:
        nav.append(
            InlineKeyboardButton(text="▶️", callback_data=f"admin_orders_f_{filter_key}_{page + 1}")
        )
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="admin_back_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_order_card(
    order_id: int,
    filter_key: str = "active",
    page: int = 0,
    *,
    restaurant_tg: int = 0,
    courier_tg: int = 0,
    phone: str = "",
    status: str = "",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    st = (status or "").lower()
    active = st not in ("delivered", "cancelled", "canceled")
    if active:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📣 Пинг",
                    callback_data=f"admin_oc_ping_{order_id}_{filter_key}_{page}",
                ),
                InlineKeyboardButton(
                    text="📡 Реброадкаст",
                    callback_data=f"admin_oc_rebcast_{order_id}_{filter_key}_{page}",
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"admin_oc_cancel_{order_id}_{filter_key}_{page}",
                )
            ]
        )
    links = []
    if restaurant_tg > 0:
        links.append(
            InlineKeyboardButton(text="🍽 Чат", url=f"tg://user?id={restaurant_tg}")
        )
    if courier_tg > 0:
        links.append(
            InlineKeyboardButton(text="🛵 Чат", url=f"tg://user?id={courier_tg}")
        )
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if digits and len(digits) >= 9:
        links.append(
            InlineKeyboardButton(text="📞 Клиент", url=f"tg://resolve?phone={digits}")
        )
    if links:
        rows.append(links[:3])
    rows.append(
        [
            InlineKeyboardButton(
                text="← К заказам",
                callback_data=f"admin_orders_f_{filter_key}_{page}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_restaurants(items: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for r in items[:40]:
        mark = "🟢" if r["is_open"] else "🔴"
        act = r.get("active_orders") or 0
        suffix = f" · {act}" if act else ""
        label = f"{mark} {r['name']}{suffix}"
        if len(label) > 60:
            label = label[:57] + "…"
        cb = f"admin_restaurant_{r['id']}"
        if len(cb.encode("utf-8")) > 64:
            log.warning("skip restaurant button, callback too long: %s", r["id"])
            continue
        rows.append([InlineKeyboardButton(text=label, callback_data=cb)])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="admin_back_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_restaurant_card(restaurant_id: str, *, is_open: bool = True, partner_tg: int = 0) -> InlineKeyboardMarkup:
    rid = restaurant_id
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🔴 Закрыть" if is_open else "🟢 Открыть",
                callback_data=f"admin_rc_toggle_{rid}",
            )
        ],
        [
            InlineKeyboardButton(text="✉️ Написать", callback_data=f"admin_msg_rest_{rid}"),
        ],
    ]
    if partner_tg > 0:
        rows[-1].append(
            InlineKeyboardButton(text="💬 Чат", url=f"tg://user?id={partner_tg}")
        )
    rows.append(
        [InlineKeyboardButton(text="← К списку ресторанов", callback_data="admin_back_restaurants")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_couriers(items: list[dict], *, online_only: bool = False) -> InlineKeyboardMarkup:
    rows = []
    shown = items
    if online_only:
        shown = [c for c in items if c.get("is_online")]
    for c in shown[:40]:
        mark = "🟢" if c["is_online"] else "🔴"
        act = c.get("active_order")
        suffix = f" · #{act['id']}" if act else ""
        label = f"{mark} {c['name']}{suffix}"
        if len(label) > 60:
            label = label[:57] + "…"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"admin_courier_{c['telegram_id']}")]
        )
    filt = "online" if online_only else "all"
    other = "all" if online_only else "online"
    other_label = "Все" if online_only else "Только online"
    rows.append(
        [
            InlineKeyboardButton(
                text=f"Фильтр: {other_label}",
                callback_data=f"admin_couriers_f_{other}",
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="admin_back_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_courier_card(telegram_id: int, *, is_online: bool = False, blocked: bool = False) -> InlineKeyboardMarkup:
    tg = int(telegram_id)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="✉️ Написать", callback_data=f"admin_msg_cour_{tg}"),
            InlineKeyboardButton(text="💬 Чат", url=f"tg://user?id={tg}"),
        ],
    ]
    if is_online:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⏹ Снять с линии",
                    callback_data=f"admin_cc_offline_{tg}",
                )
            ]
        )
    if blocked:
        rows.append(
            [InlineKeyboardButton(text="✅ Снять блок", callback_data=f"admin_cc_unblock_{tg}")]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(text="🚫 1ч", callback_data=f"admin_cc_block_{tg}_1"),
                InlineKeyboardButton(text="🚫 24ч", callback_data=f"admin_cc_block_{tg}_24"),
                InlineKeyboardButton(text="🚫 7д", callback_data=f"admin_cc_block_{tg}_168"),
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="← К списку курьеров", callback_data="admin_back_couriers")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_confirm(action: str, back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_yes_{action}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=back_cb),
            ]
        ]
    )


async def build_home_text() -> tuple[str, int]:
    db = _db()
    stats = await db.get_stats()
    platform_today = await db.get_platform_today_income()
    platform_lifetime = await db.get_platform_lifetime_income()
    online_ids = await db.get_online_courier_ids()
    online_lines = []
    for tg_id in online_ids:
        user = await db.get_bot_user(tg_id)
        name = (user or {}).get("backend_username", f"id:{tg_id}")
        online_lines.append(f"  • {html.escape(str(name))}")
    online_str = "\n".join(online_lines) if online_lines else "  — нет —"
    now = datetime.now().strftime("%H:%M:%S")
    E = _E()
    active_n = await asyncio.to_thread(_count_orders, "active")
    overdue_n = await asyncio.to_thread(_count_overdue_active)
    pending_payouts = 0
    try:
        reqs = await db.get_pending_payout_requests()
        pending_payouts = len(reqs or [])
    except Exception:
        pass

    overdue_line = (
        f"Просрочки SLA: <b>{overdue_n}</b>\n"
        if overdue_n
        else "Просрочек SLA нет\n"
    )
    text = (
        f'{_ce(E["dashboard"], "🛡")} <b>Панель администратора MestiDelivery</b>\n'
        f"Обновлено: {now}\n\n"
        f'{_ce(E["balance"], "💰")} <b>Баланс сервиса</b>\n'
        f"Сегодня: <b>{_fmt_money(platform_today)} ₾</b>\n"
        f"Всего: <b>{_fmt_money(platform_lifetime)} ₾</b>\n"
        f"<i>15% от позиций + сервисный сбор</i>\n\n"
        f'{_ce(E["btn_orders"], "📦")} <b>Заказы</b>\n'
        f"Активных: <b>{active_n}</b>\n"
        f"{overdue_line}\n"
        f'{_ce(E["courier"], "🛵")} <b>Курьеры</b>\n'
        f"Всего: <b>{stats['couriers_total']}</b> · "
        f"на линии: <b>{stats['couriers_online']}</b> · "
        f"офлайн: <b>{stats['couriers_total'] - stats['couriers_online']}</b>\n"
        f"Онлайн:\n{online_str}\n\n"
        f'{_ce(E["restaurateur"], "🍽")} <b>Рестораны-партнёры:</b> <b>{stats["restaurants_total"]}</b>'
    )
    return _clip(text), pending_payouts


def build_orders_text(filter_key: str, page: int) -> tuple[str, InlineKeyboardMarkup]:
    items, total = _query_orders(filter_key, page)
    titles = {"active": "Активные", "done": "Выполненные", "all": "Все"}
    E = _E()
    lines = [
        f'{_ce(E["btn_orders"], "📦")} <b>Заказы — {titles.get(filter_key, filter_key)}</b>',
        f"Всего в выборке: <b>{total}</b> · стр. кнопок ниже",
        "",
    ]
    if not items:
        lines.append("Нет заказов в этой выборке.")
    else:
        for it in items:
            flag = f" · {_overdue_label(it['overdue'])}" if it["overdue"] else ""
            addr = html.escape(it["address"])
            if len(addr) > 42:
                addr = addr[:39] + "…"
            rest = html.escape(it["restaurant"])
            lines.append(
                f"<b>#{it['id']}</b>{flag}\n"
                f"{_status_label(it['status'])} · {_fmt_money(it['total'])} ₾\n"
                f"{rest} → {addr}\n"
                f"Курьер: {html.escape(str(it['courier']))}"
            )
            lines.append("")
    return _clip("\n".join(lines).rstrip()), kb_orders(filter_key, page, total, items)


def build_order_card_text(
    order_id: int,
    *,
    filter_key: str = "active",
    page: int = 0,
    restaurant_tg: int = 0,
    courier_tg: int = 0,
) -> tuple[str, InlineKeyboardMarkup]:
    o = _query_order_card(order_id)
    E = _E()
    if not o:
        return (
            f'{_ce(E["btn_orders"], "📦")} Заказ <b>#{order_id}</b> не найден.',
            kb_order_card(order_id, filter_key, page),
        )
    created = html.escape(str(o.get("created_at") or "—"))
    lines = [
        f'{_ce(E["btn_orders"], "📦")} <b>Заказ #{o["id"]}</b>',
        f"Статус: <b>{_status_label(o['status'])}</b>"
        + (f" · {_overdue_label(o['overdue'])}" if o["overdue"] else ""),
        f"Создан: {created}",
        "",
        f'{_ce(E["restaurateur"], "🍽")} <b>{html.escape(o["restaurant"])}</b>',
        f"Адрес: {html.escape(o['address'])}",
        f"Клиент: {html.escape(str(o['customer_name']))} · {html.escape(str(o['phone']))}",
        f"Оплата: {html.escape(str(o['payment_method']))}",
        "",
        f'{_ce(E["balance"], "💰")} Итого: <b>{_fmt_money(o["total"])} ₾</b>',
        f"Доставка: {_fmt_money(o['delivery_fee'])} · сервис: {_fmt_money(o['service_fee'])} · "
        f"чаевые: {_fmt_money(o['tips'])}",
        "",
        f'{_ce(E["courier"], "🛵")} Курьер: <b>{html.escape(str(o["courier"]))}</b>',
    ]
    if o.get("courier_taken_at"):
        lines.append(f"Взял: {html.escape(str(o['courier_taken_at']))}")
    if o.get("comment"):
        lines += ["", f"Комментарий: {html.escape(o['comment'][:200])}"]
    return _clip("\n".join(lines)), kb_order_card(
        order_id,
        filter_key,
        page,
        restaurant_tg=restaurant_tg,
        courier_tg=courier_tg,
        phone=str(o.get("phone") or ""),
        status=str(o.get("status") or ""),
    )


def build_restaurants_text() -> tuple[str, InlineKeyboardMarkup]:
    items = _query_restaurants()
    E = _E()
    open_n = sum(1 for r in items if r["is_open"])
    lines = [
        f'{_ce(E["restaurateur"], "🍽")} <b>Рестораны</b>',
        f"Всего: <b>{len(items)}</b> · открыто: <b>{open_n}</b>",
        "",
        "Выберите ресторан:",
    ]
    return "\n".join(lines), kb_restaurants(items)


def build_restaurant_card_text(
    restaurant_id: str, *, partner_tg: int = 0
) -> tuple[str, InlineKeyboardMarkup]:
    c = _query_restaurant_card(restaurant_id)
    E = _E()
    st = "открыт" if c.get("is_open") else "закрыт"
    lines = [
        f'{_ce(E["restaurateur"], "🍽")} <b>{html.escape(c.get("name") or restaurant_id)}</b>',
        f"Статус: <b>{st}</b> · рейтинг: <b>{html.escape(str(c.get('rating') or '—'))}</b>",
        f"ID: <code>{html.escape(restaurant_id)}</code>",
        "",
        f'{_ce(E["income_today"], "📈")} <b>Сегодня:</b> заказов {c.get("today_count", 0)}, '
        f"сумма {_fmt_money(c.get('today_sum', 0))} ₾",
        "",
        f"<b>Активные заказы ({len(c.get('active_list') or [])}):</b>",
    ]
    active = c.get("active_list") or []
    if not active:
        lines.append("— нет —")
    else:
        for o in active:
            lines.append(
                f"#{o['id']} · {_fmt_money(o['total'])} ₾ · {_status_label(o['status'])}"
            )
    return "\n".join(lines), kb_restaurant_card(
        restaurant_id, is_open=bool(c.get("is_open")), partner_tg=partner_tg
    )


def build_couriers_text(*, online_only: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    items = _query_couriers()
    E = _E()
    online = sum(1 for c in items if c["is_online"])
    title = "Курьеры (online)" if online_only else "Курьеры"
    lines = [
        f'{_ce(E["courier"], "🛵")} <b>{title}</b>',
        f"Всего: <b>{len(items)}</b> · на линии: <b>{online}</b>",
        "",
        "Выберите курьера:",
    ]
    return "\n".join(lines), kb_couriers(items, online_only=online_only)


def build_courier_card_text(
    telegram_id: int, *, block: Optional[dict] = None
) -> tuple[str, InlineKeyboardMarkup]:
    c = _query_courier_card(telegram_id)
    E = _E()
    st = "на линии" if c.get("is_online") else "офлайн"
    lines = [
        f'{_ce(E["courier"], "🛵")} <b>{html.escape(str(c.get("name") or telegram_id))}</b>',
        f"TG: <code>{telegram_id}</code>",
        f"Статус: <b>{st}</b>",
    ]
    if block:
        until_hm = datetime.fromtimestamp(float(block["until_ts"])).strftime("%d.%m %H:%M")
        lines.append(f"⛔ <b>Блок до {until_hm}</b> · {html.escape(str(block.get('reason') or ''))}")
    lines.append("")
    act = c.get("active_order")
    if act:
        lines.append(
            f"<b>Текущая доставка:</b> #{act['id']} · {_status_label(act['status'])} · "
            f"{_fmt_money(act['total'])} ₾\n{html.escape(str(act.get('address') or '—'))}"
        )
    else:
        lines.append("<b>Текущая доставка:</b> — нет —")
    lines += [
        "",
        f'{_ce(E["income_today"], "📈")} <b>Сегодня:</b> доставок {c.get("today_count", 0)}, '
        f"доход {_fmt_money(c.get('today_income', 0))} ₾",
    ]
    hist = c.get("history") or []
    if hist:
        lines.append("")
        lines.append("<b>История сегодня:</b>")
        for h in hist[:8]:
            lines.append(
                f"#{h['id']} · {_status_label(h['status'])} · доход {_fmt_money(h['earn'])} ₾"
            )
    return "\n".join(lines), kb_courier_card(
        telegram_id,
        is_online=bool(c.get("is_online")),
        blocked=bool(block),
    )


# ── message edit helper / state ──────────────────────────────


async def _save_panel_message(chat_id: int, message_id: int) -> None:
    db = _db()
    try:
        await db._db.execute(
            """
            INSERT INTO admin_panel_state (chat_id, message_id, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(chat_id) DO UPDATE SET
              message_id = excluded.message_id,
              updated_at = excluded.updated_at
            """,
            (chat_id, message_id),
        )
        await db._db.commit()
    except Exception as e:
        log.warning("save admin panel state: %s", e)


async def _get_panel_message_id(chat_id: int) -> Optional[int]:
    db = _db()
    try:
        async with db._db.execute(
            "SELECT message_id FROM admin_panel_state WHERE chat_id = ?",
            (chat_id,),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else None
    except Exception:
        return None


async def render_admin(
    chat_id: int,
    *,
    message_id: Optional[int],
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> int:
    bot = _bot()
    text = _clip(text)
    target_id = message_id
    if target_id is None:
        target_id = await _get_panel_message_id(chat_id)

    if target_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=target_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            await _save_panel_message(chat_id, target_id)
            return target_id
        except Exception as e:
            err = str(e).lower()
            if "message is not modified" in err:
                return target_id
            log.warning("admin edit failed (%s) — send new", e)

    msg = await bot.send_message(
        chat_id,
        text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await _save_panel_message(chat_id, msg.message_id)
    return msg.message_id


async def open_home(chat_id: int, message_id: Optional[int] = None) -> None:
    text, pending = await build_home_text()
    overdue_n = await asyncio.to_thread(_count_overdue_active)
    await render_admin(
        chat_id,
        message_id=message_id,
        text=text,
        keyboard=kb_home(pending_payouts=pending, overdue_n=overdue_n),
    )


def build_overdue_text() -> tuple[str, InlineKeyboardMarkup]:
    items = _scan_sla_candidates()
    # unique orders
    by_id: dict[int, dict] = {}
    for it in items:
        oid = int(it["order_id"])
        if oid not in by_id:
            by_id[oid] = it
            by_id[oid]["flags"] = [it["type"]]
        else:
            by_id[oid]["flags"].append(it["type"])
    E = _E()
    lines = [
        f'{_ce(E["profile_setup"], "⚠️")} <b>Нужно внимание</b>',
        f"Просроченных заказов: <b>{len(by_id)}</b>",
        "",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    if not by_id:
        lines.append("Сейчас всё спокойно.")
    else:
        for oid, it in sorted(by_id.items(), key=lambda x: -x[0])[:30]:
            flags = _overdue_label(it.get("flags") or [it["type"]])
            lines.append(
                f"<b>#{oid}</b> {flags}\n"
                f"{html.escape(str(it.get('restaurant') or '—'))} · "
                f"{_status_label(it.get('status') or '')}"
            )
            rows.append(
                [InlineKeyboardButton(text=f"#{oid}", callback_data=f"admin_order_{oid}")]
            )
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="admin_back_home")])
    return _clip("\n".join(lines)), InlineKeyboardMarkup(inline_keyboard=rows)


async def _resolve_restaurant_tg(restaurant_id: str) -> int:
    rid = str(restaurant_id or "").strip()
    if not rid:
        return 0
    try:
        partner = await _db().get_partner_by_restaurant(rid)
        return int((partner or {}).get("telegram_id") or 0)
    except Exception as e:
        log.warning("resolve restaurant tg: %s", e)
        return 0


def _resolve_courier_tg(backend_courier_id: int) -> int:
    cid = int(backend_courier_id or 0)
    if cid <= 0:
        return 0
    for path in _auth_paths():
        if not os.path.exists(path):
            continue
        try:
            conn = _connect(path)
            row = conn.execute(
                "SELECT telegram_id FROM admin_users WHERE id = ? AND role = 'courier'",
                (cid,),
            ).fetchone()
            conn.close()
            if row and row["telegram_id"]:
                return int(row["telegram_id"])
        except Exception as e:
            log.warning("resolve courier tg: %s", e)
    return 0


async def open_order_card(
    chat_id: int,
    message_id: Optional[int],
    order_id: int,
    *,
    filter_key: str = "active",
    page: int = 0,
) -> None:
    o = _query_order_card(order_id) or {}
    rest_tg = await _resolve_restaurant_tg(str(o.get("restaurant_id") or ""))
    cour_tg = _resolve_courier_tg(int(o.get("courier_id") or 0))
    text, kb = build_order_card_text(
        order_id,
        filter_key=filter_key,
        page=page,
        restaurant_tg=rest_tg,
        courier_tg=cour_tg,
    )
    await render_admin(chat_id, message_id=message_id, text=text, keyboard=kb)


async def open_courier_card(
    chat_id: int, message_id: Optional[int], telegram_id: int
) -> None:
    block = None
    getter = _ops().get("get_courier_block")
    if getter:
        try:
            block = await getter(int(telegram_id))
        except Exception as e:
            log.warning("get_courier_block: %s", e)
    text, kb = build_courier_card_text(int(telegram_id), block=block)
    await render_admin(chat_id, message_id=message_id, text=text, keyboard=kb)


async def open_restaurant_card(
    chat_id: int, message_id: Optional[int], restaurant_id: str
) -> None:
    partner_tg = await _resolve_restaurant_tg(restaurant_id)
    text, kb = build_restaurant_card_text(restaurant_id, partner_tg=partner_tg)
    await render_admin(chat_id, message_id=message_id, text=text, keyboard=kb)


def register_admin_handlers(
    router: Router,
    *,
    get_db: Callable,
    get_bot: Callable,
    admin_tg_id: int,
    order_db_paths: list[str],
    catalog_db_paths: list[str],
    auth_db_paths: list[str],
    partners_db_path: str,
    emoji: dict,
    open_payouts: Optional[Callable] = None,
    is_super_admin: Optional[Callable] = None,
    ops: Optional[dict] = None,
) -> None:
    _deps.update(
        {
            "get_db": get_db,
            "get_bot": get_bot,
            "admin_tg_id": admin_tg_id,
            "order_db_paths": order_db_paths,
            "catalog_db_paths": catalog_db_paths,
            "auth_db_paths": auth_db_paths,
            "partners_db_path": partners_db_path,
            "emoji": emoji,
            "open_payouts": open_payouts,
            "is_super_admin": is_super_admin,
            "ops": ops or {},
        }
    )

    @router.message(Command("admin"))
    async def cmd_admin(message: Message, state: FSMContext):
        if not await _is_admin_async(message.from_user.id):
            return
        await state.clear()
        mid = await _get_panel_message_id(message.chat.id)
        await open_home(message.chat.id, message_id=mid)
        try:
            await message.delete()
        except Exception:
            pass

    @router.callback_query(F.data == "admin_noop")
    async def on_noop(callback: CallbackQuery):
        await callback.answer()

    @router.callback_query(F.data.in_({"admin_refresh", "admin_back_home"}))
    async def on_home(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        await state.clear()
        await open_home(callback.message.chat.id, callback.message.message_id)
        await callback.answer("Обновлено" if callback.data == "admin_refresh" else "")

    @router.callback_query(F.data == "admin_overdue")
    async def on_overdue(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        await state.clear()
        text, kb = build_overdue_text()
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text=text,
            keyboard=kb,
        )
        await callback.answer()

    @router.callback_query(F.data == "admin_orders")
    async def on_orders(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        await state.clear()
        text, kb = build_orders_text("active", 0)
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text=text,
            keyboard=kb,
        )
        await callback.answer()

    @router.callback_query(F.data.regexp(r"^admin_orders_f_(active|done|all)_(\d+)$"))
    async def on_orders_page(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        await state.clear()
        parts = callback.data.split("_")
        filter_key = parts[3]
        page = int(parts[4])
        text, kb = build_orders_text(filter_key, page)
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text=text,
            keyboard=kb,
        )
        await callback.answer()

    @router.callback_query(F.data.regexp(r"^admin_order_(\d+)$"))
    async def on_order_card(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        await state.clear()
        oid = int(callback.data.split("_")[-1])
        await open_order_card(
            callback.message.chat.id,
            callback.message.message_id,
            oid,
            filter_key="active",
            page=0,
        )
        await callback.answer()

    @router.callback_query(F.data.regexp(r"^admin_oc_ping_(\d+)_(active|done|all)_(\d+)$"))
    async def on_order_ping(callback: CallbackQuery):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        parts = callback.data.split("_")
        oid, filter_key, page = int(parts[3]), parts[4], int(parts[5])
        fn = _ops().get("ping_couriers")
        if not fn:
            await callback.answer("Недоступно", show_alert=True)
            return
        ok, msg = await fn(oid)
        await callback.answer(msg[:180], show_alert=True)
        await open_order_card(
            callback.message.chat.id,
            callback.message.message_id,
            oid,
            filter_key=filter_key,
            page=page,
        )

    @router.callback_query(F.data.regexp(r"^admin_oc_rebcast_(\d+)_(active|done|all)_(\d+)$"))
    async def on_order_rebcast(callback: CallbackQuery):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        parts = callback.data.split("_")
        oid, filter_key, page = int(parts[3]), parts[4], int(parts[5])
        fn = _ops().get("rebroadcast")
        if not fn:
            await callback.answer("Недоступно", show_alert=True)
            return
        ok, msg = await fn(oid)
        await callback.answer(msg[:180], show_alert=True)
        await open_order_card(
            callback.message.chat.id,
            callback.message.message_id,
            oid,
            filter_key=filter_key,
            page=page,
        )

    @router.callback_query(F.data.regexp(r"^admin_oc_cancel_(\d+)_(active|done|all)_(\d+)$"))
    async def on_order_cancel_ask(callback: CallbackQuery):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        parts = callback.data.split("_")
        oid, filter_key, page = int(parts[3]), parts[4], int(parts[5])
        action = f"oc_cancel_{oid}_{filter_key}_{page}"
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text=f"❌ Отменить заказ <b>#{oid}</b>?",
            keyboard=kb_confirm(action, f"admin_order_{oid}"),
        )
        await callback.answer()

    @router.callback_query(F.data == "admin_payouts")
    async def on_payouts(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        await state.clear()
        open_payouts_fn = _deps.get("open_payouts")
        if not open_payouts_fn:
            await callback.answer("Выплаты недоступны", show_alert=True)
            return
        await open_payouts_fn(callback.message.chat.id, callback.message.message_id)
        await callback.answer()

    @router.callback_query(F.data == "admin_restaurants")
    @router.callback_query(F.data == "admin_back_restaurants")
    async def on_restaurants(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        await state.clear()
        text, kb = build_restaurants_text()
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text=text,
            keyboard=kb,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_restaurant_"))
    async def on_restaurant_card(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        if callback.data.startswith("admin_restaurants"):
            return
        await state.clear()
        rid = callback.data[len("admin_restaurant_") :]
        await open_restaurant_card(
            callback.message.chat.id, callback.message.message_id, rid
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_rc_toggle_"))
    async def on_restaurant_toggle_ask(callback: CallbackQuery):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        rid = callback.data[len("admin_rc_toggle_") :]
        card = _query_restaurant_card(rid)
        want_open = not bool(card.get("is_open"))
        verb = "открыть" if want_open else "закрыть"
        action = f"rc_open_{rid}" if want_open else f"rc_close_{rid}"
        name = html.escape(str(card.get("name") or rid))
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text=f"Подтвердите: <b>{verb}</b> ресторан\n{name}",
            keyboard=kb_confirm(action, f"admin_restaurant_{rid}"),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_msg_rest_"))
    async def on_msg_rest(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        rid = callback.data[len("admin_msg_rest_") :]
        partner_tg = await _resolve_restaurant_tg(rid)
        if partner_tg <= 0:
            await callback.answer("Партнёр не привязан", show_alert=True)
            return
        await state.set_state(AdminMessageState.waiting_text)
        await state.update_data(
            target_tg=partner_tg,
            back_cb=f"admin_restaurant_{rid}",
            kind="restaurant",
        )
        cancel_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_restaurant_{rid}")]
            ]
        )
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text="✉️ Введите сообщение партнёру ресторана:",
            keyboard=cancel_kb,
        )
        await callback.answer()

    @router.callback_query(F.data == "admin_couriers")
    @router.callback_query(F.data == "admin_back_couriers")
    async def on_couriers(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        await state.clear()
        text, kb = build_couriers_text(online_only=False)
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text=text,
            keyboard=kb,
        )
        await callback.answer()

    @router.callback_query(F.data.in_({"admin_couriers_f_online", "admin_couriers_f_all"}))
    async def on_couriers_filter(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        await state.clear()
        online_only = callback.data.endswith("_online")
        text, kb = build_couriers_text(online_only=online_only)
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text=text,
            keyboard=kb,
        )
        await callback.answer()

    @router.callback_query(F.data.regexp(r"^admin_courier_(\d+)$"))
    async def on_courier_card(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        await state.clear()
        tg = int(callback.data[len("admin_courier_") :])
        await open_courier_card(
            callback.message.chat.id, callback.message.message_id, tg
        )
        await callback.answer()

    @router.callback_query(F.data.regexp(r"^admin_msg_cour_(\d+)$"))
    async def on_msg_cour(callback: CallbackQuery, state: FSMContext):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        tg = int(callback.data.split("_")[-1])
        await state.set_state(AdminMessageState.waiting_text)
        await state.update_data(
            target_tg=tg, back_cb=f"admin_courier_{tg}", kind="courier"
        )
        cancel_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_courier_{tg}")]
            ]
        )
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text="✉️ Введите сообщение курьеру:",
            keyboard=cancel_kb,
        )
        await callback.answer()

    @router.callback_query(F.data.regexp(r"^admin_cc_offline_(\d+)$"))
    async def on_courier_offline_ask(callback: CallbackQuery):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        tg = int(callback.data.split("_")[-1])
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text=f"⏹ Снять курьера <code>{tg}</code> с линии?",
            keyboard=kb_confirm(f"cc_offline_{tg}", f"admin_courier_{tg}"),
        )
        await callback.answer()

    @router.callback_query(F.data.regexp(r"^admin_cc_block_(\d+)_(\d+)$"))
    async def on_courier_block_ask(callback: CallbackQuery):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        parts = callback.data.split("_")
        tg, hours = int(parts[3]), int(parts[4])
        label = {1: "1 час", 24: "24 часа", 168: "7 дней"}.get(hours, f"{hours}ч")
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text=f"🚫 Заблокировать курьера <code>{tg}</code> на <b>{label}</b>?",
            keyboard=kb_confirm(f"cc_block_{tg}_{hours}", f"admin_courier_{tg}"),
        )
        await callback.answer()

    @router.callback_query(F.data.regexp(r"^admin_cc_unblock_(\d+)$"))
    async def on_courier_unblock_ask(callback: CallbackQuery):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        tg = int(callback.data.split("_")[-1])
        await render_admin(
            callback.message.chat.id,
            message_id=callback.message.message_id,
            text=f"✅ Снять блок с курьера <code>{tg}</code>?",
            keyboard=kb_confirm(f"cc_unblock_{tg}", f"admin_courier_{tg}"),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_yes_"))
    async def on_confirm_yes(callback: CallbackQuery):
        if not await _is_admin_async(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        action = callback.data[len("admin_yes_") :]
        ops = _ops()
        chat_id = callback.message.chat.id
        mid = callback.message.message_id

        if action.startswith("oc_cancel_"):
            parts = action.split("_")
            oid, filter_key, page = int(parts[2]), parts[3], int(parts[4])
            fn = ops.get("cancel_order")
            if not fn:
                await callback.answer("Недоступно", show_alert=True)
                return
            ok, msg = await fn(oid)
            await callback.answer(msg[:180], show_alert=not ok)
            await open_order_card(chat_id, mid, oid, filter_key=filter_key, page=page)
            return

        if action.startswith("cc_offline_"):
            tg = int(action.split("_")[-1])
            fn = ops.get("force_offline")
            if not fn:
                await callback.answer("Недоступно", show_alert=True)
                return
            ok, msg = await fn(tg)
            await callback.answer(msg[:180], show_alert=not ok)
            await open_courier_card(chat_id, mid, tg)
            return

        if action.startswith("cc_block_"):
            parts = action.split("_")
            tg, hours = int(parts[2]), int(parts[3])
            fn = ops.get("block_courier")
            if not fn:
                await callback.answer("Недоступно", show_alert=True)
                return
            ok, msg = await fn(tg, hours, admin_id=callback.from_user.id)
            await callback.answer(msg[:180], show_alert=not ok)
            await open_courier_card(chat_id, mid, tg)
            return

        if action.startswith("cc_unblock_"):
            tg = int(action.split("_")[-1])
            fn = ops.get("unblock_courier")
            if not fn:
                await callback.answer("Недоступно", show_alert=True)
                return
            ok, msg = await fn(tg)
            await callback.answer(msg[:180], show_alert=not ok)
            await open_courier_card(chat_id, mid, tg)
            return

        if action.startswith("rc_open_") or action.startswith("rc_close_"):
            want_open = action.startswith("rc_open_")
            rid = action[len("rc_open_") if want_open else len("rc_close_") :]
            fn = ops.get("set_restaurant_open")
            if not fn:
                await callback.answer("Недоступно", show_alert=True)
                return
            ok, msg = await fn(rid, want_open)
            await callback.answer(msg[:180], show_alert=not ok)
            await open_restaurant_card(chat_id, mid, rid)
            return

        await callback.answer("Неизвестное действие", show_alert=True)

    @router.message(AdminMessageState.waiting_text)
    async def on_admin_message_text(message: Message, state: FSMContext):
        if not await _is_admin_async(message.from_user.id):
            return
        data = await state.get_data()
        target_tg = int(data.get("target_tg") or 0)
        back_cb = str(data.get("back_cb") or "admin_back_home")
        await state.clear()
        fn = _ops().get("send_message")
        if not fn or target_tg <= 0:
            await message.answer("Отправка недоступна")
            return
        ok, msg = await fn(target_tg, message.text or "")
        try:
            await message.delete()
        except Exception:
            pass
        panel_mid = await _get_panel_message_id(message.chat.id)
        if back_cb.startswith("admin_courier_"):
            tg = int(back_cb[len("admin_courier_") :])
            await open_courier_card(message.chat.id, panel_mid, tg)
        elif back_cb.startswith("admin_restaurant_"):
            rid = back_cb[len("admin_restaurant_") :]
            await open_restaurant_card(message.chat.id, panel_mid, rid)
        else:
            await open_home(message.chat.id, message_id=panel_mid)
        try:
            await _bot().send_message(
                message.chat.id,
                ("✅ " if ok else "⚠️ ") + msg,
            )
        except Exception:
            pass


# ── SLA alerts ───────────────────────────────────────────────


async def _alert_already_sent(order_id: int, alert_type: str) -> bool:
    db = _db()
    async with db._db.execute(
        "SELECT 1 FROM admin_sla_alerts WHERE order_id = ? AND alert_type = ?",
        (order_id, alert_type),
    ) as cur:
        return await cur.fetchone() is not None


async def _mark_alert_sent(order_id: int, alert_type: str) -> None:
    db = _db()
    await db._db.execute(
        "INSERT OR IGNORE INTO admin_sla_alerts (order_id, alert_type) VALUES (?, ?)",
        (order_id, alert_type),
    )
    await db._db.commit()


def _scan_sla_candidates() -> list[dict]:
    path = _first_existing(_order_paths())
    if not path:
        return []
    names = _load_restaurant_names()
    couriers = _load_courier_names()
    now = datetime.now(timezone.utc)
    conn = _connect(path)
    rows = conn.execute(
        f"""
        SELECT id, restaurant_id, status, total, address, courier_id,
               created_at, restaurant_confirmed_at, courier_taken_at
        FROM orders
        WHERE status IN ({",".join(repr(s) for s in ACTIVE_STATUSES)})
        ORDER BY id DESC
        LIMIT 200
        """
    ).fetchall()
    conn.close()

    out = []
    for r in rows:
        flags = _order_overdue_flags(r, now)
        for f in flags:
            cid = int(r["courier_id"] or 0)
            out.append(
                {
                    "order_id": int(r["id"]),
                    "type": f,
                    "restaurant": names.get(str(r["restaurant_id"] or ""), str(r["restaurant_id"] or "—")),
                    "courier": couriers.get(cid, "—") if cid else "—",
                    "total": float(r["total"] or 0),
                    "status": r["status"],
                    "address": (r["address"] or "—").strip(),
                }
            )
    return out


def _format_sla_alert(item: dict) -> str:
    E = _E()
    titles = {
        "accept": "Ресторан не принял заказ (~5 мин)",
        "assign": "Курьер не назначен (~5 мин)",
        "ready": "Заказ не готов к выдаче",
        "deliver": "Курьер не завершил доставку",
    }
    title = titles.get(item["type"], "Просрочка по заказу")
    who = (
        f"Ресторан: <b>{html.escape(item['restaurant'])}</b>"
        if item["type"] in ("accept", "ready", "assign")
        else f"Курьер: <b>{html.escape(str(item['courier']))}</b>"
    )
    return (
        f'{_ce(E["profile_setup"], "⚠️")} <b>{title}</b>\n'
        f"Заказ <b>#{item['order_id']}</b> · {_fmt_money(item['total'])} ₾ · {_status_label(item['status'])}\n"
        f"{who}\n"
        f"Адрес: {html.escape(item['address'][:80])}"
    )


async def sla_watch_loop(stop_event: asyncio.Event) -> None:
    log.info("Admin SLA watcher started (every %ss)", SLA_POLL_SEC)
    # небольшая пауза после старта
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=15)
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            candidates = await asyncio.to_thread(_scan_sla_candidates)
            for item in candidates:
                if await _alert_already_sent(item["order_id"], item["type"]):
                    continue
                text = _format_sla_alert(item)
                try:
                    oid = int(item["order_id"])
                    kb = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text=f"Открыть #{oid}",
                                    callback_data=f"admin_order_{oid}",
                                )
                            ]
                        ]
                    )
                    await _bot().send_message(
                        _admin_id(),
                        text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=kb,
                    )
                    await _mark_alert_sent(item["order_id"], item["type"])
                    log.info(
                        "SLA alert sent order=%s type=%s",
                        item["order_id"],
                        item["type"],
                    )
                except Exception as e:
                    log.warning("SLA send failed: %s", e)
        except Exception as e:
            log.error("SLA watcher error: %s", e)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SLA_POLL_SEC)
            break
        except asyncio.TimeoutError:
            continue

    log.info("Admin SLA watcher stopped")
