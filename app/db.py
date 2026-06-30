import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from app.config import settings

log = logging.getLogger("db")


class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.local_users: Set[int] = set()
        self.local_banned: Set[int] = set()
        self.local_admins: Set[int] = set()
        self.local_downloads = 0
        self.local_nodes = list(settings.api_urls)
        self.local_monitors: Dict[str, Dict[str, Any]] = {}

    def connect(self):
        if not settings.mongo_url:
            log.warning("MONGO_URL missing: using in-memory fallback. Data resets on restart.")
            return
        try:
            self.client = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")
            self.db = self.client["instadl_bot_db"]
            log.info("MongoDB connected")
            for url in settings.api_urls:
                self.db.api_nodes.update_one({"url": url}, {"$setOnInsert": {"url": url, "added_at": datetime.utcnow()}}, upsert=True)
        except Exception as e:
            log.exception("MongoDB failed, using in-memory fallback: %s", e)
            self.client = None
            self.db = None

    @property
    def enabled(self) -> bool:
        return self.db is not None

    def register_user(self, user) -> None:
        uid = int(user.id)
        if self.enabled:
            try:
                self.db.users.update_one(
                    {"_id": uid},
                    {"$set": {"first_name": user.first_name or "", "username": user.username or "", "last_active": datetime.utcnow()},
                     "$setOnInsert": {"date_joined": datetime.utcnow(), "total_downloads": 0}},
                    upsert=True,
                )
                return
            except PyMongoError as e:
                log.warning("register_user mongo error: %s", e)
        self.local_users.add(uid)

    def is_banned(self, user_id: int) -> bool:
        if self.enabled:
            try:
                return self.db.banned_users.find_one({"_id": int(user_id)}) is not None
            except PyMongoError:
                pass
        return int(user_id) in self.local_banned

    def ban(self, user_id: int, by: int) -> None:
        if self.enabled:
            self.db.banned_users.update_one({"_id": int(user_id)}, {"$set": {"date_banned": datetime.utcnow(), "banned_by": int(by)}}, upsert=True)
        else:
            self.local_banned.add(int(user_id))

    def unban(self, user_id: int) -> None:
        if self.enabled:
            self.db.banned_users.delete_one({"_id": int(user_id)})
        else:
            self.local_banned.discard(int(user_id))

    def admins_count(self) -> int:
        count = 1 if settings.admin_id else 0
        if self.enabled:
            try:
                return count + self.db.admins.count_documents({})
            except PyMongoError:
                return count
        return count + len(self.local_admins)

    def add_admin(self, user_id: int) -> None:
        if self.enabled:
            self.db.admins.update_one({"_id": int(user_id)}, {"$set": {"date_added": datetime.utcnow()}}, upsert=True)
        else:
            self.local_admins.add(int(user_id))

    def remove_admin(self, user_id: int) -> None:
        if self.enabled:
            self.db.admins.delete_one({"_id": int(user_id)})
        else:
            self.local_admins.discard(int(user_id))

    def is_admin(self, user_id: int) -> bool:
        uid = int(user_id)
        if settings.admin_id and uid == settings.admin_id:
            return True
        if self.enabled:
            try:
                if self.db.admins.find_one({"_id": uid}):
                    return True
            except PyMongoError:
                pass
        if uid in self.local_admins:
            return True
        if self.admins_count() == 0:
            log.warning("No admin configured. First /admin claimant registered: %s", uid)
            self.add_admin(uid)
            return True
        return False

    def stats(self) -> Dict[str, int]:
        if self.enabled:
            try:
                return {
                    "users": self.db.users.count_documents({}),
                    "downloads": self.db.downloads.count_documents({}),
                    "admins": self.admins_count(),
                    "banned": self.db.banned_users.count_documents({}),
                    "nodes": len(self.get_nodes()),
                }
            except PyMongoError:
                pass
        return {"users": len(self.local_users), "downloads": self.local_downloads, "admins": self.admins_count(), "banned": len(self.local_banned), "nodes": len(self.local_nodes)}

    def log_download(self, user_id: int, shortcode: str, media_type: str) -> None:
        if self.enabled:
            try:
                self.db.downloads.insert_one({"user_id": int(user_id), "shortcode": shortcode, "media_type": media_type, "timestamp": datetime.utcnow()})
                self.db.users.update_one({"_id": int(user_id)}, {"$inc": {"total_downloads": 1}})
                return
            except PyMongoError as e:
                log.warning("download log failed: %s", e)
        self.local_downloads += 1

    def get_nodes(self) -> List[str]:
        if self.enabled:
            try:
                nodes = [x["url"].rstrip("/") for x in self.db.api_nodes.find({}) if x.get("url")]
                return nodes or list(settings.api_urls)
            except PyMongoError:
                pass
        return self.local_nodes or list(settings.api_urls)

    def add_node(self, url: str) -> None:
        url = url.strip().rstrip("/")
        if self.enabled:
            self.db.api_nodes.update_one({"url": url}, {"$set": {"url": url, "added_at": datetime.utcnow()}}, upsert=True)
        if url not in self.local_nodes:
            self.local_nodes.append(url)

    def delete_node(self, url: str) -> None:
        url = url.strip().rstrip("/")
        if self.enabled:
            self.db.api_nodes.delete_one({"url": url})
        self.local_nodes = [u for u in self.local_nodes if u != url]


db = Database()
