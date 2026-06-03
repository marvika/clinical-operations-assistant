"""Name resolution: the agent never guesses ids, it looks names up.

Matching is case-insensitive and partial, and clinician lookups tolerate a
missing/extra "Dr." prefix in either the query or the stored name.
"""

from app.domain import resolve


class TestPatients:
    def test_exact_name(self, conn):
        matches = resolve.find_patients(conn, "Sara Thompson")
        assert [m["name"] for m in matches] == ["Sara Thompson"]

    def test_case_insensitive_partial(self, conn):
        matches = resolve.find_patients(conn, "sara")
        assert any(m["name"] == "Sara Thompson" for m in matches)

    def test_no_match_returns_empty(self, conn):
        assert resolve.find_patients(conn, "Nonexistent Person") == []

    def test_includes_dob_for_disambiguation(self, conn):
        match = resolve.find_patients(conn, "Sara Thompson")[0]
        assert set(match) == {"patient_id", "name", "dob"}


class TestClinicians:
    def test_full_name_with_title(self, conn):
        matches = resolve.find_clinicians(conn, "Dr. Alice Nguyen")
        assert [m["name"] for m in matches] == ["Dr. Alice Nguyen"]

    def test_name_without_title_still_matches(self, conn):
        matches = resolve.find_clinicians(conn, "Alice Nguyen")
        assert [m["name"] for m in matches] == ["Dr. Alice Nguyen"]

    def test_title_in_query_but_not_in_db(self, alt_db_path):
        # alt db has "Dr. Kari Nordmann"; query with and without title.
        from app.db.connection import connect

        with connect(alt_db_path) as conn:
            assert resolve.find_clinicians(conn, "Kari Nordmann")
            assert resolve.find_clinicians(conn, "Dr. Kari Nordmann")


class TestLocations:
    def test_partial_match(self, conn):
        matches = resolve.find_locations(conn, "101")
        assert [m["name"] for m in matches] == ["Room 101"]

    def test_all_locations_listed_for_empty_query(self, conn):
        assert len(resolve.find_locations(conn, "")) >= 2
