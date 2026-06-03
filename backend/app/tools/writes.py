"""Mutating tools. Every tool in this module requires human approval before it
runs — the agent graph pauses on an interrupt and only executes the call once
a reviewer approves it.

Each tool validates its references up front so the human reviewing the action
gets a clear error story, and the database trigger (no overlapping bookings
per location) is surfaced as a ConflictError the agent can relay.
"""

import sqlite3
from typing import Any

from langchain_core.tools import tool

from app.db import repository
from app.db.connection import connect
from app.tools.reads import normalize_iso


def _require(conn: sqlite3.Connection, table: str, id_column: str, value: int) -> None:
    row = conn.execute(f"SELECT 1 FROM {table} WHERE {id_column} = ?", [value]).fetchone()
    if row is None:
        raise ValueError(f"No {table[:-1].replace('_', ' ')} with id {value}")


def _validate_window(start_iso: str, end_iso: str) -> None:
    if start_iso >= end_iso:
        raise ValueError("start_time must be before end_time")


@tool
def create_appointment(
    patient_id: int,
    clinician_id: int,
    location_id: int,
    start_time: str,
    end_time: str,
    type: str,
) -> dict[str, Any]:
    """Book a new appointment. Times are ISO-8601; resolve patient_id,
    clinician_id and location_id with the find_* tools first.

    Fails if the location already has a booking overlapping the time window.
    """
    start_iso, end_iso = normalize_iso(start_time), normalize_iso(end_time)
    _validate_window(start_iso, end_iso)
    with connect() as conn:
        _require(conn, "patients", "patient_id", patient_id)
        _require(conn, "clinicians", "clinician_id", clinician_id)
        _require(conn, "locations", "location_id", location_id)
        return repository.insert_appointment(
            conn,
            patient_id=patient_id,
            clinician_id=clinician_id,
            location_id=location_id,
            start_time=start_iso,
            end_time=end_iso,
            type=type,
        )


@tool
def update_appointment(
    appointment_id: int,
    start_time: str | None = None,
    end_time: str | None = None,
    type: str | None = None,
    clinician_id: int | None = None,
    location_id: int | None = None,
) -> dict[str, Any]:
    """Change one or more fields of an existing appointment (reschedule,
    change type, move room, reassign clinician).

    Fails if the new time/location overlaps an existing booking.
    """
    fields: dict[str, Any] = {
        "start_time": normalize_iso(start_time) if start_time else None,
        "end_time": normalize_iso(end_time) if end_time else None,
        "type": type,
        "clinician_id": clinician_id,
        "location_id": location_id,
    }
    with connect() as conn:
        if clinician_id is not None:
            _require(conn, "clinicians", "clinician_id", clinician_id)
        if location_id is not None:
            _require(conn, "locations", "location_id", location_id)
        current = repository.get_appointment(conn, appointment_id)
        if current is None:
            raise ValueError(f"No appointment with id {appointment_id}")
        _validate_window(
            fields["start_time"] or current["start_time"],
            fields["end_time"] or current["end_time"],
        )
        return repository.update_appointment(conn, appointment_id, **fields)  # type: ignore[return-value]


@tool
def add_journal_note(patient_id: int, created_by: int, summary: str) -> dict[str, Any]:
    """Add a journal note to a patient's record. created_by is the authoring
    clinician's id (resolve it with find_clinician first)."""
    with connect() as conn:
        _require(conn, "patients", "patient_id", patient_id)
        _require(conn, "clinicians", "clinician_id", created_by)
        return repository.insert_journal_note(
            conn, patient_id=patient_id, created_by=created_by, summary=summary
        )


@tool
def create_service_assignment(
    patient_id: int,
    service: str,
    planned_start: str | None = None,
    planned_end: str | None = None,
) -> dict[str, Any]:
    """Assign a service (e.g. physiotherapy, home nursing) to a patient, with
    an optional planned start/end."""
    with connect() as conn:
        _require(conn, "patients", "patient_id", patient_id)
        return repository.insert_service_assignment(
            conn,
            patient_id=patient_id,
            service=service,
            planned_start=normalize_iso(planned_start) if planned_start else None,
            planned_end=normalize_iso(planned_end) if planned_end else None,
        )


WRITE_TOOL_LIST = [
    create_appointment,
    update_appointment,
    add_journal_note,
    create_service_assignment,
]
