from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 System Stats", callback_data="admin_stats"), InlineKeyboardButton(text="🏥 Server Health", callback_data="admin_health")],
        [InlineKeyboardButton(text="📡 API Nodes", callback_data="admin_nodes"), InlineKeyboardButton(text="🚫 Ban Help", callback_data="admin_banhelp")],
        [InlineKeyboardButton(text="❌ Close", callback_data="admin_close")],
    ])


def profile_menu(username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ HD DP", callback_data=f"profile_dp:{username}"), InlineKeyboardButton(text="🌌 Stories", callback_data=f"profile_stories:{username}")],
        [InlineKeyboardButton(text="🎬 Reels", callback_data=f"profile_reels:{username}"), InlineKeyboardButton(text="📁 Posts", callback_data=f"profile_posts:{username}")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data=f"profile_cancel:{username}")],
    ])
