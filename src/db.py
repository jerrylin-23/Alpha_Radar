"""
PostgreSQL persistence for Alpha Radar scan results.

Design goal: *optional and non-breaking*. If DATABASE_URL is unset, psycopg2 is
missing, or the connection fails, every function degrades to a no-op and the app
falls back to its in-memory cache. This lets the same codebase run locally with
zero setup and on Heroku with a Postgres add-on for durable scan results that
survive dyno restarts.

Enable on Heroku with:
    heroku addons:create heroku-postgresql:mini
"""

import os
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Heroku hands out legacy "postgres://" URLs; psycopg2/SQLAlchemy want "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_psycopg2 = None
_enabled = False

if DATABASE_URL:
    try:
        import psycopg2
        import psycopg2.extras

        _psycopg2 = psycopg2
        _enabled = True
    except ImportError:
        logger.warning("DATABASE_URL set but psycopg2 not installed; using in-memory cache only.")


def is_enabled() -> bool:
    """True only if a DB is configured AND the driver is available."""
    return _enabled


def _connect():
    """Open a new connection. Heroku Postgres requires SSL."""
    sslmode = "require" if "amazonaws.com" in DATABASE_URL or "render.com" in DATABASE_URL else "prefer"
    return _psycopg2.connect(DATABASE_URL, sslmode=sslmode, connect_timeout=10)


def init_db() -> bool:
    """Create the scan_results table if it doesn't exist. Returns success."""
    if not _enabled:
        return False
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_results (
                    symbol      TEXT PRIMARY KEY,
                    price       DOUBLE PRECISION,
                    entry       DOUBLE PRECISION,
                    dist        DOUBLE PRECISION,
                    setup       TEXT,
                    rr_ratio    DOUBLE PRECISION,
                    valid       BOOLEAN,
                    near_entry  BOOLEAN,
                    updated_at  TIMESTAMPTZ DEFAULT now()
                );
                """
            )
        logger.info("Postgres persistence enabled (scan_results ready).")
        return True
    except Exception as e:
        logger.warning(f"init_db failed, falling back to in-memory cache: {e}")
        _disable()
        return False


def upsert_results(results) -> None:
    """Insert or update a batch of scan-result dicts. Silent no-op on failure."""
    if not _enabled or not results:
        return
    rows = [
        (
            r["symbol"], r.get("price"), r.get("entry"), r.get("dist"),
            r.get("setup"), r.get("rr_ratio"), r.get("valid"), r.get("near_entry"),
        )
        for r in results
    ]
    try:
        with _connect() as conn, conn.cursor() as cur:
            _psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO scan_results
                    (symbol, price, entry, dist, setup, rr_ratio, valid, near_entry)
                VALUES %s
                ON CONFLICT (symbol) DO UPDATE SET
                    price=EXCLUDED.price, entry=EXCLUDED.entry, dist=EXCLUDED.dist,
                    setup=EXCLUDED.setup, rr_ratio=EXCLUDED.rr_ratio,
                    valid=EXCLUDED.valid, near_entry=EXCLUDED.near_entry,
                    updated_at=now();
                """,
                rows,
            )
    except Exception as e:
        logger.warning(f"upsert_results failed: {e}")


def fetch_results(near_only: bool = False):
    """Return persisted scan results as a list of dicts. Empty list on failure."""
    if not _enabled:
        return []
    query = (
        "SELECT symbol, price, entry, dist, setup, rr_ratio, valid, near_entry, "
        "updated_at FROM scan_results"
    )
    if near_only:
        query += " WHERE near_entry = TRUE"
    try:
        with _connect() as conn, conn.cursor(cursor_factory=_psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            out = []
            for row in cur.fetchall():
                d = dict(row)
                if d.get("updated_at") is not None:
                    d["timestamp"] = d.pop("updated_at").isoformat()
                out.append(d)
            return out
    except Exception as e:
        logger.warning(f"fetch_results failed: {e}")
        return []


def _disable():
    global _enabled
    _enabled = False
