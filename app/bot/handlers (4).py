from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from app.db import db
from app.services.jobs import job_manager
from app.services.monitor import add_monitor as add_profile_monitor
from app.services.nodes import node_manager
from app.bot.keyboards import admin_menu, profile_menu, api_nodes_menu, monitor_menu, monitor_delete_menu
from app.utils.instagram import is_instagram_media_link, extract_profile_username, h

router = Router()
PENDING_ACTIONS: dict[int, str] = {}


async def safe_edit(message, text: str, reply_markup=None, parse_mode: str = "HTML"):
    try:
        return await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return None
        raise


def monitor_title(prefix: str) -> str:
    if prefix == "admin_mon":
        return "🔄 <b>Admin Auto-Monitor Management</b>\n\nYahan se kisi bhi profile ko add/remove/list kar sakte ho."
    return "🔄 <b>SaveGr Profile Auto-Monitor Center</b>\n\nNormal users max 5 profiles monitor kar sakte hain."


def monitor_username(mon: dict) -> str:
    raw = mon.get("username") or str(mon.get("_id", "")).split(":")[-1]
    return str(raw).replace("@", "").strip().lower()


async def safe_answer(call: CallbackQuery, text: str | None = None, show_alert: bool = False):
    try:
        await call.answer(text, show_alert=show_alert)
    except Exception:
        pass


@router.message(Command("start"))
async def start(message: Message):
    if db.is_banned(message.from_user.id):
        await message.answer("❌ Aap banned ho.")
        return
    db.register_user(message.from_user)
    await message.answer(
        "⚡ <b>Hey! I am SaveGr Premium Downloader Bot.</b>\n\n"
        "Public Instagram Reel, Photo, Video, Carousel, Story link bhejo.\n"
        "Admin username/profile bhejkar DP/Stories/Reels/Posts bhi fetch kar sakta hai.\n\n"
        "✨ Private accounts supported nahi hain.",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "📖 <b>Help Guide</b>\n\n"
        "1️⃣ Instagram public link copy karo.\n"
        "2️⃣ Yahan paste karo.\n"
        "3️⃣ Normal users queue me manage honge; admins VIP priority me chalenge.\n\n"
        "Commands: /start /help /admin /monitor /ban /unban",
        parse_mode="HTML",
    )


@router.message(Command("monitor"))
async def monitor_cmd(message: Message):
    if db.is_banned(message.from_user.id):
        return
    await message.answer(monitor_title("user_mon"), reply_markup=monitor_menu("user_mon"), parse_mode="HTML")


@router.message(Command("admin"))
async def admin(message: Message):
    if not db.is_admin(message.from_user.id):
        await message.answer("❌ Access Denied! Admin only.")
        return
    await message.answer("⚙️ <b>SaveGr Ultra Bot - Admin Control Panel</b>", reply_markup=admin_menu(), parse_mode="HTML")


@router.message(Command("ban"))
async def ban_cmd(message: Message):
    if not db.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /ban user_id")
        return
    try:
        db.ban(int(parts[1]), message.from_user.id)
        await message.answer(f"✅ User <code>{h(parts[1])}</code> banned.", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Error: {h(e)}", parse_mode="HTML")


@router.message(Command("unban"))
async def unban_cmd(message: Message):
    if not db.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /unban user_id")
        return
    try:
        db.unban(int(parts[1]))
        await message.answer(f"✅ User <code>{h(parts[1])}</code> unbanned.", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Error: {h(e)}", parse_mode="HTML")


@router.callback_query(lambda call: call.data in {
    "admin_stats", "admin_health", "admin_nodes", "admin_monitors",
    "admin_main", "admin_banhelp", "admin_close"
})
async def admin_callbacks(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("Access denied", show_alert=True)
        return
    data = call.data
    if data == "admin_stats":
        s = db.stats()
        await safe_edit(call.message, 
            f"📊 <b>System Stats</b>\n"
            f"👥 Users: <code>{s['users']}</code>\n"
            f"📥 Downloads: <code>{s['downloads']}</code>\n"
            f"🛡️ Admins: <code>{s['admins']}</code>\n"
            f"🚫 Banned: <code>{s['banned']}</code>\n"
            f"📡 Nodes: <code>{s['nodes']}</code>",
            reply_markup=admin_menu(), parse_mode="HTML")
    elif data == "admin_health":
        lines = await node_manager.health_report()
        await safe_edit(call.message, "🏥 <b>API Node Health</b>\n\n" + "\n\n".join(lines), reply_markup=admin_menu(), parse_mode="HTML")
    elif data == "admin_nodes":
        nodes = db.get_nodes()
        txt = "📡 <b>API Scraper Nodes Pool</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        txt += "\n".join([f"{i+1}. <code>{h(n)}</code>" for i, n in enumerate(nodes)]) or "⚠️ No nodes configured."
        txt += "\n\nButtons se API node add/delete kar sakte ho."
        await safe_edit(call.message, txt, reply_markup=api_nodes_menu(nodes), parse_mode="HTML")
    elif data == "admin_monitors":
        await safe_edit(call.message, monitor_title("admin_mon"), reply_markup=monitor_menu("admin_mon"), parse_mode="HTML")
    elif data == "admin_main":
        await safe_edit(call.message, "⚙️ <b>SaveGr Ultra Bot - Admin Control Panel</b>", reply_markup=admin_menu(), parse_mode="HTML")
    elif data == "admin_banhelp":
        await safe_edit(call.message, "🚫 <b>Ban Commands</b>\n/ban user_id\n/unban user_id", reply_markup=admin_menu(), parse_mode="HTML")
    elif data == "admin_close":
        await call.message.delete()
    await call.answer()


@router.callback_query(F.data.startswith("api_"))
async def api_callbacks(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("Admin only", show_alert=True)
        return
    data = call.data
    if data == "api_add_prompt":
        PENDING_ACTIONS[call.from_user.id] = "api_add"
        await call.message.answer("✍️ New API Node URL bhejo. Example:\n<code>https://your-node.netlify.app</code>", parse_mode="HTML")
        await call.answer("Send URL")
        return
    if data.startswith("api_delete:"):
        try:
            idx = int(data.split(":", 1)[1])
            nodes = db.get_nodes()
            if 0 <= idx < len(nodes):
                db.delete_node(nodes[idx])
                nodes = db.get_nodes()
                txt = "✅ Node deleted.\n\n📡 <b>API Nodes</b>\n" + ("\n".join([f"{i+1}. <code>{h(n)}</code>" for i, n in enumerate(nodes)]) or "No nodes.")
                await safe_edit(call.message, txt, reply_markup=api_nodes_menu(nodes), parse_mode="HTML")
            else:
                await call.answer("Invalid node", show_alert=True)
        except Exception as e:
            await call.answer(f"Error: {e}", show_alert=True)
        return


@router.callback_query(F.data.startswith("admin_mon_") | F.data.startswith("user_mon_"))
async def monitor_callbacks(call: CallbackQuery):
    is_admin_panel = call.data.startswith("admin_mon_")
    prefix = "admin_mon" if is_admin_panel else "user_mon"

    if is_admin_panel and not db.is_admin(call.from_user.id):
        await safe_answer(call, "Admin only", show_alert=True)
        return
    if db.is_banned(call.from_user.id):
        await safe_answer(call, "Access denied", show_alert=True)
        return

    action = call.data[len(prefix) + 1:]
    owner_id = None if is_admin_panel else call.from_user.id

    if action == "close":
        await call.message.delete()
        await safe_answer(call, "Closed")
        return

    if action == "main":
        await safe_edit(call.message, monitor_title(prefix), reply_markup=monitor_menu(prefix), parse_mode="HTML")
        await safe_answer(call)
        return

    if action == "list":
        mons = db.list_monitors(owner_id)
        txt = "🔄 <b>Monitored Profiles</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        if mons:
            for i, m in enumerate(mons, 1):
                uname = monitor_username(m)
                owner = m.get("owner_id") or m.get("admin_id") or "?"
                txt += f"{i}. @{h(uname)}"
                if is_admin_panel:
                    txt += f" → <code>{owner}</code>"
                txt += "\n"
        else:
            txt += "💡 No profiles are currently monitored."
        await safe_edit(call.message, txt, reply_markup=monitor_menu(prefix), parse_mode="HTML")
        await safe_answer(call)
        return

    if action == "add":
        PENDING_ACTIONS[call.from_user.id] = "admin_monitor_add" if is_admin_panel else "user_monitor_add"
        await call.message.answer(
            "✍️ <b>Instagram username bhejo monitor ke liye</b>\n\n"
            "Example: <code>username</code> ya <code>@username</code>\n\n"
            "Bot current posts/reels/stories cache karega, future new uploads auto-send honge.",
            parse_mode="HTML",
        )
        await safe_answer(call, "Send username")
        return

    if action == "del":
        mons = db.list_monitors(owner_id)
        if not mons:
            await safe_answer(call, "No monitors to remove", show_alert=True)
            return
        await safe_edit(call.message, "❌ <b>Select profile to stop monitoring:</b>", reply_markup=monitor_delete_menu(mons, prefix), parse_mode="HTML")
        await safe_answer(call)
        return

    if action.startswith("remove:"):
        uname = action.split(":", 1)[1].replace("@", "").strip().lower()
        db.delete_monitor(uname, None if is_admin_panel else call.from_user.id)
        mons = db.list_monitors(owner_id)
        txt = f"✅ <b>Stopped monitoring @{h(uname)}</b>\n\n🔄 <b>Remaining Profiles</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        if mons:
            for i, m in enumerate(mons, 1):
                txt += f"{i}. @{h(monitor_username(m))}\n"
        else:
            txt += "No monitors."
        await safe_edit(call.message, txt, reply_markup=monitor_menu(prefix), parse_mode="HTML")
        await safe_answer(call, f"Stopped @{uname}", show_alert=True)
        return

    await safe_answer(call)


@router.callback_query(F.data.startswith("profile_"))
async def profile_callbacks(call: CallbackQuery, bot: Bot):
    if not db.is_admin(call.from_user.id):
        await call.answer("Admin only", show_alert=True)
        return
    action, username = call.data.split(":", 1)
    if action == "profile_cancel":
        await call.message.delete()
        await call.answer("Cancelled")
        return
    if action == "profile_stories":
        target = f"https://www.instagram.com/stories/{username}/"
    else:
        target = f"https://www.instagram.com/{username}/"
    await call.message.delete()
    await job_manager.submit(bot, call.message.chat.id, call.from_user, target, True)
    await call.answer("VIP processing")


@router.message(F.text)
async def catch_all(message: Message, bot: Bot):
    if db.is_banned(message.from_user.id):
        await message.answer("❌ Aap banned ho.")
        return
    db.register_user(message.from_user)
    text = message.text.strip()
    is_admin = db.is_admin(message.from_user.id)

    pending = PENDING_ACTIONS.pop(message.from_user.id, None)
    if pending == "api_add":
        if not is_admin:
            return
        if not ((text.startswith("http://") or text.startswith("https://")) and "." in text):
            await message.answer("❌ Invalid API URL. Example: <code>https://your-node.netlify.app</code>", parse_mode="HTML")
            return
        db.add_node(text.rstrip("/"))
        await message.answer(f"✅ <b>API Node added:</b>\n<code>{h(text.rstrip('/'))}</code>", parse_mode="HTML")
        return

    if pending in {"admin_monitor_add", "user_monitor_add"}:
        username = extract_profile_username(text) or text.strip().replace("@", "").lower()
        if pending == "admin_monitor_add" and not is_admin:
            return
        status = await message.answer(f"⏳ <b>Adding @{h(username)} to auto-monitor...</b>\nCurrent posts/reels/stories cache ho rahe hain, thoda wait karo.", parse_mode="HTML")
        ok, msg = await add_profile_monitor(username, message.from_user.id)
        try:
            await status.edit_text(msg, parse_mode="HTML")
        except TelegramBadRequest:
            await message.answer(msg, parse_mode="HTML")
        return

    # Direct admin API node add support
    if is_admin and (text.startswith("http://") or text.startswith("https://")) and "instagram.com" not in text and "." in text:
        db.add_node(text.rstrip("/"))
        await message.answer(f"✅ <b>API Node added:</b>\n<code>{h(text.rstrip('/'))}</code>", parse_mode="HTML")
        return

    if not is_instagram_media_link(text):
        username = extract_profile_username(text)
        if username:
            if is_admin:
                await message.answer(
                    f"👤 <b>Instagram Profile Detected</b>\n🆔 Username: @{h(username)}\nSelect option, ya /monitor se auto-monitor add karo:",
                    reply_markup=profile_menu(username), parse_mode="HTML")
                return
            await message.answer("❌ Profile scanning feature admin only hai. Auto-monitor add karne ke liye /monitor use karo, ya public post/reel/story link bhejo.")
            return
        await message.answer("❌ Valid public Instagram link bhejo.")
        return
    await job_manager.submit(bot, message.chat.id, message.from_user, text, is_admin)
