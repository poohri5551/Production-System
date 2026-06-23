from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from scripts.smoke_helpers import ensure_smoke_admin, cleanup_smoke_user  # noqa: E402


def print_check(name, ok, payload=None):
    status = "PASS" if ok else "FAIL"
    print(f"{status} {name}")
    if not ok and payload is not None:
        print(f"  payload: {payload}")
    return ok


def main():
    stamp = int(time.time())
    smoke_admin = f"smoke_users_admin_{stamp}"
    username = f"phase7_user_{stamp}"
    password = "12345"
    admin_password = "SmokeAdmin123"
    checks = []
    created_user = None

    ensure_smoke_admin(smoke_admin, admin_password)

    try:
        with app.test_client() as client:
            def get_json(path):
                response = client.get(path)
                return response.status_code, response.get_json(silent=True) or {}

            def post_json(path, data):
                response = client.post(path, data=data)
                return response.status_code, response.get_json(silent=True) or {}

            status, payload = post_json("/api/login", {"username": smoke_admin, "password": admin_password})
            checks.append(print_check("login admin", status == 200 and payload.get("success") is True, payload))

            status, payload = get_json("/api/users")
            checks.append(print_check("list users", status == 200 and payload.get("success") is True, payload))

            status, payload = post_json(
                "/api/users",
                {
                    "username": username,
                    "password": password,
                    "role": "Sup",
                    "admin_password": admin_password,
                },
            )
            checks.append(print_check("create user", status == 200 and payload.get("success") is True, payload))

            _, payload = get_json("/api/users")
            created_user = next((user for user in payload.get("users", []) if user.get("username") == username), None)
            checks.append(print_check("created user appears", created_user is not None, payload))

            if created_user:
                status, payload = post_json(
                    f"/api/users/{created_user['id']}/role",
                    {"role": "Manager", "admin_password": "wrong-password"},
                )
                checks.append(print_check("wrong admin password rejected", payload.get("success") is False, payload))

                status, payload = post_json(
                    f"/api/users/{created_user['id']}/role",
                    {"role": "Manager", "admin_password": admin_password},
                )
                checks.append(print_check("change role", status == 200 and payload.get("success") is True, payload))

                status, payload = post_json(
                    f"/api/users/{created_user['id']}/delete",
                    {"admin_password": admin_password},
                )
                checks.append(print_check("delete user", status == 200 and payload.get("success") is True, payload))

            _, payload = get_json("/api/users")
            admin = next((user for user in payload.get("users", []) if user.get("username") == "admin"), None)
            checks.append(print_check("main admin user exists", admin is not None, payload))

            if admin:
                status, payload = post_json(
                    f"/api/users/{admin['id']}/delete",
                    {"admin_password": admin_password},
                )
                checks.append(print_check("main admin delete guard", payload.get("success") is False, payload))
    finally:
        cleanup_smoke_user(smoke_admin)

    passed = sum(1 for ok in checks if ok)
    failed = len(checks) - passed
    print("\nSUMMARY")
    print(f"  total checks: {len(checks)}")
    print(f"  passed: {passed}")
    print(f"  failed: {failed}")
    print(f"  smoke username: {username}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
