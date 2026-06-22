from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app, get_db_connection, ensure_users_table, count_admin_users  # noqa: E402
from scripts.smoke_helpers import ensure_smoke_admin, cleanup_smoke_user  # noqa: E402


ADMIN_PASSWORD = "SmokeAdmin123"
TEMP_PASSWORD = "12345"


def print_check(name, ok, payload=None):
    status = "PASS" if ok else "FAIL"
    print(f"{status} {name}")
    if not ok and payload is not None:
        print(f"  payload: {payload}")
    return ok


def post_json(client, path, data=None):
    response = client.post(path, data=data or {})
    return response.status_code, response.get_json(silent=True) or {}


def get_json(client, path):
    response = client.get(path)
    return response.status_code, response.get_json(silent=True) or {}


def db_all_user_roles():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            cursor.execute("SELECT id, username, role FROM users")
            return cursor.fetchall()
    finally:
        conn.close()


def restore_roles(role_rows):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            for row in role_rows:
                cursor.execute("UPDATE users SET role = %s WHERE id = %s", (row["role"], row["id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cleanup_temp_users(prefix):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE username LIKE %s", (f"{prefix}%",))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_user(admin_client, username, role="Admin"):
    status, payload = post_json(
        admin_client,
        "/api/users",
        {
            "username": username,
            "password": TEMP_PASSWORD,
            "role": role,
            "admin_password": ADMIN_PASSWORD,
        },
    )
    if status != 200 or not payload.get("success"):
        return None, status, payload
    _, users_payload = get_json(admin_client, "/api/users")
    user = next((item for item in users_payload.get("users", []) if item.get("username") == username), None)
    return user, status, payload


def force_only_admin(username):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET role = 'Manager' WHERE LOWER(role) = 'admin' AND username <> %s", (username,))
            cursor.execute("UPDATE users SET role = 'Admin' WHERE username = %s", (username,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    stamp = int(time.time())
    prefix = f"admin_safety_{stamp}_"
    smoke_admin = f"smoke_admin_safety_{stamp}"
    checks = []
    original_roles = db_all_user_roles()

    admin_client = app.test_client()
    try:
        ensure_smoke_admin(smoke_admin, ADMIN_PASSWORD)
        status, payload = post_json(admin_client, "/api/login", {"username": smoke_admin, "password": ADMIN_PASSWORD})
        checks.append(print_check("main admin login", status == 200 and payload.get("success") is True, payload))

        demote_user, _, payload = create_user(admin_client, f"{prefix}demote")
        checks.append(print_check("create admin for demote-allowed case", demote_user is not None, payload))
        if demote_user:
            status, payload = post_json(
                admin_client,
                f"/api/users/{demote_user['id']}/role",
                {"role": "Sup", "admin_password": ADMIN_PASSWORD},
            )
            checks.append(print_check("demote one admin when another admin remains", status == 200 and payload.get("success") is True, payload))

        delete_user, _, payload = create_user(admin_client, f"{prefix}delete")
        checks.append(print_check("create admin for delete-allowed case", delete_user is not None, payload))
        if delete_user:
            status, payload = post_json(admin_client, f"/api/users/{delete_user['id']}/delete", {"admin_password": ADMIN_PASSWORD})
            checks.append(print_check("delete one admin when another admin remains", status == 200 and payload.get("success") is True, payload))

        last_user, _, payload = create_user(admin_client, f"{prefix}last")
        checks.append(print_check("create admin for last-admin blocked case", last_user is not None, payload))
        if last_user:
            force_only_admin(last_user["username"])
            last_client = app.test_client()
            status, payload = post_json(last_client, "/api/login", {"username": last_user["username"], "password": TEMP_PASSWORD})
            checks.append(print_check("last admin login", status == 200 and payload.get("success") is True, payload))

            status, payload = post_json(
                last_client,
                f"/api/users/{last_user['id']}/role",
                {"role": "Manager", "admin_password": TEMP_PASSWORD},
            )
            checks.append(print_check("cannot demote the last admin", status == 400 and payload.get("success") is False, payload))

            status, payload = post_json(last_client, f"/api/users/{last_user['id']}/delete", {"admin_password": TEMP_PASSWORD})
            checks.append(print_check("cannot delete the last admin", status == 400 and payload.get("success") is False, payload))

            restore_roles(original_roles)
            ensure_smoke_admin(smoke_admin, ADMIN_PASSWORD)
            admin_client = app.test_client()
            status, payload = post_json(admin_client, "/api/login", {"username": smoke_admin, "password": ADMIN_PASSWORD})
            checks.append(print_check("smoke admin restored after last-admin scenario", status == 200 and payload.get("success") is True, payload))

        self_user, _, payload = create_user(admin_client, f"{prefix}self")
        checks.append(print_check("create admin for self-delete allowed case", self_user is not None, payload))
        if self_user:
            self_client = app.test_client()
            status, payload = post_json(self_client, "/api/login", {"username": self_user["username"], "password": TEMP_PASSWORD})
            checks.append(print_check("self-delete admin login", status == 200 and payload.get("success") is True, payload))

            status, payload = post_json(self_client, f"/api/users/{self_user['id']}/delete", {"admin_password": TEMP_PASSWORD})
            checks.append(print_check("self-delete admin succeeds when another admin remains", status == 200 and payload.get("logged_out") is True, payload))

            status, payload = get_json(self_client, "/api/me")
            checks.append(print_check("self-delete admin session is rejected", status == 401 and payload.get("auth_required") is True, payload))

        bootstrap_username = f"{prefix}bootstrap"
        bootstrap = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "bootstrap_admin.py"),
                "--username",
                bootstrap_username,
                "--password",
                TEMP_PASSWORD,
                "--force-create-user",
            ],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        checks.append(print_check("bootstrap_admin.py can create forced Admin", bootstrap.returncode == 0 and "PASS created" in bootstrap.stdout, bootstrap.stdout + bootstrap.stderr))

        bootstrap_client = app.test_client()
        status, payload = post_json(bootstrap_client, "/api/login", {"username": bootstrap_username, "password": TEMP_PASSWORD})
        checks.append(print_check("bootstrap-created Admin can login", status == 200 and payload.get("role") == "Admin", payload))

    finally:
        restore_roles(original_roles)
        cleanup_temp_users(prefix)
        cleanup_smoke_user(smoke_admin)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            admin_count = count_admin_users(cursor)
        checks.append(print_check("at least one Admin remains after smoke", admin_count >= 1, {"admin_count": admin_count}))
    finally:
        conn.close()

    passed = sum(1 for ok in checks if ok)
    failed = len(checks) - passed
    print("\nSUMMARY")
    print(f"  total checks: {len(checks)}")
    print(f"  passed: {passed}")
    print(f"  failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
