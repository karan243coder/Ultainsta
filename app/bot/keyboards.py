from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 System Stats", callback_data="admin_stats"), InlineKeyboardButton(text="🏥 Server Health", callback_data="admin_health")],
        [InlineKeyboardButton(text="📡 Manage API Nodes", callback_data="admin_nodes"), InlineKeyboardButton(text="🔄 Auto-Monitor", callback_data="admin_monitors")],
        [InlineKeyboardButton(text="🚫 Ban Help", callback_data="admin_banhelp"), InlineKeyboardButton(text="❌ Close", callback_data="admin_close")],
    ])


def api_nodes_menu(nodes: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="➕ Add API Node", callback_data="api_add_prompt")]]
    for i, node in enumerate(nodes):
        short = node.replace("https://", "").replace("http://", "")[:32]
        rows.append([InlineKeyboardButton(text=f"🗑️ Delete #{i+1}: {short}", callback_data=f"api_delete:{i}")])
    rows.append([InlineKeyboardButton(text="↩️ Back", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def monitor_menu(prefix: str = "user_mon") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 List", callback_data=f"{prefix}_list"), InlineKeyboardButton(text="➕ Add Profile", callback_data=f"{prefix}_add")],
        [InlineKeyboardButton(text="❌ Remove Profile", callback_data=f"{prefix}_del"), InlineKeyboardButton(text="↩️ Back", callback_data="admin_main" if prefix == "admin_mon" else f"{prefix}_main")],
    ])


def monitor_delete_menu(monitors: list[dict], prefix: str = "user_mon") -> InlineKeyboardMarkup:
    rows = []
    for m in monitors:
        uname = m.get("username") or m.get("_id", "")
        rows.append([InlineKeyboardButton(text=f"🗑️ Stop @{uname}", callback_data=f"{prefix}_remove:{uname}")])
    rows.append([InlineKeyboardButton(text="↩️ Back", callback_data=f"{prefix}_main" if prefix == "user_mon" else "admin_monitors")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_menu(username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ HD DP", callback_data=f"profile_dp:{username}"), InlineKeyboardButton(text="🌌 Stories", callback_data=f"profile_stories:{username}")],
        [InlineKeyboardButton(text="🎬 Reels", callback_data=f"profile_reels:{username}"), InlineKeyboardButton(text="📁 Posts", callback_data=f"profile_posts:{username}")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data=f"profile_cancel:{username}")],
    ])
