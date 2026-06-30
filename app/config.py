import os
from dataclasses import dataclass, field
from typing import List, Optional


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _urls() -> List[str]:
    raw = os.getenv("WEBSITE_API_URLS", "")
    defaults = [
        "https://beamish-kulfi-ed0fed.netlify.app",
        "https://warm-muffin-ab9ffe.netlify.app",
        "https://dazzling-blancmange-158c4d.netlify.app",
    ]
    urls = [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]
    return urls or defaults


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    mongo_url: Optional[str] = os.getenv("MONGO_URL") or None
    admin_id: Optional[int] = None
    log_channel_id: Optional[str] = os.getenv("LOG_CHANNEL_ID") or None
    api_urls: List[str] = field(default_factory=_urls)

    port: int = _int("PORT", 8000)
    bot_mode: str = os.getenv("BOT_MODE", "polling").lower()
    webhook_url: Optional[str] = os.getenv("WEBHOOK_URL") or None
    webhook_secret: Optional[str] = os.getenv("WEBHOOK_SECRET") or None

    normal_workers: int = _int("NORMAL_WORKERS", 3)
    admin_workers: int = _int("ADMIN_WORKERS", 2)
    normal_user_max_active_jobs: int = _int("NORMAL_USER_MAX_ACTIVE_JOBS", 1)
    admin_max_active_jobs: int = _int("ADMIN_MAX_ACTIVE_JOBS", 5)
    max_queue_size: int = _int("MAX_QUEUE_SIZE", 300)
    max_file_mb: int = _int("MAX_FILE_MB", 45)

    send_preview: bool = _bool("SEND_PREVIEW", True)
    send_document: bool = _bool("SEND_DOCUMENT", False)
    log_channel_media: bool = _bool("LOG_CHANNEL_MEDIA", False)
    log_channel_text: bool = _bool("LOG_CHANNEL_TEXT", True)

    api_node_timeout: int = _int("API_NODE_TIMEOUT", 8)
    media_download_timeout: int = _int("MEDIA_DOWNLOAD_TIMEOUT", 25)
    node_cooldown_seconds: int = _int("NODE_COOLDOWN_SECONDS", 180)

    def __post_init__(self):
        raw_admin = os.getenv("ADMIN_ID")
        admin = None
        if raw_admin:
            try:
                admin = int(raw_admin)
            except ValueError:
                admin = None
        object.__setattr__(self, "admin_id", admin)


settings = Settings()
