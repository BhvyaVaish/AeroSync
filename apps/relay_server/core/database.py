"""
AeroSync Database Layer

Async SQLite database with aiosqlite for local development.
Schema mirrors the Supabase design so migration is trivial.
Can be swapped to Supabase by setting SUPABASE_URL in environment.
"""

import aiosqlite
from typing import Any, Dict, List, Optional

from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Module-level database connection
_db: Optional[aiosqlite.Connection] = None
_db_path: str = ""


# =============================================================================
# Schema Definitions
# =============================================================================

_SCHEMA_SQL = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Devices table
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_name TEXT NOT NULL,
    device_fingerprint TEXT UNIQUE NOT NULL,
    platform TEXT NOT NULL DEFAULT 'windows',
    is_online INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT,
    pairing_token TEXT UNIQUE,
    pairing_token_expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Sessions (workspace transfer sessions) table
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    transfer_id TEXT UNIQUE NOT NULL,
    source_device_id TEXT REFERENCES devices(id),
    target_device_id TEXT REFERENCES devices(id),
    status TEXT NOT NULL DEFAULT 'pending',
    package_url TEXT,
    package_size_bytes INTEGER DEFAULT 0,
    encrypted_key TEXT,
    expires_at TEXT,
    initiated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    metadata TEXT
);

-- Paired devices table
CREATE TABLE IF NOT EXISTS paired_devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_a_id TEXT NOT NULL REFERENCES devices(id),
    device_b_id TEXT NOT NULL REFERENCES devices(id),
    paired_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Refresh tokens table (for token invalidation)
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Constellations (isolated rooms of linked computers, maximum 5 computers)
CREATE TABLE IF NOT EXISTS constellations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    join_code TEXT UNIQUE NOT NULL,
    creator_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    max_devices INTEGER NOT NULL DEFAULT 5,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Constellation Members (computers linked into a constellation)
CREATE TABLE IF NOT EXISTS constellation_members (
    id TEXT PRIMARY KEY,
    constellation_id TEXT NOT NULL REFERENCES constellations(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    joined_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(constellation_id, device_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_devices_user_id ON devices(user_id);
CREATE INDEX IF NOT EXISTS idx_devices_fingerprint ON devices(device_fingerprint);
CREATE INDEX IF NOT EXISTS idx_sessions_transfer_id ON sessions(transfer_id);
CREATE INDEX IF NOT EXISTS idx_sessions_source_device ON sessions(source_device_id);
CREATE INDEX IF NOT EXISTS idx_sessions_target_device ON sessions(target_device_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_paired_devices_user ON paired_devices(user_id);
CREATE INDEX IF NOT EXISTS idx_paired_devices_a ON paired_devices(device_a_id);
CREATE INDEX IF NOT EXISTS idx_paired_devices_b ON paired_devices(device_b_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_constellations_join_code ON constellations(join_code);
CREATE INDEX IF NOT EXISTS idx_constellation_members_c ON constellation_members(constellation_id);
CREATE INDEX IF NOT EXISTS idx_constellation_members_d ON constellation_members(device_id);
CREATE INDEX IF NOT EXISTS idx_constellation_members_u ON constellation_members(user_id);
"""


# =============================================================================
# Connection Management
# =============================================================================

async def init_database(db_path: Optional[str] = None) -> None:
    """
    Initialize the database connection and create tables.
    
    Args:
        db_path: Optional path to SQLite database file. 
                 Defaults to settings value or 'aerosync.db'.
    """
    global _db, _db_path
    
    if db_path is None:
        try:
            from config.settings import get_settings
            settings = get_settings()
            # Extract path from SQLite URL
            url = settings.database.database_url
            if ":///" in url:
                db_path = url.split(":///")[-1]
            else:
                db_path = "aerosync.db"
        except Exception:
            db_path = "aerosync.db"
    
    _db_path = db_path
    logger.info(f"Initializing database: {_db_path}")
    
    _db = await aiosqlite.connect(_db_path)
    _db.row_factory = aiosqlite.Row
    
    # Enable WAL mode for better concurrent read performance
    await _db.execute("PRAGMA journal_mode=WAL")
    # Enable foreign keys
    await _db.execute("PRAGMA foreign_keys=ON")
    
    # Create tables
    await _db.executescript(_SCHEMA_SQL)
    await _db.commit()
    
    logger.info("Database tables created/verified")


async def close_database() -> None:
    """Close the database connection."""
    global _db
    if _db:
        await _db.close()
        _db = None
        logger.info("Database connection closed")


async def get_db() -> aiosqlite.Connection:
    """
    Get the active database connection.
    
    Returns:
        aiosqlite.Connection: The active database connection.
        
    Raises:
        RuntimeError: If database is not initialized.
    """
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db


# =============================================================================
# Query Helpers
# =============================================================================

async def execute(query: str, params: tuple = ()) -> aiosqlite.Cursor:
    """
    Execute a SQL query.
    
    Args:
        query: SQL query string with ? placeholders.
        params: Query parameters.
        
    Returns:
        aiosqlite.Cursor: The cursor after execution.
    """
    db = await get_db()
    cursor = await db.execute(query, params)
    await db.commit()
    return cursor


async def fetch_one(query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    """
    Execute a query and return the first row as a dict.
    
    Args:
        query: SQL query string.
        params: Query parameters.
        
    Returns:
        Optional[Dict]: The first row as a dictionary, or None if no results.
    """
    db = await get_db()
    cursor = await db.execute(query, params)
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


async def fetch_all(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """
    Execute a query and return all rows as a list of dicts.
    
    Args:
        query: SQL query string.
        params: Query parameters.
        
    Returns:
        List[Dict]: All rows as dictionaries.
    """
    db = await get_db()
    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def execute_returning_id(query: str, params: tuple = ()) -> Optional[str]:
    """
    Execute an INSERT query and return the last row id.
    
    Note: For our schema we use TEXT UUIDs, so this returns the
    value passed as the id parameter rather than lastrowid.
    
    Args:
        query: SQL INSERT query.
        params: Query parameters (first should be the UUID id).
        
    Returns:
        Optional[str]: The ID of the inserted row.
    """
    db = await get_db()
    await db.execute(query, params)
    await db.commit()
    if params:
        return params[0]  # Return the UUID we passed in
    return None
