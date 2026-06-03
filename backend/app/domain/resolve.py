"""Name -> id resolution.

The agent is instructed never to guess ids: it resolves names through these
lookups and asks the user to disambiguate when more than one row matches.
Matching is case-insensitive and partial; clinician lookups also tolerate a
"Dr." prefix present or absent on either side.
"""

import sqlite3
from typing import Any


def _like(conn: sqlite3.Connection, query: str, params: list[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def find_patients(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    return _like(
        conn,
        """
        SELECT patient_id, name, dob FROM patients
        WHERE name LIKE ? COLLATE NOCASE ORDER BY name
        """,
        [f"%{name.strip()}%"],
    )


def find_clinicians(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    stripped = name.strip()
    bare = stripped[3:].lstrip(". ") if stripped.lower().startswith("dr") else stripped
    return _like(
        conn,
        """
        SELECT clinician_id, name FROM clinicians
        WHERE name LIKE ? COLLATE NOCASE OR name LIKE ? COLLATE NOCASE
        ORDER BY name
        """,
        [f"%{stripped}%", f"%{bare}%"],
    )


def find_locations(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    return _like(
        conn,
        """
        SELECT location_id, name FROM locations
        WHERE name LIKE ? COLLATE NOCASE ORDER BY name
        """,
        [f"%{name.strip()}%"],
    )
