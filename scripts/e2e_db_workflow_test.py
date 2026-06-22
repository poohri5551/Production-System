import argparse
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app, db_config, get_db_connection, hash_password, password_matches  # noqa: E402


EXPECTED_DATABASE = "inventory_db"
RESET_TABLES = [
    "production_finishes",
    "production_starts",
    "qc_inspections",
    "setting_dies",
    "production_plans",
    "parts",
    "users",
]


class WorkflowAbort(Exception):
    pass


class Reporter:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.warning = 0
        self.created = {}

    def pass_step(self, label, detail=""):
        self.total += 1
        self.passed += 1
        suffix = f" - {detail}" if detail else ""
        print(f"PASS {label}{suffix}")

    def fail_step(self, label, detail="", endpoint=None, response=None, sql=None, expected=None, actual=None):
        self.total += 1
        self.failed += 1
        print(f"FAIL {label}")
        if detail:
            print(f"  detail: {detail}")
        if endpoint:
            print(f"  endpoint: {endpoint}")
        if response is not None:
            print(f"  response JSON: {response}")
        if sql:
            print(f"  SQL check: {sql}")
        if expected is not None or actual is not None:
            print(f"  expected: {expected}")
            print(f"  actual: {actual}")

    def warn(self, label, detail=""):
        self.warning += 1
        suffix = f" - {detail}" if detail else ""
        print(f"WARN {label}{suffix}")

    def expect(self, condition, label, **kwargs):
        if condition:
            self.pass_step(label, kwargs.get("detail", ""))
            return True
        self.fail_step(label, **{k: v for k, v in kwargs.items() if k != "detail"})
        return False

    def require(self, condition, label, **kwargs):
        if not self.expect(condition, label, **kwargs):
            raise WorkflowAbort(label)

    def remember(self, key, value):
        self.created[key] = value
        return value

    def summary(self):
        print("\nSUMMARY")
        print(f"  total checks: {self.total}")
        print(f"  passed: {self.passed}")
        print(f"  failed: {self.failed}")
        print(f"  warning: {self.warning}")
        for key, value in self.created.items():
            print(f"  {key}: {value}")
        return self.failed == 0


def connect():
    return get_db_connection()


def current_database(cursor):
    cursor.execute("SELECT DATABASE() AS db_name")
    row = cursor.fetchone()
    return row["db_name"]


def table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def fetch_one(sql, params=()):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
    finally:
        conn.close()


def fetch_all(sql, params=()):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
    finally:
        conn.close()


def reset_db(reporter, guard):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            db_name = current_database(cursor)
            print(f"Database selected for reset: {db_name}")
            reporter.require(
                db_name == EXPECTED_DATABASE,
                "Safety database name check",
                sql="SELECT DATABASE()",
                expected=EXPECTED_DATABASE,
                actual=db_name,
            )
            reporter.require(
                guard,
                "Reset safety guard present",
                expected="--i-understand-this-clears-mock-db",
                actual="present" if guard else "missing",
            )

            existing_tables = [table for table in RESET_TABLES if table_exists(cursor, table)]
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            try:
                for table in existing_tables:
                    cursor.execute(f"DELETE FROM {table}")
                    reporter.pass_step(f"Reset table {table}", "DELETE only; schema preserved")
            finally:
                cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def seed_admin(reporter):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (username, password, role)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE password = VALUES(password), role = VALUES(role)
                """,
                ("admin", hash_password("1234"), "Admin"),
            )
        conn.commit()
        row = fetch_one("SELECT username, password, role FROM users WHERE username = %s", ("admin",))
        reporter.require(
            row and password_matches(row["password"], "1234") and row["role"] == "Admin",
            "Seed admin user",
            sql="SELECT username, password, role FROM users WHERE username='admin'",
            expected={"username": "admin", "password": "<hashed valid for 1234>", "role": "Admin"},
            actual={**row, "password": "<redacted>"} if row else row,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def response_json(response):
    try:
        data = response.get_json()
        if data is None:
            return {}
        return data
    except Exception:
        return {"raw": response.get_data(as_text=True)}


def api_post(client, endpoint, data):
    response = client.post(endpoint, data=data)
    return response, response_json(response)


def api_get(client, endpoint):
    response = client.get(endpoint)
    return response, response_json(response)


def require_api_success(reporter, client, endpoint, data=None, method="POST"):
    if method == "POST":
        response, payload = api_post(client, endpoint, data or {})
    else:
        response, payload = api_get(client, endpoint)
    reporter.require(
        response.status_code == 200 and payload.get("success") is True,
        f"{method} {endpoint}",
        endpoint=endpoint,
        response=payload,
        expected={"status_code": 200, "success": True},
        actual={"status_code": response.status_code, "success": payload.get("success")},
    )
    return payload


def list_contains_plan(rows, plan_no):
    return any(row.get("plan_no") == plan_no for row in rows)


def run_workflow(reporter):
    stamp = int(time.time())
    part_no = f"E2E-PART-{stamp}"
    plan_no = f"E2E-PLAN-{stamp}"
    lot_no = f"E2E-LOT-{stamp}"
    reporter.remember("plan_no", plan_no)

    client = app.test_client()

    login = require_api_success(
        reporter,
        client,
        "/api/login",
        {"username": "admin", "password": "1234"},
    )
    reporter.require(
        login.get("role") == "Admin",
        "Login role is Admin",
        endpoint="/api/login",
        response=login,
        expected="Admin",
        actual=login.get("role"),
    )

    production_data = {
        "prod-date": "2026-06-17",
        "prod-zone": "A",
        "prod-part-no": part_no,
        "prod-die-no": "E2E-DIE-01",
        "prod-qty": "100",
    }
    require_api_success(reporter, client, "/api/production", production_data)
    production_plan = fetch_one(
        "SELECT * FROM production_plans WHERE part_no = %s AND deleted_at IS NULL ORDER BY id DESC LIMIT 1",
        (part_no,),
    )
    reporter.require(
        production_plan and production_plan.get("part_id") is not None,
        "Production Plan created with part_id",
        sql="SELECT * FROM production_plans WHERE part_no=%s",
        expected="row with non-null part_id",
        actual=production_plan,
    )
    production_plan_id = reporter.remember("production_plan_id", production_plan["id"])

    part = fetch_one("SELECT * FROM parts WHERE id = %s", (production_plan["part_id"],))
    reporter.require(
        part and part.get("normalized_part_no") == part_no,
        "Part row created and normalized",
        sql="SELECT * FROM parts WHERE id=%s",
        expected={"normalized_part_no": part_no},
        actual=part,
    )
    reporter.remember("part_id", production_plan["part_id"])

    setting_data = {
        "plan_id": str(production_plan_id),
        "set-part-no": part_no,
        "set-lot-no": lot_no,
        "set-die-no": "E2E-DIE-01",
        "set-plan-no": plan_no,
        "set-process-die": "E2E-PROCESS",
        "set-dh": "10",
        "set-spm": "25",
        "set-time-start": "2026-06-17T08:00",
        "set-time-end": "2026-06-17T08:30",
        "set-material": "E2E-MATERIAL",
        "custom-time-1": "2026-06-17T08:31",
        "custom-time-2": "2026-06-17T08:45",
        "custom-time-3": "2026-06-17T08:46",
        "custom-time-4": "2026-06-17T09:00",
        "set-technician": "E2E-TECH",
    }
    require_api_success(reporter, client, "/api/setting_die", setting_data)
    setting = fetch_one(
        "SELECT * FROM setting_dies WHERE plan_no = %s AND deleted_at IS NULL ORDER BY id DESC LIMIT 1",
        (plan_no,),
    )
    reporter.require(
        setting
        and setting.get("plan_id") == production_plan_id
        and setting.get("part_id") == production_plan["part_id"]
        and setting.get("part_no") == part_no,
        "Setting Die linked to plan_id and part_id",
        sql="SELECT * FROM setting_dies WHERE plan_no=%s",
        expected={"plan_id": production_plan_id, "part_id": production_plan["part_id"], "part_no": part_no},
        actual=setting,
    )
    reporter.remember("setting_die_id", setting["id"])

    _, qc_plans_before = api_get(client, "/api/qc/plans")
    reporter.require(
        isinstance(qc_plans_before, list) and list_contains_plan(qc_plans_before, plan_no),
        "QC plans include plan before finish",
        endpoint="/api/qc/plans",
        response=qc_plans_before,
        expected=f"contains {plan_no}",
        actual=[row.get("plan_no") for row in qc_plans_before] if isinstance(qc_plans_before, list) else qc_plans_before,
    )

    qc_data = {
        "qc-lot-no": lot_no,
        "qc-plan-no": plan_no,
        "qc-part-no": part_no,
        "qc-time-start": "2026-06-17T09:05",
        "qc-time-end": "2026-06-17T09:10",
        "qc-percent": "98",
        "qc-status": "Pass",
        "qc-problem-area": "none",
        "qc-problem-point": "",
        "qc-cause": "",
        "qc-solution": "",
    }
    require_api_success(reporter, client, "/api/qc", qc_data)
    qc = fetch_one(
        "SELECT * FROM qc_inspections WHERE plan_no = %s AND deleted_at IS NULL ORDER BY id DESC LIMIT 1",
        (plan_no,),
    )
    reporter.require(
        qc and qc.get("plan_id") == production_plan_id and qc.get("part_id") == production_plan["part_id"],
        "QC created with plan_id and part_id",
        sql="SELECT * FROM qc_inspections WHERE plan_no=%s",
        expected={"plan_id": production_plan_id, "part_id": production_plan["part_id"]},
        actual=qc,
    )
    qc_id = reporter.remember("qc_id", qc["id"])

    notify_data = {"plan_no": plan_no, "lot_no": lot_no, "part_no": part_no}
    require_api_success(reporter, client, "/api/production_start/from_qc", notify_data)
    production_start = fetch_one(
        "SELECT * FROM production_starts WHERE plan_no = %s AND deleted_at IS NULL ORDER BY id DESC LIMIT 1",
        (plan_no,),
    )
    reporter.require(
        production_start
        and production_start.get("plan_id") == production_plan_id
        and production_start.get("part_id") == production_plan["part_id"]
        and production_start.get("confirm_status") == "waiting",
        "Notify Operator creates waiting Production Start with plan_id and part_id",
        sql="SELECT * FROM production_starts WHERE plan_no=%s",
        expected={"plan_id": production_plan_id, "part_id": production_plan["part_id"], "confirm_status": "waiting"},
        actual=production_start,
    )
    start_id = reporter.remember("production_start_id", production_start["id"])

    _, finish_plans_waiting = api_get(client, "/api/production_finish/plans")
    reporter.require(
        isinstance(finish_plans_waiting, list) and not list_contains_plan(finish_plans_waiting, plan_no),
        "Finish dropdown excludes waiting Production Start",
        endpoint="/api/production_finish/plans",
        response=finish_plans_waiting,
        expected=f"does not contain {plan_no}",
        actual=[row.get("plan_no") for row in finish_plans_waiting] if isinstance(finish_plans_waiting, list) else finish_plans_waiting,
    )

    duplicate_start_plans = api_get(client, "/api/production_start/plans")[1]
    reporter.require(
        isinstance(duplicate_start_plans, list) and not list_contains_plan(duplicate_start_plans, plan_no),
        "Production Start dropdown excludes active started plan",
        endpoint="/api/production_start/plans",
        response=duplicate_start_plans,
        expected=f"does not contain {plan_no}",
        actual=[row.get("plan_no") for row in duplicate_start_plans] if isinstance(duplicate_start_plans, list) else duplicate_start_plans,
    )

    waiting_finish_data = {
        "finish-plan-no": plan_no,
        "finish-lot-no": lot_no,
        "finish-actual-qty": "97",
        "finish-note": "Should be rejected while waiting",
        "finish-time-finish": "2026-06-17T10:00",
        "finish-hold-time": "",
    }
    waiting_response, waiting_payload = api_post(client, "/api/production_finish", waiting_finish_data)
    reporter.require(
        waiting_response.status_code == 200 and waiting_payload.get("success") is False,
        "Production Finish rejects waiting Production Start",
        endpoint="/api/production_finish",
        response=waiting_payload,
        expected={"success": False},
        actual={"status_code": waiting_response.status_code, "success": waiting_payload.get("success")},
    )

    require_api_success(reporter, client, f"/api/production_start/{start_id}/confirm", {})
    production_start = fetch_one("SELECT * FROM production_starts WHERE id = %s", (start_id,))
    reporter.require(
        production_start and production_start.get("confirm_status") == "confirmed",
        "Production Start confirm_status becomes confirmed",
        sql="SELECT * FROM production_starts WHERE id=%s",
        expected="confirmed",
        actual=production_start,
    )

    _, finish_plans_confirmed = api_get(client, "/api/production_finish/plans")
    reporter.require(
        isinstance(finish_plans_confirmed, list) and list_contains_plan(finish_plans_confirmed, plan_no),
        "Finish dropdown includes confirmed Production Start",
        endpoint="/api/production_finish/plans",
        response=finish_plans_confirmed,
        expected=f"contains {plan_no}",
        actual=[row.get("plan_no") for row in finish_plans_confirmed] if isinstance(finish_plans_confirmed, list) else finish_plans_confirmed,
    )

    finish_data = {
        "finish-plan-no": plan_no,
        "finish-lot-no": lot_no,
        "finish-actual-qty": "97",
        "finish-note": "E2E completed",
        "finish-time-finish": "2026-06-17T10:20",
        "finish-hold-time": "2026-06-17T10:00",
    }
    require_api_success(reporter, client, "/api/production_finish", finish_data)
    finish = fetch_one(
        "SELECT * FROM production_finishes WHERE plan_no = %s AND deleted_at IS NULL ORDER BY id DESC LIMIT 1",
        (plan_no,),
    )
    reporter.require(
        finish
        and finish.get("plan_id") == production_plan_id
        and finish.get("part_id") == production_plan["part_id"]
        and finish.get("part_no") == part_no,
        "Production Finish created with plan_id and part_id",
        sql="SELECT * FROM production_finishes WHERE plan_no=%s",
        expected={"plan_id": production_plan_id, "part_id": production_plan["part_id"], "part_no": part_no},
        actual=finish,
    )
    finish_id = reporter.remember("production_finish_id", finish["id"])

    require_api_success(reporter, client, f"/api/production_finish/{finish_id}/confirm", {})
    finish = fetch_one("SELECT * FROM production_finishes WHERE id = %s", (finish_id,))
    reporter.require(
        finish and finish.get("finish_status") == "confirmed",
        "Production Finish status becomes confirmed",
        sql="SELECT * FROM production_finishes WHERE id=%s",
        expected="confirmed",
        actual=finish,
    )

    active_rows = {
        "production_plans": fetch_one("SELECT id, is_finished FROM production_plans WHERE id = %s", (production_plan_id,)),
        "setting_dies": fetch_one("SELECT id, is_finished FROM setting_dies WHERE id = %s", (setting["id"],)),
        "qc_inspections": fetch_one("SELECT id, is_finished FROM qc_inspections WHERE id = %s", (qc_id,)),
        "production_starts": fetch_one("SELECT id, is_finished FROM production_starts WHERE id = %s", (start_id,)),
    }
    for table_name, row in active_rows.items():
        reporter.require(
            row and int(row.get("is_finished") or 0) == 1,
            f"{table_name}.is_finished marked after Confirm Finish",
            sql=f"SELECT id, is_finished FROM {table_name} WHERE id=%s",
            expected=1,
            actual=row,
        )

    _, qc_plans_after = api_get(client, "/api/qc/plans")
    reporter.require(
        isinstance(qc_plans_after, list) and not list_contains_plan(qc_plans_after, plan_no),
        "QC plans exclude plan after Confirm Finish",
        endpoint="/api/qc/plans",
        response=qc_plans_after,
        expected=f"does not contain {plan_no}",
        actual=[row.get("plan_no") for row in qc_plans_after] if isinstance(qc_plans_after, list) else qc_plans_after,
    )

    delete_response, delete_payload = api_post(
        client,
        "/api/production_finish/bulk_delete",
        {"admin_password": "1234", "ids[]": [str(finish_id)]},
    )
    reporter.require(
        delete_response.status_code == 200 and delete_payload.get("success") is True,
        "Bulk delete Production Finish succeeds",
        endpoint="/api/production_finish/bulk_delete",
        response=delete_payload,
        expected={"success": True},
        actual={"status_code": delete_response.status_code, "success": delete_payload.get("success")},
    )
    deleted_finish = fetch_one("SELECT id, deleted_at FROM production_finishes WHERE id = %s", (finish_id,))
    reporter.require(
        deleted_finish and deleted_finish.get("deleted_at") is not None,
        "Bulk delete is soft delete for Production Finish",
        sql="SELECT id, deleted_at FROM production_finishes WHERE id=%s",
        expected="row exists with deleted_at not null",
        actual=deleted_finish,
    )
    visible_finishes = api_get(client, "/api/production_finishes")[1]
    reporter.require(
        isinstance(visible_finishes, list) and all(row.get("id") != finish_id for row in visible_finishes),
        "Soft-deleted Production Finish is hidden from list API",
        endpoint="/api/production_finishes",
        response=visible_finishes,
        expected=f"id {finish_id} hidden",
        actual=[row.get("id") for row in visible_finishes] if isinstance(visible_finishes, list) else visible_finishes,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Full DB E2E workflow test for inventory_db.")
    parser.add_argument("--reset-db", action="store_true", help="Clear app data with DELETE statements.")
    parser.add_argument("--seed", action="store_true", help="Seed admin/1234/Admin.")
    parser.add_argument("--run-workflow", action="store_true", help="Run API workflow test.")
    parser.add_argument("--all", action="store_true", help="Run reset, seed, and workflow.")
    parser.add_argument(
        "--i-understand-this-clears-mock-db",
        action="store_true",
        help="Required with --reset-db or --all.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.all:
        args.reset_db = True
        args.seed = True
        args.run_workflow = True

    if not any([args.reset_db, args.seed, args.run_workflow]):
        print("Choose at least one mode: --reset-db, --seed, --run-workflow, or --all")
        return 2

    reporter = Reporter()
    print(f"Configured database: {db_config.get('database')}")

    try:
        if args.reset_db:
            reset_db(reporter, args.i_understand_this_clears_mock_db)
        if args.seed:
            seed_admin(reporter)
        if args.run_workflow:
            run_workflow(reporter)
    except WorkflowAbort as exc:
        reporter.warn("Workflow aborted after required check failed", str(exc))
    except Exception as exc:
        reporter.fail_step("Unhandled exception", detail=repr(exc))

    ok = reporter.summary()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
