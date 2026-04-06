"""
database.py - Database initialization and helper functions
Handles SQLite connection, schema creation, and reusable query utilities.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "finance.db")


def get_connection():
    """Create and return a SQLite connection with row_factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Allows column access by name
    conn.execute("PRAGMA foreign_keys = ON")  # Enforce foreign key constraints
    return conn


def init_db():
    """Initialize the database schema. Creates tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # ── Users Table ──────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT    NOT NULL,
            role      TEXT    NOT NULL CHECK(role IN ('admin', 'analyst', 'viewer')),
            status    TEXT    NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive')),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Financial Records Table ───────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            amount     REAL    NOT NULL CHECK(amount > 0),
            type       TEXT    NOT NULL CHECK(type IN ('income', 'expense')),
            category   TEXT    NOT NULL,
            date       TEXT    NOT NULL,   -- Stored as YYYY-MM-DD string
            note       TEXT,
            user_id    INTEGER NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,  -- Soft delete flag (0=active, 1=deleted)
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully.")


def row_to_dict(row):
    """Convert a sqlite3.Row object to a plain Python dict."""
    return dict(row) if row else None


def rows_to_list(rows):
    """Convert a list of sqlite3.Row objects to a list of dicts."""
    return [dict(r) for r in rows]