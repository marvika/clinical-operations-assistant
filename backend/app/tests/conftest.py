"""Shared fixtures.

Tests never touch the provided ``database.db`` directly: every test gets a
throwaway copy, which also exercises the "reviewer swaps in a different db
file" requirement.
"""

import shutil
import sqlite3
from pathlib import Path

import pytest

PROVIDED_DB = Path(__file__).resolve().parents[3] / "database.db"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """A disposable copy of the provided SQLite database."""
    target = tmp_path / "database.db"
    shutil.copy(PROVIDED_DB, target)
    return target


@pytest.fixture()
def conn(db_path: Path):
    """An open connection to the disposable database copy."""
    from app.db.connection import connect

    with connect(db_path) as conn:
        yield conn


@pytest.fixture()
def alt_db_path(tmp_path: Path) -> Path:
    """A database with the same schema but different ids/names.

    Used to prove the code has no hardcoded names or ids (the review may swap
    in a different ``database.db``).
    """
    source = sqlite3.connect(PROVIDED_DB)
    schema = ";\n".join(
        row[0] for row in source.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL")
    )
    source.close()

    target = tmp_path / "alt.db"
    conn = sqlite3.connect(target)
    conn.executescript(schema)
    conn.executescript(
        """
        INSERT INTO clinicians (clinician_id, name) VALUES (7, 'Dr. Kari Nordmann');
        INSERT INTO locations (location_id, name) VALUES (3, 'Room 303');
        -- primary_clinician_id stored as INTEGER here (provided db stores TEXT)
        -- to prove the join tolerates both representations.
        INSERT INTO patients (patient_id, name, dob, risk_level, diagnoses, medications,
                              allergies, primary_clinician_id)
        VALUES (101, 'Ola Hansen', '1979-01-31', 'medium', NULL, NULL, NULL, 7);
        INSERT INTO appointments (appointment_id, patient_id, start_time, end_time, type,
                                  clinician_id, location_id)
        VALUES (501, 101, '2025-03-18T10:00:00+00:00', '2025-03-18T10:30:00+00:00',
                'Follow-up', 7, 3);
        """
    )
    conn.commit()
    conn.close()
    return target
