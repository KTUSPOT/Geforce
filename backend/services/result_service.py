import re
import time
import logging
from typing import Optional, Dict, Any
from backend.cache.manager import cache_manager
from backend.cache.singleflight import single_flight
from backend.db.repository import repository
from backend.monitoring.metrics import (
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    SINGLEFLIGHT_SAVED_TOTAL
)

logger = logging.getLogger("ktu.service.result")

# Standard KTU Register Number regex pattern (e.g. TVE21CS001, KTE20ME045, RET19EC012)
KTU_REG_PATTERN = re.compile(r"^[A-Z]{3}\d{2}[A-Z]{2}\d{3}$", re.IGNORECASE)

class ResultService:
    """
    Ultra-High-Performance Student Result Service.
    Implements: L1 Cache -> L2 Redis -> SingleFlight Coalescer -> Indexed Database.
    """

    async def search_result(self, register_number: str, exam_id: str) -> Dict[str, Any]:
        reg_clean = register_number.strip().upper()
        exam_clean = exam_id.strip()

        # 1. Validation
        if not reg_clean:
            return {"success": False, "error": "Register number is required", "status_code": 400}
        
        if not exam_clean:
            return {"success": False, "error": "Examination selection is required", "status_code": 400}

        # 2. Multi-tier Cache Check (L1 Memory Cache -> L2 Redis)
        cached_result = await cache_manager.get_result(exam_clean, reg_clean)
        if cached_result is not None:
            CACHE_HITS_TOTAL.labels(tier="redis_or_l1").inc()
            return {
                "success": True,
                "data": cached_result,
                "cached": True,
                "source": "cache"
            }

        CACHE_MISSES_TOTAL.inc()

        # 3. Single-Flight Coalescing: Thundering Herd Protection
        # If 10,000 requests query this exact register_number during a cache miss,
        # single_flight ensures ONLY 1 database query executes.
        flight_key = f"db_fetch:{exam_clean}:{reg_clean}"
        initial_coalesced_count = single_flight.coalesced_count

        async def fetch_from_db():
            db_start = time.perf_counter()
            data = await repository.get_student_result(reg_clean, exam_clean)
            query_time_ms = (time.perf_counter() - db_start) * 1000
            logger.debug(f"DB query for {reg_clean} took {query_time_ms:.2f}ms")
            return data

        db_result = await single_flight.do(flight_key, fetch_from_db)

        # Track saved queries in Prometheus
        saved = single_flight.coalesced_count - initial_coalesced_count
        if saved > 0:
            SINGLEFLIGHT_SAVED_TOTAL.inc(saved)

        if not db_result:
            return {
                "success": False,
                "error": f"No result found for Register No. '{reg_clean}' in selected examination.",
                "status_code": 404
            }

        if db_result.get("status") == "UNPUBLISHED":
            return {
                "success": False,
                "error": db_result.get("message", "Result not published yet."),
                "status_code": 403
            }

        # 4. Asynchronously populate cache for future requests
        await cache_manager.set_result(exam_clean, reg_clean, db_result)

        return {
            "success": True,
            "data": db_result,
            "cached": False,
            "source": "database"
        }

result_service = ResultService()
