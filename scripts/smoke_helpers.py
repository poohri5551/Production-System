from app import get_db_connection, ensure_users_table, hash_password, count_admin_users


def ensure_smoke_admin(username, password):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            cursor.execute("SELECT id, username, role FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            if user:
                cursor.execute(
                    "UPDATE users SET password = %s, role = 'Admin' WHERE id = %s",
                    (hash_password(password), user["id"]),
                )
            else:
                cursor.execute(
                    "INSERT INTO users (username, password, role) VALUES (%s, %s, 'Admin')",
                    (username, hash_password(password)),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cleanup_smoke_user(username):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            if count_admin_users(cursor) <= 1:
                return
            cursor.execute("DELETE FROM users WHERE username = %s", (username,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
