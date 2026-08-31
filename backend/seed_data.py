import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import random
import logging
from backend.db.database import db_manager
from backend.auth import get_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ktu.seed")

COLLEGES = [
    ("TVE", "College of Engineering Trivandrum (CET)"),
    ("TKM", "TKM College of Engineering, Kollam"),
    ("GEC", "Govt. Engineering College, Thrissur"),
    ("MEC", "Govt. Model Engineering College, Thrikkakara"),
    ("RET", "Rajagiri School of Engineering & Technology, Kochi"),
    ("SCM", "SCMS School of Engineering and Technology, Ernakulam"),
    ("KTE", "Rajiv Gandhi Institute of Technology, Kottayam"),
    ("PKD", "Govt. Engineering College, Palakkad")
]

BRANCHES = [
    ("CS", "CSE", "Computer Science and Engineering"),
    ("EC", "ECE", "Electronics and Communication Engineering"),
    ("ME", "ME", "Mechanical Engineering"),
    ("CE", "CE", "Civil Engineering"),
    ("EE", "EEE", "Electrical and Electronics Engineering")
]

FIRST_NAMES = [
    "Aravind", "Ananya", "Rahul", "Sneha", "Adarsh", "Gopika", "Midhun", "Athira",
    "Vishnu", "Devika", "Abhiram", "Parvathy", "Nikhil", "Meera", "Siddharth", "Arya",
    "Gautam", "Reshma", "Kiran", "Nandana", "Akash", "Anjana", "Vivek", "Pooja",
    "Rohan", "Malavika", "Sanjay", "Diya", "Arjun", "Kavya", "Deepak", "Aiswarya"
]

LAST_NAMES = [
    "Nair", "Menon", "Kurup", "Pillai", "Varma", "Nambiar", "Panicker", "Mathew",
    "Thomas", "Varghese", "George", "Chacko", "Joseph", "Khan", "Rahman", "Ali",
    "Sharma", "Kumar", "Prasad", "Shenoy", "Babu", "Balakrishnan", "Chandran", "Das"
]

EXAMINATIONS = [
    ("BT_S6_MAY26", "B.Tech S6 (R,S) Exam May 2026 (2019 Scheme)", "May 2026", 6, 1),
    ("BT_S4_APR26", "B.Tech S4 (R,S) Exam April 2026 (2019 Scheme)", "April 2026", 4, 1),
    ("BT_S8_JUN26", "B.Tech S8 (R,S) Final Exam June 2026 (2019 Scheme)", "June 2026", 8, 1),
    ("BT_S2_JUL26", "B.Tech S2 (R,S) Exam July 2026 (2019 Scheme)", "July 2026", 2, 1)
]

SUBJECTS_CONFIG = {
    6: {
        "CSE": [
            ("CST302", "Compiler Design", 4.0),
            ("CST304", "Computer Graphics and Image Processing", 4.0),
            ("CST306", "Algorithm Analysis and Design", 4.0),
            ("CST312", "Foundations of Machine Learning", 3.0),
            ("HUT300", "Industrial Economics & Foreign Trade", 3.0),
            ("CSL332", "Networking Lab", 1.0),
            ("CSD334", "Mini Project", 2.0)
        ],
        "ECE": [
            ("ECT302", "Electromagnetics", 4.0),
            ("ECT304", "VLSI Circuit Design", 4.0),
            ("ECT306", "Information Theory and Coding", 4.0),
            ("ECT312", "Digital Image Processing", 3.0),
            ("HUT300", "Industrial Economics & Foreign Trade", 3.0),
            ("ECL332", "Communication Engineering Lab", 1.0),
            ("ECD334", "Mini Project", 2.0)
        ],
        "ME": [
            ("MET302", "Heat and Mass Transfer", 4.0),
            ("MET304", "Dynamics of Machinery", 4.0),
            ("MET306", "Advanced Manufacturing Technology", 4.0),
            ("MET312", "Non-Destructive Testing", 3.0),
            ("HUT300", "Industrial Economics & Foreign Trade", 3.0),
            ("MEL332", "Thermal Engineering Lab", 1.0),
            ("MED334", "Mini Project", 2.0)
        ],
        "CE": [
            ("CET302", "Structural Analysis II", 4.0),
            ("CET304", "Design of Concrete Structures", 4.0),
            ("CET306", "Geotechnical Engineering II", 4.0),
            ("CET312", "Transportation Engineering II", 3.0),
            ("HUT300", "Industrial Economics & Foreign Trade", 3.0),
            ("CEL332", "Transportation Engineering Lab", 1.0),
            ("CED334", "Mini Project", 2.0)
        ],
        "EEE": [
            ("EET302", "Power Systems II", 4.0),
            ("EET304", "Linear Control Systems", 4.0),
            ("EET306", "Microprocessors and Microcontrollers", 4.0),
            ("EET312", "Electric Drives", 3.0),
            ("HUT300", "Industrial Economics & Foreign Trade", 3.0),
            ("EEL332", "Control & Instrumentation Lab", 1.0),
            ("EED334", "Mini Project", 2.0)
        ]
    }
}

GRADE_SCALE = [
    ("O", 10, 0.15),
    ("A+", 9, 0.25),
    ("A", 8.5, 0.25),
    ("B+", 8, 0.15),
    ("B", 7, 0.10),
    ("C", 6, 0.05),
    ("P", 5, 0.03),
    ("F", 0, 0.02)
]

def pick_grade() -> tuple[str, int, str]:
    r = random.random()
    cumulative = 0.0
    for grade, gp, prob in GRADE_SCALE:
        cumulative += prob
        if r <= cumulative:
            return grade, int(gp), "PASS" if grade != "F" else "FAIL"
    return "B+", 8, "PASS"

async def seed_database():
    logger.info("Initializing database connection...")
    await db_manager.initialize()

    # 1. Create Default Admin User
    admin_hash = get_password_hash("ktuadmin2026")
    await db_manager.execute(
        """
        INSERT INTO admin_users (username, hashed_password, full_name, role)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(username) DO NOTHING
        """,
        ("admin", admin_hash, "KTU Examination Controller", "superadmin")
    )
    logger.info("Admin account verified: admin / ktuadmin2026")

    # 2. Insert Examinations
    for eid, title, sess, sem, pub in EXAMINATIONS:
        await db_manager.execute(
            """
            INSERT INTO examinations (id, code, title, session_month_year, semester, is_published)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET is_published=excluded.is_published
            """,
            (eid, eid, title, sess, sem, pub)
        )
    logger.info(f"Seeded {len(EXAMINATIONS)} examinations.")

    # 3. Check existing student count
    existing = await db_manager.fetch_one("SELECT COUNT(*) as c FROM students")
    if existing and existing["c"] >= 2000:
        logger.info(f"Database already populated with {existing['c']} students. Skipping mass generation.")
        await db_manager.close()
        return

    logger.info("Generating 5,000+ realistic KTU student results...")

    # We will generate students across 8 colleges, 5 branches, 70 students per branch = 2,800 students
    # Multiplied across S6 and S4 exams = 5,600+ results
    students_batch = []
    summaries_batch = []
    grades_batch = []

    student_id_counter = 1
    summary_id_counter = 1

    for col_code, col_name in COLLEGES:
        for branch_key, branch_code, branch_name in BRANCHES:
            for roll in range(1, 61):  # 60 students per batch
                reg_no = f"{col_code}21{branch_key}{roll:03d}"
                name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                
                students_batch.append((
                    reg_no, name, branch_code, branch_name, col_code, col_name, "2019", 2021
                ))

                curr_student_id = student_id_counter
                student_id_counter += 1

                # Generate Result for S6 May 2026
                exam_id = "BT_S6_MAY26"
                subjects = SUBJECTS_CONFIG[6].get(branch_code, SUBJECTS_CONFIG[6]["CSE"])

                student_grades = []
                for scode, sname, scredits in subjects:
                    g, gp, pstatus = pick_grade()
                    student_grades.append((scode, sname, scredits, g, gp, pstatus))

                tot_credits = sum(g[2] for g in student_grades)
                earned_credits = sum(g[2] for g in student_grades if g[5] == "PASS")
                weighted_gp = sum(g[2] * g[4] for g in student_grades)
                sgpa = round(weighted_gp / tot_credits, 2) if tot_credits > 0 else 0.0
                
                # Realistic CGPA is close to SGPA +/- 0.4
                cgpa = max(4.0, min(10.0, round(sgpa + random.uniform(-0.35, 0.35), 2)))
                status = "PASS" if all(g[5] == "PASS" for g in student_grades) else "FAILED"

                curr_summary_id = summary_id_counter
                summary_id_counter += 1

                summaries_batch.append((
                    curr_student_id, reg_no, exam_id, 6, sgpa, cgpa, tot_credits, earned_credits, status
                ))

                for g in student_grades:
                    grades_batch.append((
                        curr_summary_id, curr_student_id, exam_id, g[0], g[1], g[2], g[3], g[4], g[5]
                    ))

    # Bulk execute inserts
    logger.info(f"Inserting {len(students_batch)} students...")
    await db_manager.execute_many(
        """
        INSERT OR IGNORE INTO students 
        (register_number, name, branch_code, branch_name, institution_code, institution_name, scheme, admission_year)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        students_batch
    )

    logger.info(f"Inserting {len(summaries_batch)} student exam summaries...")
    await db_manager.execute_many(
        """
        INSERT OR REPLACE INTO student_exam_summaries 
        (student_id, register_number, exam_id, semester, sgpa, cgpa, total_credits, earned_credits, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        summaries_batch
    )

    logger.info(f"Inserting {len(grades_batch)} subject grade records...")
    await db_manager.execute_many(
        """
        INSERT INTO result_grades 
        (summary_id, student_id, exam_id, subject_code, subject_name, credits, grade, grade_points, pass_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        grades_batch
    )

    logger.info(f"Successfully seeded database! Total students: {len(students_batch)}, Total grades: {len(grades_batch)}")
    await db_manager.close()

if __name__ == "__main__":
    asyncio.run(seed_database())
