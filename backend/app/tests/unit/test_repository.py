"""Repository tests run against a throwaway copy of the provided database."""

import pytest

from app.db import repository
from app.db.repository import ConflictError


class TestReads:
    def test_upcoming_appointments_within_window(self, conn):
        rows = repository.list_appointments_between(
            conn, "2025-03-16T09:00:00+00:00", "2025-03-23T09:00:00+00:00"
        )
        assert rows, "provided db has appointments in the 7 days after the frozen now"
        for row in rows:
            assert "2025-03-16T09:00:00+00:00" <= row["start_time"] <= "2025-03-23T09:00:00+00:00"
            assert row["patient_name"]
            assert row["clinician_name"]
            assert row["location_name"]

    def test_appointments_filter_by_patient(self, conn):
        all_rows = repository.list_appointments_between(
            conn, "2025-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"
        )
        patient_id = all_rows[0]["patient_id"]
        rows = repository.list_appointments_between(
            conn, "2025-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", patient_id=patient_id
        )
        assert rows and all(r["patient_id"] == patient_id for r in rows)

    def test_abnormal_labs_high_in_last_14_days(self, conn):
        rows = repository.list_abnormal_labs(conn, "2025-03-02T09:00:00+00:00", flag="HIGH")
        assert rows
        for row in rows:
            assert row["flag"] == "HIGH"
            assert row["sampled_at"] >= "2025-03-02T09:00:00+00:00"
            assert row["patient_name"]

    def test_get_patient_includes_primary_clinician_despite_text_id(self, conn):
        # patients.primary_clinician_id is TEXT in the provided schema while
        # clinicians.clinician_id is INTEGER; the join must tolerate that.
        patient = repository.get_patient(conn, 1)
        assert patient["name"]
        assert patient["primary_clinician_name"], "TEXT/INTEGER join must still resolve"

    def test_get_patient_missing_returns_none(self, conn):
        assert repository.get_patient(conn, 999_999) is None


class TestWrites:
    def test_insert_appointment_returns_row(self, conn):
        patient = repository.get_patient(conn, 1)
        row = repository.insert_appointment(
            conn,
            patient_id=patient["patient_id"],
            clinician_id=1,
            location_id=1,
            start_time="2025-03-18T09:00:00+00:00",
            end_time="2025-03-18T09:30:00+00:00",
            type="Follow-up",
        )
        assert row["appointment_id"] > 0
        assert row["start_time"] == "2025-03-18T09:00:00+00:00"

    def test_overlapping_appointment_raises_conflict(self, conn):
        repository.insert_appointment(
            conn,
            patient_id=1,
            clinician_id=1,
            location_id=1,
            start_time="2025-03-18T09:00:00+00:00",
            end_time="2025-03-18T09:30:00+00:00",
            type="Follow-up",
        )
        with pytest.raises(ConflictError, match="overlaps existing booking"):
            repository.insert_appointment(
                conn,
                patient_id=2,
                clinician_id=2,
                location_id=1,  # same room, overlapping time -> db trigger aborts
                start_time="2025-03-18T09:15:00+00:00",
                end_time="2025-03-18T09:45:00+00:00",
                type="Consult",
            )

    def test_conflict_rolls_back_cleanly(self, conn):
        before = repository.list_appointments_between(
            conn, "2025-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"
        )
        with pytest.raises(ConflictError):
            repository.insert_appointment(
                conn,
                patient_id=1,
                clinician_id=1,
                location_id=2,
                start_time="2025-03-12T11:00:00+00:00",  # overlaps appointment 2 (Room 202)
                end_time="2025-03-12T11:30:00+00:00",
                type="Consult",
            )
        after = repository.list_appointments_between(
            conn, "2025-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"
        )
        assert len(after) == len(before)

    def test_update_appointment(self, conn):
        created = repository.insert_appointment(
            conn,
            patient_id=1,
            clinician_id=1,
            location_id=1,
            start_time="2025-03-19T09:00:00+00:00",
            end_time="2025-03-19T09:30:00+00:00",
            type="Follow-up",
        )
        updated = repository.update_appointment(
            conn, created["appointment_id"], type="Lab review"
        )
        assert updated["type"] == "Lab review"
        assert updated["start_time"] == created["start_time"]

    def test_update_missing_appointment_returns_none(self, conn):
        assert repository.update_appointment(conn, 999_999, type="X") is None

    def test_insert_journal_note(self, conn):
        row = repository.insert_journal_note(
            conn, patient_id=1, created_by=1, summary="Called patient re: follow-up."
        )
        assert row["note_id"] > 0
        assert row["created_at"] == "2025-03-16T09:00:00+00:00"  # stamped with frozen now

    def test_insert_service_assignment(self, conn):
        row = repository.insert_service_assignment(
            conn, patient_id=1, service="Physiotherapy", planned_start="2025-03-20"
        )
        assert row["assignment_id"] > 0
        assert row["service"] == "Physiotherapy"


class TestSwappedDb:
    """Same schema, different ids/names, INTEGER primary_clinician_id."""

    def test_reads_work_against_alt_db(self, alt_db_path):
        from app.db.connection import connect

        with connect(alt_db_path) as conn:
            patient = repository.get_patient(conn, 101)
            assert patient["name"] == "Ola Hansen"
            assert patient["primary_clinician_name"] == "Dr. Kari Nordmann"
            rows = repository.list_appointments_between(
                conn, "2025-03-16T09:00:00+00:00", "2025-03-23T09:00:00+00:00"
            )
            assert [r["patient_name"] for r in rows] == ["Ola Hansen"]
