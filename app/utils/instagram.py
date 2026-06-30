import base64
import re
from html import escape
from typing import Optional, Tuple

RESERVED = {"explore", "developer", "about", "blog", "jobs", "help", "api", "privacy", "terms", "accounts"}


def is_instagram_media_link(text: str) -> bool:
    return bool(re.search(r"instagram\.com/(p|reel|reels|stories|share/p|share/reel|tv|s|stories/highlights)/", text, re.I))


def extract_profile_username(text: str) -> Optional[str]:
    text = text.strip()
    m = re.search(r"instagram\.com/([A-Za-z0-9_.-]+)", text, re.I)
    if m:
        username = m.group(1).strip("/ ").lower()
        return username if username and username not in RESERVED else None
    if text.startswith("@") and len(text) > 1:
        username = text[1:].strip().lower()
        return username if re.fullmatch(r"[A-Za-z0-9_.-]{1,30}", username) else None
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,30}", text) and text.lower() not in {"start", "help", "admin", "ban", "unban", "monitor"}:
        return text.lower()
    return None


def media_id_to_shortcode(media_id: str) -> Optional[str]:
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    try:
        num = int(media_id)
        out = ''
        while num > 0:
            num, rem = divmod(num, 64)
            out = alphabet[rem] + out
        return out or None
    except Exception:
        return None


def extract_shortcode(url: str) -> str:
    story_id_match = re.search(r'stories/[A-Za-z0-9_.-]+/([0-9]+)', url)
    media_id_match = re.search(r'story_media_id=([0-9]+)', url)
    if story_id_match:
        return media_id_to_shortcode(story_id_match.group(1)) or "instadl_media"
    if media_id_match:
        return media_id_to_shortcode(media_id_match.group(1)) or "instadl_media"
    short_highlights = re.search(r'/s/([A-Za-z0-9_-]+)', url)
    if short_highlights:
        encoded = short_highlights.group(1)
        try:
            decoded = base64.b64decode(encoded + "===").decode('utf-8', errors='ignore')
            if 'highlight:' in decoded:
                return decoded.split('highlight:')[1]
        except Exception:
            pass
        return encoded
    long_highlights = re.search(r'stories/highlights/([0-9A-Za-z_-]+)', url)
    if long_highlights:
        return long_highlights.group(1)
    m = re.search(r'(?:p|reel|reels|stories|share/p|share/reel|tv)/([A-Za-z0-9_-]+)', url)
    return m.group(1) if m else 'instadl_media'


def extract_author_userid_from_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    author = None
    uid = None
    m = re.search(r'stories/([A-Za-z0-9_.-]+)/', url)
    if m and m.group(1) != "highlights":
        author = f"@{m.group(1)}"
    u = re.search(r'story_media_id=[0-9]+_([0-9]+)', url)
    if u:
        uid = u.group(1)
    return author, uid


def h(text: object) -> str:
    return escape(str(text or ""), quote=False)
