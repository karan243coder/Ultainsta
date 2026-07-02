import logging
import re
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


    def add_monitor(self, username: str, owner_id: int, last_seen: list[str] | None = None) -> None:
        username = username.strip().replace("@", "").lower()
        doc = {
            "_id": f"{int(owner_id)}:{username}",
            "username": username,
            "owner_id": int(owner_id),
            "admin_id": int(owner_id),
            "last_seen_items": last_seen or [],
            "added_at": datetime.utcnow(),
            "last_checked": datetime.utcnow(),
        }
        if self.enabled:
            self.db.monitored_profiles.update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
        else:
            self.local_monitors[doc["_id"]] = doc

    def delete_monitor(self, username: str, owner_id: int | None = None) -> int:
        """
        Robustly removes a monitored profile.
        Supports new docs (_id='owner:username', username, owner_id) and older docs
        (_id='username' or admin_id-only) so admin remove really deletes from Mongo.
        Returns deleted count when available.
        """
        username = username.strip().replace("@", "").lower()
        if not username:
            return 0

        deleted = 0
        if self.enabled:
            escaped = re.escape(username)
            if owner_id is None:
                query = {
                    "$or": [
                        {"username": username},
                        {"_id": username},
                        {"_id": {"$regex": f":{escaped}$"}},
                    ]
                }
            else:
                uid = int(owner_id)
                query = {
                    "$or": [
                        {"username": username, "owner_id": uid},
                        {"username": username, "admin_id": uid},
                        {"_id": f"{uid}:{username}"},
                        {"_id": username, "owner_id": uid},
                        {"_id": username, "admin_id": uid},
                    ]
                }
            try:
                result = self.db.monitored_profiles.delete_many(query)
                deleted = int(getattr(result, "deleted_count", 0) or 0)
            except PyMongoError as e:
                log.warning("delete_monitor mongo error: %s", e)
                deleted = 0
        else:
            keys = []
            for k, v in self.local_monitors.items():
                stored_username = str(v.get("username") or k).split(":")[-1].replace("@", "").lower()
                stored_owner = v.get("owner_id") or v.get("admin_id")
                owner_ok = owner_id is None or (stored_owner is not None and int(stored_owner) == int(owner_id)) or k == f"{owner_id}:{username}"
                if stored_username == username and owner_ok:
                    keys.append(k)
            for k in keys:
                self.local_monitors.pop(k, None)
            deleted = len(keys)
        return deleted

    def list_monitors(self, owner_id: int | None = None) -> List[Dict[str, Any]]:
        if self.enabled:
            try:
                query = {"owner_id": int(owner_id)} if owner_id is not None else {}
                return list(self.db.monitored_profiles.find(query))
            except PyMongoError:
                pass
        vals = list(self.local_monitors.values())
        if owner_id is not None:
            vals = [v for v in vals if v.get("owner_id") == int(owner_id)]
        return vals

    def count_monitors(self, owner_id: int) -> int:
        return len(self.list_monitors(owner_id))

    def update_monitor_seen(self, monitor_id: str, last_seen: list[str]) -> None:
        last_seen = last_seen[-150:]
        if self.enabled:
            self.db.monitored_profiles.update_one({"_id": monitor_id}, {"$set": {"last_seen_items": last_seen, "last_checked": datetime.utcnow()}})
        elif monitor_id in self.local_monitors:
            self.local_monitors[monitor_id]["last_seen_items"] = last_seen
            self.local_monitors[monitor_id]["last_checked"] = datetime.utcnow()


    def get_user_info(self, user_id: int) -> Dict[str, Any]:
        """Returns Telegram user info saved by register_user. Safe fallback if not found."""
        uid = int(user_id)
        if self.enabled:
            try:
                doc = self.db.users.find_one({"_id": uid}) or {}
                return {
                    "_id": uid,
                    "first_name": doc.get("first_name") or "Unknown",
                    "username": doc.get("username") or "NoUsername",
                    "total_downloads": doc.get("total_downloads", 0),
                    "last_active": doc.get("last_active"),
                    "date_joined": doc.get("date_joined"),
                }
            except PyMongoError:
                pass
        return {"_id": uid, "first_name": "Unknown", "username": "NoUsername", "total_downloads": 0}

    def monitor_stats(self) -> Dict[str, int]:
        """Total monitor profiles and unique owners."""
        monitors = self.list_monitors()
        owners = set()
        for m in monitors:
            owner = m.get("owner_id") or m.get("admin_id")
            if owner is not None:
                try:
                    owners.add(int(owner))
                except Exception:
                    pass
        return {"total_monitors": len(monitors), "unique_users": len(owners)}


db = Database()
