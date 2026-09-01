# -*- coding: utf-8 -*-
"""Patch get_main_inline_kb in bot.py to be role-aware."""

with open("bot.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_func_lines = [
    "\n",
    "MINIAPP_URL = \"https://t.me/MestiDelivery_Robot/partners\"\n",
    "SUPPORT_BOT_URL = \"https://t.me/MestiDelivery_Robot\"\n",
    "\n",
    "def get_main_inline_kb(lang: str, role: str = \"\") -> InlineKeyboardMarkup:\n",
    "    \"\"\"Role-aware inline navigation keyboard.\"\"\"\n",
    "    if lang == \"ru\":\n",
    "        lbl_profile  = \"\U0001f464 \u041f\u0440\u043e\u0444\u0438\u043b\u044c\"\n",
    "        lbl_orders   = \"\U0001f4e6 \u0417\u0430\u043a\u0430\u0437\u044b\"\n",
    "        lbl_history  = \"\U0001f4dc \u0418\u0441\u0442\u043e\u0440\u0438\u044f\"\n",
    "        lbl_stats    = \"\U0001f4ca \u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430\"\n",
    "        lbl_menu     = \"\U0001f374 \u041c\u0435\u043d\u044e\"\n",
    "        lbl_schedule = \"\U0001f4c5 \u0413\u0440\u0430\u0444\u0438\u043a \u0441\u043c\u0435\u043d\"\n",
    "        lbl_support  = \"\U0001f3a7 \u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430\"\n",
    "    elif lang == \"en\":\n",
    "        lbl_profile  = \"\U0001f464 Profile\"\n",
    "        lbl_orders   = \"\U0001f4e6 Orders\"\n",
    "        lbl_history  = \"\U0001f4dc History\"\n",
    "        lbl_stats    = \"\U0001f4ca Stats\"\n",
    "        lbl_menu     = \"\U0001f374 Menu\"\n",
    "        lbl_schedule = \"\U0001f4c5 Schedule\"\n",
    "        lbl_support  = \"\U0001f3a7 Support\"\n",
    "    else:\n",
    "        lbl_profile  = \"\U0001f464 \u10de\u10e0\u10dd\u10e4\u10d8\u10da\u10d8\"\n",
    "        lbl_orders   = \"\U0001f4e6 \u10e8\u10d4\u10d9\u10d5\u10d4\u10d7\u10d4\u10d1\u10d8\"\n",
    "        lbl_history  = \"\U0001f4dc \u10d8\u10e1\u10e2\u10dd\u10e0\u10d8\u10d0\"\n",
    "        lbl_stats    = \"\U0001f4ca \u10e1\u10e2\u10d0\u10e2\u10d8\u10e1\u10e2\u10d8\u10d9\u10d0\"\n",
    "        lbl_menu     = \"\U0001f374 \u10db\u10d4\u10dc\u10d8\u10e3\"\n",
    "        lbl_schedule = \"\U0001f4c5 \u10d2\u10d0\u10dc\u10e0\u10d8\u10d2\u10d8\"\n",
    "        lbl_support  = \"\U0001f3a7 \u10db\u10ee\u10d0\u10e0\u10d3\u10d0\u10ec\u10d4\u10e0\u10d0\"\n",
    "\n",
    "    if role == \"restaurant_admin\":\n",
    "        kb = [\n",
    "            [\n",
    "                InlineKeyboardButton(text=lbl_profile, callback_data=\"nav_profile\"),\n",
    "                InlineKeyboardButton(text=lbl_orders,  url=MINIAPP_URL),\n",
    "            ],\n",
    "            [\n",
    "                InlineKeyboardButton(text=lbl_stats,   url=MINIAPP_URL),\n",
    "                InlineKeyboardButton(text=lbl_history, url=MINIAPP_URL),\n",
    "            ],\n",
    "            [\n",
    "                InlineKeyboardButton(text=lbl_menu,    url=MINIAPP_URL),\n",
    "                InlineKeyboardButton(text=lbl_support, url=SUPPORT_BOT_URL),\n",
    "            ],\n",
    "        ]\n",
    "    else:\n",
    "        kb = [\n",
    "            [\n",
    "                InlineKeyboardButton(text=lbl_profile,  callback_data=\"nav_profile\"),\n",
    "                InlineKeyboardButton(text=lbl_orders,   url=MINIAPP_URL),\n",
    "            ],\n",
    "            [\n",
    "                InlineKeyboardButton(text=lbl_stats,    url=MINIAPP_URL),\n",
    "                InlineKeyboardButton(text=lbl_schedule, url=MINIAPP_URL),\n",
    "            ],\n",
    "            [\n",
    "                InlineKeyboardButton(text=lbl_support,  url=SUPPORT_BOT_URL),\n",
    "            ],\n",
    "        ]\n",
    "    return InlineKeyboardMarkup(inline_keyboard=kb)\n",
]

# Function is at lines 444-456 (1-indexed) => 0-indexed 443-455
new_lines = lines[:443] + new_func_lines + lines[456:]

with open("bot.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
print("Done! New total lines:", len(new_lines))
