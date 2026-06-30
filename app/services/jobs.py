import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from aiogram import Bot
from aiogram.types import User
from app.config import settings
from app.db import db
from app.services.nodes import node_manager
from app.services.sender import send_album, send_text
from app.services.downloader import get_content_length, size_str
from app.utils.instagram import extract_author_userid_from_url, extract_shortcode, h

log = logging.getLogger("jobs")


@dataclass(order=True)
class Job:
    priority: int
    created: float
    chat_id: int = field(compare=False)
    user_id: int = field(compare=False)
    url: str = field(compare=False)
    user: User = field(compare=False)
    status_message_id: Optional[int] = field(default=None, compare=False)
    is_admin: bool = field(default=False, compare=False)


class JobManager:
    def __init__(self):
        self.queue: asyncio.PriorityQueue[Job] = asyncio.PriorityQueue(maxsize=settings.max_queue_size)
        self.active_by_user: Dict[int, int] = {}
        self.lock = asyncio.Lock()
        self.started = False
        self.bot: Optional[Bot] = None

    async def start(self, bot: Bot):
        if self.started:
            return
        self.started = True
        self.bot = bot
        for i in range(settings.admin_workers):
            asyncio.create_task(self.worker(f"admin-worker-{i+1}"))
        for i in range(settings.normal_workers):
            asyncio.create_task(self.worker(f"normal-worker-{i+1}"))
        log.info("Job workers started: admin=%s normal=%s", settings.admin_workers, settings.normal_workers)

    async def can_accept(self, user_id: int, is_admin: bool) -> tuple[bool, str]:
        async with self.lock:
            active = self.active_by_user.get(user_id, 0)
            limit = settings.admin_max_active_jobs if is_admin else settings.normal_user_max_active_jobs
            if active >= limit:
                return False, "⚠️ Pehle wala download complete hone do bhai." if not is_admin else "👑 VIP limit reached, thoda wait karo."
            if self.queue.full() and not is_admin:
                return False, "🚦 Server queue full hai bhai, 1-2 minute baad try karo."
            self.active_by_user[user_id] = active + 1
            return True, ""

    async def release_user(self, user_id: int):
        async with self.lock:
            cur = self.active_by_user.get(user_id, 0)
            if cur <= 1:
                self.active_by_user.pop(user_id, None)
            else:
                self.active_by_user[user_id] = cur - 1

    async def submit(self, bot: Bot, chat_id: int, user: User, url: str, is_admin: bool) -> None:
        ok, msg = await self.can_accept(user.id, is_admin)
        if not ok:
            await send_text(bot, chat_id, msg)
            return
        priority = 0 if is_admin else 10
        qsize = self.queue.qsize()
        text = "👑 <b>VIP Admin request accepted.</b>\n⚡ Priority processing started..." if is_admin else f"✅ <b>Link received!</b>\n📌 Queue Position: <code>#{qsize + 1}</code>\n⚡ Processing soon..."
        status = await bot.send_message(chat_id, text, parse_mode="HTML")
        job = Job(priority=priority, created=time.time(), chat_id=chat_id, user_id=user.id, url=url, user=user, status_message_id=status.message_id, is_admin=is_admin)
        await self.queue.put(job)

    async def worker(self, name: str):
        while True:
            job = await self.queue.get()
            try:
                await self.process(job)
            except Exception as e:
                log.exception("job failed: %s", e)
                if self.bot:
                    await send_text(self.bot, job.chat_id, "❌ Download failed. Please try again after some time.")
            finally:
                await self.release_user(job.user_id)
                self.queue.task_done()

    async def process(self, job: Job):
        assert self.bot is not None
        bot = self.bot
        try:
            await bot.edit_message_text("🔍 <b>Analyzing link...</b>\n⚡ Selecting best scraper node...", job.chat_id, job.status_message_id, parse_mode="HTML")
        except Exception:
            pass
        data = await node_manager.fetch_media(job.url)
        if not data or not data.get("items"):
            await send_text(bot, job.chat_id, "❌ All API nodes busy/rate-limited hain. Thodi der baad try karo.")
            return
        items = data["items"]
        first_url = items[0].get("url", "")
        length = await get_content_length(first_url)
        if length and length > settings.max_file_mb * 1024 * 1024:
            await send_text(bot, job.chat_id, f"⚠️ File bahut large hai ({size_str(length)}). Free server mode me max {settings.max_file_mb}MB allowed hai.")
            return
        shortcode = extract_shortcode(job.url)
        author, uid = extract_author_userid_from_url(job.url)
        parts = ["✨ <b>InstaMedia Album</b> ✨\n"]
        if author:
            parts.append(f"👤 Author: <b>{h(author)}</b>")
        if uid:
            parts.append(f"🆔 User ID: <code>{h(uid)}</code>")
        parts.append(f"💾 Size: <b>{size_str(length)}</b>")
        caption = "\n".join(parts)
        try:
            await bot.edit_message_text("📤 <b>Uploading media to Telegram...</b>", job.chat_id, job.status_message_id, parse_mode="HTML")
        except Exception:
            pass
        success = await send_album(bot, job.chat_id, items, caption)
        if success:
            for item in items:
                db.log_download(job.user_id, shortcode, item.get("type", "unknown"))
            if settings.log_channel_id:
                if settings.log_channel_text:
                    await send_text(bot, settings.log_channel_id, f"📥 <b>Download Log</b>\n👤 {h(job.user.first_name)} (@{h(job.user.username or 'NoUsername')})\n🆔 <code>{job.user_id}</code>\n🔗 <code>{h(job.url[:500])}</code>", parse_mode="HTML")
                if settings.log_channel_media:
                    await send_album(bot, settings.log_channel_id, items, f"📥 <b>Log Copy</b>\n{caption}")
        else:
            await send_text(bot, job.chat_id, "❌ Failed to deliver media. Please try again.")
        try:
            await bot.delete_message(job.chat_id, job.status_message_id)
        except Exception:
            pass


job_manager = JobManager()
