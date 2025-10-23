"""
Database helpers for the maintenance planning tab.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import streamlit as st

BAKIM_DB_PATH = Path("bakim_planlama.db")


def _ensure_parent_dir(path: Path) -> None:
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing_cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS bakim_ucaklari (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tail_number TEXT NOT NULL UNIQUE,
            aircraft_type TEXT,
            model TEXT,
            status TEXT,
            last_maintenance_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS bakim_afml_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tail_number TEXT NOT NULL,
            flight_date TEXT NOT NULL,
            total_flight_minutes INTEGER NOT NULL,
            total_block_minutes INTEGER NOT NULL,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tail_number) REFERENCES bakim_ucaklari(tail_number)
        );

        CREATE TABLE IF NOT EXISTS bakim_rutin_isler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tail_number TEXT NOT NULL,
            task_name TEXT NOT NULL,
            part_number TEXT,
            task_serial_number TEXT,
            hour_interval_minutes INTEGER DEFAULT 0,
            day_interval INTEGER DEFAULT 0,
            co_start_time_minutes INTEGER DEFAULT 0,
            co_start_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tail_number) REFERENCES bakim_ucaklari(tail_number)
        );

        CREATE INDEX IF NOT EXISTS idx_bakim_afml_tail_date
            ON bakim_afml_logs (tail_number, flight_date);

        CREATE INDEX IF NOT EXISTS idx_bakim_rutin_tail
            ON bakim_rutin_isler (tail_number);
        """
    )

    _ensure_column(conn, "bakim_ucaklari", "manufacturer", "TEXT")
    _ensure_column(conn, "bakim_ucaklari", "serial_number", "TEXT")
    conn.commit()


@st.cache_resource(show_spinner=False)
def get_bakim_connection() -> sqlite3.Connection:
    _ensure_parent_dir(BAKIM_DB_PATH)
    conn = sqlite3.connect(BAKIM_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn
