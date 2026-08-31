import asyncio
import logging
from typing import Dict, Any, Callable, Coroutine

logger = logging.getLogger("ktu.singleflight")

class SingleFlightGroup:
    """
    Request Coalescer / Single-Flight Pattern Manager.
    Prevents cache stampedes and thundering herd problems by ensuring only
    ONE database query is executed for concurrent identical cache misses.
    All concurrent callers await the same in-flight task and receive identical results.
    """
    def __init__(self):
        self._in_flight: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self.coalesced_count = 0  # Total requests saved from hitting DB

    async def do(self, key: str, coro_fn: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
        """
        Execute coro_fn only if key is not currently in-flight.
        If in-flight, await the ongoing future and return its result.
        """
        async with self._lock:
            if key in self._in_flight:
                future = self._in_flight[key]
                self.coalesced_count += 1
                is_leader = False
            else:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._in_flight[key] = future
                is_leader = True

        if not is_leader:
            # Follower: Wait for the leader coroutine to complete
            return await future

        # Leader: Execute the actual fetch operation
        try:
            result = await coro_fn()
            future.set_result(result)
            return result
        except Exception as e:
            future.set_exception(e)
            raise e
        finally:
            async with self._lock:
                if key in self._in_flight:
                    del self._in_flight[key]

single_flight = SingleFlightGroup()
