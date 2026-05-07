"""
Disk-based OHLCV cache for yfinance data.
Stores pickled DataFrames with TTL to avoid redundant API calls.
"""

import os
import pickle
import time
import hashlib
import logging

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
DEFAULT_TTL = 300  # 5 minutes


def _cache_path(key: str) -> str:
    """Generate cache file path from a string key."""
    safe_key = hashlib.md5(key.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{safe_key}.pkl")


def get(key: str, ttl: int = DEFAULT_TTL):
    """
    Retrieve cached data if it exists and is fresher than `ttl` seconds.
    Returns None on miss or expiry.
    """
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        mtime = os.path.getmtime(path)
        if time.time() - mtime > ttl:
            return None  # Expired
        with open(path, 'rb') as f:
            return pickle.load(f)
    except Exception as e:
        logger.warning(f"Cache read error for {key}: {e}")
        return None


def put(key: str, data):
    """Store data in the cache directory as a pickle file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(key)
    try:
        with open(path, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        logger.warning(f"Cache write error for {key}: {e}")


def clear():
    """Remove all cached files."""
    if os.path.exists(CACHE_DIR):
        for fname in os.listdir(CACHE_DIR):
            try:
                os.remove(os.path.join(CACHE_DIR, fname))
            except Exception:
                pass
        logger.info("Cache cleared")
