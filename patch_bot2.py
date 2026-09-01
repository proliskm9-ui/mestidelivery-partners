# -*- coding: utf-8 -*-
"""Patch 2: Update callers of get_main_inline_kb to pass role, and fix nav_profile handler."""

with open("bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Fix cmd_start caller (line 558 area): pass role=role
content = content.replace(
    "            keyboard=get_main_inline_kb(lang),\n"
    "            caption=caption,\n"
    "        )\n"
    "        return\n",
    "            keyboard=get_main_inline_kb(lang, role=role),\n"
    "            caption=caption,\n"
    "        )\n"
    "        return\n",
    1
)

# 2. Fix process_password caller (line 687 area): pass role=role
content = content.replace(
    "            keyboard=get_main_inline_kb(language),\n"
    "            caption=caption,\n"
    "        )\n"
    "        await state.clear()\n",
    "            keyboard=get_main_inline_kb(language, role=role),\n"
    "            caption=caption,\n"
    "        )\n"
    "        await state.clear()\n",
    1
)

# 3. Fix process_nav handler at the bottom - replace with real profile handler
old_nav = """@router.callback_query(F.data.startswith('nav_'))
async def process_nav(callback: CallbackQuery, state: FSMContext):
    await callback.answer('\u23f3 \u0420\u0430\u0437\u0434\u0435\u043b \u0432 \u0440\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u043a\u0435', show_alert=True)"""

new_nav = """@router.callback_query(F.data == "nav_profile")
async def nav_profile(callback: CallbackQuery):
    \"\"\"Show profile banner when user taps Profile button.\"\"\"
    await callback.answer()
    tg = callback.from_user.id
    user = await db.get_bot_user(tg) or {}
    role = user.get("role", "")

    if role == "restaurant_admin":
        partner = (
            await db.get_partner_by_telegram(callback.message.chat.id)
            or await db.get_partner_by_telegram(tg)
            or {}
        )
        name = partner.get("restaurant_name") or partner.get("restaurant_id") or "Restaurant"
        lang = user.get("language", "ru")
        if lang == "ru":
            cap = f"\U0001f464 <b>\u0412\u0430\u0448 \u043f\u0440\u043e\u0444\u0438\u043b\u044c</b>\\n\U0001f3ea <b>{name}</b>\\n\\n\U0001f4ca \u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430 \u0438 \u0434\u0430\u043d\u043d\u044b\u0435 \u0432\u0430\u0448\u0435\u0433\u043e \u0440\u0435\u0441\u0442\u043e\u0440\u0430\u043d\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b \u0432 \u043f\u0430\u043d\u0435\u043b\u0438 \u043f\u0430\u0440\u0442\u043d\u0451\u0440\u0430."
        elif lang == "en":
            cap = f"\U0001f464 <b>Your profile</b>\\n\U0001f3ea <b>{name}</b>\\n\\n\U0001f4ca Statistics and settings are available in the partner dashboard."
        else:
            cap = f"\U0001f464 <b>\u10d7\u10e5\u10d5\u10d4\u10dc\u10d8 \u10de\u10e0\u10dd\u10e4\u10d8\u10da\u10d8</b>\\n\U0001f3ea <b>{name}</b>"
        await send_banner_photo(
            callback.message.chat.id, "profile_restaurant",
            {"restaurant_name": name, "rating": "4.9", "status_badge": "open", "active_orders": "0", "payout": "0"},
            caption=cap,
        )
    else:
        name = callback.from_user.first_name or "Courier"
        lang = user.get("language", "ru")
        if lang == "ru":
            cap = f"\U0001f464 <b>\u0412\u0430\u0448 \u043f\u0440\u043e\u0444\u0438\u043b\u044c</b>\\n\U0001f69a <b>{name}</b>\\n\\n\U0001f4ca \u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0434\u043e\u0441\u0442\u0430\u0432\u043e\u043a \u0438 \u0437\u0430\u0440\u0430\u0431\u043e\u0442\u043e\u043a \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b \u0432 \u043f\u0430\u043d\u0435\u043b\u0438 \u043f\u0430\u0440\u0442\u043d\u0451\u0440\u0430."
        elif lang == "en":
            cap = f"\U0001f464 <b>Your profile</b>\\n\U0001f69a <b>{name}</b>\\n\\n\U0001f4ca Delivery history and earnings are available in the partner dashboard."
        else:
            cap = f"\U0001f464 <b>\u10d7\u10e5\u10d5\u10d4\u10dc\u10d8 \u10de\u10e0\u10dd\u10e4\u10d8\u10da\u10d8</b>\\n\U0001f69a <b>{name}</b>"
        await send_banner_photo(
            callback.message.chat.id, "profile_courier",
            {"courier_name": name, "rating": "5.0", "status_badge": "online", "deliveries_count": "0", "earnings": "0"},
            caption=cap,
        )"""

if old_nav in content:
    content = content.replace(old_nav, new_nav, 1)
    print("✅ Fixed process_nav -> nav_profile handler")
else:
    print("❌ old_nav not found, trying partial match...")
    idx = content.find("@router.callback_query(F.data.startswith('nav_'))")
    if idx != -1:
        end_idx = content.find("\n\n", idx + 50)
        print(f"Found at {idx}, snippet: {repr(content[idx:idx+150])}")

with open("bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Patch 2 done")
