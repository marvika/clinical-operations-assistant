"""Tool-layer tests.

Tools are the only thing the LLM can touch, so this is where input validation
and error behavior matter: friendly ValueError for bad references, timestamps
normalized to the database's +00:00 format, and an airtight read/write split.
"""

import pytest

from app.db import repository
from app.db.connection import connect
from app.db.repository import ConflictError
from app.tools import ALL_TOOLS, WRITE_TOOLS
from app.tools.reads import (
    find_clinician,
    find_patient,
    get_abnormal_labs,
    list_appointments,
)
from app.tools.writes import add_journal_note, create_appointment


@pytest.fixture(autouse=True)
def _use_db_copy(db_path, monkeypatch):
    """Point the app settings at the throwaway database copy."""
    from app.config import settings

    monkeypatch.setattr(settings, "database_path", db_path)


class TestClassification:
    def test_every_tool_is_classified(self):
        names = {t.name for t in ALL_TOOLS}
        assert WRITE_TOOLS <= names
        assert len(names) == len(ALL_TOOLS)

    def test_write_set_is_exactly_the_mutating_tools(self):
        assert WRITE_TOOLS == {
            "create_appointment",
            "update_appointment",
            "add_journal_note",
            "create_service_assignment",
        }


class TestReadTools:
    def test_find_patient(self):
        matches = find_patient.invoke({"name": "sara"})
        assert any(m["name"] == "Sara Thompson" for m in matches)

    def test_find_clinician_without_title(self):
        matches = find_clinician.invoke({"name": "Alice Nguyen"})
        assert [m["name"] for m in matches] == ["Dr. Alice Nguyen"]

    def test_list_appointments_accepts_z_suffix(self):
        rows = list_appointments.invoke(
            {"start_time": "2025-03-16T09:00:00Z", "end_time": "2025-03-23T09:00:00Z"}
        )
        assert rows, "Z-suffixed timestamps must be normalized, not return nothing"

    def test_abnormal_labs_default_flag_high(self):
        rows = get_abnormal_labs.invoke({"since": "2025-03-02T09:00:00Z"})
        assert rows and all(r["flag"] == "HIGH" for r in rows)


class TestWriteTools:
    def test_create_appointment_validates_references(self):
        with pytest.raises(ValueError, match="patient"):
            create_appointment.invoke(
                {
                    "patient_id": 999_999,
                    "clinician_id": 1,
                    "location_id": 1,
                    "start_time": "2025-03-18T09:00:00Z",
                    "end_time": "2025-03-18T09:30:00Z",
                    "type": "Follow-up",
                }
            )

    def test_create_appointment_rejects_inverted_times(self):
        with pytest.raises(ValueError, match="before"):
            create_appointment.invoke(
                {
                    "patient_id": 1,
                    "clinician_id": 1,
                    "location_id": 1,
                    "start_time": "2025-03-18T10:00:00Z",
                    "end_time": "2025-03-18T09:30:00Z",
                    "type": "Follow-up",
                }
            )

    def test_create_appointment_normalizes_and_persists(self, db_path):
        result = create_appointment.invoke(
            {
                "patient_id": 1,
                "clinician_id": 1,
                "location_id": 1,
                "start_time": "2025-03-18T09:00:00Z",
                "end_time": "2025-03-18T09:30:00Z",
                "type": "Follow-up",
            }
        )
        assert result["start_time"] == "2025-03-18T09:00:00+00:00"
        with connect(db_path) as conn:
            assert repository.get_appointment(conn, result["appointment_id"])

    def test_room_conflict_propagates(self):
        create_appointment.invoke(
            {
                "patient_id": 1,
                "clinician_id": 1,
                "location_id": 1,
                "start_time": "2025-03-18T09:00:00Z",
                "end_time": "2025-03-18T09:30:00Z",
                "type": "Follow-up",
            }
        )
        with pytest.raises(ConflictError, match="overlaps"):
            create_appointment.invoke(
                {
                    "patient_id": 2,
                    "clinician_id": 2,
                    "location_id": 1,
                    "start_time": "2025-03-18T09:15:00Z",
                    "end_time": "2025-03-18T09:45:00Z",
                    "type": "Consult",
                }
            )

    def test_add_journal_note(self, db_path):
        result = add_journal_note.invoke(
            {"patient_id": 1, "created_by": 1, "summary": "Spoke with patient."}
        )
        assert result["note_id"] > 0
