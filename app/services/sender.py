import asyncio
import logging
from pathlib import Path
from typing import List
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest, TelegramNetworkError
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from app.config import settings
from app.services.downloader import download_media

log = logging.getLogger("sender")


async def retry_call(func, *args, **kwargs):
    for attempt in range(4):
        try:
            return await func(*args, **kwargs)
        except TelegramRetryAfter as e:
            wait = int(getattr(e, "retry_after", 5)) + 1
            log.warning("Telegram 429 retry_after=%s", wait)
            await asyncio.sleep(wait)
        except (TelegramNetworkError, TelegramBadRequest) as e:
            if attempt >= 2:
                raise
            log.warning("Telegram send retry %s: %s", attempt + 1, e)
            await asyncio.sleep(2 + attempt)
    return None


async def send_text(bot: Bot, chat_id: int | str, text: str, **kwargs):
    return await retry_call(bot.send_message, chat_id, text, **kwargs)


async def send_album(bot: Bot, chat_id: int | str, items: List[dict], caption: str) -> bool:
    downloaded = []
    try:
        for item in items[:10]:
            path = await download_media(item["url"], item.get("type", "photo"))
            if path:
                downloaded.append({"path": path, "type": item.get("type", "photo")})
        if not downloaded:
            return False

        if settings.send_preview:
            media = []
            for i, f in enumerate(downloaded):
                inp = FSInputFile(str(f["path"]))
                cap = caption if i == 0 else None
                if f["type"] == "video":
                    media.append(InputMediaVideo(media=inp, caption=cap, parse_mode="HTML"))
                else:
                    media.append(InputMediaPhoto(media=inp, caption=cap, parse_mode="HTML"))
            await retry_call(bot.send_media_group, chat_id, media)

        if settings.send_document:
            docs = []
            for i, f in enumerate(downloaded):
                inp = FSInputFile(str(f["path"]))
                cap = f"{caption}\n\n💎 Original Quality" if i == 0 else None
                docs.append(InputMediaDocument(media=inp, caption=cap, parse_mode="HTML"))
            await retry_call(bot.send_media_group, chat_id, docs)

        if not settings.send_preview and not settings.send_document:
            # fallback: send document if both disabled accidentally
            for i, f in enumerate(downloaded):
                await retry_call(bot.send_document, chat_id, FSInputFile(str(f["path"])), caption=caption if i == 0 else None, parse_mode="HTML")
        return True
    except Exception as e:
        log.exception("send_album failed: %s", e)
        return False
    finally:
        for f in downloaded:
            try:
                Path(f["path"]).unlink(missing_ok=True)
            except Exception:
                pass
