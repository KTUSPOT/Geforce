import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    # App Settings
    APP_NAME: str = "KTU High-Performance Result Application"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Server Settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    WORKERS: int = int(os.getenv("WORKERS", "4"))
    
    # Database Settings
    # Supports "sqlite:///ktu_results.db" or "postgresql://user:password@localhost:5432/ktu_results"
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        f"sqlite:///{BASE_DIR / 'ktu_results.db'}"
    )
    DB_POOL_MIN_SIZE: int = int(os.getenv("DB_POOL_MIN_SIZE", "10"))
    DB_POOL_MAX_SIZE: int = int(os.getenv("DB_POOL_MAX_SIZE", "50"))
    
    # Redis Cache Settings
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "true").lower() == "true"
    CACHE_DEFAULT_TTL: int = int(os.getenv("CACHE_DEFAULT_TTL", "86400"))  # 24 hours in seconds
    L1_CACHE_MAX_ITEMS: int = int(os.getenv("L1_CACHE_MAX_ITEMS", "20000"))
    L1_CACHE_TTL: int = int(os.getenv("L1_CACHE_TTL", "300"))  # 5 minutes in-memory
    
    # Security & Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "ktu-production-secret-key-high-performance-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_SEARCH_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_SEARCH_PER_MINUTE", "60"))
    RATE_LIMIT_BURST: int = int(os.getenv("RATE_LIMIT_BURST", "15"))
    
    # Static & Frontend paths
    FRONTEND_DIR: Path = BASE_DIR / "frontend"
    UPLOADS_DIR: Path = BASE_DIR / "uploads"

settings = Settings()
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
