import json
import logging
from typing import Optional, Dict, Any, List
from backend.db.database import db_manager

logger = logging.getLogger("ktu.repo")

class ResultRepository:
    """
    High-Performance Repository optimized for sub-2ms reads during peak result traffic.
    """

    async def get_student_result(self, register_number: str, exam_id: str) -> Optional[Dict[str, Any]]:
        """
        Fast single/compound indexed result retrieval.
        Utilizes `idx_summary_reg_exam` for O(1) index lookup.
        """
        reg_clean = register_number.strip().upper()
        
        # 1. Fetch summary + student + exam in a single joined indexed query
        summary_query = """
            SELECT 
                s.id as summary_id,
                s.register_number,
                s.semester,
                s.sgpa,
                s.cgpa,
                s.total_credits,
                s.earned_credits,
                s.status as result_status,
                s.withheld_reason,
                st.name as student_name,
                st.branch_code,
                st.branch_name,
                st.institution_code,
                st.institution_name,
                st.scheme,
                e.id as exam_id,
                e.code as exam_code,
                e.title as exam_title,
                e.session_month_year as exam_session,
                e.is_published
            FROM student_exam_summaries s
            JOIN students st ON st.id = s.student_id
            JOIN examinations e ON e.id = s.exam_id
            WHERE s.register_number = ? AND s.exam_id = ?
            LIMIT 1
        """
        summary_row = await db_manager.fetch_one(summary_query, (reg_clean, exam_id))
        if not summary_row:
            return None

        # If exam is not published, hide result unless admin
        if not summary_row.get("is_published", True):
            return {"status": "UNPUBLISHED", "message": "Results for this examination have not been published yet."}

        summary_id = summary_row["summary_id"]

        # 2. Fetch subject grades indexed on summary_id
        grades_query = """
            SELECT 
                subject_code,
                subject_name,
                credits,
                grade,
                grade_points,
                pass_status
            FROM result_grades
            WHERE summary_id = ?
            ORDER BY subject_code ASC
        """
        grades_rows = await db_manager.fetch_all(grades_query, (summary_id,))

        return {
            "student": {
                "register_number": summary_row["register_number"],
                "name": summary_row["student_name"],
                "branch_code": summary_row["branch_code"],
                "branch_name": summary_row["branch_name"],
                "institution_code": summary_row["institution_code"],
                "institution_name": summary_row["institution_name"],
                "scheme": summary_row["scheme"]
            },
            "exam": {
                "id": summary_row["exam_id"],
                "code": summary_row["exam_code"],
                "title": summary_row["exam_title"],
                "session": summary_row["exam_session"],
                "semester": summary_row["semester"]
            },
            "summary": {
                "sgpa": float(summary_row["sgpa"]) if summary_row["sgpa"] is not None else 0.0,
                "cgpa": float(summary_row["cgpa"]) if summary_row["cgpa"] is not None else 0.0,
                "total_credits": float(summary_row["total_credits"]) if summary_row["total_credits"] is not None else 0.0,
                "earned_credits": float(summary_row["earned_credits"]) if summary_row["earned_credits"] is not None else 0.0,
                "status": summary_row["result_status"],
                "withheld_reason": summary_row.get("withheld_reason")
            },
            "grades": [
                {
                    "code": g["subject_code"],
                    "name": g["subject_name"],
                    "credits": float(g["credits"]),
                    "grade": g["grade"],
                    "grade_points": g["grade_points"],
                    "pass_status": g["pass_status"]
                }
                for g in grades_rows
            ]
        }

    async def get_published_exams(self) -> List[Dict[str, Any]]:
        """Retrieve list of active examinations for search dropdown."""
        query = """
            SELECT id, code, title, session_month_year, semester, scheme, published_at
            FROM examinations
            WHERE is_published = 1
            ORDER BY published_at DESC
        """
        return await db_manager.fetch_all(query)

    async def get_all_exams_admin(self) -> List[Dict[str, Any]]:
        """Retrieve all exams with student count and pass stats for admin portal."""
        query = """
            SELECT 
                e.id, e.code, e.title, e.session_month_year, e.semester, e.is_published, e.published_at,
                COUNT(s.id) as total_students,
                SUM(CASE WHEN s.status = 'PASS' THEN 1 ELSE 0 END) as passed_students,
                AVG(s.sgpa) as avg_sgpa
            FROM examinations e
            LEFT JOIN student_exam_summaries s ON s.exam_id = e.id
            GROUP BY e.id
            ORDER BY e.created_at DESC
        """
        rows = await db_manager.fetch_all(query)
        result = []
        for r in rows:
            tot = r.get("total_students", 0) or 0
            passed = r.get("passed_students", 0) or 0
            pass_rate = round((passed / tot * 100), 1) if tot > 0 else 0.0
            avg_sgpa = round(float(r["avg_sgpa"]), 2) if r.get("avg_sgpa") is not None else 0.0
            result.append({
                "id": r["id"],
                "code": r["code"],
                "title": r["title"],
                "session": r["session_month_year"],
                "semester": r["semester"],
                "is_published": bool(r["is_published"]),
                "published_at": r["published_at"],
                "total_students": tot,
                "passed_students": passed,
                "pass_rate": pass_rate,
                "avg_sgpa": avg_sgpa
            })
        return result

    async def set_exam_published(self, exam_id: str, is_published: bool) -> bool:
        """Toggle exam publication status."""
        query = "UPDATE examinations SET is_published = ? WHERE id = ?"
        await db_manager.execute(query, (1 if is_published else 0, exam_id))
        return True

    async def get_all_register_numbers_for_exam(self, exam_id: str) -> List[str]:
        """Fetch all register numbers for an exam to pre-warm cache."""
        query = "SELECT register_number FROM student_exam_summaries WHERE exam_id = ?"
        rows = await db_manager.fetch_all(query, (exam_id,))
        return [r["register_number"] for r in rows]

    async def get_system_stats(self) -> Dict[str, Any]:
        """Retrieve aggregated database statistics for monitoring."""
        st_count = (await db_manager.fetch_one("SELECT COUNT(*) as c FROM students"))["c"]
        ex_count = (await db_manager.fetch_one("SELECT COUNT(*) as c FROM examinations"))["c"]
        res_count = (await db_manager.fetch_one("SELECT COUNT(*) as c FROM student_exam_summaries"))["c"]
        pass_count = (await db_manager.fetch_one("SELECT COUNT(*) as c FROM student_exam_summaries WHERE status = 'PASS'"))["c"]
        
        pass_rate = round((pass_count / res_count * 100), 1) if res_count > 0 else 0.0
        
        return {
            "total_students": st_count,
            "total_examinations": ex_count,
            "total_results": res_count,
            "overall_pass_rate": pass_rate
        }

    async def get_admin_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Fetch administrator record by username."""
        query = "SELECT id, username, hashed_password, full_name, role FROM admin_users WHERE username = ?"
        return await db_manager.fetch_one(query, (username,))

    async def create_admin_user(self, username: str, hashed_pw: str, full_name: str, role: str = "admin") -> int:
        """Create a new administrator."""
        query = "INSERT OR IGNORE INTO admin_users (username, hashed_password, full_name, role) VALUES (?, ?, ?, ?)"
        return await db_manager.execute(query, (username, hashed_pw, full_name, role))

repository = ResultRepository()
