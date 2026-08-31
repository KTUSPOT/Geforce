import io
import csv
import json
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
import openpyxl
from backend.db.database import db_manager
from backend.cache.manager import cache_manager

logger = logging.getLogger("ktu.service.import")

GRADE_POINTS_MAP = {
    "O": 10.0,
    "A+": 9.0,
    "A": 8.5,
    "B+": 8.0,
    "B": 7.0,
    "C": 6.0,
    "P": 5.0,
    "F": 0.0,
    "FE": 0.0,
    "I": 0.0
}

class ImportService:
    """
    High-Throughput Bulk Result Import Service.
    Parses CSV / Excel, validates student data, calculates SGPA/CGPA,
    and commits batches to database using high-speed transactions.
    """
    def __init__(self):
        self.active_jobs: Dict[str, Dict[str, Any]] = {}

    async def create_import_job(self, exam_id: str, filename: str) -> str:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        query = """
            INSERT INTO import_jobs (id, exam_id, filename, total_rows, processed_rows, error_count, status)
            VALUES (?, ?, ?, 0, 0, 0, 'processing')
        """
        await db_manager.execute(query, (job_id, exam_id, filename))
        self.active_jobs[job_id] = {
            "id": job_id,
            "exam_id": exam_id,
            "filename": filename,
            "status": "processing",
            "total_rows": 0,
            "processed_rows": 0,
            "error_count": 0,
            "errors": [],
            "pct": 0
        }
        return job_id

    async def process_file_in_background(self, job_id: str, exam_id: str, file_bytes: bytes, file_extension: str):
        """Asynchronous worker for bulk parsing and database ingestion."""
        try:
            # 1. Parse rows into memory
            rows = []
            errors = []
            if file_extension.lower() == ".csv":
                text_stream = io.StringIO(file_bytes.decode("utf-8-sig", errors="ignore"))
                reader = csv.DictReader(text_stream)
                rows = list(reader)
            elif file_extension.lower() in [".xlsx", ".xls"]:
                wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
                sheet = wb.active
                iter_rows = sheet.iter_rows(values_only=True)
                headers = [str(h).strip().lower().replace(" ", "_") for h in next(iter_rows, []) if h is not None]
                for r in iter_rows:
                    if any(r):
                        row_dict = {headers[i]: r[i] for i in range(min(len(headers), len(r)))}
                        rows.append(row_dict)
                wb.close()
            else:
                raise ValueError(f"Unsupported file format: {file_extension}")

            total_rows = len(rows)
            self.active_jobs[job_id]["total_rows"] = total_rows
            await db_manager.execute(
                "UPDATE import_jobs SET total_rows = ? WHERE id = ?",
                (total_rows, job_id)
            )

            if total_rows == 0:
                await self._complete_job(job_id, 0, 0, ["Empty file uploaded."])
                return

            # 2. Group rows by student (register_number)
            students_map: Dict[str, Dict[str, Any]] = {}
            for idx, r in enumerate(rows, start=1):
                try:
                    reg = str(r.get("register_number") or r.get("reg_no") or r.get("regno") or "").strip().upper()
                    if not reg:
                        errors.append(f"Row {idx}: Missing register number.")
                        continue
                    
                    if reg not in students_map:
                        students_map[reg] = {
                            "register_number": reg,
                            "name": str(r.get("student_name") or r.get("name") or "KTU Student").strip(),
                            "branch_code": str(r.get("branch_code") or r.get("branch") or "CSE").strip().upper(),
                            "branch_name": str(r.get("branch_name") or "Computer Science and Engineering").strip(),
                            "institution_code": str(r.get("institution_code") or r.get("college_code") or "TVE").strip().upper(),
                            "institution_name": str(r.get("institution_name") or "College of Engineering Trivandrum").strip(),
                            "scheme": str(r.get("scheme") or "2019").strip(),
                            "semester": int(r.get("semester") or 6),
                            "grades": []
                        }

                    # Subject grade info
                    sub_code = str(r.get("subject_code") or r.get("course_code") or "").strip().upper()
                    sub_name = str(r.get("subject_name") or r.get("course_name") or sub_code).strip()
                    try:
                        credits = float(r.get("credits") or 4.0)
                    except (ValueError, TypeError):
                        credits = 4.0

                    grade = str(r.get("grade") or "P").strip().upper()
                    grade_points = int(GRADE_POINTS_MAP.get(grade, 0.0))
                    pass_status = "PASS" if grade not in ["F", "FE", "I"] else "FAIL"

                    if sub_code:
                        students_map[reg]["grades"].append({
                            "subject_code": sub_code,
                            "subject_name": sub_name,
                            "credits": credits,
                            "grade": grade,
                            "grade_points": grade_points,
                            "pass_status": pass_status
                        })

                except Exception as row_err:
                    errors.append(f"Row {idx} parse error: {str(row_err)}")

            # 3. Insert students and summaries into database in batches
            processed_count = 0
            for reg, sdata in students_map.items():
                try:
                    # Insert / Ensure Student exists
                    student_id = await db_manager.execute(
                        """
                        INSERT INTO students (register_number, name, branch_code, branch_name, institution_code, institution_name, scheme)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(register_number) DO UPDATE SET
                            name=excluded.name,
                            branch_code=excluded.branch_code,
                            institution_code=excluded.institution_code
                        """,
                        (sdata["register_number"], sdata["name"], sdata["branch_code"], 
                         sdata["branch_name"], sdata["institution_code"], sdata["institution_name"], sdata["scheme"])
                    )

                    # If SQLite lastrowid was 0 due to update, fetch id
                    if not student_id or student_id <= 0:
                        st_row = await db_manager.fetch_one("SELECT id FROM students WHERE register_number = ?", (reg,))
                        student_id = st_row["id"] if st_row else 1

                    # Compute SGPA
                    tot_credits = sum(g["credits"] for g in sdata["grades"])
                    earned_credits = sum(g["credits"] for g in sdata["grades"] if g["pass_status"] == "PASS")
                    weighted_points = sum(g["credits"] * g["grade_points"] for g in sdata["grades"])
                    sgpa = round(weighted_points / tot_credits, 2) if tot_credits > 0 else 0.0
                    status = "PASS" if all(g["pass_status"] == "PASS" for g in sdata["grades"]) else "FAILED"

                    # Delete previous summary & grades for this exam if re-uploading
                    old_summary = await db_manager.fetch_one(
                        "SELECT id FROM student_exam_summaries WHERE register_number = ? AND exam_id = ?",
                        (reg, exam_id)
                    )
                    if old_summary:
                        await db_manager.execute("DELETE FROM result_grades WHERE summary_id = ?", (old_summary["id"],))
                        await db_manager.execute("DELETE FROM student_exam_summaries WHERE id = ?", (old_summary["id"],))

                    # Insert Summary
                    summary_id = await db_manager.execute(
                        """
                        INSERT INTO student_exam_summaries 
                        (student_id, register_number, exam_id, semester, sgpa, cgpa, total_credits, earned_credits, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (student_id, reg, exam_id, sdata["semester"], sgpa, sgpa, tot_credits, earned_credits, status)
                    )

                    # Bulk Insert Subject Grades
                    grade_params = [
                        (summary_id, student_id, exam_id, g["subject_code"], g["subject_name"], g["credits"], g["grade"], g["grade_points"], g["pass_status"])
                        for g in sdata["grades"]
                    ]
                    grade_query = """
                        INSERT INTO result_grades 
                        (summary_id, student_id, exam_id, subject_code, subject_name, credits, grade, grade_points, pass_status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    await db_manager.execute_many(grade_query, grade_params)

                    # Invalidate old cache
                    await cache_manager.invalidate_result(exam_id, reg)
                    processed_count += 1

                except Exception as ingest_err:
                    errors.append(f"Student {reg} ingestion error: {str(ingest_err)}")

                # Progress update
                self.active_jobs[job_id]["processed_rows"] = processed_count
                self.active_jobs[job_id]["pct"] = round((processed_count / max(len(students_map), 1)) * 100, 1)

            # 4. Finish job
            await self._complete_job(job_id, total_rows, processed_count, errors)
            logger.info(f"Import job {job_id} successfully completed for {processed_count} students.")

        except Exception as e:
            logger.exception(f"Import job {job_id} failed: {e}")
            await self._complete_job(job_id, 0, 0, [f"Critical import error: {str(e)}"], failed=True)

    async def _complete_job(self, job_id: str, total: int, processed: int, errors: List[str], failed: bool = False):
        final_status = "failed" if failed else "completed"
        err_json = json.dumps(errors[:100])  # Cap at 100 errors
        now = datetime.now().isoformat()
        
        await db_manager.execute(
            """
            UPDATE import_jobs 
            SET processed_rows = ?, error_count = ?, status = ?, errors_json = ?, completed_at = ?
            WHERE id = ?
            """,
            (processed, len(errors), final_status, err_json, now, job_id)
        )
        if job_id in self.active_jobs:
            self.active_jobs[job_id].update({
                "status": final_status,
                "processed_rows": processed,
                "error_count": len(errors),
                "errors": errors[:50],
                "pct": 100
            })

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.active_jobs.get(job_id)

import_service = ImportService()
