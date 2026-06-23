from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app, get_db_connection  # noqa: E402
from scripts.smoke_helpers import ensure_smoke_admin, cleanup_smoke_user  # noqa: E402


ADMIN_PASSWORD = "SmokeAdmin123"


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


def create_user(admin_client, username, role="Admin"):
    status, payload = post_json(
        admin_client,
        "/api/users",
        {
            "username": username,
            "password": "12345",
            "role": role,
            "admin_password": ADMIN_PASSWORD,
        },
    )
    if status != 200 or not payload.get("success"):
        return None, status, payload

    _, users_payload = get_json(admin_client, "/api/users")
    user = next((item for item in users_payload.get("users", []) if item.get("username") == username), None)
    return user, status, payload


def cleanup_temp_users():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE username LIKE 'session_remote_%' OR username LIKE 'session_self_%'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    stamp = int(time.time())
    smoke_admin = f"smoke_session_admin_{stamp}"
    remote_username = f"session_remote_{stamp}"
    self_username = f"session_self_{stamp}"
    checks = []

    cleanup_temp_users()
    ensure_smoke_admin(smoke_admin, ADMIN_PASSWORD)

    try:
        admin_client = app.test_client()
        status, payload = post_json(admin_client, "/api/login", {"username": smoke_admin, "password": ADMIN_PASSWORD})
        checks.append(print_check("admin login", status == 200 and payload.get("success") is True, payload))

        remote_user, status, payload = create_user(admin_client, remote_username)
        checks.append(print_check("create remotely-deleted user", remote_user is not None, payload))

        if remote_user:
            remote_client = app.test_client()
            status, payload = post_json(remote_client, "/api/login", {"username": remote_username, "password": "12345"})
            checks.append(print_check("remote user login", status == 200 and payload.get("success") is True, payload))

            status, payload = post_json(admin_client, f"/api/users/{remote_user['id']}/delete", {"admin_password": ADMIN_PASSWORD})
            checks.append(print_check("admin deletes logged-in remote user", status == 200 and payload.get("success") is True, payload))

            status, payload = get_json(remote_client, "/api/me")
            checks.append(print_check("deleted remote user session rejected", status == 401 and payload.get("auth_required") is True, payload))
            with remote_client.session_transaction() as session:
                checks.append(print_check("deleted remote user session cleared", "username" not in session, dict(session)))

        self_user, status, payload = create_user(admin_client, self_username)
        checks.append(print_check("create self-delete user", self_user is not None, payload))

        if self_user:
            self_client = app.test_client()
            status, payload = post_json(self_client, "/api/login", {"username": self_username, "password": "12345"})
            checks.append(print_check("self-delete user login", status == 200 and payload.get("success") is True, payload))

            status, payload = post_json(self_client, f"/api/users/{self_user['id']}/delete", {"admin_password": "12345"})
            checks.append(print_check("self-delete returns logged_out", status == 200 and payload.get("success") is True and payload.get("logged_out") is True, payload))

            status, payload = get_json(self_client, "/api/me")
            checks.append(print_check("self-deleted session rejected", status == 401 and payload.get("auth_required") is True, payload))
    finally:
        cleanup_temp_users()
        cleanup_smoke_user(smoke_admin)

    passed = sum(1 for ok in checks if ok)
    failed = len(checks) - passed
    print("\nSUMMARY")
    print(f"  total checks: {len(checks)}")
    print(f"  passed: {passed}")
    print(f"  failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
