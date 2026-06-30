import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import uvicorn
from app.config import settings
from app.db import db
from app.utils.logging import setup_logging
from app.bot.handlers import router
from app.services.jobs import job_manager

setup_logging()
log = logging.getLogger("main")

if not settings.bot_token or settings.bot_token == "YOUR_TELEGRAM_BOT_TOKEN_IF_LOCAL":
    log.warning("BOT_TOKEN is missing. Set BOT_TOKEN in Koyeb environment variables.")

bot = Bot(token=settings.bot_token or "0:missing", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(router)

polling_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global polling_task
    db.connect()
    await job_manager.start(bot)
    if settings.bot_mode == "webhook" and settings.webhook_url:
        webhook_endpoint = settings.webhook_url.rstrip("/") + "/webhook/telegram"
        await bot.set_webhook(webhook_endpoint, secret_token=settings.webhook_secret)
        log.info("Webhook set: %s", webhook_endpoint)
    else:
        await bot.delete_webhook(drop_pending_updates=False)
        polling_task = asyncio.create_task(dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()))
        log.info("Polling started with FastAPI health server")
    yield
    if polling_task:
        polling_task.cancel()
    try:
        await bot.session.close()
    except Exception:
        pass


app = FastAPI(title="SaveGr Pro Telegram Bot", version="4.0", lifespan=lifespan)


@app.get("/")
@app.get("/health")
async def health():
    return {"status": "healthy", "bot": "SaveGr Pro Bot active", "mode": settings.bot_mode, "queue": job_manager.queue.qsize()}


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    if settings.webhook_secret:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret != settings.webhook_secret:
            raise HTTPException(status_code=403, detail="bad secret")
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return Response(status_code=200)


def main():
    uvicorn.run(app, host="0.0.0.0", port=settings.port, reload=False, workers=1)


if __name__ == "__main__":
    main()
