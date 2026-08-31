-- KTU University High-Performance Examination Result Database Schema
-- Production-Grade Relational Schema with Composite Indexing

-- 1. Students Table
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    register_number VARCHAR(30) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    branch_code VARCHAR(20) NOT NULL,
    branch_name VARCHAR(150),
    institution_code VARCHAR(20) NOT NULL,
    institution_name VARCHAR(200),
    scheme VARCHAR(10) DEFAULT '2019',
    admission_year INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Examinations Table
CREATE TABLE IF NOT EXISTS examinations (
    id VARCHAR(50) PRIMARY KEY,
    code VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    session_month_year VARCHAR(50) NOT NULL,
    semester INTEGER NOT NULL,
    scheme VARCHAR(10) DEFAULT '2019',
    is_published BOOLEAN DEFAULT 1,
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Subjects Table
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(30) NOT NULL,
    name VARCHAR(200) NOT NULL,
    credits NUMERIC(3,1) NOT NULL,
    semester INTEGER NOT NULL,
    branch_code VARCHAR(20),
    scheme VARCHAR(10) DEFAULT '2019',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Student Exam Summaries (One row per student per exam)
CREATE TABLE IF NOT EXISTS student_exam_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    register_number VARCHAR(30) NOT NULL,
    exam_id VARCHAR(50) NOT NULL,
    semester INTEGER NOT NULL,
    sgpa NUMERIC(4,2) NOT NULL DEFAULT 0.0,
    cgpa NUMERIC(4,2) DEFAULT 0.0,
    total_credits NUMERIC(5,1) NOT NULL DEFAULT 0.0,
    earned_credits NUMERIC(5,1) NOT NULL DEFAULT 0.0,
    status VARCHAR(20) NOT NULL DEFAULT 'PASS',
    withheld_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (exam_id) REFERENCES examinations(id) ON DELETE CASCADE
);

-- 5. Result Grades (Detailed Subject-wise marks/grades)
CREATE TABLE IF NOT EXISTS result_grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    exam_id VARCHAR(50) NOT NULL,
    subject_code VARCHAR(30) NOT NULL,
    subject_name VARCHAR(200) NOT NULL,
    credits NUMERIC(3,1) NOT NULL,
    grade VARCHAR(5) NOT NULL,
    grade_points INTEGER NOT NULL,
    pass_status VARCHAR(10) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (summary_id) REFERENCES student_exam_summaries(id) ON DELETE CASCADE
);

-- 6. Administrators Table
CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role VARCHAR(20) DEFAULT 'admin',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Bulk Import Jobs Table
CREATE TABLE IF NOT EXISTS import_jobs (
    id VARCHAR(50) PRIMARY KEY,
    exam_id VARCHAR(50) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    total_rows INTEGER DEFAULT 0,
    processed_rows INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    errors_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- HIGH-PERFORMANCE COMPOSITE INDEXES
-- Designed for sub-2ms lookup under 100k concurrent requests
CREATE UNIQUE INDEX IF NOT EXISTS idx_student_reg ON students(register_number);
CREATE INDEX IF NOT EXISTS idx_student_branch ON students(branch_code, institution_code);
CREATE INDEX IF NOT EXISTS idx_exam_published ON examinations(is_published, semester);
CREATE UNIQUE INDEX IF NOT EXISTS idx_summary_reg_exam ON student_exam_summaries(register_number, exam_id);
CREATE INDEX IF NOT EXISTS idx_summary_exam_status ON student_exam_summaries(exam_id, status);
CREATE INDEX IF NOT EXISTS idx_grades_summary ON result_grades(summary_id);
CREATE INDEX IF NOT EXISTS idx_grades_subject ON result_grades(subject_code, grade);
CREATE INDEX IF NOT EXISTS idx_import_jobs_status ON import_jobs(status, created_at);
