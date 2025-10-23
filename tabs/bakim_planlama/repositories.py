"""
CRUD helpers that talk to the maintenance planning database.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Dict, List, Optional

from .database import ensure_schema


def insert_aircraft(
    conn: sqlite3.Connection,
    *,
    tail_number: str,
    aircraft_type: str,
    model: str,
    manufacturer: str,
    serial_number: str,
    status: str,
    last_maintenance_date: Optional[str],
    notes: str,
) -> None:
    conn.execute(
        """
        INSERT INTO bakim_ucaklari (
            tail_number,
            aircraft_type,
            model,
            manufacturer,
            serial_number,
            status,
            last_maintenance_date,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tail_number.strip().upper(),
            aircraft_type.strip(),
            model.strip(),
            manufacturer.strip(),
            serial_number.strip(),
            status.strip(),
            last_maintenance_date,
            notes.strip(),
        ),
    )
    conn.commit()


def update_aircraft(
    conn: sqlite3.Connection,
    *,
    aircraft_id: int,
    tail_number: str,
    aircraft_type: str,
    model: str,
    manufacturer: str,
    serial_number: str,
    status: str,
    last_maintenance_date: Optional[str],
    notes: str,
) -> None:
    conn.execute(
        """
        UPDATE bakim_ucaklari
        SET
            tail_number = ?,
            aircraft_type = ?,
            model = ?,
            manufacturer = ?,
            serial_number = ?,
            status = ?,
            last_maintenance_date = ?,
            notes = ?
        WHERE id = ?
        """,
        (
            tail_number.strip().upper(),
            aircraft_type.strip(),
            model.strip(),
            manufacturer.strip(),
            serial_number.strip(),
            status.strip(),
            last_maintenance_date,
            notes.strip(),
            aircraft_id,
        ),
    )
    conn.commit()


def insert_afml_entry(
    conn: sqlite3.Connection,
    *,
    tail_number: str,
    flight_date: date,
    total_flight_minutes: int,
    total_block_minutes: int,
    notes: str,
) -> None:
    conn.execute(
        """
        INSERT INTO bakim_afml_logs (
            tail_number,
            flight_date,
            total_flight_minutes,
            total_block_minutes,
            notes
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            tail_number.strip().upper(),
            flight_date.isoformat(),
            total_flight_minutes,
            total_block_minutes,
            notes.strip(),
        ),
    )
    conn.commit()


def update_afml_entry(
    conn: sqlite3.Connection,
    *,
    entry_id: int,
    tail_number: str,
    flight_date: date,
    total_flight_minutes: int,
    total_block_minutes: int,
    notes: str,
) -> None:
    conn.execute(
        """
        UPDATE bakim_afml_logs
        SET
            tail_number = ?,
            flight_date = ?,
            total_flight_minutes = ?,
            total_block_minutes = ?,
            notes = ?
        WHERE id = ?
        """,
        (
            tail_number.strip().upper(),
            flight_date.isoformat(),
            total_flight_minutes,
            total_block_minutes,
            notes.strip(),
            entry_id,
        ),
    )
    conn.commit()


def insert_task(
    conn: sqlite3.Connection,
    *,
    tail_number: str,
    task_name: str,
    part_number: str,
    task_serial_number: str,
    hour_interval_minutes: int,
    day_interval: int,
    co_start_time_minutes: int,
    co_start_date: Optional[str],
    notes: str,
) -> None:
    conn.execute(
        """
        INSERT INTO bakim_rutin_isler (
            tail_number,
            task_name,
            part_number,
            task_serial_number,
            hour_interval_minutes,
            day_interval,
            co_start_time_minutes,
            co_start_date,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tail_number.strip().upper(),
            task_name.strip(),
            part_number.strip(),
            task_serial_number.strip(),
            hour_interval_minutes,
            day_interval,
            co_start_time_minutes,
            co_start_date,
            notes.strip(),
        ),
    )
    conn.commit()


def fetch_aircraft(conn: sqlite3.Connection) -> List[dict]:
    ensure_schema(conn)
    rows = conn.execute(
        """
        SELECT
            id,
            tail_number,
            aircraft_type,
            model,
            manufacturer,
            serial_number,
            status,
            last_maintenance_date,
            notes,
            created_at
        FROM bakim_ucaklari
        ORDER BY tail_number COLLATE NOCASE
        """
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_afml_entries(conn: sqlite3.Connection) -> List[dict]:
    rows = conn.execute(
        """
        SELECT
            id,
            tail_number,
            flight_date,
            total_flight_minutes,
            total_block_minutes,
            notes,
            created_at
        FROM bakim_afml_logs
        ORDER BY flight_date DESC, tail_number ASC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_tasks_for_tail(conn: sqlite3.Connection, tail_number: str) -> List[dict]:
    ensure_schema(conn)
    rows = conn.execute(
        """
        SELECT
            id,
            tail_number,
            task_name,
            part_number,
            task_serial_number,
            hour_interval_minutes,
            day_interval,
            co_start_time_minutes,
            co_start_date,
            notes,
            created_at
        FROM bakim_rutin_isler
        WHERE tail_number = ?
        ORDER BY task_name COLLATE NOCASE
        """,
        (tail_number.strip().upper(),),
    ).fetchall()
    return [dict(r) for r in rows]


def get_afml_summary(conn: sqlite3.Connection) -> Dict[str, Dict[str, Optional[str]]]:
    rows = conn.execute(
        """
        SELECT
            tail_number,
            SUM(total_flight_minutes) AS total_flight_minutes,
            MAX(flight_date) AS last_flight_date
        FROM bakim_afml_logs
        GROUP BY tail_number
        """
    ).fetchall()
    summary: Dict[str, Dict[str, Optional[str]]] = {}
    for row in rows:
        summary[row["tail_number"]] = {
            "total_flight_minutes": row["total_flight_minutes"] or 0,
            "last_flight_date": row["last_flight_date"],
        }
    return summary
