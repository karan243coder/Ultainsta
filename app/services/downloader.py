import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional
import aiohttp
from app.config import settings

log = logging.getLogger("downloader")
TMP_DIR = Path("/tmp/instadl")
TMP_DIR.mkdir(parents=True, exist_ok=True)


def stable_media_id(url: str) -> str:
    try:
        return url.split("?")[0].split("/")[-1] or url
    except Exception:
        return url


def detect_label(source_url: str, media_type: str) -> str:
    if "/stories/" in source_url:
        return "Story 🌌"
    if "/reel/" in source_url or "/reels/" in source_url:
        return "Reel 🎬"
    if "/p/" in source_url:
        return "Post 📁"
    return "Video 🎬" if media_type == "video" else "Photo 🖼️"


async def get_content_length(url: str) -> int:
    timeout = aiohttp.ClientTimeout(total=5)
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.head(url, allow_redirects=True) as resp:
                length = resp.headers.get("Content-Length")
                return int(length or 0)
    except Exception:
        return 0


def size_str(bytes_count: int) -> str:
    if not bytes_count:
        return "Unknown"
    if bytes_count >= 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.2f}mb ☁️"
    return f"{bytes_count / 1024:.1f}kb ☁️"


async def download_media(url: str, media_type: str) -> Optional[Path]:
    ext = "mp4" if media_type == "video" else "jpg"
    path = TMP_DIR / f"{uuid.uuid4()}.{ext}"
    timeout = aiohttp.ClientTimeout(total=settings.media_download_timeout)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119 Safari/537.36"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    log.warning("media download status %s", resp.status)
                    return None
                max_bytes = settings.max_file_mb * 1024 * 1024
                written = 0
                with open(path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 64):
                        written += len(chunk)
                        if written > max_bytes:
                            try: path.unlink(missing_ok=True)
                            except Exception: pass
                            raise ValueError(f"File larger than {settings.max_file_mb} MB")
                        f.write(chunk)
        return path
    except Exception as e:
        log.warning("download failed: %s", e)
        try: path.unlink(missing_ok=True)
        except Exception: pass
        return None
