import asyncio
import logging
import random
import time
from typing import Dict, List, Optional
import aiohttp
from app.config import settings
from app.db import db

log = logging.getLogger("nodes")


class ApiNodeManager:
    def __init__(self):
        self.fail_until: Dict[str, float] = {}
        self.latency_ms: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    def nodes(self) -> List[str]:
        return db.get_nodes()

    async def healthy_nodes(self) -> List[str]:
        now = time.time()
        nodes = [n for n in self.nodes() if self.fail_until.get(n, 0) <= now]
        return nodes or self.nodes()

    async def mark_failed(self, node: str):
        async with self._lock:
            self.fail_until[node] = time.time() + settings.node_cooldown_seconds

    async def fetch_media(self, insta_url: str) -> Optional[dict]:
        nodes = await self.healthy_nodes()
        random.shuffle(nodes)
        fallback = None
        timeout = aiohttp.ClientTimeout(total=settings.api_node_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for node in nodes:
                endpoint = f"{node.rstrip('/')}/api/download"
                started = time.perf_counter()
                try:
                    async with session.post(endpoint, json={"url": insta_url}, headers={"Content-Type": "application/json"}) as resp:
                        elapsed = (time.perf_counter() - started) * 1000
                        self.latency_ms[node] = elapsed
                        if resp.status != 200:
                            await self.mark_failed(node)
                            continue
                        data = await resp.json(content_type=None)
                        if data.get("ok") and data.get("items"):
                            first = data["items"][0].get("url", "")
                            is_fallback = "unsplash.com" in first or "mixkit" in first or "mixkit-girl" in first
                            if is_fallback:
                                fallback = data
                                continue
                            return data
                except Exception as e:
                    log.warning("API node failed %s: %s", node, e)
                    await self.mark_failed(node)
        return fallback

    async def health_report(self) -> List[str]:
        nodes = self.nodes()
        if not nodes:
            return ["No API nodes configured"]
        lines = []
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for i, node in enumerate(nodes, 1):
                started = time.perf_counter()
                try:
                    async with session.get(node) as resp:
                        ms = (time.perf_counter() - started) * 1000
                        lines.append(f"🟢 Node #{i}: {int(ms)}ms ({resp.status})\n<code>{node}</code>")
                except Exception:
                    lines.append(f"🔴 Node #{i}: OFFLINE/TIMEOUT\n<code>{node}</code>")
        return lines


node_manager = ApiNodeManager()
