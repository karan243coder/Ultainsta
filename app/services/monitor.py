import asyncio
import logging
import random
import re
from typing import Any
from aiogram import Bot
from app.config import settings
from app.db import db
from app.services.nodes import node_manager
from app.services.downloader import stable_media_id, get_content_length, size_str
from app.services.sender import send_album, send_text
from app.utils.instagram import h

log = logging.getLogger("monitor")

MONITOR_TARGETS = ("profile", "reels", "stories")


def _clean_username(username: str) -> str:
    return (username or "").strip().replace("@", "").lower()


def _target_url(username: str, target: str) -> str:
    if target == "stories":
        return f"https://www.instagram.com/stories/{username}/"
    if target == "reels":
        return f"https://www.instagram.com/{username}/reels/"
    return f"https://www.instagram.com/{username}/"


def _is_real_item(item: dict[str, Any]) -> bool:
    media_url = item.get("url", "")
    if not media_url:
        return False
    bad = ("unsplash.com", "mixkit", "mixkit-girl")
    return not any(x in media_url for x in bad)


def _extract_shortcode_from_text(text: str) -> str | None:
    if not text:
        return None
    for marker in ("/p/", "/reel/", "/reels/", "/tv/"):
        if marker in text:
            try:
                code = text.split(marker, 1)[1].split("/", 1)[0].split("?", 1)[0]
                return code.strip() or None
            except Exception:
                pass
    return None


def _extract_shortcode_from_item(item: dict[str, Any]) -> str | None:
    for key in ("shortcode", "code", "short_code"):
        val = item.get(key)
        if val and isinstance(val, str):
            return val.strip().strip("/")
    for key in ("post_url", "permalink", "source_url", "instagram_url", "link", "page_url", "url"):
        val = item.get(key)
        if val and isinstance(val, str):
            code = _extract_shortcode_from_text(val)
            if code:
                return code
    return None


def _extract_owner_username(item: dict[str, Any]) -> str | None:
    """Read owner username from common scraper response shapes."""
    keys = (
        "username", "owner_username", "author_username", "author", "user", "owner", "profile_username",
        "taken_by", "creator", "account",
    )
    for key in keys:
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            val = val.strip()
            # Some captions may store @username in author.
            if val.startswith("@"):
                val = val[1:]
            if re.fullmatch(r"[A-Za-z0-9_.]{1,30}", val):
                return _clean_username(val)
        if isinstance(val, dict):
            for sub in ("username", "user_name", "name"):
                subval = val.get(sub)
                if isinstance(subval, str) and subval.strip():
                    subval = subval.strip().replace("@", "")
                    if re.fullmatch(r"[A-Za-z0-9_.]{1,30}", subval):
                        return _clean_username(subval)

    meta = item.get("meta")
    if isinstance(meta, dict):
        for key in ("username", "owner_username", "author"):
            val = meta.get(key)
            if isinstance(val, str) and val.strip():
                return _clean_username(val)
    return None


def _owner_matches(monitored_username: str, item: dict[str, Any]) -> bool:
    """
    If scraper gives owner username and it doesn't match, skip item.
    If scraper gives no owner, allow it because many current APIs return only CDN URL/type.
    """
    owner = _extract_owner_username(item)
    if not owner:
        return True
    return _clean_username(owner) == _clean_username(monitored_username)


def _item_id(item: dict[str, Any]) -> str:
    """Stable duplicate key. Prefer shortcode/original ID over rotating CDN query tokens."""
    if item.get("monitor_stable_id"):
        return str(item["monitor_stable_id"])
    if item.get("original_monitor_id"):
        return str(item["original_monitor_id"])
    shortcode = _extract_shortcode_from_item(item)
    if shortcode:
        return f"code:{shortcode}"
    media_url = item.get("url", "")
    return stable_media_id(media_url)


async def _upgrade_item_quality(username: str, item: dict[str, Any]) -> dict[str, Any]:
    """
    Profile/reels endpoints sometimes return lower quality CDN URLs.
    If shortcode/permalink exists, re-fetch exact /p/ or /reel/ URL like manual download.
    Safety: if upgraded response exposes a different owner username, reject upgrade.
    """
    target = item.get("monitor_target")
    if target not in {"profile", "reels"}:
        return item

    shortcode = _extract_shortcode_from_item(item)
    if not shortcode:
        return item

    urls = []
    if target == "reels":
        urls.append(f"https://www.instagram.com/reel/{shortcode}/")
    urls.append(f"https://www.instagram.com/p/{shortcode}/")

    original_id = _item_id(item)
    for url in urls:
        try:
            data = await node_manager.fetch_media(url)
            if data and data.get("items"):
                upgraded = data["items"][0]
                if _is_real_item(upgraded) and _owner_matches(username, upgraded):
                    upgraded["monitor_target"] = target
                    upgraded["original_monitor_id"] = original_id
                    upgraded["monitor_stable_id"] = f"code:{shortcode}"
                    return upgraded
        except Exception as e:
            log.warning("quality upgrade failed @%s shortcode=%s: %s", username, shortcode, e)
    return item


async def fetch_profile_items(username: str) -> list[dict[str, Any]]:
    """Fetch posts, reels and stories. Only accept owner-matching items when owner metadata is available."""
    username = _clean_username(username)
    all_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for target in MONITOR_TARGETS:
        try:
            data = await node_manager.fetch_media(_target_url(username, target))
            if not data or not data.get("items"):
                continue

            for item in data["items"]:
                if not _is_real_item(item):
                    continue
                item["monitor_target"] = target

                # Wrong-user bug protection: skip if API identifies a different owner.
                if not _owner_matches(username, item):
                    log.warning("monitor skipped wrong-owner item for @%s owner=%s target=%s", username, _extract_owner_username(item), target)
                    continue

                sid = _item_id(item)
                if not sid or sid in seen_ids:
                    continue

                upgraded = await _upgrade_item_quality(username, item)
                upgraded_id = _item_id(upgraded) or sid
                if upgraded_id in seen_ids:
                    continue
                all_items.append(upgraded)
                seen_ids.add(upgraded_id)
        except Exception as e:
            log.warning("monitor fetch failed @%s target=%s: %s", username, target, e)
    return all_items


async def pre_cache_profile(username: str) -> list[str]:
    """Cache current items first so old posts/stories do not spam immediately."""
    items = await fetch_profile_items(username)
    seen = [_item_id(item) for item in items if _item_id(item)]
    return list(dict.fromkeys(seen))[-settings.monitor_keep_seen_limit:]


async def add_monitor(username: str, owner_id: int) -> tuple[bool, str]:
    username = _clean_username(username)
    if not username:
        return False, "❌ Invalid username."
    if not db.is_admin(owner_id) and db.count_monitors(owner_id) >= 5:
        return False, "❌ Limit exceeded! Normal users max 5 profiles monitor kar sakte hain."

    seen = await pre_cache_profile(username)
    db.add_monitor(username, owner_id, seen)
    return True, (
        f"✅ <b>Started Auto-Monitoring @{h(username)}</b>\n\n"
        f"📌 Current posts/reels/stories cached: <code>{len(seen)}</code>\n"
        "Ab future me jo bhi naya post, reel ya story aayega, bot automatically high-quality me bhej dega.\n"
        "Duplicate dobara nahi aayega."
    )


async def _send_new_item(bot: Bot, owner_id: int, username: str, item: dict[str, Any]) -> bool:
    length = await get_content_length(item.get("url", ""))
    target = item.get("monitor_target") or "media"
    label = {"profile": "Post/Profile Media 📁", "reels": "Reel 🎬", "stories": "Story 🌌"}.get(target, "Media")
    caption = (
        "✨ <b>[AUTO-DOWNLOAD COMPLETE]</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Author:</b> @{h(username)}\n"
        f"💾 <b>Type:</b> <b>{label}</b>\n"
        f"💾 <b>Size:</b> <b>{size_str(length)}</b>\n"
        "🛰️ <b>Status:</b> <b>Dynamic Monitoring Active</b>\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    ok = await send_album(bot, owner_id, [item], caption)
    if ok and settings.log_channel_id and settings.log_channel_text:
        await send_text(
            bot,
            settings.log_channel_id,
            f"🔄 <b>Auto-Monitor Log</b>\n@{h(username)} → sent to <code>{owner_id}</code>\nType: <b>{label}</b>",
            parse_mode="HTML",
        )
    return ok


async def process_one_monitor(bot: Bot, mon: dict[str, Any], sem: asyncio.Semaphore) -> None:
    async with sem:
        monitor_id = mon.get("_id")
        username = _clean_username(mon.get("username") or str(monitor_id or "").split(":")[-1])
        owner_id = int(mon.get("owner_id") or mon.get("admin_id"))
        last_seen = list(mon.get("last_seen_items", []) or [])
        last_seen_set = set(last_seen)

        if not username or not owner_id or not monitor_id:
            return

        try:
            all_items = await fetch_profile_items(username)
            new_items: list[dict[str, Any]] = []
            new_ids: list[str] = []

            for item in all_items:
                # Final guard: never send item if owner metadata says it belongs to another account.
                if not _owner_matches(username, item):
                    continue
                sid = _item_id(item)
                if not sid or sid in last_seen_set or sid in new_ids:
                    continue
                new_items.append(item)
                new_ids.append(sid)

            if not new_items:
                log.info("monitor @%s no new items", username)
                return

            # API usually returns latest first. Send latest unseen items only; duplicates are blocked by stable IDs.
            limited = new_items[:settings.monitor_max_new_items_per_profile]
            limited_ids = new_ids[:settings.monitor_max_new_items_per_profile]
            log.info("monitor @%s found %s new items, sending %s", username, len(new_items), len(limited))

            sent_ids: list[str] = []
            for item, sid in zip(limited, limited_ids):
                ok = await _send_new_item(bot, owner_id, username, item)
                if ok:
                    sent_ids.append(sid)
                await asyncio.sleep(0.8)

            if sent_ids:
                updated_seen = (last_seen + sent_ids)[-settings.monitor_keep_seen_limit:]
                db.update_monitor_seen(monitor_id, updated_seen)
        except Exception as e:
            log.exception("monitor process failed @%s: %s", username, e)


async def run_monitor_round(bot: Bot) -> None:
    monitors = db.list_monitors()
    if not monitors:
        log.info("monitor round: no profiles configured")
        return

    random.shuffle(monitors)
    sem = asyncio.Semaphore(max(1, settings.monitor_concurrency))
    log.info("monitor round started: profiles=%s concurrency=%s", len(monitors), settings.monitor_concurrency)
    await asyncio.gather(*(process_one_monitor(bot, mon, sem) for mon in monitors), return_exceptions=True)
    log.info("monitor round completed")


async def monitor_loop(bot: Bot):
    log.info(
        "Profile auto-monitor loop started interval=%ss concurrency=%s",
        settings.monitor_interval_seconds,
        settings.monitor_concurrency,
    )
    await asyncio.sleep(settings.monitor_initial_delay_seconds)
    while True:
        try:
            await run_monitor_round(bot)
        except Exception as e:
            log.exception("monitor loop round error: %s", e)
        jitter = random.randint(0, 60)
        await asyncio.sleep(settings.monitor_interval_seconds + jitter)
