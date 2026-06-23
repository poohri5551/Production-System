from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app, get_db_connection, ensure_users_table  # noqa: E402
from permissions import ROLE_PERMISSIONS, VALID_ROLES, has_permission, permissions_for_role  # noqa: E402
from scripts.smoke_helpers import ensure_smoke_admin, cleanup_smoke_user  # noqa: E402


ADMIN_PASSWORD = "SmokeAdmin123"
TEMP_PASSWORD = "12345"

EXPECTED_ROLE_PERMISSIONS = {
    "Admin": set(ROLE_PERMISSIONS["Admin"]),
    "Sup": {
        "dashboard.view",
        "production.view",
        "production.manage",
        "setting_die.view",
        "setting_die.manage",
        "qc.view",
        "production_start.view",
        "production_finish.view",
    },
    "Manager": {
        "dashboard.view",
        "production.view",
        "setting_die.view",
        "qc.view",
        "production_start.view",
        "production_finish.view",
    },
    "PC": {
        "dashboard.view",
        "production.view",
        "production.manage",
        "setting_die.view",
        "qc.view",
        "production_start.view",
        "production_finish.view",
    },
    "Technician": {
        "dashboard.view",
        "production.view",
        "setting_die.view",
        "setting_die.manage",
        "qc.view",
        "production_start.view",
        "production_finish.view",
    },
    "QC Line": {
        "dashboard.view",
        "production.view",
        "setting_die.view",
        "qc.view",
        "qc.manage",
        "production_start.view",
        "production_finish.view",
    },
    "Operator": {
        "dashboard.view",
        "production.view",
        "production_start.view",
        "production_start.manage",
        "production_finish.view",
        "production_finish.manage",
    },
}


def print_check(name, ok, payload=None):
    status = "PASS" if ok else "FAIL"
    print(f"{status} {name}")
    if not ok and payload is not None:
        print(f"  payload: {payload}")
    return ok


def post_json(client, path, data=None):
    response = client.post(path, data=data or {})
    return response.status_code, response.get_json(silent=True) or {}


def post_json_body(client, path, payload=None):
    response = client.post(path, json=payload or {})
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


def create_user(admin_client, username, role):
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


def assert_forbidden(checks, role, method, path, data=None, json_body=False):
    client = app.test_client()
    username = f"{assert_forbidden.prefix}_{role.lower().replace(' ', '_')}"
    status, payload = post_json(client, "/api/login", {"username": username, "password": TEMP_PASSWORD})
    checks.append(print_check(f"{role} login for forbidden checks", status == 200 and payload.get("success") is True, payload))
    if status != 200 or not payload.get("success"):
        return

    if method == "GET":
        status, payload = get_json(client, path)
    elif json_body:
        status, payload = post_json_body(client, path, data)
    else:
        status, payload = post_json(client, path, data)
    checks.append(print_check(f"{role} forbidden {method} {path}", status == 403 and payload.get("permission_denied") is True, payload))


assert_forbidden.prefix = ""


def main():
    stamp = int(time.time())
    prefix = f"role_perm_{stamp}"
    smoke_admin = f"smoke_role_perm_admin_{stamp}"
    checks = []
    created_users = {}

    cleanup_temp_users(prefix)
    ensure_smoke_admin(smoke_admin, ADMIN_PASSWORD)

    try:
        checks.append(print_check("valid roles include new roles", tuple(EXPECTED_ROLE_PERMISSIONS.keys()) == VALID_ROLES, VALID_ROLES))
        for role, expected_permissions in EXPECTED_ROLE_PERMISSIONS.items():
            actual_permissions = set(permissions_for_role(role))
            checks.append(print_check(f"{role} permission map", actual_permissions == expected_permissions, sorted(actual_permissions)))
            for permission in expected_permissions:
                checks.append(print_check(f"{role} has {permission}", has_permission(role, permission)))

        admin_client = app.test_client()
        status, payload = post_json(admin_client, "/api/login", {"username": smoke_admin, "password": ADMIN_PASSWORD})
        checks.append(print_check("admin login", status == 200 and payload.get("success") is True, payload))

        status, payload = get_json(admin_client, "/api/me")
        me_user = payload.get("user", {})
        checks.append(print_check("/api/me returns permissions", status == 200 and set(payload.get("permissions", [])) == EXPECTED_ROLE_PERMISSIONS["Admin"], payload))
        checks.append(print_check("/api/me omits password", "password" not in me_user and "password_hash" not in me_user, payload))

        for role in ["PC", "Technician", "QC Line", "Operator"]:
            username = f"{prefix}_{role.lower().replace(' ', '_')}"
            user, status, payload = create_user(admin_client, username, role)
            created_users[role] = user
            checks.append(print_check(f"admin creates {role}", user is not None, payload))

        update_user, _, payload = create_user(admin_client, f"{prefix}_role_update", "Manager")
        checks.append(print_check("create user for role updates", update_user is not None, payload))
        if update_user:
            for role in ["PC", "Technician", "QC Line", "Operator"]:
                status, payload = post_json(
                    admin_client,
                    f"/api/users/{update_user['id']}/role",
                    {"role": role, "admin_password": ADMIN_PASSWORD},
                )
                checks.append(print_check(f"admin changes role to {role}", status == 200 and payload.get("success") is True, payload))

            status, payload = post_json(
                admin_client,
                f"/api/users/{update_user['id']}/role",
                {"role": "BadRole", "admin_password": ADMIN_PASSWORD},
            )
            checks.append(print_check("invalid update role rejected", status == 400 and payload.get("success") is False, payload))

        status, payload = post_json(
            admin_client,
            "/api/users",
            {
                "username": f"{prefix}_bad_role",
                "password": TEMP_PASSWORD,
                "role": "BadRole",
                "admin_password": ADMIN_PASSWORD,
            },
        )
        checks.append(print_check("invalid create role rejected", status == 400 and payload.get("success") is False, payload))

        for role, user in created_users.items():
            if not user:
                continue
            client = app.test_client()
            status, payload = post_json(client, "/api/login", {"username": user["username"], "password": TEMP_PASSWORD})
            checks.append(print_check(f"{role} login", status == 200 and payload.get("role") == role, payload))

            status, payload = get_json(client, "/api/me")
            checks.append(print_check(f"{role} /api/me permissions", status == 200 and set(payload.get("permissions", [])) == EXPECTED_ROLE_PERMISSIONS[role], payload))

            status, payload = get_json(client, "/api/users")
            checks.append(print_check(f"{role} cannot list users", status == 403 and payload.get("permission_denied") is True, payload))

        assert_forbidden.prefix = prefix
        assert_forbidden(checks, "PC", "POST", "/api/users/1/reset-password", {"new_password": "abcdefgh", "confirm_password": "abcdefgh"}, json_body=True)
        assert_forbidden(checks, "Technician", "POST", "/api/qc/from_setting_die", {"plan_no": "SMOKE"})
        assert_forbidden(checks, "QC Line", "POST", "/api/setting_die", {"plan_id": "1"})
        assert_forbidden(checks, "Operator", "POST", "/api/qc", {"qc-plan-no": "SMOKE"})
        assert_forbidden(checks, "Operator", "POST", "/api/setting_die", {"plan_id": "1"})

        manager_user, _, payload = create_user(admin_client, f"{prefix}_manager", "Manager")
        checks.append(print_check("create manager for write denial checks", manager_user is not None, payload))
        if manager_user:
            for path in ["/api/production", "/api/setting_die", "/api/qc", "/api/production_start", "/api/production_finish"]:
                client = app.test_client()
                status, payload = post_json(client, "/api/login", {"username": manager_user["username"], "password": TEMP_PASSWORD})
                checks.append(print_check(f"Manager login for {path}", status == 200 and payload.get("success") is True, payload))
                status, payload = post_json(client, path, {})
                checks.append(print_check(f"Manager write denied {path}", status == 403 and payload.get("permission_denied") is True, payload))

    finally:
        cleanup_temp_users(prefix)
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
