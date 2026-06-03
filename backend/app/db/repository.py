"""All SQL lives here, parameterized, one function per query.

Robustness notes (the review may swap in a different db with the same schema):
- ``patients.primary_clinician_id`` is declared TEXT but references the
  INTEGER ``clinicians.clinician_id``; joins CAST both sides so either
  representation works.
- Timestamps are ISO-8601 strings with a +00:00 offset; comparing them as
  strings is correct because the format is lexicographically ordered.
- The schema's triggers abort appointments that overlap an existing booking
  for the same location; that surfaces as :class:`ConflictError`.
"""

import sqlite3
from typing import Any

from app import clock


class ConflictError(Exception):
    """A write was rejected by a database constraint or trigger."""


def _rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def _row(cursor: sqlite3.Cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    return dict(row) if row else None


# --- reads -----------------------------------------------------------------

APPOINTMENT_SELECT = """
    SELECT a.appointment_id, a.patient_id, a.start_time, a.end_time, a.type,
           a.clinician_id, a.location_id,
           p.name AS patient_name, c.name AS clinician_name, l.name AS location_name
    FROM appointments a
    JOIN patients p ON p.patient_id = a.patient_id
    JOIN clinicians c ON c.clinician_id = a.clinician_id
    JOIN locations l ON l.location_id = a.location_id
"""


def list_appointments_between(
    conn: sqlite3.Connection,
    start_iso: str,
    end_iso: str,
    *,
    patient_id: int | None = None,
    clinician_id: int | None = None,
) -> list[dict[str, Any]]:
    query = APPOINTMENT_SELECT + " WHERE a.start_time >= ? AND a.start_time <= ?"
    params: list[Any] = [start_iso, end_iso]
    if patient_id is not None:
        query += " AND a.patient_id = ?"
        params.append(patient_id)
    if clinician_id is not None:
        query += " AND a.clinician_id = ?"
        params.append(clinician_id)
    query += " ORDER BY a.start_time"
    return _rows(conn.execute(query, params))


def get_appointment(conn: sqlite3.Connection, appointment_id: int) -> dict[str, Any] | None:
    return _row(conn.execute(APPOINTMENT_SELECT + " WHERE a.appointment_id = ?", [appointment_id]))


def list_abnormal_labs(
    conn: sqlite3.Connection, since_iso: str, *, flag: str = "HIGH"
) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            """
            SELECT lr.lab_id, lr.patient_id, lr.sampled_at, lr.test_name, lr.value,
                   lr.unit, lr.ref_low, lr.ref_high, lr.flag, p.name AS patient_name
            FROM lab_results lr
            JOIN patients p ON p.patient_id = lr.patient_id
            WHERE lr.sampled_at >= ? AND UPPER(lr.flag) = UPPER(?)
            ORDER BY lr.sampled_at DESC
            """,
            [since_iso, flag],
        )
    )


def get_patient(conn: sqlite3.Connection, patient_id: int) -> dict[str, Any] | None:
    # CAST both sides: provided db stores primary_clinician_id as TEXT,
    # a swapped db may store it as INTEGER.
    return _row(
        conn.execute(
            """
            SELECT p.patient_id, p.name, p.dob, p.risk_level, p.diagnoses,
                   p.medications, p.allergies,
                   c.clinician_id AS primary_clinician_id,
                   c.name AS primary_clinician_name
            FROM patients p
            LEFT JOIN clinicians c
              ON CAST(c.clinician_id AS INTEGER) = CAST(p.primary_clinician_id AS INTEGER)
            WHERE p.patient_id = ?
            """,
            [patient_id],
        )
    )


def list_patient_labs(
    conn: sqlite3.Connection, patient_id: int, since_iso: str | None = None
) -> list[dict[str, Any]]:
    query = "SELECT * FROM lab_results WHERE patient_id = ?"
    params: list[Any] = [patient_id]
    if since_iso is not None:
        query += " AND sampled_at >= ?"
        params.append(since_iso)
    query += " ORDER BY sampled_at DESC"
    return _rows(conn.execute(query, params))


def list_patient_notes(conn: sqlite3.Connection, patient_id: int) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            """
            SELECT jn.note_id, jn.patient_id, jn.created_at, jn.summary,
                   c.name AS created_by_name
            FROM journal_notes jn
            LEFT JOIN clinicians c ON c.clinician_id = jn.created_by
            WHERE jn.patient_id = ?
            ORDER BY jn.created_at DESC
            """,
            [patient_id],
        )
    )


def list_service_assignments(
    conn: sqlite3.Connection, patient_id: int | None = None
) -> list[dict[str, Any]]:
    query = """
        SELECT sa.assignment_id, sa.patient_id, sa.service, sa.created_at,
               sa.planned_start, sa.planned_end, p.name AS patient_name
        FROM service_assignments sa
        JOIN patients p ON p.patient_id = sa.patient_id
    """
    params: list[Any] = []
    if patient_id is not None:
        query += " WHERE sa.patient_id = ?"
        params.append(patient_id)
    query += " ORDER BY sa.created_at DESC"
    return _rows(conn.execute(query, params))


# --- writes ----------------------------------------------------------------


def insert_appointment(
    conn: sqlite3.Connection,
    *,
    patient_id: int,
    clinician_id: int,
    location_id: int,
    start_time: str,
    end_time: str,
    type: str,
) -> dict[str, Any]:
    try:
        cursor = conn.execute(
            """
            INSERT INTO appointments (patient_id, start_time, end_time, type,
                                      clinician_id, location_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [patient_id, start_time, end_time, type, clinician_id, location_id],
        )
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ConflictError(str(exc)) from exc
    conn.commit()
    return get_appointment(conn, cursor.lastrowid)  # type: ignore[return-value]


def update_appointment(
    conn: sqlite3.Connection, appointment_id: int, **fields: Any
) -> dict[str, Any] | None:
    allowed = {"patient_id", "clinician_id", "location_id", "start_time", "end_time", "type"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        raise ValueError("No updatable fields given")
    if get_appointment(conn, appointment_id) is None:
        return None
    assignments = ", ".join(f"{column} = ?" for column in updates)
    try:
        conn.execute(
            f"UPDATE appointments SET {assignments} WHERE appointment_id = ?",
            [*updates.values(), appointment_id],
        )
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ConflictError(str(exc)) from exc
    conn.commit()
    return get_appointment(conn, appointment_id)


def insert_journal_note(
    conn: sqlite3.Connection, *, patient_id: int, created_by: int, summary: str
) -> dict[str, Any]:
    try:
        cursor = conn.execute(
            """
            INSERT INTO journal_notes (patient_id, created_at, created_by, summary)
            VALUES (?, ?, ?, ?)
            """,
            [patient_id, clock.iso(clock.now()), created_by, summary],
        )
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ConflictError(str(exc)) from exc
    conn.commit()
    return _row(conn.execute("SELECT * FROM journal_notes WHERE note_id = ?", [cursor.lastrowid]))  # type: ignore[return-value]


def insert_service_assignment(
    conn: sqlite3.Connection,
    *,
    patient_id: int,
    service: str,
    planned_start: str | None = None,
    planned_end: str | None = None,
) -> dict[str, Any]:
    try:
        cursor = conn.execute(
            """
            INSERT INTO service_assignments (patient_id, service, created_at,
                                             planned_start, planned_end)
            VALUES (?, ?, ?, ?, ?)
            """,
            [patient_id, service, clock.iso(clock.now()), planned_start, planned_end],
        )
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ConflictError(str(exc)) from exc
    conn.commit()
    return _row(
        conn.execute(
            "SELECT * FROM service_assignments WHERE assignment_id = ?", [cursor.lastrowid]
        )
    )  # type: ignore[return-value]
