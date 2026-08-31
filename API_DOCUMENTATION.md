# KTU University Examination Result API — Technical Specification

Comprehensive RESTful API documentation for APJ Abdul Kalam Technological University (KTU) examination results, cache management, and bulk ingestion.

---

## Base URLs
- **Local Standalone**: `http://localhost:8000`
- **Docker Production (Nginx)**: `http://localhost:80`

---

## 1. Student Public Endpoints

### 1.1 Fetch Student Result
Retrieve provisional result card for a specific student register number and examination.

- **Method**: `GET`
- **Path**: `/api/v1/results`
- **Rate Limit**: 60 req/min (Burst: 15)
- **Caching**: L1 Memory (<0.1ms) -> L2 Redis (<1ms) -> Single-Flight Coalescer (<2ms)

#### Query Parameters
| Parameter | Type | Required | Description | Example |
| :--- | :--- | :--- | :--- | :--- |
| `registerNumber` | string | **Yes** | KTU Student Register Number | `TVE21CS001` |
| `examId` | string | **Yes** | Target Examination ID | `BT_S6_MAY26` |

#### Request Example
```bash
curl -X GET "http://localhost:8000/api/v1/results?registerNumber=TVE21CS001&examId=BT_S6_MAY26"
```

#### Response Example (200 OK)
```json
{
  "success": true,
  "cached": true,
  "source": "cache",
  "data": {
    "student": {
      "register_number": "TVE21CS001",
      "name": "Aravind Nair",
      "branch_code": "CSE",
      "branch_name": "Computer Science and Engineering",
      "institution_code": "TVE",
      "institution_name": "College of Engineering Trivandrum (CET)",
      "scheme": "2019"
    },
    "exam": {
      "id": "BT_S6_MAY26",
      "code": "BT_S6_MAY26",
      "title": "B.Tech S6 (R,S) Exam May 2026 (2019 Scheme)",
      "session": "May 2026",
      "semester": 6
    },
    "summary": {
      "sgpa": 8.78,
      "cgpa": 8.65,
      "total_credits": 21.0,
      "earned_credits": 21.0,
      "status": "PASS",
      "withheld_reason": null
    },
    "grades": [
      {
        "code": "CSD334",
        "name": "Mini Project",
        "credits": 2.0,
        "grade": "O",
        "grade_points": 10,
        "pass_status": "PASS"
      },
      {
        "code": "CSL332",
        "name": "Networking Lab",
        "credits": 1.0,
        "grade": "A+",
        "grade_points": 9,
        "pass_status": "PASS"
      },
      {
        "code": "CST302",
        "name": "Compiler Design",
        "credits": 4.0,
        "grade": "A",
        "grade_points": 8,
        "pass_status": "PASS"
      }
    ]
  }
}
```

---

### 1.2 Get Active Examinations
Fetches all currently published examination sessions for populating search dropdowns.

- **Method**: `GET`
- **Path**: `/api/v1/exams`

#### Request Example
```bash
curl -X GET "http://localhost:8000/api/v1/exams"
```

---

## 2. Administrator & Publication Endpoints

### 2.1 Admin Authentication
Generate JWT access token for administrative actions.

- **Method**: `POST`
- **Path**: `/api/v1/admin/auth/login`

#### Request Body
```json
{
  "username": "admin",
  "password": "ktuadmin2026"
}
```

#### Response Example
```json
{
  "success": true,
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
  "token_type": "bearer",
  "user": {
    "username": "admin",
    "name": "KTU Examination Controller",
    "role": "superadmin"
  }
}
```

---

### 2.2 Trigger Cache Pre-Warming
Pre-populates Redis cache for an entire examination before public announcement.

- **Method**: `POST`
- **Path**: `/api/v1/admin/cache/warm`
- **Headers**: `Authorization: Bearer <TOKEN>`

#### Request Body
```json
{
  "exam_id": "BT_S6_MAY26"
}
```

---

### 2.3 Bulk Result Upload
Streams CSV / Excel spreadsheet to background ingestion worker.

- **Method**: `POST`
- **Path**: `/api/v1/admin/results/upload`
- **Headers**: `Authorization: Bearer <TOKEN>`, `Content-Type: multipart/form-data`

#### Form Fields
- `exam_id`: `BT_S6_MAY26`
- `file`: `sample_results.csv`

---

## 3. Health & Telemetry

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/health/live` | `GET` | Container liveness probe |
| `/health/ready` | `GET` | Readiness probe (verifies DB & Redis) |
| `/metrics` | `GET` | Prometheus telemetry scraper |
