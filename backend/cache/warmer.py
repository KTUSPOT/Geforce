import asyncio
import logging
from typing import Dict, Any, Optional
from backend.db.repository import repository
from backend.cache.manager import cache_manager

logger = logging.getLogger("ktu.warmer")

class CacheWarmer:
    """
    Asynchronous Cache Pre-Warming Engine.
    Pre-populates Redis L2 cache before result announcements so that 100,000+
    students experience immediate sub-millisecond cache hits without hammering the database.
    """
    def __init__(self):
        self.active_jobs: Dict[str, Dict[str, Any]] = {}

    async def start_warming_job(self, exam_id: str, batch_size: int = 200) -> str:
        job_id = f"warm_{exam_id}"
        self.active_jobs[job_id] = {
            "exam_id": exam_id,
            "status": "running",
            "total": 0,
            "processed": 0,
            "pct": 0,
            "message": "Initializing cache warming pipeline..."
        }
        # Run warming as an unblocked background coroutine
        asyncio.create_task(self._run_warming(job_id, exam_id, batch_size))
        return job_id

    async def _run_warming(self, job_id: str, exam_id: str, batch_size: int):
        try:
            reg_numbers = await repository.get_all_register_numbers_for_exam(exam_id)
            total = len(reg_numbers)
            self.active_jobs[job_id]["total"] = total
            self.active_jobs[job_id]["message"] = f"Warming {total} student result records..."

            if total == 0:
                self.active_jobs[job_id]["status"] = "completed"
                self.active_jobs[job_id]["pct"] = 100
                self.active_jobs[job_id]["message"] = "No students found for this examination."
                return

            processed = 0
            for i in range(0, total, batch_size):
                chunk = reg_numbers[i:i + batch_size]
                tasks = [self._warm_single_student(exam_id, reg) for reg in chunk]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                processed += len(chunk)
                pct = round((processed / total) * 100, 1)
                self.active_jobs[job_id]["processed"] = processed
                self.active_jobs[job_id]["pct"] = pct
                self.active_jobs[job_id]["message"] = f"Warmed {processed}/{total} student results ({pct}%)"
                
                # Small micro-pause to avoid starving event loop
                await asyncio.sleep(0.01)

            self.active_jobs[job_id]["status"] = "completed"
            self.active_jobs[job_id]["pct"] = 100
            self.active_jobs[job_id]["message"] = f"Successfully pre-warmed {total} student results in cache!"
            logger.info(f"Cache warming job {job_id} completed for {total} students.")
        except Exception as e:
            logger.exception(f"Cache warming failed for {exam_id}: {e}")
            self.active_jobs[job_id]["status"] = "failed"
            self.active_jobs[job_id]["message"] = f"Error during warming: {str(e)}"

    async def _warm_single_student(self, exam_id: str, register_number: str):
        try:
            data = await repository.get_student_result(register_number, exam_id)
            if data:
                await cache_manager.set_result(exam_id, register_number, data)
        except Exception as e:
            logger.error(f"Error pre-warming {register_number}: {e}")

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.active_jobs.get(job_id)

cache_warmer = CacheWarmer()
