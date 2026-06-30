# SaveGr Pro Industrial Telegram Bot

Production-ready Koyeb free friendly Instagram downloader Telegram bot.

## Features

- aiogram 3 async Telegram bot
- FastAPI health server / optional webhook
- Normal user fast queue
- Admin VIP priority lane
- Multiple API scraper nodes with cooldown/failover
- MongoDB optional persistence with in-memory fallback
- Telegram 429 retry handling
- File size protection
- Koyeb deploy ready
- Text-only log mode by default to keep free server fast

## Required Environment Variables

Set these in Koyeb:

```env
BOT_TOKEN=your_botfather_token
ADMIN_ID=your_telegram_user_id
MONGO_URL=mongodb+srv://user:pass@cluster.mongodb.net/
WEBSITE_API_URLS=https://node1.netlify.app,https://node2.netlify.app
LOG_CHANNEL_ID=-100xxxxxxxxxx
PORT=8000
BOT_MODE=polling
```

For Koyeb free, recommended:

```env
NORMAL_WORKERS=3
ADMIN_WORKERS=2
NORMAL_USER_MAX_ACTIVE_JOBS=1
ADMIN_MAX_ACTIVE_JOBS=5
MAX_QUEUE_SIZE=300
MAX_FILE_MB=45
SEND_PREVIEW=true
SEND_DOCUMENT=false
LOG_CHANNEL_MEDIA=false
LOG_CHANNEL_TEXT=true
API_NODE_TIMEOUT=8
MEDIA_DOWNLOAD_TIMEOUT=25
NODE_COOLDOWN_SECONDS=180
```

## Deploy on Koyeb

1. Extract this zip.
2. Push files to GitHub repo.
3. Koyeb → Create Web Service → connect repo.
4. Run command: `python -m app.main`
5. Add environment variables.
6. Deploy.

Health check path: `/health`

## Notes

- Normal users enter queue and get queue position.
- Admin gets VIP priority over normal users.
- Do not set unlimited workers on free Koyeb. More workers can crash free instance.
- If `MONGO_URL` missing, bot works but users/admin/nodes/log data resets on restart.
