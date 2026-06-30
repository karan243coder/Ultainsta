import asyncio
import logging
from pathlib import Path
from typing import List
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest, TelegramNetworkError, TelegramEntityTooLarge
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from app.config import settings
from app.services.downloader import download_media

log = logging.getLogger("sender")


async def retry_call(func, *args, **kwargs):
    for attempt in range(4):
        try:
            return await func(*args, **kwargs)
        except TelegramEntityTooLarge:
            # Permanent error. Retrying won't help.
            raise
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


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _preview_media(downloaded: list[dict], caption: str):
    media = []
    for i, f in enumerate(downloaded):
        inp = FSInputFile(str(f["path"]))
        cap = caption if i == 0 else None
        if f["type"] == "video":
            media.append(InputMediaVideo(media=inp, caption=cap, parse_mode="HTML"))
        else:
            media.append(InputMediaPhoto(media=inp, caption=cap, parse_mode="HTML"))
    return media


def _document_media(downloaded: list[dict], caption: str):
    media = []
    for i, f in enumerate(downloaded):
        inp = FSInputFile(str(f["path"]))
        cap = f"{caption}\n\n💎 Original Quality" if i == 0 else None
        media.append(InputMediaDocument(media=inp, caption=cap, parse_mode="HTML"))
    return media


async def _send_group_with_fallback(bot: Bot, chat_id: int | str, media: list) -> int:
    """Telegram album max is 10. If multipart is too large, fallback to single sends."""
    if not media:
        return 0
    try:
        await retry_call(bot.send_media_group, chat_id, media)
        return len(media)
    except TelegramEntityTooLarge as e:
        log.warning("Media group too large, falling back to single sends: %s", e)
        sent = 0
        for single in media:
            try:
                await retry_call(bot.send_media_group, chat_id, [single])
                sent += 1
            except TelegramEntityTooLarge as one_err:
                log.warning("Skipping one Telegram-too-large media: %s", one_err)
            except Exception as one_err:
                log.warning("Single media send failed: %s", one_err)
        return sent


async def send_album(bot: Bot, chat_id: int | str, items: List[dict], caption: str) -> bool:
    """
    Sends ALL items, not only first 10.
    Telegram allows max 10 items per media_group, so large highlights are sent in chunks.
    """
    any_sent = False
    total_items = len(items)
    log.info("send_album: preparing %s items", total_items)

    # Process in chunks to keep /tmp, RAM and Telegram multipart size under control.
    for item_chunk in _chunks(items, 10):
        downloaded = []
        try:
            for item in item_chunk:
                path = await download_media(item["url"], item.get("type", "photo"))
                if path:
                    downloaded.append({"path": path, "type": item.get("type", "photo")})
            if not downloaded:
                continue

            if settings.send_preview:
                media = _preview_media(downloaded, caption if not any_sent else "")
                sent = await _send_group_with_fallback(bot, chat_id, media)
                any_sent = any_sent or sent > 0

            if settings.send_document:
                docs = _document_media(downloaded, caption if not any_sent else "")
                sent = await _send_group_with_fallback(bot, chat_id, docs)
                any_sent = any_sent or sent > 0

            if not settings.send_preview and not settings.send_document:
                for i, f in enumerate(downloaded):
                    try:
                        await retry_call(bot.send_document, chat_id, FSInputFile(str(f["path"])), caption=caption if not any_sent and i == 0 else None, parse_mode="HTML")
                        any_sent = True
                    except TelegramEntityTooLarge as e:
                        log.warning("Skipping too-large document: %s", e)
        except Exception as e:
            log.exception("send_album chunk failed: %s", e)
        finally:
            for f in downloaded:
                try:
                    Path(f["path"]).unlink(missing_ok=True)
                except Exception:
                    pass

        # Small pause reduces Telegram 429 when many highlight chunks are sent.
        await asyncio.sleep(0.4)

    return any_sent
