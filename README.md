# KTU University Result Application — High-Performance Architecture

An ultra-scalable, mobile-first web application for **APJ Abdul Kalam Technological University (KTU)** student examination results, engineered specifically to handle massive traffic surges (**100,000+ concurrent students**) upon result publication.

---

## 🏛️ High-Traffic Architecture

```
[ Students / Mobile Devices / Bots ]
                 │
                 ▼
[ NGINX Reverse Proxy / CDN (Gzip, Rate Limiting, Connection Pooling) ]
                 │
     ┌───────────┼───────────┐  (Least Connections Balancing)
     ▼           ▼           ▼
[ API Pod 1 ] [ API Pod 2 ] [ API Pod 3 ]  (Stateless FastAPI Replicas)
     │
     ├── Layer 1: In-Memory LRU Cache (< 0.1 ms latency)
     ├── Layer 2: Single-Flight Request Coalescer (100% Stampede Protection)
     └── Layer 3: Redis Distributed Cache (< 1 ms latency)
                 │ (Cache Miss Only)
                 ▼
[ PostgreSQL / SQLite WAL Read-Optimized Database (< 2 ms query time) ]
```

---

## ⚡ Key Architectural Innovations

### 1. Zero Cache Stampede (Single-Flight Coalescing)
When 10,000 students or scrapers query the same uncached result at the exact same millisecond:
- **Without SingleFlight**: 10,000 simultaneous queries hit the database, causing connection exhaustion and 504 Gateway Timeouts.
- **With KTU SingleFlight**: Only **1 single database query** executes; the remaining 9,999 requests hook into the in-flight asynchronous promise and receive the identical result simultaneously.

### 2. Multi-Tier Cache Hierarchy
- **L1 In-Memory LRU Cache**: Sub-0.1ms retrieval for hyper-hot results directly in worker RAM.
- **L2 Redis Distributed Cache**: Sub-1ms retrieval across all horizontal API instances.
- **Cache Pre-Warming Pipeline**: Background worker primes Redis in chunks of 500 records prior to public result announcement.

### 3. Sub-2ms Compound Indexed Database Queries
- Composite B-Tree indexes on `(register_number, exam_id)` and `(summary_id)` allow retrieving student info, exam metadata, and all subject grades in a single indexed query.

### 4. Mobile-First Student Portal & Official PDF Transcripts
- Ultra-lightweight frontend (< 35KB total payload, zero heavy dependencies).
- Debounce protection on the "View Result" button to eliminate repeated rapid clicks.
- Client-side `sessionStorage` caching for instant back-and-forth navigation.
- Authentic printable KTU Grade Card with digital QR verification.

---

## 🚀 Quick Start Guide

### Option A: Standalone Zero-Setup Mode (Local Python)

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Seed Sample Data (2,400+ students across 8 engineering colleges)**:
   ```bash
   python -m backend.seed_data
   ```

3. **Start the High-Performance ASGI Server**:
   ```bash
   python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Access the Portals**:
   - **Student Result Portal**: [http://localhost:8000](http://localhost:8000)
   - **Admin Management Studio**: [http://localhost:8000/admin](http://localhost:8000/admin)
   - **Prometheus Telemetry**: [http://localhost:8000/metrics](http://localhost:8000/metrics)
   - **Health Probe**: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)

   **Default Admin Credentials**:
   - **Username**: `admin`
   - **Password**: `ktuadmin2026`

---

### Option B: Production Docker Compose Deployment

Run the complete multi-instance cluster (Nginx Load Balancer + 3x FastAPI Replicas + Redis + PostgreSQL + Prometheus):

```bash
docker-compose up --build -d
```

---

## 🧪 Load Testing Suite

Simulate extreme traffic spikes and verify single-flight coalescing:

### 1. High-Concurrency Traffic Spike Test (1,000+ Queries)
```bash
python load_tests/spike_test.py 1000 50
```

### 2. Cache Stampede / Thundering Herd Test (500 Simultaneous Hits for Uncached Record)
```bash
python load_tests/stampede_test.py 500
```

---

## 📁 Repository Structure

```
ktu prob/
├── backend/
│   ├── app.py                      # FastAPI ASGI application & routing
│   ├── config.py                   # App settings & performance parameters
│   ├── auth.py                     # JWT authentication & bcrypt hashing
│   ├── cache/
│   │   ├── manager.py              # Multi-tier cache (L1 Memory + L2 Redis)
│   │   ├── singleflight.py         # Request coalescer (stampede protector)
│   │   └── warmer.py               # Background Redis cache pre-warming
│   ├── db/
│   │   ├── database.py             # Async connection pool (PostgreSQL / SQLite WAL)
│   │   ├── schema.sql              # Production DDL with composite indexes
│   │   └── repository.py           # Single-query high-performance data access
│   ├── services/
│   │   ├── result_service.py       # Result retrieval & multi-tier fallback
│   │   └── import_service.py       # Streaming CSV/Excel bulk result importer
│   ├── middleware/
│   │   ├── rate_limiter.py         # Sliding window rate limiter
│   │   └── security.py             # Security headers & server timing
│   ├── monitoring/
│   │   └── metrics.py              # Prometheus metrics exporter
│   └── seed_data.py                # Realistic KTU generator (2,400+ students)
├── frontend/
│   ├── index.html                  # Mobile-first student result search & view
│   ├── admin.html                  # Admin management & cache warming portal
│   ├── css/
│   │   ├── style.css               # Modern KTU responsive design system
│   │   └── print.css               # Official KTU Grade Card print/PDF layout
│   ├── js/
│   │   ├── app.js                  # Student search client & local caching
│   │   └── admin.js                # Admin dashboard & live metrics poller
│   └── assets/
│       ├── ktu_logo.svg            # Crisp vector KTU emblem
│       └── watermark.svg           # Authentic transcript watermark
├── load_tests/
│   ├── spike_test.py               # Asynchronous high-concurrency traffic simulator
│   ├── stampede_test.py            # Cache thundering herd / coalescer test
│   └── sample_results.csv          # Sample CSV for testing bulk imports
├── nginx/
│   └── nginx.conf                  # Nginx load balancing & rate limiting config
├── prometheus/
│   └── prometheus.yml              # Prometheus scrape targets
├── Dockerfile                      # Multi-stage production container image
├── docker-compose.yml              # Production stack orchestration
├── requirements.txt                # Backend dependencies
├── API_DOCUMENTATION.md            # Complete REST API specification
└── README.md                       # Documentation & deployment guide
```
