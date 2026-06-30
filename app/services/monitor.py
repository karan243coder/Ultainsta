import asyncio
import logging
from aiogram import Bot
from app.config import settings
from app.db import db
from app.services.nodes import node_manager
from app.services.downloader import stable_media_id, get_content_length, size_str
from app.services.sender import send_album, send_text
from app.utils.instagram import h

log = logging.getLogger("monitor")


async def pre_cache_profile(username: str) -> list[str]:
    username = username.strip().replace("@", "").lower()
    seen: list[str] = []
    urls = [
        f"https://www.instagram.com/{username}/",
        f"https://www.instagram.com/{username}/reels/",
        f"https://www.instagram.com/stories/{username}/",
    ]
    for url in urls:
        data = await node_manager.fetch_media(url)
        if data and data.get("items"):
            for item in data["items"]:
                media_url = item.get("url", "")
                if media_url and "unsplash.com" not in media_url and "mixkit" not in media_url:
                    seen.append(stable_media_id(media_url))
    return list(dict.fromkeys(seen))[-150:]


async def add_monitor(username: str, owner_id: int) -> tuple[bool, str]:
    username = username.strip().replace("@", "").lower()
    if not username:
        return False, "❌ Invalid username."
    if not db.is_admin(owner_id) and db.count_monitors(owner_id) >= 5:
        return False, "❌ Limit exceeded! Normal users max 5 profiles monitor kar sakte hain."
    seen = await pre_cache_profile(username)
    db.add_monitor(username, owner_id, seen)
    return True, f"✅ <b>Started Auto-Monitoring @{h(username)}</b>\nFuture posts/reels/stories automatically yahin bheje jayenge."


async def monitor_loop(bot: Bot):
    log.info("Profile auto-monitor loop started interval=%ss", settings.monitor_interval_seconds)
    await asyncio.sleep(15)
    while True:
        try:
            monitors = db.list_monitors()
            for mon in monitors:
                username = mon.get("username") or mon.get("_id", "").split(":")[-1]
                owner_id = int(mon.get("owner_id") or mon.get("admin_id"))
                last_seen = mon.get("last_seen_items", []) or []
                all_items = []
                for url in [f"https://www.instagram.com/{username}/", f"https://www.instagram.com/stories/{username}/"]:
                    data = await node_manager.fetch_media(url)
                    if data and data.get("items"):
                        all_items.extend(data["items"])
                new_items = []
                new_ids = []
                for item in all_items:
                    media_url = item.get("url", "")
                    if not media_url or "unsplash.com" in media_url or "mixkit" in media_url:
                        continue
                    sid = stable_media_id(media_url)
                    if sid not in last_seen and sid not in new_ids:
                        new_items.append(item)
                        new_ids.append(sid)
                if new_items:
                    log.info("monitor found %s new items for @%s", len(new_items), username)
                    for item in new_items[:5]:
                        length = await get_content_length(item.get("url", ""))
                        caption = (
                            "✨ <b>[AUTO-DOWNLOAD COMPLETE]</b> ✨\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 <b>Author:</b> @{h(username)}\n"
                            f"💾 <b>Size:</b> <b>{size_str(length)}</b>\n"
                            "🛰️ <b>Status:</b> <b>Dynamic Monitoring Active</b>\n"
                            "━━━━━━━━━━━━━━━━━━━━"
                        )
                        await send_album(bot, owner_id, [item], caption)
                        if settings.log_channel_id and settings.log_channel_text:
                            await send_text(bot, settings.log_channel_id, f"🔄 <b>Auto-Monitor Log</b>\n@{h(username)} → sent to <code>{owner_id}</code>", parse_mode="HTML")
                    db.update_monitor_seen(mon.get("_id"), list(last_seen) + new_ids)
        except Exception as e:
            log.exception("monitor loop error: %s", e)
        await asyncio.sleep(settings.monitor_interval_seconds)
