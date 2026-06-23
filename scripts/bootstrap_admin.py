import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import (  # noqa: E402
    get_db_connection,
    ensure_users_table,
    count_admin_users,
    hash_password,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Server-only emergency bootstrap for an Admin account. Do not expose this through web/API."
    )
    parser.add_argument("--username", default=os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", ""))
    parser.add_argument("--role", default="Admin")
    parser.add_argument(
        "--force-create-user",
        action="store_true",
        help="Allow creating the requested Admin account even when another Admin already exists.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    username = (args.username or "").strip()
    password = args.password or ""
    role = (args.role or "Admin").strip()

    if not username:
        print("FAIL username is required")
        return 2
    if not password:
        print("FAIL password is required")
        return 2
    if role.lower() != "admin":
        print("FAIL bootstrap role must be Admin")
        return 2

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)

            cursor.execute("SELECT id, username, role FROM users WHERE username = %s", (username,))
            existing_user = cursor.fetchone()
            if existing_user:
                print(f"SKIP user already exists: {username}")
                print(f"INFO existing role: {existing_user.get('role')}")
                return 0

            admin_count = count_admin_users(cursor)
            if admin_count > 0 and not args.force_create_user:
                print(f"SKIP {admin_count} Admin account(s) already exist.")
                print("INFO use --force-create-user only if you intentionally need another Admin.")
                return 0

            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (username, hash_password(password), "Admin"),
            )
        conn.commit()
        print(f"PASS created emergency Admin account: {username}")
        print("INFO password was not printed. Login through /api/login or the Vue app to verify.")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"FAIL bootstrap failed: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
