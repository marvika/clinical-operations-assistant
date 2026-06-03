"""Read-only tools. These execute directly — no human approval required.

Each tool opens a short-lived connection and returns plain JSON-serializable
data. Date arguments accept any ISO-8601 form (including a Z suffix) and are
normalized to the +00:00 format the database stores.
"""

from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool

from app.db import repository
from app.db.connection import connect
from app.domain import resolve


def normalize_iso(value: str) -> str:
    """Normalize an ISO-8601 timestamp to UTC with a +00:00 offset.

    The database stores timestamps as text, so string comparison only works if
    every timestamp uses the exact same format.
    """
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Not a valid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


@tool
def find_patient(name: str) -> list[dict[str, Any]]:
    """Look up patients by (partial, case-insensitive) name.

    Returns matching patients with their id and date of birth. Use this to
    resolve a patient name to a patient_id before any other patient operation.
    If multiple patients match, ask the user which one they mean.
    """
    with connect() as conn:
        return resolve.find_patients(conn, name)


@tool
def find_clinician(name: str) -> list[dict[str, Any]]:
    """Look up clinicians by (partial, case-insensitive) name; 'Dr.' optional.

    Returns matching clinicians with their id. Use this to resolve a clinician
    name to a clinician_id.
    """
    with connect() as conn:
        return resolve.find_clinicians(conn, name)


@tool
def find_location(name: str = "") -> list[dict[str, Any]]:
    """Look up locations (rooms) by partial name; empty name lists all locations.

    Use this to resolve a location name to a location_id, or to pick an
    available room when the user did not specify one.
    """
    with connect() as conn:
        return resolve.find_locations(conn, name)


@tool
def get_patient_details(patient_id: int) -> dict[str, Any]:
    """Fetch a patient's full record: demographics, risk level, diagnoses,
    medications, allergies and their primary clinician."""
    with connect() as conn:
        patient = repository.get_patient(conn, patient_id)
    if patient is None:
        raise ValueError(f"No patient with id {patient_id}")
    return patient


@tool
def list_appointments(
    start_time: str,
    end_time: str,
    patient_id: int | None = None,
    clinician_id: int | None = None,
) -> list[dict[str, Any]]:
    """List appointments starting within [start_time, end_time] (ISO-8601),
    optionally filtered by patient and/or clinician.

    Returns appointments with patient, clinician and location names joined in.
    """
    with connect() as conn:
        return repository.list_appointments_between(
            conn,
            normalize_iso(start_time),
            normalize_iso(end_time),
            patient_id=patient_id,
            clinician_id=clinician_id,
        )


@tool
def get_abnormal_labs(since: str, flag: str = "HIGH") -> list[dict[str, Any]]:
    """List lab results sampled since the given ISO-8601 time whose flag matches
    (HIGH, LOW or NORMAL; defaults to HIGH), with patient names included."""
    with connect() as conn:
        return repository.list_abnormal_labs(conn, normalize_iso(since), flag=flag)


@tool
def list_patient_labs(patient_id: int, since: str | None = None) -> list[dict[str, Any]]:
    """List all lab results for one patient, optionally only those sampled
    since the given ISO-8601 time."""
    with connect() as conn:
        return repository.list_patient_labs(
            conn, patient_id, normalize_iso(since) if since else None
        )


@tool
def list_patient_notes(patient_id: int) -> list[dict[str, Any]]:
    """List journal notes for one patient, most recent first, with the
    authoring clinician's name."""
    with connect() as conn:
        return repository.list_patient_notes(conn, patient_id)


@tool
def list_service_assignments(patient_id: int | None = None) -> list[dict[str, Any]]:
    """List service assignments (e.g. home care services), for one patient or
    for all patients."""
    with connect() as conn:
        return repository.list_service_assignments(conn, patient_id)


READ_TOOLS = [
    find_patient,
    find_clinician,
    find_location,
    get_patient_details,
    list_appointments,
    get_abnormal_labs,
    list_patient_labs,
    list_patient_notes,
    list_service_assignments,
]
