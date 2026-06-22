import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from part_services import (  # noqa: E402
    PartValidationError,
    find_or_create_part_by_part_no,
    normalize_part_no,
    run_part_transaction,
    soft_delete_part_by_part_no,
    validate_plan_part_consistency,
)


class FakeCursor:
    def __init__(self):
        self.parts = []
        self.plans = {}
        self.relations = {
            "production_plans": [],
            "setting_dies": [],
            "qc_inspections": [],
            "production_starts": [],
            "production_finishes": [],
        }
        self.history = []
        self.lastrowid = None
        self._rows = []

    def execute(self, sql, params=()):
        self.history.append((sql, params))
        normalized_sql = " ".join(sql.split()).upper()

        if "FROM PARTS" in normalized_sql and "WHERE NORMALIZED_PART_NO = %S" in normalized_sql:
            normalized = params[0]
            self._rows = [part for part in self.parts if part["normalized_part_no"] == normalized]
            return

        if normalized_sql.startswith("INSERT INTO PARTS"):
            part_no = params[0]
            normalized = normalize_part_no(part_no)
            if any(part["normalized_part_no"] == normalized for part in self.parts):
                raise AssertionError("duplicate normalized part_no should have been selected first")
            self.lastrowid = len(self.parts) + 1
            self.parts.append(
                {
                    "id": self.lastrowid,
                    "part_no": part_no,
                    "normalized_part_no": normalized,
                    "description": None,
                    "created_at": None,
                    "updated_at": None,
                    "deleted_at": None,
                }
            )
            self._rows = []
            return

        if normalized_sql.startswith("UPDATE PARTS SET DELETED_AT = NULL"):
            part_id = params[0]
            for part in self.parts:
                if part["id"] == part_id:
                    part["deleted_at"] = None
            self._rows = []
            return

        if normalized_sql.startswith("UPDATE PARTS SET DELETED_AT = NOW()"):
            part_id = params[0]
            for part in self.parts:
                if part["id"] == part_id:
                    part["deleted_at"] = "NOW"
            self._rows = []
            return

        if "FROM PRODUCTION_PLANS" in normalized_sql and "WHERE ID = %S" in normalized_sql:
            plan_id = params[0]
            plan = self.plans.get(plan_id)
            self._rows = [plan] if plan and plan.get("deleted_at") is None else []
            return

        if normalized_sql.startswith("UPDATE PRODUCTION_PLANS SET PART_ID"):
            part_id, plan_id = params
            self.plans[plan_id]["part_id"] = part_id
            self._rows = []
            return

        if normalized_sql.startswith("SELECT * FROM"):
            table_name = normalized_sql.split("FROM ", 1)[1].split(" ", 1)[0].lower()
            part_id = params[0]
            self._rows = [row for row in self.relations.get(table_name, []) if row.get("part_id") == part_id]
            return

        raise AssertionError(f"Unexpected SQL in fake cursor: {sql}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConnection:
    def __init__(self, should_fail=False):
        self.cursor_obj = FakeCursor()
        self.should_fail = should_fail
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self

    def __enter__(self):
        return self.cursor_obj

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class PartServiceTests(unittest.TestCase):
    def test_normalize_part_no_trims_and_uppercases(self):
        self.assertEqual(normalize_part_no(" abc "), "ABC")

    def test_same_part_no_with_spacing_and_case_reuses_part_id(self):
        cursor = FakeCursor()
        first = find_or_create_part_by_part_no(cursor, " abc ")
        second = find_or_create_part_by_part_no(cursor, "ABC")

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(cursor.parts), 1)

    def test_new_part_no_creates_parts_row(self):
        cursor = FakeCursor()
        part = find_or_create_part_by_part_no(cursor, "PN-100")

        self.assertEqual(part["normalized_part_no"], "PN-100")
        self.assertEqual(len(cursor.parts), 1)

    def test_existing_part_no_reuses_existing_parts_id(self):
        cursor = FakeCursor()
        first = find_or_create_part_by_part_no(cursor, "PN-200")
        second = find_or_create_part_by_part_no(cursor, " pn-200 ")

        self.assertEqual(second["id"], first["id"])
        self.assertEqual(len(cursor.parts), 1)

    def test_different_plan_id_same_part_no_does_not_create_duplicate_parts(self):
        cursor = FakeCursor()
        cursor.plans[1] = {"id": 1, "part_id": None, "part_no": "ABC", "deleted_at": None}
        cursor.plans[2] = {"id": 2, "part_id": None, "part_no": " abc ", "deleted_at": None}

        part_one, _ = validate_plan_part_consistency(cursor, 1, "ABC")
        part_two, _ = validate_plan_part_consistency(cursor, 2, " abc ")

        self.assertEqual(part_one["id"], part_two["id"])
        self.assertEqual(cursor.plans[1]["part_id"], cursor.plans[2]["part_id"])
        self.assertEqual(len(cursor.parts), 1)

    def test_plan_id_with_mismatched_part_no_returns_validation_error(self):
        cursor = FakeCursor()
        part = find_or_create_part_by_part_no(cursor, "ABC")
        cursor.plans[1] = {"id": 1, "part_id": part["id"], "part_no": "ABC", "deleted_at": None}

        with self.assertRaises(PartValidationError):
            validate_plan_part_consistency(cursor, 1, "XYZ")

    def test_delete_by_part_no_soft_deletes_part_and_preserves_qc_history(self):
        cursor = FakeCursor()
        part = find_or_create_part_by_part_no(cursor, "ABC")
        cursor.relations["qc_inspections"].append({"id": 10, "part_id": part["id"]})

        soft_delete_part_by_part_no(cursor, " abc ")

        self.assertEqual(cursor.parts[0]["deleted_at"], "NOW")
        self.assertEqual(cursor.relations["qc_inspections"], [{"id": 10, "part_id": part["id"]}])
        self.assertFalse(any(sql.strip().upper().startswith("DELETE") for sql, _ in cursor.history))

    def test_part_transaction_rolls_back_on_failure(self):
        conn = FakeConnection()

        def failing_operation(_cursor):
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            run_part_transaction(conn, failing_operation)

        self.assertFalse(conn.committed)
        self.assertTrue(conn.rolled_back)

    def test_migration_declares_generated_unique_normalized_part_no_and_fks(self):
        migration = (ROOT / "migrations" / "001_add_parts_part_ids.sql").read_text(encoding="utf-8")

        self.assertIn("GENERATED ALWAYS AS (UPPER(TRIM(part_no))) STORED", migration)
        self.assertIn("UNIQUE KEY uq_parts_normalized_part_no", migration)
        self.assertIn("fk_production_plans_part", migration)
        self.assertIn("fk_qc_inspections_plan", migration)
        self.assertIn("ON DELETE SET NULL", migration)


if __name__ == "__main__":
    unittest.main()
