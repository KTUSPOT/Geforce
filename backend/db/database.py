import os
import asyncio
import logging
from typing import AsyncGenerator, Optional, Any, List, Dict
from pathlib import Path
from backend.config import settings

logger = logging.getLogger("ktu.db")

class DatabaseManager:
    """
    High-Performance Async Database Manager supporting both SQLite (WAL mode)
    and PostgreSQL connection pooling.
    """
    def __init__(self):
        self.is_postgres = settings.DATABASE_URL.startswith("postgres")
        self._sqlite_path: Optional[str] = None
        self._pg_pool = None
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return

        if self.is_postgres:
            try:
                import asyncpg
                self._pg_pool = await asyncpg.create_pool(
                    settings.DATABASE_URL,
                    min_size=settings.DB_POOL_MIN_SIZE,
                    max_size=settings.DB_POOL_MAX_SIZE,
                    command_timeout=10.0
                )
                logger.info(f"PostgreSQL connection pool established ({settings.DB_POOL_MIN_SIZE}-{settings.DB_POOL_MAX_SIZE} connections)")
            except Exception as e:
                logger.warning(f"Could not connect to PostgreSQL ({e}). Falling back to SQLite.")
                self.is_postgres = False

        if not self.is_postgres:
            import aiosqlite
            # Extract SQLite path
            db_path = settings.DATABASE_URL.replace("sqlite:///", "")
            self._sqlite_path = db_path
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Initialize SQLite with WAL mode for high concurrency
            async with aiosqlite.connect(self._sqlite_path) as db:
                await db.execute("PRAGMA journal_mode = WAL;")
                await db.execute("PRAGMA synchronous = NORMAL;")
                await db.execute("PRAGMA cache_size = -64000;")  # 64MB in-memory cache
                await db.execute("PRAGMA temp_store = MEMORY;")
                await db.execute("PRAGMA mmap_size = 30000000000;") # Memory-mapped I/O
                await db.commit()
            logger.info(f"SQLite WAL mode database initialized at {self._sqlite_path}")

        # Run schema creation
        await self._run_migrations()
        self._initialized = True

    async def _run_migrations(self):
        schema_file = Path(__file__).resolve().parent / "schema.sql"
        if not schema_file.exists():
            return
        
        sql_content = schema_file.read_text(encoding="utf-8")
        
        if self.is_postgres:
            # PostgreSQL schema adaptation
            pg_sql = sql_content.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            pg_sql = pg_sql.replace("BOOLEAN DEFAULT 1", "BOOLEAN DEFAULT TRUE")
            async with self._pg_pool.acquire() as conn:
                await conn.execute(pg_sql)
        else:
            import aiosqlite
            async with aiosqlite.connect(self._sqlite_path) as db:
                await db.executescript(sql_content)
                await db.commit()
        logger.info("Database schema migrations verified and applied.")

    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single record as a dict."""
        if self.is_postgres:
            # Convert ? to $1, $2 for postgres
            pg_query = self._convert_params_to_pg(query)
            async with self._pg_pool.acquire() as conn:
                record = await conn.fetchrow(pg_query, *params)
                return dict(record) if record else None
        else:
            import aiosqlite
            async with aiosqlite.connect(self._sqlite_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(query, params) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None

    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch multiple records as a list of dicts."""
        if self.is_postgres:
            pg_query = self._convert_params_to_pg(query)
            async with self._pg_pool.acquire() as conn:
                records = await conn.fetch(pg_query, *params)
                return [dict(r) for r in records]
        else:
            import aiosqlite
            async with aiosqlite.connect(self._sqlite_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]

    async def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute a query (INSERT, UPDATE, DELETE)."""
        if self.is_postgres:
            pg_query = self._convert_params_to_pg(query)
            async with self._pg_pool.acquire() as conn:
                return await conn.execute(pg_query, *params)
        else:
            import aiosqlite
            async with aiosqlite.connect(self._sqlite_path) as db:
                cursor = await db.execute(query, params)
                await db.commit()
                return cursor.lastrowid

    async def execute_many(self, query: str, params_list: List[tuple]) -> None:
        """High-speed batch execution for bulk imports."""
        if not params_list:
            return
        if self.is_postgres:
            pg_query = self._convert_params_to_pg(query)
            async with self._pg_pool.acquire() as conn:
                await conn.executemany(pg_query, params_list)
        else:
            import aiosqlite
            async with aiosqlite.connect(self._sqlite_path) as db:
                await db.executemany(query, params_list)
                await db.commit()

    def _convert_params_to_pg(self, query: str) -> str:
        """Convert SQLite '?' placeholders to PostgreSQL '$1, $2...' format."""
        parts = query.split("?")
        if len(parts) <= 1:
            return query
        new_query = []
        for i, part in enumerate(parts[:-1]):
            new_query.append(part)
            new_query.append(f"${i+1}")
        new_query.append(parts[-1])
        return "".join(new_query)

    async def close(self):
        if self._pg_pool:
            await self._pg_pool.close()
            logger.info("PostgreSQL connection pool closed.")
        self._initialized = False

db_manager = DatabaseManager()
