from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from app.db import db
from app.services.jobs import job_manager
from app.services.nodes import node_manager
from app.bot.keyboards import admin_menu, profile_menu
from app.utils.instagram import is_instagram_media_link, extract_profile_username, h

router = Router()


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
        "Commands: /start /help /admin /ban /unban",
        parse_mode="HTML",
    )


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


@router.callback_query(F.data.startswith("admin_"))
async def admin_callbacks(call: CallbackQuery):
    if not db.is_admin(call.from_user.id):
        await call.answer("Access denied", show_alert=True)
        return
    data = call.data
    if data == "admin_stats":
        s = db.stats()
        await call.message.edit_text(
            f"📊 <b>System Stats</b>\n"
            f"👥 Users: <code>{s['users']}</code>\n"
            f"📥 Downloads: <code>{s['downloads']}</code>\n"
            f"🛡️ Admins: <code>{s['admins']}</code>\n"
            f"🚫 Banned: <code>{s['banned']}</code>\n"
            f"📡 Nodes: <code>{s['nodes']}</code>",
            reply_markup=admin_menu(), parse_mode="HTML")
    elif data == "admin_health":
        lines = await node_manager.health_report()
        await call.message.edit_text("🏥 <b>API Node Health</b>\n\n" + "\n\n".join(lines), reply_markup=admin_menu(), parse_mode="HTML")
    elif data == "admin_nodes":
        nodes = db.get_nodes()
        txt = "📡 <b>API Nodes</b>\n\n" + "\n".join([f"{i+1}. <code>{h(n)}</code>" for i, n in enumerate(nodes)])
        txt += "\n\nAdd/Delete currently via Mongo/env. For safety, keep WEBSITE_API_URLS updated."
        await call.message.edit_text(txt, reply_markup=admin_menu(), parse_mode="HTML")
    elif data == "admin_banhelp":
        await call.message.edit_text("🚫 <b>Ban Commands</b>\n/ban user_id\n/unban user_id", reply_markup=admin_menu(), parse_mode="HTML")
    elif data == "admin_close":
        await call.message.delete()
    await call.answer()


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
    if not is_instagram_media_link(text):
        username = extract_profile_username(text)
        if username:
            if not is_admin:
                await message.answer("❌ Profile scanning feature admin only hai. Public post/reel/story link bhejo.")
                return
            await message.answer(
                f"👤 <b>Instagram Profile Detected</b>\n🆔 Username: @{h(username)}\nSelect option:",
                reply_markup=profile_menu(username), parse_mode="HTML")
            return
        await message.answer("❌ Valid public Instagram link bhejo.")
        return
    await job_manager.submit(bot, message.chat.id, message.from_user, text, is_admin)
