import time
import json
import logging
from typing import Optional, Dict, Any
from collections import OrderedDict
from backend.config import settings

logger = logging.getLogger("ktu.cache")

class LRUMemoryCache:
    """Fast in-process LRU cache with TTL."""
    def __init__(self, max_items: int = 20000, default_ttl: int = 300):
        self.max_items = max_items
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        val, expiry = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return val

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        if ttl is None:
            ttl = self.default_ttl
        expiry = time.time() + ttl
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, expiry)
        if len(self._cache) > self.max_items:
            self._cache.popitem(last=False)

    def delete(self, key: str):
        if key in self._cache:
            del self._cache[key]

    def clear(self):
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)

class CacheManager:
    """
    Multi-Tier Cache Manager (L1 Memory Cache + L2 Redis Distributed Cache).
    Provides sub-millisecond retrieval and auto-failover.
    """
    def __init__(self):
        self.l1 = LRUMemoryCache(
            max_items=settings.L1_CACHE_MAX_ITEMS, 
            default_ttl=settings.L1_CACHE_TTL
        )
        self.redis_client = None
        self.redis_available = False
        self.stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "misses": 0,
            "sets": 0
        }

    async def initialize(self):
        """Connect to Redis if enabled."""
        if not settings.REDIS_ENABLED:
            logger.info("Redis disabled via config. Using L1 in-memory caching only.")
            return

        try:
            import redis.asyncio as aioredis
            self.redis_client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=1.5,
                socket_connect_timeout=2.0,
                max_connections=50
            )
            # Test ping
            await self.redis_client.ping()
            self.redis_available = True
            logger.info(f"Connected to Redis at {settings.REDIS_URL}")
        except Exception as e:
            self.redis_available = False
            logger.warning(f"Redis not available ({e}). Operating in high-speed L1 in-memory cache mode.")

    @staticmethod
    def make_result_key(exam_id: str, register_number: str) -> str:
        norm_reg = register_number.strip().upper()
        norm_exam = exam_id.strip()
        return f"result:{norm_exam}:{norm_reg}"

    async def get_result(self, exam_id: str, register_number: str) -> Optional[Dict[str, Any]]:
        key = self.make_result_key(exam_id, register_number)
        
        # 1. Check L1 Memory Cache (0.05ms)
        l1_val = self.l1.get(key)
        if l1_val is not None:
            self.stats["l1_hits"] += 1
            return l1_val

        # 2. Check L2 Redis Cache (0.8ms)
        if self.redis_available and self.redis_client:
            try:
                raw = await self.redis_client.get(key)
                if raw:
                    data = json.loads(raw)
                    # Promote into L1 for subsequent ultra-fast hits
                    self.l1.set(key, data, ttl=settings.L1_CACHE_TTL)
                    self.stats["l2_hits"] += 1
                    return data
            except Exception as e:
                logger.error(f"Redis read error: {e}")

        self.stats["misses"] += 1
        return None

    async def set_result(self, exam_id: str, register_number: str, data: Dict[str, Any], ttl: Optional[int] = None):
        key = self.make_result_key(exam_id, register_number)
        if ttl is None:
            ttl = settings.CACHE_DEFAULT_TTL

        # Set in L1 Memory Cache
        self.l1.set(key, data, ttl=min(ttl, settings.L1_CACHE_TTL))

        # Set in L2 Redis Cache
        if self.redis_available and self.redis_client:
            try:
                payload = json.dumps(data, separators=(",", ":"))
                await self.redis_client.set(key, payload, ex=ttl)
            except Exception as e:
                logger.error(f"Redis write error: {e}")

        self.stats["sets"] += 1

    async def invalidate_result(self, exam_id: str, register_number: str):
        key = self.make_result_key(exam_id, register_number)
        self.l1.delete(key)
        if self.redis_available and self.redis_client:
            try:
                await self.redis_client.delete(key)
            except Exception as e:
                logger.error(f"Redis delete error: {e}")

    async def invalidate_exam(self, exam_id: str):
        """Invalidate all cached results for an examination."""
        self.l1.clear()
        if self.redis_available and self.redis_client:
            try:
                keys = []
                async for k in self.redis_client.scan_iter(f"result:{exam_id}:*"):
                    keys.append(k)
                    if len(keys) >= 500:
                        await self.redis_client.delete(*keys)
                        keys = []
                if keys:
                    await self.redis_client.delete(*keys)
            except Exception as e:
                logger.error(f"Redis exam flush error: {e}")

    def get_stats(self) -> Dict[str, Any]:
        total_requests = self.stats["l1_hits"] + self.stats["l2_hits"] + self.stats["misses"]
        total_hits = self.stats["l1_hits"] + self.stats["l2_hits"]
        hit_rate = round((total_hits / total_requests * 100), 2) if total_requests > 0 else 100.0
        return {
            **self.stats,
            "total_requests": total_requests,
            "hit_rate_pct": hit_rate,
            "l1_items_count": self.l1.size(),
            "redis_connected": self.redis_available
        }

    async def close(self):
        if self.redis_client:
            await self.redis_client.close()

cache_manager = CacheManager()
