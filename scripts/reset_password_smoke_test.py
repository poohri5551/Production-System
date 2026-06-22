from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app, get_db_connection, ensure_users_table  # noqa: E402
from scripts.smoke_helpers import ensure_smoke_admin, cleanup_smoke_user  # noqa: E402


ADMIN_PASSWORD = "SmokeAdmin123"
OLD_PASSWORD = "OldPass123"
NEW_PASSWORD = "NewPass123"
SELF_NEW_PASSWORD = "SelfNew123"


def print_check(name, ok, payload=None):
    status = "PASS" if ok else "FAIL"
    print(f"{status} {name}")
    if not ok and payload is not None:
        print(f"  payload: {payload}")
    return ok


def post_json(client, path, data=None, json=None):
    if json is not None:
        response = client.post(path, json=json)
    else:
        response = client.post(path, data=data or {})
    return response.status_code, response.get_json(silent=True) or {}


def get_json(client, path):
    response = client.get(path)
    return response.status_code, response.get_json(silent=True) or {}


def cleanup_temp_users(prefix):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            cursor.execute("DELETE FROM users WHERE username LIKE %s", (f"{prefix}%",))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            cursor.execute("SELECT id, username, password, role, created_at FROM users WHERE username = %s", (username,))
            return cursor.fetchone()
    finally:
        conn.close()


def create_user(admin_client, username, role="Sup", password=OLD_PASSWORD):
    status, payload = post_json(
        admin_client,
        "/api/users",
        data={
            "username": username,
            "password": password,
            "role": role,
            "admin_password": ADMIN_PASSWORD,
        },
    )
    if status != 200 or not payload.get("success"):
        return None, status, payload
    return get_user_by_username(username), status, payload


def reset_password(client, user_id, new_password, confirm_password):
    return post_json(
        client,
        f"/api/users/{user_id}/reset-password",
        json={
            "new_password": new_password,
            "confirm_password": confirm_password,
        },
    )


def main():
    stamp = int(time.time())
    prefix = f"reset_pw_{stamp}_"
    admin_username = f"smoke_reset_admin_{stamp}"
    target_username = f"{prefix}target"
    non_admin_username = f"{prefix}nonadmin"
    self_admin_username = f"{prefix}selfadmin"
    checks = []

    cleanup_temp_users(prefix)
    ensure_smoke_admin(admin_username, ADMIN_PASSWORD)

    admin_client = app.test_client()
    try:
        status, payload = post_json(admin_client, "/api/login", data={"username": admin_username, "password": ADMIN_PASSWORD})
        checks.append(print_check("admin login", status == 200 and payload.get("success") is True, payload))

        target_user, _, payload = create_user(admin_client, target_username, "Sup", OLD_PASSWORD)
        checks.append(print_check("create target user", target_user is not None, payload))

        if target_user:
            original = target_user.copy()
            status, payload = reset_password(admin_client, target_user["id"], NEW_PASSWORD, NEW_PASSWORD)
            checks.append(print_check("admin reset password succeeds", status == 200 and payload.get("success") is True, payload))

            updated_user = get_user_by_username(target_username)
            checks.append(print_check("password hash is scrypt", str(updated_user.get("password", "")).startswith("scrypt:"), {"password_prefix": str(updated_user.get("password", ""))[:12]}))
            checks.append(print_check("password is not plaintext", updated_user.get("password") != NEW_PASSWORD, {"stored": updated_user.get("password")}))
            checks.append(print_check("user identity fields preserved", updated_user["id"] == original["id"] and updated_user["username"] == original["username"] and updated_user["role"] == original["role"] and updated_user["created_at"] == original["created_at"], updated_user))

            old_login_client = app.test_client()
            _, payload = post_json(old_login_client, "/api/login", data={"username": target_username, "password": OLD_PASSWORD})
            checks.append(print_check("old password login fails", payload.get("success") is False, payload))

            new_login_client = app.test_client()
            status, payload = post_json(new_login_client, "/api/login", data={"username": target_username, "password": NEW_PASSWORD})
            checks.append(print_check("new password login succeeds", status == 200 and payload.get("success") is True, payload))

            status, payload = reset_password(admin_client, target_user["id"], "Mismatch123", "Different123")
            checks.append(print_check("mismatched confirmation rejected", status == 400 and payload.get("success") is False, payload))

            status, payload = reset_password(admin_client, target_user["id"], "short", "short")
            checks.append(print_check("short password rejected", status == 400 and payload.get("success") is False, payload))

        status, payload = reset_password(admin_client, 999999999, "Missing123", "Missing123")
        checks.append(print_check("missing user rejected", status == 404 and payload.get("success") is False, payload))

        non_admin_user, _, payload = create_user(admin_client, non_admin_username, "Manager", OLD_PASSWORD)
        checks.append(print_check("create non-admin user", non_admin_user is not None, payload))
        if non_admin_user and target_user:
            non_admin_client = app.test_client()
            status, payload = post_json(non_admin_client, "/api/login", data={"username": non_admin_username, "password": OLD_PASSWORD})
            checks.append(print_check("non-admin login", status == 200 and payload.get("success") is True, payload))

            status, payload = reset_password(non_admin_client, target_user["id"], "Blocked123", "Blocked123")
            checks.append(print_check("non-admin reset rejected", status == 403 and payload.get("success") is False, payload))

        self_admin_user, _, payload = create_user(admin_client, self_admin_username, "Admin", OLD_PASSWORD)
        checks.append(print_check("create self-reset admin", self_admin_user is not None, payload))
        if self_admin_user:
            self_client = app.test_client()
            status, payload = post_json(self_client, "/api/login", data={"username": self_admin_username, "password": OLD_PASSWORD})
            checks.append(print_check("self-reset admin login", status == 200 and payload.get("success") is True, payload))

            status, payload = reset_password(self_client, self_admin_user["id"], SELF_NEW_PASSWORD, SELF_NEW_PASSWORD)
            checks.append(print_check("self reset logs out session", status == 200 and payload.get("success") is True and payload.get("logged_out") is True, payload))

            status, payload = get_json(self_client, "/api/me")
            checks.append(print_check("self reset session cannot continue", status == 401 and payload.get("auth_required") is True, payload))

    finally:
        cleanup_temp_users(prefix)
        cleanup_smoke_user(admin_username)

    passed = sum(1 for ok in checks if ok)
    failed = len(checks) - passed
    print("\nSUMMARY")
    print(f"  total checks: {len(checks)}")
    print(f"  passed: {passed}")
    print(f"  failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
