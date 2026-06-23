import os
import sys
import uuid
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, session, g, has_request_context
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import pymysql
from permissions import (
    VALID_ROLES,
    has_any_permission,
    has_permission,
    normalize_user_role,
    permissions_for_role,
)
from part_services import (
    PartNotFoundError,
    PartValidationError,
    ensure_parts_schema,
    find_or_create_part_by_part_no,
    get_part_with_relations,
    normalize_part_no,
    run_part_transaction,
    soft_delete_part_by_part_no,
    update_part_by_part_no,
    validate_plan_part_consistency,
)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'inventory-local-dev-secret-change-me')
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=15 * 1024 * 1024,
)

# --- ตั้งค่าอัปโหลดไฟล์รูปภาพ ---
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join('static', 'uploads'))
if not os.path.isabs(UPLOAD_FOLDER):
    UPLOAD_FOLDER = os.path.join(app.root_path, UPLOAD_FOLDER)
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_UPLOAD_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'pdf'}
GENERIC_ERROR_MESSAGE = "เกิดข้อผิดพลาด กรุณาติดต่อผู้ดูแลระบบ"

VUE_DIST_FOLDER = os.path.join(app.root_path, 'frontend', 'dist')
VUE_ASSETS_FOLDER = os.path.join(VUE_DIST_FOLDER, 'assets')

# --- ตั้งค่า MySQL ---
db_config = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '3306')),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'database': os.environ.get('DB_NAME', 'inventory_db'),
    'cursorclass': pymysql.cursors.DictCursor
}

def get_db_connection():
    return pymysql.connect(**db_config)

ALLOWED_USER_ROLES = VALID_ROLES

class UploadValidationError(ValueError):
    pass

def error_response(message=GENERIC_ERROR_MESSAGE, status=500):
    if message == GENERIC_ERROR_MESSAGE:
        current_error = sys.exc_info()[1]
        if current_error:
            log_exception(request.endpoint or 'api', current_error)
    return jsonify({"success": False, "message": message}), status

def log_exception(context, error):
    app.logger.exception("%s: %s", context, error)

def allowed_file(filename):
    if not filename or '.' not in filename:
        return False
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in ALLOWED_UPLOAD_EXTENSIONS

def generate_safe_upload_filename(original_filename):
    cleaned_name = secure_filename(original_filename or '')
    if not allowed_file(cleaned_name):
        raise UploadValidationError("ไฟล์ไม่รองรับ")
    extension = cleaned_name.rsplit('.', 1)[1].lower()
    return f"{uuid.uuid4().hex}.{extension}"

def save_uploaded_file(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    filename = generate_safe_upload_filename(file_storage.filename)
    upload_root = os.path.realpath(app.config['UPLOAD_FOLDER'])
    save_path = os.path.realpath(os.path.join(upload_root, filename))
    if os.path.commonpath([upload_root, save_path]) != upload_root:
        raise UploadValidationError("ไฟล์ไม่รองรับ")
    os.makedirs(upload_root, exist_ok=True)
    file_storage.save(save_path)
    return filename

@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(error):
    if request.path.startswith('/api/'):
        return error_response("ไฟล์มีขนาดใหญ่เกินไป", 413)
    return "ไฟล์มีขนาดใหญ่เกินไป", 413

@app.errorhandler(404)
def handle_not_found(error):
    if request.path.startswith('/api/'):
        return error_response("ไม่พบข้อมูล", 404)
    return error

@app.errorhandler(500)
def handle_internal_server_error(error):
    if request.path.startswith('/api/'):
        app.logger.exception("Unhandled API error: %s", error)
        return error_response()
    return error

def format_datetime(dt_str):
    if dt_str: return dt_str.replace('T', ' ') + ':00'
    return None

def empty_to_none(value):
    if value == '':
        return None
    return value

def hash_password(password):
    return generate_password_hash(password or '')

def password_matches(stored_password, submitted_password):
    stored_password = stored_password or ''
    submitted_password = submitted_password or ''
    if stored_password.startswith(('scrypt:', 'pbkdf2:')):
        return check_password_hash(stored_password, submitted_password)
    # Backward compatibility for existing users created before password hashing.
    return stored_password == submitted_password

def ensure_production_starts_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS production_starts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plan_no VARCHAR(100) NOT NULL,
            lot_no VARCHAR(100),
            part_no VARCHAR(100),
            die_no VARCHAR(100),
            qty VARCHAR(50),
            time_start DATETIME,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_plan_no (plan_no)
        )
    """)
    cursor.execute("SHOW COLUMNS FROM production_starts LIKE 'confirm_status'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE production_starts ADD COLUMN confirm_status VARCHAR(30) DEFAULT 'waiting'")
    cursor.execute("SHOW COLUMNS FROM production_starts LIKE 'is_finished'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE production_starts ADD COLUMN is_finished TINYINT DEFAULT 0")

def ensure_production_finishes_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS production_finishes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plan_no VARCHAR(100) NOT NULL,
            lot_no VARCHAR(100),
            part_no VARCHAR(100),
            die_no VARCHAR(100),
            planned_qty VARCHAR(50),
            actual_qty VARCHAR(50),
            note TEXT,
            time_finish DATETIME,
            hold_time DATETIME,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_plan_no (plan_no)
        )
    """)
    cursor.execute("SHOW COLUMNS FROM production_finishes LIKE 'finish_status'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE production_finishes ADD COLUMN finish_status VARCHAR(30) DEFAULT 'pending'")
    snapshot_columns = [
        ('production_plan_id', 'production_plan_id INT'),
        ('setting_die_id', 'setting_die_id INT'),
        ('qc_inspection_id', 'qc_inspection_id INT'),
        ('production_start_id', 'production_start_id INT'),
        ('prod_date', 'prod_date DATE'),
        ('zone', 'zone VARCHAR(100)'),
        ('production_plan_status', 'production_plan_status VARCHAR(50)'),
        ('image_path', 'image_path VARCHAR(255)'),
        ('process_die', 'process_die VARCHAR(100)'),
        ('dh', 'dh VARCHAR(100)'),
        ('spm', 'spm VARCHAR(100)'),
        ('setting_time_start', 'setting_time_start DATETIME'),
        ('setting_time_end', 'setting_time_end DATETIME'),
        ('material', 'material VARCHAR(255)'),
        ('material_time_start', 'material_time_start DATETIME'),
        ('material_time_end', 'material_time_end DATETIME'),
        ('adjust_time_start', 'adjust_time_start DATETIME'),
        ('adjust_time_end', 'adjust_time_end DATETIME'),
        ('technician', 'technician VARCHAR(255)'),
        ('qc_time_start', 'qc_time_start DATETIME'),
        ('qc_time_end', 'qc_time_end DATETIME'),
        ('qc_percent_result', 'qc_percent_result VARCHAR(50)'),
        ('qc_status', 'qc_status VARCHAR(50)'),
        ('qc_problem_area', 'qc_problem_area VARCHAR(100)'),
        ('qc_problem_point', 'qc_problem_point VARCHAR(255)'),
        ('qc_image_path', 'qc_image_path VARCHAR(255)'),
        ('qc_cause', 'qc_cause TEXT'),
        ('qc_solution', 'qc_solution TEXT'),
        ('production_start_time', 'production_start_time DATETIME'),
        ('production_start_confirm_status', 'production_start_confirm_status VARCHAR(30)'),
    ]
    for column_name, column_definition in snapshot_columns:
        ensure_column(cursor, 'production_finishes', column_name, column_definition)

def ensure_column(cursor, table_name, column_name, column_definition):
    cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE %s", (column_name,))
    if not cursor.fetchone():
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")

WORKFLOW_TABLES = [
    'production_plans',
    'setting_dies',
    'qc_inspections',
    'production_starts',
    'production_finishes',
]

def ensure_workflow_created_by_columns(cursor):
    for table_name in WORKFLOW_TABLES:
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        if not cursor.fetchone():
            continue
        ensure_column(cursor, table_name, 'created_by_user_id', 'created_by_user_id INT NULL')
        ensure_column(cursor, table_name, 'created_by_username', 'created_by_username VARCHAR(80) NULL')

def created_by_values():
    return (
        session.get('user_id') if has_request_context() else None,
        session.get('username') if has_request_context() else None,
    )

def ensure_users_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(30) NOT NULL DEFAULT 'Admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    ensure_column(cursor, 'users', 'role', "role VARCHAR(30) NOT NULL DEFAULT 'Admin'")
    ensure_column(cursor, 'users', 'created_at', "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

def ensure_active_visibility_columns(cursor):
    ensure_column(cursor, 'production_plans', 'is_finished', 'is_finished TINYINT DEFAULT 0')
    ensure_column(cursor, 'setting_dies', 'is_finished', 'is_finished TINYINT DEFAULT 0')
    ensure_column(cursor, 'qc_inspections', 'is_finished', 'is_finished TINYINT DEFAULT 0')
    ensure_production_starts_table(cursor)
    ensure_production_finishes_table(cursor)
    ensure_parts_schema(cursor)
    ensure_workflow_created_by_columns(cursor)

def clear_active_work_for_plan(cursor, plan_no):
    ensure_active_visibility_columns(cursor)
    cursor.execute("SELECT plan_id FROM setting_dies WHERE plan_no = %s", (plan_no,))
    plan_ids = [row['plan_id'] for row in cursor.fetchall() if row.get('plan_id')]

    cursor.execute("UPDATE qc_inspections SET is_finished = 1 WHERE plan_no = %s", (plan_no,))
    cursor.execute("UPDATE production_starts SET is_finished = 1 WHERE plan_no = %s", (plan_no,))
    cursor.execute("UPDATE setting_dies SET is_finished = 1 WHERE plan_no = %s", (plan_no,))

    if plan_ids:
        placeholders = ','.join(['%s'] * len(plan_ids))
        cursor.execute(f"UPDATE production_plans SET is_finished = 1 WHERE id IN ({placeholders})", tuple(plan_ids))

def get_production_start_plan(cursor, plan_no):
    cursor.execute("""
        SELECT
            p.id AS plan_id,
            COALESCE(s.part_id, p.part_id) AS part_id,
            s.plan_no,
            s.lot_no,
            COALESCE(NULLIF(s.part_no, ''), p.part_no) AS part_no,
            COALESCE(NULLIF(s.die_no, ''), p.die_no) AS die_no,
            p.qty
        FROM setting_dies s
        LEFT JOIN production_plans p ON p.id = s.plan_id
        WHERE s.plan_no = %s
            AND s.deleted_at IS NULL
            AND p.deleted_at IS NULL
        ORDER BY s.id DESC
        LIMIT 1
    """, (plan_no,))
    return cursor.fetchone()

def first_value(*values):
    for value in values:
        if value not in (None, ''):
            return value
    return None

def collect_finish_snapshot(cursor, finish):
    plan_no = finish.get('plan_no')
    snapshot = {
        'lot_no': finish.get('lot_no'),
        'part_no': finish.get('part_no'),
        'die_no': finish.get('die_no'),
        'planned_qty': finish.get('planned_qty'),
    }

    cursor.execute("""
        SELECT
            p.id AS production_plan_id,
            p.part_id AS plan_part_id,
            p.prod_date,
            p.zone,
            p.status AS production_plan_status,
            p.image_path,
            p.qty AS plan_qty,
            s.id AS setting_die_id,
            s.lot_no AS setting_lot_no,
            COALESCE(NULLIF(s.part_no, ''), p.part_no) AS setting_part_no,
            COALESCE(NULLIF(s.die_no, ''), p.die_no) AS setting_die_no,
            s.process_die,
            s.dh,
            s.spm,
            s.time_start AS setting_time_start,
            s.time_end AS setting_time_end,
            s.material,
            s.custom_time_1 AS material_time_start,
            s.custom_time_2 AS material_time_end,
            s.custom_time_3 AS adjust_time_start,
            s.custom_time_4 AS adjust_time_end,
            s.technician
        FROM setting_dies s
        LEFT JOIN production_plans p ON p.id = s.plan_id
        WHERE s.plan_no = %s
        ORDER BY s.id DESC
        LIMIT 1
    """, (plan_no,))
    setting = cursor.fetchone() or {}

    cursor.execute("""
        SELECT
            id AS qc_inspection_id,
            part_id,
            lot_no AS qc_lot_no,
            part_no AS qc_part_no,
            time_start AS qc_time_start,
            time_end AS qc_time_end,
            percent_result AS qc_percent_result,
            status AS qc_status,
            problem_area AS qc_problem_area,
            problem_point AS qc_problem_point,
            image_path AS qc_image_path,
            cause AS qc_cause,
            solution AS qc_solution
        FROM qc_inspections
        WHERE plan_no = %s
        ORDER BY id DESC
        LIMIT 1
    """, (plan_no,))
    qc = cursor.fetchone() or {}

    cursor.execute("""
        SELECT
            id AS production_start_id,
            part_id,
            lot_no AS start_lot_no,
            part_no AS start_part_no,
            die_no AS start_die_no,
            qty AS start_qty,
            time_start AS production_start_time,
            confirm_status AS production_start_confirm_status
        FROM production_starts
        WHERE plan_no = %s
        ORDER BY id DESC
        LIMIT 1
    """, (plan_no,))
    start = cursor.fetchone() or {}

    snapshot.update({
        'lot_no': first_value(snapshot.get('lot_no'), setting.get('setting_lot_no'), start.get('start_lot_no'), qc.get('qc_lot_no')),
        'part_no': first_value(snapshot.get('part_no'), setting.get('setting_part_no'), start.get('start_part_no'), qc.get('qc_part_no')),
        'die_no': first_value(snapshot.get('die_no'), setting.get('setting_die_no'), start.get('start_die_no')),
        'planned_qty': first_value(snapshot.get('planned_qty'), setting.get('plan_qty'), start.get('start_qty')),
        'part_id': first_value(setting.get('plan_part_id'), start.get('part_id'), qc.get('part_id')),
    })

    snapshot.update({key: value for key, value in setting.items() if key not in ['setting_lot_no', 'setting_part_no', 'setting_die_no', 'plan_qty', 'plan_part_id']})
    snapshot.update({key: value for key, value in qc.items() if key not in ['part_id', 'qc_lot_no', 'qc_part_no']})
    snapshot.update({key: value for key, value in start.items() if key not in ['part_id', 'start_lot_no', 'start_part_no', 'start_die_no', 'start_qty']})
    return snapshot

def update_production_finish_snapshot(cursor, finish_id, finish):
    snapshot = collect_finish_snapshot(cursor, finish)
    if not snapshot:
        return

    columns = list(snapshot.keys())
    assignments = ', '.join([f"{column} = %s" for column in columns])
    values = [snapshot[column] for column in columns]
    cursor.execute(
        f"UPDATE production_finishes SET {assignments} WHERE id = %s",
        tuple(values + [finish_id])
    )

def verify_admin_password(cursor, password):
    if not password:
        return False
    ensure_users_table(cursor)
    current_user = getattr(g, 'current_user', None) if has_request_context() else None
    if current_user and current_user.get('role') == 'Admin':
        cursor.execute("SELECT id, password FROM users WHERE id = %s AND LOWER(role) = 'admin'", (current_user['id'],))
    else:
        cursor.execute("SELECT id, password FROM users WHERE username = %s AND LOWER(role) = 'admin'", ('admin',))
    admin = cursor.fetchone()
    if not admin:
        return False
    if not password_matches(admin.get('password'), password):
        return False
    if not str(admin.get('password') or '').startswith(('scrypt:', 'pbkdf2:')):
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hash_password(password), admin['id']))
    return True

def auth_error(message="Session expired or account was removed. Please login again.", status_code=401, clear_session=True):
    if clear_session:
        session.clear()
    return jsonify({
        "success": False,
        "message": message,
        "auth_required": status_code == 401,
    }), status_code

def load_session_user(cursor):
    user_id = session.get('user_id')
    username = session.get('username')
    if user_id:
        cursor.execute("SELECT id, username, role FROM users WHERE id = %s", (user_id,))
    elif username:
        cursor.execute("SELECT id, username, role FROM users WHERE username = %s", (username,))
    else:
        return None

    user = cursor.fetchone()
    if not user:
        return None

    role = normalize_user_role(user.get('role'))
    if not role:
        return None
    user['role'] = role
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = role
    return user

def current_user_is_admin():
    return (getattr(g, 'current_user', {}) or {}).get('role') == 'Admin'

def current_user_has_permission(permission):
    current_user = getattr(g, 'current_user', {}) or {}
    return has_permission(current_user.get('role'), permission)

def current_user_has_any_permission(permissions):
    current_user = getattr(g, 'current_user', {}) or {}
    return has_any_permission(current_user.get('role'), permissions)

def permission_error(required_permissions):
    permissions = list(required_permissions) if isinstance(required_permissions, (list, tuple, set)) else [required_permissions]
    return jsonify({
        "success": False,
        "message": "You do not have permission to perform this action.",
        "permission_denied": True,
        "required_permissions": permissions,
    }), 403

def require_permission(permission):
    if current_user_has_permission(permission):
        return None
    return permission_error(permission)

def require_any_permission(permissions):
    if current_user_has_any_permission(permissions):
        return None
    return permission_error(permissions)

ENDPOINT_REQUIRED_PERMISSION = {
    'verify_admin_password_api': 'users.manage',
    'add_production': 'production.manage',
    'accept_job': 'production.manage',
    'delete_job': 'production.manage',
    'bulk_delete_jobs': 'production.manage',
    'add_setting_die': 'setting_die.manage',
    'create_qc_from_setting_die': 'qc.manage',
    'delete_production_start': 'production_start.manage',
    'confirm_production_start': 'production_start.manage',
    'bulk_delete_production_start': 'production_start.manage',
    'save_production_start': 'production_start.manage',
    'save_production_finish': 'production_finish.manage',
    'confirm_production_finish': 'production_finish.manage',
    'bulk_delete_production_finish': 'production_finish.manage',
    'create_production_start_from_qc': 'qc.manage',
    'add_qc': 'qc.manage',
    'update_qc': 'qc.manage',
    'delete_qc': 'qc.manage',
    'bulk_delete_qc': 'qc.manage',
    'update_part_by_part_no_api': 'production.manage',
    'soft_delete_part_by_part_no_api': 'production.manage',
    'get_users': 'users.manage',
    'update_user_role': 'users.manage',
    'delete_user': 'users.manage',
    'reset_user_password': 'users.manage',
    'create_user': 'users.manage',
}

ENDPOINT_REQUIRED_ANY_PERMISSION = {
    'get_dashboard_parts_status': ('dashboard.view',),
    'get_dashboard_part_status_detail': ('dashboard.view',),
    'get_jobs': ('production.view', 'production.manage'),
    'get_job_detail': ('production.view', 'production.manage', 'setting_die.view', 'setting_die.manage'),
    'get_production_start_plans': ('production_start.view', 'production_start.manage'),
    'get_production_start_plan_detail': ('production_start.view', 'production_start.manage'),
    'get_qc_plans': ('qc.view', 'qc.manage'),
    'get_qc_plan_detail': ('qc.view', 'qc.manage'),
    'get_production_starts': ('production_start.view', 'production_start.manage'),
    'get_production_start_detail': ('production_start.view', 'production_start.manage'),
    'get_production_finishes': ('production_finish.view', 'production_finish.manage'),
    'get_production_finish_plans': ('production_finish.view', 'production_finish.manage'),
    'get_production_finish_plan_detail': ('production_finish.view', 'production_finish.manage'),
    'get_qc_list': ('qc.view', 'qc.manage'),
    'get_qc_detail': ('qc.view', 'qc.manage'),
    'get_part_relations_api': ('production.view', 'production.manage'),
}

def count_admin_users(cursor):
    cursor.execute("SELECT COUNT(*) AS count FROM users WHERE LOWER(role) = 'admin'")
    row = cursor.fetchone() or {}
    return row.get('count') or 0

def is_last_admin(cursor, user):
    if not user or normalize_user_role(user.get('role')) != 'Admin':
        return False
    return count_admin_users(cursor) <= 1

def require_not_last_admin_before_delete_or_demote(cursor, user, action):
    if not is_last_admin(cursor, user):
        return None
    if action == 'delete':
        return jsonify({"success": False, "message": "Cannot delete the last admin account."}), 400
    return jsonify({"success": False, "message": "Cannot demote the last admin account."}), 400

@app.before_request
def validate_api_session():
    if not request.path.startswith('/api/'):
        return None
    if request.endpoint in {'api_login', 'api_logout'}:
        return None

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            user = load_session_user(cursor)
            if not user:
                return auth_error()
            g.current_user = user
    finally:
        conn.close()

    required_permission = ENDPOINT_REQUIRED_PERMISSION.get(request.endpoint)
    if required_permission:
        denied = require_permission(required_permission)
        if denied:
            return denied

    required_any_permission = ENDPOINT_REQUIRED_ANY_PERMISSION.get(request.endpoint)
    if required_any_permission:
        denied = require_any_permission(required_any_permission)
        if denied:
            return denied

    return None

def dashboard_value(value, fallback='-'):
    return value if value not in (None, '') else fallback

def dashboard_latest(records):
    if not records:
        return None
    return sorted(records, key=lambda item: item.get('id') or 0)[-1]

def dashboard_last_updated(*records):
    values = []
    for record in records:
        if not record:
            continue
        for field in ['updated_at', 'time_finish', 'time_end', 'time_start', 'created_at']:
            value = record.get(field)
            if value:
                values.append(value)
    return max(values) if values else None

def dashboard_first_value(record, field_names, fallback='-'):
    record = record or {}
    for field_name in field_names:
        value = record.get(field_name)
        if value not in (None, ''):
            return value
    return fallback

def dashboard_recorded_by(record):
    return dashboard_first_value(record, ['created_by_username', 'created_by'])

def dashboard_detail_entry(label, value):
    return {
        'label': label,
        'value': dashboard_value(value),
    }

def dashboard_source_metadata(source_table, source_id):
    return {
        'source_table': source_table,
        'source_id': source_id,
    }

def dashboard_fetch_related(cursor, plan_ids):
    related = {
        'setting_dies': {},
        'qc_inspections': {},
        'production_starts': {},
        'production_finishes': {},
    }
    if not plan_ids:
        return related

    placeholders = ','.join(['%s'] * len(plan_ids))
    cursor.execute(f"""
        SELECT *
        FROM setting_dies
        WHERE plan_id IN ({placeholders})
            AND deleted_at IS NULL
        ORDER BY id ASC
    """, tuple(plan_ids))
    settings = cursor.fetchall()
    plan_no_to_id = {}
    for row in settings:
        related['setting_dies'].setdefault(row.get('plan_id'), []).append(row)
        if row.get('plan_no') and row.get('plan_id'):
            plan_no_to_id[row['plan_no']] = row['plan_id']

    plan_no_placeholders = ','.join(['%s'] * len(plan_no_to_id))
    plan_no_values = tuple(plan_no_to_id.keys())
    for table_name in ['qc_inspections', 'production_starts', 'production_finishes']:
        sql = f"""
            SELECT *
            FROM {table_name}
            WHERE deleted_at IS NULL
                AND (plan_id IN ({placeholders})
        """
        params = list(plan_ids)
        if plan_no_values:
            sql += f" OR plan_no IN ({plan_no_placeholders})"
            params.extend(plan_no_values)
        sql += ") ORDER BY id ASC"
        cursor.execute(sql, tuple(params))
        for row in cursor.fetchall():
            plan_id = row.get('plan_id') or plan_no_to_id.get(row.get('plan_no'))
            if plan_id:
                related[table_name].setdefault(plan_id, []).append(row)
    return related

def dashboard_derive_item(plan, related):
    plan_id = plan.get('id')
    setting = dashboard_latest(related['setting_dies'].get(plan_id, []))
    qc = dashboard_latest(related['qc_inspections'].get(plan_id, []))
    start = dashboard_latest(related['production_starts'].get(plan_id, []))
    finish = dashboard_latest(related['production_finishes'].get(plan_id, []))

    has_setting = setting is not None
    has_qc = qc is not None
    has_start = start is not None
    has_finish = finish is not None
    finish_status = (finish.get('finish_status') if finish else '') or ''
    start_status = (start.get('confirm_status') if start else '') or ''
    is_completed = bool(plan.get('is_finished')) or finish_status.lower() == 'confirmed'

    if is_completed:
        current_step = 'Completed'
        status = 'completed'
    elif has_finish:
        current_step = 'Production Finish'
        status = finish_status or 'pending'
    elif has_start:
        current_step = 'Production Start'
        status = 'confirmed' if start_status.lower() == 'confirmed' else (start_status or 'waiting')
    elif has_qc:
        current_step = 'QC'
        status = qc.get('status') or 'pending'
    elif has_setting:
        current_step = 'Setting Die'
        status = 'done'
    else:
        current_step = 'Not Started'
        status = plan.get('status') or 'pending'

    return {
        'plan_id': plan_id,
        'plan_no': dashboard_value(
            (finish or {}).get('plan_no') or (start or {}).get('plan_no') or (qc or {}).get('plan_no') or (setting or {}).get('plan_no')
        ),
        'part_id': plan.get('part_id'),
        'part_no': dashboard_value(
            (finish or {}).get('part_no') or (start or {}).get('part_no') or (qc or {}).get('part_no') or (setting or {}).get('part_no') or plan.get('part_no')
        ),
        'die_no': dashboard_value(
            (finish or {}).get('die_no') or (start or {}).get('die_no') or (setting or {}).get('die_no') or plan.get('die_no')
        ),
        'zone': dashboard_value(plan.get('zone')),
        'current_step': current_step,
        'status': status,
        'last_updated': dashboard_last_updated(finish, start, qc, setting, plan),
        'is_finished': is_completed,
        'flags': {
            'has_setting_die': has_setting,
            'has_qc': has_qc,
            'has_production_start': has_start,
            'has_production_finish': has_finish,
        }
    }

def dashboard_plan_detail(plan):
    return [
        dashboard_detail_entry('Plan No.', plan.get('plan_no')),
        dashboard_detail_entry('Part No.', plan.get('part_no')),
        dashboard_detail_entry('Die No.', plan.get('die_no')),
        dashboard_detail_entry('Zone', plan.get('zone')),
        dashboard_detail_entry('Status', plan.get('status') or 'pending'),
        dashboard_detail_entry('Is Finished', 'Yes' if plan.get('is_finished') else 'No'),
        dashboard_detail_entry('Created At', plan.get('created_at')),
        dashboard_detail_entry('Updated At', plan.get('updated_at')),
        dashboard_detail_entry('Recorded by', dashboard_recorded_by(plan)),
        dashboard_detail_entry('Source', f"production_plans #{dashboard_value(plan.get('id'))}"),
    ]

def dashboard_setting_detail(row):
    return [
        dashboard_detail_entry('Plan No.', row.get('plan_no')),
        dashboard_detail_entry('Part No.', row.get('part_no')),
        dashboard_detail_entry('Die No.', row.get('die_no')),
        dashboard_detail_entry('Lot No.', row.get('lot_no')),
        dashboard_detail_entry('Process Die', row.get('process_die')),
        dashboard_detail_entry('DH', row.get('dh')),
        dashboard_detail_entry('SPM', row.get('spm')),
        dashboard_detail_entry('Material', row.get('material')),
        dashboard_detail_entry('Technician', row.get('technician')),
        dashboard_detail_entry('Recorded by', dashboard_recorded_by(row)),
        dashboard_detail_entry('Time Start Setting Die', row.get('time_start')),
        dashboard_detail_entry('Time End Setting Die', row.get('time_end')),
        dashboard_detail_entry('Time Start Setting Material', row.get('custom_time_1')),
        dashboard_detail_entry('Time End Setting Material', row.get('custom_time_2')),
        dashboard_detail_entry('Time Start Adjust Accuracy Part', row.get('custom_time_3')),
        dashboard_detail_entry('Time End Adjust Accuracy Part', row.get('custom_time_4')),
        dashboard_detail_entry('Is Finished', 'Yes' if row.get('is_finished') else 'No'),
        dashboard_detail_entry('Created At', row.get('created_at')),
        dashboard_detail_entry('Source', f"setting_dies #{dashboard_value(row.get('id'))}"),
    ]

def dashboard_qc_detail(row):
    return [
        dashboard_detail_entry('Plan No.', row.get('plan_no')),
        dashboard_detail_entry('Part No.', row.get('part_no')),
        dashboard_detail_entry('Lot No.', row.get('lot_no')),
        dashboard_detail_entry('Result / Status', row.get('status') or 'pending'),
        dashboard_detail_entry('Percent Result', row.get('percent_result')),
        dashboard_detail_entry('Time Start', row.get('time_start')),
        dashboard_detail_entry('Time End', row.get('time_end')),
        dashboard_detail_entry('Problem Area', row.get('problem_area')),
        dashboard_detail_entry('Problem Point', row.get('problem_point')),
        dashboard_detail_entry('Cause', row.get('cause')),
        dashboard_detail_entry('Solution', row.get('solution')),
        dashboard_detail_entry('Recorded by', dashboard_recorded_by(row)),
        dashboard_detail_entry('Created At', row.get('created_at')),
        dashboard_detail_entry('Is Finished', 'Yes' if row.get('is_finished') else 'No'),
        dashboard_detail_entry('Source', f"qc_inspections #{dashboard_value(row.get('id'))}"),
    ]

def dashboard_production_start_detail(row):
    return [
        dashboard_detail_entry('Plan No.', row.get('plan_no')),
        dashboard_detail_entry('Part No.', row.get('part_no')),
        dashboard_detail_entry('Die No.', row.get('die_no')),
        dashboard_detail_entry('Lot No.', row.get('lot_no')),
        dashboard_detail_entry('Qty', row.get('qty')),
        dashboard_detail_entry('Confirm Status', row.get('confirm_status') or 'waiting'),
        dashboard_detail_entry('Time Start', row.get('time_start')),
        dashboard_detail_entry('Recorded by', dashboard_recorded_by(row)),
        dashboard_detail_entry('Created At', row.get('created_at')),
        dashboard_detail_entry('Updated At', row.get('updated_at')),
        dashboard_detail_entry('Is Finished', 'Yes' if row.get('is_finished') else 'No'),
        dashboard_detail_entry('Source', f"production_starts #{dashboard_value(row.get('id'))}"),
    ]

def dashboard_production_finish_detail(row):
    return [
        dashboard_detail_entry('Plan No.', row.get('plan_no')),
        dashboard_detail_entry('Part No.', row.get('part_no')),
        dashboard_detail_entry('Die No.', row.get('die_no')),
        dashboard_detail_entry('Lot No.', row.get('lot_no')),
        dashboard_detail_entry('Planned Qty', row.get('planned_qty')),
        dashboard_detail_entry('Actual Qty', row.get('actual_qty')),
        dashboard_detail_entry('Finish Status', row.get('finish_status') or 'pending'),
        dashboard_detail_entry('Time Finish', row.get('time_finish')),
        dashboard_detail_entry('Hold Time', row.get('hold_time')),
        dashboard_detail_entry('Note', row.get('note')),
        dashboard_detail_entry('Recorded by', dashboard_recorded_by(row)),
        dashboard_detail_entry('Created At', row.get('created_at')),
        dashboard_detail_entry('Source', f"production_finishes #{dashboard_value(row.get('id'))}"),
    ]

def dashboard_timeline_from_records(plan, related):
    plan_id = plan.get('id')
    timeline = [{
        'step': 'Production Plan',
        'status': plan.get('status') or 'pending',
        'time_start': None,
        'time_end': None,
        'time_finish': None,
        'created_at': plan.get('created_at'),
        'updated_at': None,
        'user': dashboard_recorded_by(plan),
        'source_table': 'production_plans',
        'source_id': plan_id,
        'metadata': dashboard_source_metadata('production_plans', plan_id),
        'detail': dashboard_plan_detail(plan),
    }]

    for row in related['setting_dies'].get(plan_id, []):
        timeline.append({
            'step': 'Setting Die',
            'status': 'finished' if row.get('is_finished') else 'done',
            'time_start': row.get('time_start'),
            'time_end': row.get('time_end'),
            'time_finish': None,
            'created_at': row.get('created_at'),
            'updated_at': None,
            'user': dashboard_recorded_by(row),
            'source_table': 'setting_dies',
            'source_id': row.get('id'),
            'metadata': dashboard_source_metadata('setting_dies', row.get('id')),
            'detail': dashboard_setting_detail(row),
        })

    for row in related['qc_inspections'].get(plan_id, []):
        timeline.append({
            'step': 'QC Inspection',
            'status': row.get('status') or 'pending',
            'time_start': row.get('time_start'),
            'time_end': row.get('time_end'),
            'time_finish': None,
            'created_at': row.get('created_at'),
            'updated_at': None,
            'user': dashboard_recorded_by(row),
            'source_table': 'qc_inspections',
            'source_id': row.get('id'),
            'metadata': dashboard_source_metadata('qc_inspections', row.get('id')),
            'detail': dashboard_qc_detail(row),
        })

    for row in related['production_starts'].get(plan_id, []):
        timeline.append({
            'step': 'Production Start',
            'status': row.get('confirm_status') or 'waiting',
            'time_start': row.get('time_start'),
            'time_end': None,
            'time_finish': None,
            'created_at': row.get('created_at'),
            'updated_at': row.get('updated_at'),
            'user': dashboard_recorded_by(row),
            'source_table': 'production_starts',
            'source_id': row.get('id'),
            'metadata': dashboard_source_metadata('production_starts', row.get('id')),
            'detail': dashboard_production_start_detail(row),
        })

    for row in related['production_finishes'].get(plan_id, []):
        timeline.append({
            'step': 'Production Finish',
            'status': row.get('finish_status') or 'pending',
            'time_start': None,
            'time_end': None,
            'time_finish': row.get('time_finish'),
            'created_at': row.get('created_at'),
            'updated_at': None,
            'user': dashboard_recorded_by(row),
            'source_table': 'production_finishes',
            'source_id': row.get('id'),
            'metadata': dashboard_source_metadata('production_finishes', row.get('id')),
            'detail': dashboard_production_finish_detail(row),
        })

    return sorted(
        timeline,
        key=lambda item: item.get('time_finish') or item.get('time_end') or item.get('time_start') or item.get('updated_at') or item.get('created_at')
    )

@app.route('/')
def index():
    return redirect('/app')

@app.route('/legacy-login')
def legacy_login():
    return render_template('login.html')

@app.route('/mainpage')
def mainpage():
    response = app.make_response(render_template('mainpage.html'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

def serve_vue_index():
    index_path = os.path.join(VUE_DIST_FOLDER, 'index.html')
    if not os.path.exists(index_path):
        return "Vue production build not found. Run: npm.cmd --prefix .\\frontend run build", 404
    response = send_from_directory(VUE_DIST_FOLDER, 'index.html')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response

@app.route('/app/assets/<path:filename>')
def vue_assets(filename):
    return send_from_directory(VUE_ASSETS_FOLDER, filename)

@app.route('/app')
@app.route('/app/')
def vue_app():
    return serve_vue_index()

@app.route('/app/<path:path>')
def vue_app_fallback(path):
    return serve_vue_index()

@app.route('/api/login', methods=['POST'])
def api_login():
    username = request.form.get('username')
    password = request.form.get('password')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
            user = cursor.fetchone()
            if user and password_matches(user.get('password'), password):
                role = normalize_user_role(user.get('role'))
                if not role:
                    return jsonify({"success": False, "message": "User role is invalid. Please contact an admin."}), 403
                if not str(user.get('password') or '').startswith(('scrypt:', 'pbkdf2:')):
                    cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hash_password(password), user['id']))
                    conn.commit()
                session.clear()
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = role
                return jsonify({
                    "success": True,
                    "username": user['username'],
                    "role": role,
                    "permissions": permissions_for_role(role),
                })
            return jsonify({"success": False, "message": "ล็อกอินไม่สำเร็จ"})
    finally:
        conn.close()

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({"success": True})

@app.route('/api/me', methods=['GET'])
def api_me():
    user = getattr(g, 'current_user', None)
    if not user:
        return auth_error()
    return jsonify({
        "success": True,
        "user": {
            "id": user['id'],
            "username": user['username'],
            "role": user['role'],
        },
        "permissions": permissions_for_role(user['role']),
    })

@app.route('/api/admin/verify_password', methods=['POST'])
def verify_admin_password_api():
    password = request.form.get('admin_password')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if verify_admin_password(cursor, password):
                return jsonify({"success": True})
            return jsonify({"success": False, "message": "รหัสผ่าน admin ไม่ถูกต้อง"})
    finally:
        conn.close()

# --- ดึงตาราง Production (ทั้งหมด + ระบบค้นหา) ---
@app.route('/api/dashboard/parts-status', methods=['GET'])
def get_dashboard_parts_status():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_active_visibility_columns(cursor)
            cursor.execute("""
                SELECT
                    p.id,
                    p.part_id,
                    COALESCE(parts.part_no, p.part_no) AS part_no,
                    p.die_no,
                    p.zone,
                    p.status,
                    p.created_at,
                    p.created_by_user_id,
                    p.created_by_username,
                    p.is_finished
                FROM production_plans p
                LEFT JOIN parts ON parts.id = p.part_id
                WHERE p.deleted_at IS NULL
                ORDER BY p.id DESC
            """)
            plans = cursor.fetchall()
            related = dashboard_fetch_related(cursor, [plan['id'] for plan in plans])
            items = [dashboard_derive_item(plan, related) for plan in plans]
            summary = {
                'total': len(items),
                'waiting': sum(1 for item in items if item['current_step'] == 'Not Started' or str(item['status']).lower() in ['waiting', 'pending']),
                'in_progress': sum(1 for item in items if item['current_step'] in ['Setting Die', 'Production Start', 'Production Finish'] and not item['is_finished']),
                'qc': sum(1 for item in items if item['current_step'] == 'QC'),
                'completed': sum(1 for item in items if item['is_finished']),
            }
            return jsonify({"success": True, "summary": summary, "items": items})
    finally:
        conn.close()

@app.route('/api/dashboard/parts-status/<int:plan_id>', methods=['GET'])
def get_dashboard_part_status_detail(plan_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_active_visibility_columns(cursor)
            cursor.execute("""
                SELECT
                    p.id,
                    p.part_id,
                    COALESCE(parts.part_no, p.part_no) AS part_no,
                    p.die_no,
                    p.zone,
                    p.status,
                    p.created_at,
                    p.created_by_user_id,
                    p.created_by_username,
                    p.is_finished
                FROM production_plans p
                LEFT JOIN parts ON parts.id = p.part_id
                WHERE p.id = %s
                    AND p.deleted_at IS NULL
                LIMIT 1
            """, (plan_id,))
            plan = cursor.fetchone()
            if not plan:
                return jsonify({"success": False, "message": "Dashboard plan not found"}), 404

            related = dashboard_fetch_related(cursor, [plan_id])
            item = dashboard_derive_item(plan, related)
            return jsonify({
                "success": True,
                "plan": {
                    "plan_id": item['plan_id'],
                    "plan_no": item['plan_no'],
                    "part_id": item['part_id'],
                    "part_no": item['part_no'],
                    "die_no": item['die_no'],
                    "zone": item['zone'],
                },
                "current_step": item['current_step'],
                "status": item['status'],
                "is_finished": item['is_finished'],
                "flags": item['flags'],
                "timeline": dashboard_timeline_from_records(plan, related),
            })
    finally:
        conn.close()

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    zone = request.args.get('zone', '')
    part_no = normalize_part_no(request.args.get('part_no', ''))
    die_no = request.args.get('die_no', '')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # ใช้ 1=1 เพื่อให้ง่ายต่อการต่อ String ของ SQL
            ensure_active_visibility_columns(cursor)
            sql = "SELECT * FROM production_plans WHERE COALESCE(is_finished, 0) = 0 AND deleted_at IS NULL"
            params = []
            
            if zone:
                sql += " AND zone = %s"
                params.append(zone)
            if part_no:
                sql += " AND UPPER(TRIM(part_no)) LIKE %s"
                params.append(f"%{part_no}%")  # ใส่ % เพื่อให้ค้นหาแค่บางคำได้
            if die_no:
                sql += " AND die_no LIKE %s"
                params.append(f"%{die_no}%")
                
            sql += " ORDER BY id DESC"
            cursor.execute(sql, tuple(params))
            return jsonify(cursor.fetchall())
    finally:
        conn.close()

# --- [ใหม่] ดึงข้อมูล Production เชิงลึกตาม ID (รวม Setting Die) ---
@app.route('/api/jobs/<int:job_id>', methods=['GET'])
def get_job_detail(job_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # ดึงข้อมูลงาน
            ensure_parts_schema(cursor)
            cursor.execute("SELECT * FROM production_plans WHERE id = %s AND deleted_at IS NULL", (job_id,))
            job = cursor.fetchone()
            if not job:
                return jsonify({"success": False, "message": "ไม่พบข้อมูล"})
            
            # ดึงข้อมูล Setting Die (ถ้ามี)
            cursor.execute("SELECT * FROM setting_dies WHERE plan_id = %s AND deleted_at IS NULL ORDER BY id DESC LIMIT 1", (job_id,))
            setting = cursor.fetchone()
            
            return jsonify({"success": True, "job": job, "setting": setting})
    except Exception as e:
        return error_response()
    finally:
        conn.close()

@app.route('/api/production', methods=['POST'])
def add_production():
    date = request.form.get('prod-date')
    zone = request.form.get('prod-zone')
    part_no = request.form.get('prod-part-no')
    die_no = request.form.get('prod-die-no')
    qty = request.form.get('prod-qty')
    
    image_path = None
    try:
        image_path = save_uploaded_file(request.files.get('prod-image'))
    except UploadValidationError as e:
        return error_response(str(e), 400)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_parts_schema(cursor)
            ensure_workflow_created_by_columns(cursor)
            part = find_or_create_part_by_part_no(cursor, part_no)
            created_by_user_id, created_by_username = created_by_values()
            cursor.execute("""
                INSERT INTO production_plans
                (prod_date, zone, part_no, part_id, image_path, die_no, qty, created_by_user_id, created_by_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (date, zone, part['part_no'], part['id'], image_path, die_no, qty, created_by_user_id, created_by_username))
        conn.commit()
        return jsonify({"success": True})
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/jobs/<int:job_id>/accept', methods=['POST'])
def accept_job(job_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_parts_schema(cursor)
            cursor.execute("UPDATE production_plans SET status = 'accepted' WHERE id = %s AND deleted_at IS NULL", (job_id,))
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()

@app.route('/api/jobs/<int:job_id>/delete', methods=['POST'])
def delete_job(job_id):
    password = request.form.get('admin_password')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if not verify_admin_password(cursor, password):
                return jsonify({"success": False, "message": "รหัสผ่าน admin ไม่ถูกต้อง"})

            ensure_parts_schema(cursor)
            cursor.execute("UPDATE setting_dies SET deleted_at = NOW() WHERE plan_id = %s", (job_id,))
            cursor.execute("UPDATE production_plans SET deleted_at = NOW() WHERE id = %s", (job_id,))
        conn.commit()
        return jsonify({"success": True})
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/jobs/bulk_delete', methods=['POST'])
def bulk_delete_jobs():
    password = request.form.get('admin_password')
    ids = request.form.getlist('ids[]') or request.form.getlist('ids')
    ids = [int(item_id) for item_id in ids if str(item_id).isdigit()]

    if not ids:
        return jsonify({"success": False, "message": "กรุณาเลือกรายการที่ต้องการลบ"})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if not verify_admin_password(cursor, password):
                return jsonify({"success": False, "message": "รหัสผ่าน admin ไม่ถูกต้อง"})

            placeholders = ','.join(['%s'] * len(ids))
            ensure_parts_schema(cursor)
            cursor.execute(f"UPDATE setting_dies SET deleted_at = NOW() WHERE plan_id IN ({placeholders})", tuple(ids))
            cursor.execute(f"UPDATE production_plans SET deleted_at = NOW() WHERE id IN ({placeholders})", tuple(ids))
        conn.commit()
        return jsonify({"success": True, "deleted": len(ids)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/setting_die', methods=['POST'])
def add_setting_die():
    plan_id = request.form.get('plan_id')
    form = request.form
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # ตรวจสอบก่อนว่าเคยมีการบันทึก Setting Die ของ plan_id นี้ไปหรือยัง?
            ensure_parts_schema(cursor)
            ensure_workflow_created_by_columns(cursor)
            part, _plan = validate_plan_part_consistency(cursor, plan_id, form.get('set-part-no'))
            cursor.execute("SELECT id FROM setting_dies WHERE plan_id = %s AND deleted_at IS NULL", (plan_id,))
            existing = cursor.fetchone()

            if existing:
                # ถ้า "มีข้อมูลเก่าอยู่แล้ว" -> ให้ทำการอัปเดต (UPDATE) ทับของเดิม
                cursor.execute("""
                    UPDATE setting_dies SET 
                    part_id=%s, part_no=%s, lot_no=%s, plan_no=%s, process_die=%s, dh=%s, spm=%s, 
                    time_start=%s, time_end=%s, material=%s, 
                    custom_time_1=%s, custom_time_2=%s, custom_time_3=%s, custom_time_4=%s, 
                    technician=%s
                    WHERE plan_id=%s
                """, (
                    part['id'], part['part_no'], form.get('set-lot-no'), form.get('set-plan-no'), form.get('set-process-die'),
                    empty_to_none(form.get('set-dh')), empty_to_none(form.get('set-spm')),
                    format_datetime(form.get('set-time-start')), format_datetime(form.get('set-time-end')),
                    form.get('set-material'), 
                    format_datetime(form.get('custom-time-1')), format_datetime(form.get('custom-time-2')),
                    format_datetime(form.get('custom-time-3')), format_datetime(form.get('custom-time-4')), 
                    form.get('set-technician'),
                    plan_id
                ))
            else:
                # ถ้า "ยังไม่เคยมีข้อมูล" -> ให้เพิ่มข้อมูลใหม่ (INSERT)
                created_by_user_id, created_by_username = created_by_values()
                cursor.execute("""
                    INSERT INTO setting_dies 
                    (plan_id, part_id, part_no, lot_no, die_no, plan_no, process_die, dh, spm, time_start, time_end, material, custom_time_1, custom_time_2, custom_time_3, custom_time_4, technician, created_by_user_id, created_by_username)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    plan_id, part['id'], part['part_no'], form.get('set-lot-no'), form.get('set-die-no'), form.get('set-plan-no'), form.get('set-process-die'),
                    empty_to_none(form.get('set-dh')), empty_to_none(form.get('set-spm')), format_datetime(form.get('set-time-start')), format_datetime(form.get('set-time-end')),
                    form.get('set-material'), format_datetime(form.get('custom-time-1')), format_datetime(form.get('custom-time-2')),
                    format_datetime(form.get('custom-time-3')), format_datetime(form.get('custom-time-4')), form.get('set-technician'),
                    created_by_user_id, created_by_username
                ))
                
        conn.commit()
        return jsonify({"success": True})
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/production_start/plans', methods=['GET'])
def get_production_start_plans():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_active_visibility_columns(cursor)
            cursor.execute("""
                SELECT
                    p.id AS plan_id,
                    COALESCE(s.part_id, p.part_id) AS part_id,
                    s.plan_no,
                    s.lot_no,
                    COALESCE(NULLIF(s.part_no, ''), p.part_no) AS part_no,
                    COALESCE(NULLIF(s.die_no, ''), p.die_no) AS die_no,
                    p.qty
                FROM setting_dies s
                LEFT JOIN production_plans p ON p.id = s.plan_id
                WHERE s.plan_no IS NOT NULL AND s.plan_no <> ''
                    AND COALESCE(s.is_finished, 0) = 0
                    AND COALESCE(p.is_finished, 0) = 0
                    AND s.deleted_at IS NULL
                    AND p.deleted_at IS NULL
                    AND NOT EXISTS (
                        SELECT 1
                        FROM production_starts ps
                        WHERE ps.plan_no = s.plan_no
                            AND COALESCE(ps.is_finished, 0) = 0
                            AND ps.deleted_at IS NULL
                    )
                ORDER BY s.id DESC
            """)
            rows = cursor.fetchall()
            plans = []
            seen = set()
            for row in rows:
                if row['plan_no'] in seen:
                    continue
                seen.add(row['plan_no'])
                plans.append(row)
            return jsonify(plans)
    finally:
        conn.close()

@app.route('/api/production_start/plan', methods=['GET'])
def get_production_start_plan_detail():
    plan_no = request.args.get('plan_no', '')
    if not plan_no:
        return jsonify({"success": False, "message": "กรุณาเลือก Plan No."})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_parts_schema(cursor)
            plan = get_production_start_plan(cursor, plan_no)
            if not plan:
                return jsonify({"success": False, "message": "ไม่พบข้อมูล Plan No. นี้"})
            return jsonify({"success": True, "plan": plan})
    finally:
        conn.close()

@app.route('/api/qc/plans', methods=['GET'])
def get_qc_plans():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_active_visibility_columns(cursor)
            cursor.execute("""
                SELECT
                    p.id AS plan_id,
                    COALESCE(s.part_id, p.part_id) AS part_id,
                    s.plan_no,
                    s.lot_no,
                    COALESCE(NULLIF(s.part_no, ''), p.part_no) AS part_no,
                    COALESCE(NULLIF(s.die_no, ''), p.die_no) AS die_no,
                    p.qty
                FROM setting_dies s
                LEFT JOIN production_plans p ON p.id = s.plan_id
                WHERE s.plan_no IS NOT NULL AND s.plan_no <> ''
                    AND COALESCE(s.is_finished, 0) = 0
                    AND COALESCE(p.is_finished, 0) = 0
                    AND s.deleted_at IS NULL
                    AND p.deleted_at IS NULL
                ORDER BY s.id DESC
            """)
            rows = cursor.fetchall()
            plans = []
            seen = set()
            for row in rows:
                if row['plan_no'] in seen:
                    continue
                seen.add(row['plan_no'])
                plans.append(row)
            return jsonify(plans)
    finally:
        conn.close()

@app.route('/api/qc/plan', methods=['GET'])
def get_qc_plan_detail():
    plan_no = request.args.get('plan_no', '')
    if not plan_no:
        return jsonify({"success": False, "message": "กรุณาเลือก Plan No."})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_active_visibility_columns(cursor)
            plan = get_production_start_plan(cursor, plan_no)
            if not plan:
                return jsonify({"success": False, "message": "ไม่พบข้อมูล Plan No. นี้"})

            cursor.execute("""
                SELECT
                    COALESCE(s.is_finished, 0) AS setting_finished,
                    COALESCE(p.is_finished, 0) AS plan_finished
                FROM setting_dies s
                LEFT JOIN production_plans p ON p.id = s.plan_id
                WHERE s.plan_no = %s
                    AND s.deleted_at IS NULL
                    AND p.deleted_at IS NULL
                ORDER BY s.id DESC
                LIMIT 1
            """, (plan_no,))
            visibility = cursor.fetchone() or {}
            if visibility.get('setting_finished') or visibility.get('plan_finished'):
                return jsonify({"success": False, "message": "Plan No. นี้ถูก Finish แล้ว"})

            return jsonify({"success": True, "plan": plan})
    finally:
        conn.close()

@app.route('/api/qc/from_setting_die', methods=['POST'])
def create_qc_from_setting_die():
    plan_no = (request.form.get('plan_no') or '').strip()
    if not plan_no:
        return jsonify({"success": False, "message": "Plan No. is required"})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_active_visibility_columns(cursor)
            cursor.execute("""
                SELECT
                    p.id AS plan_id,
                    COALESCE(s.part_id, p.part_id) AS part_id,
                    s.plan_no,
                    s.lot_no,
                    COALESCE(NULLIF(s.part_no, ''), p.part_no) AS part_no,
                    COALESCE(NULLIF(s.die_no, ''), p.die_no) AS die_no,
                    p.qty
                FROM setting_dies s
                LEFT JOIN production_plans p ON p.id = s.plan_id
                WHERE s.plan_no = %s
                    AND COALESCE(s.is_finished, 0) = 0
                    AND COALESCE(p.is_finished, 0) = 0
                    AND s.deleted_at IS NULL
                    AND p.deleted_at IS NULL
                ORDER BY s.id DESC
                LIMIT 1
            """, (plan_no,))
            plan = cursor.fetchone()
            if not plan:
                return jsonify({"success": False, "message": "Active Setting Die plan not found"})

            ensure_workflow_created_by_columns(cursor)
            part, _plan = validate_plan_part_consistency(cursor, plan.get('plan_id'), plan.get('part_no'))

            cursor.execute("""
                SELECT id
                FROM qc_inspections
                WHERE plan_no = %s
                    AND COALESCE(is_finished, 0) = 0
                    AND deleted_at IS NULL
                ORDER BY id DESC
                LIMIT 1
            """, (plan_no,))
            existing = cursor.fetchone()
            if existing:
                return jsonify({
                    "success": True,
                    "created": False,
                    "qc_id": existing['id'],
                    "message": "This plan is already waiting in QC Line"
                })

            created_by_user_id, created_by_username = created_by_values()
            cursor.execute("""
                INSERT INTO qc_inspections
                (plan_id, part_id, lot_no, plan_no, part_no, time_start, time_end, percent_result, status, problem_area, problem_point, image_path, cause, solution, created_by_user_id, created_by_username)
                VALUES (%s, %s, %s, %s, %s, NULL, NULL, NULL, %s, %s, NULL, NULL, NULL, NULL, %s, %s)
            """, (
                plan.get('plan_id'),
                part['id'],
                plan.get('lot_no'),
                plan.get('plan_no'),
                part['part_no'],
                'Waiting',
                'none',
                created_by_user_id,
                created_by_username,
            ))
            qc_id = cursor.lastrowid
        conn.commit()
        return jsonify({
            "success": True,
            "created": True,
            "qc_id": qc_id,
            "message": "Sent to QC Line"
        })
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/production_starts', methods=['GET'])
def get_production_starts():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_parts_schema(cursor)
            cursor.execute("SELECT * FROM production_starts WHERE COALESCE(is_finished, 0) = 0 AND deleted_at IS NULL ORDER BY id DESC")
            return jsonify(cursor.fetchall())
    finally:
        conn.close()

@app.route('/api/production_start/<int:start_id>', methods=['GET'])
def get_production_start_detail(start_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_parts_schema(cursor)
            cursor.execute("SELECT * FROM production_starts WHERE id = %s AND deleted_at IS NULL", (start_id,))
            row = cursor.fetchone()
            if row:
                return jsonify({"success": True, "production_start": row})
            return jsonify({"success": False, "message": "ไม่พบข้อมูล Production Start"})
    finally:
        conn.close()

@app.route('/api/production_start/<int:start_id>/delete', methods=['POST'])
def delete_production_start(start_id):
    password = request.form.get('admin_password')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            if not verify_admin_password(cursor, password):
                return jsonify({"success": False, "message": "รหัสผ่าน admin ไม่ถูกต้อง"})

            ensure_parts_schema(cursor)
            cursor.execute("UPDATE production_starts SET deleted_at = NOW() WHERE id = %s", (start_id,))
        conn.commit()
        return jsonify({"success": True})
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/production_start/<int:start_id>/confirm', methods=['POST'])
def confirm_production_start(start_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_parts_schema(cursor)
            cursor.execute("UPDATE production_starts SET confirm_status = 'confirmed' WHERE id = %s AND deleted_at IS NULL", (start_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/production_start/bulk_delete', methods=['POST'])
def bulk_delete_production_start():
    password = request.form.get('admin_password')
    ids = request.form.getlist('ids[]') or request.form.getlist('ids')
    ids = [int(item_id) for item_id in ids if str(item_id).isdigit()]

    if not ids:
        return jsonify({"success": False, "message": "กรุณาเลือกรายการที่ต้องการลบ"})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            if not verify_admin_password(cursor, password):
                return jsonify({"success": False, "message": "รหัสผ่าน admin ไม่ถูกต้อง"})

            placeholders = ','.join(['%s'] * len(ids))
            ensure_parts_schema(cursor)
            cursor.execute(f"UPDATE production_starts SET deleted_at = NOW() WHERE id IN ({placeholders})", tuple(ids))
        conn.commit()
        return jsonify({"success": True, "deleted": len(ids)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/production_start', methods=['POST'])
def save_production_start():
    form = request.form
    start_id = form.get('start-id')
    plan_no = form.get('start-plan-no')
    if not plan_no:
        return jsonify({"success": False, "message": "กรุณาเลือก Plan No."})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_parts_schema(cursor)
            ensure_workflow_created_by_columns(cursor)
            plan = get_production_start_plan(cursor, plan_no) or {}
            lot_no = form.get('start-lot-no') or plan.get('lot_no')
            part_no = form.get('start-part-no') or plan.get('part_no')
            die_no = form.get('start-die-no') or plan.get('die_no')
            qty = form.get('start-qty') or plan.get('qty')
            time_start = format_datetime(form.get('start-time-start'))

            if not all([lot_no, part_no, die_no, qty, time_start]):
                return jsonify({"success": False, "message": "ข้อมูล Production Start ยังไม่ครบ ไม่สามารถบันทึกได้"})

            plan_id = plan.get('plan_id')
            part, _plan = validate_plan_part_consistency(cursor, plan_id, part_no)
            cursor.execute("""
                SELECT id
                FROM setting_dies
                WHERE plan_no = %s
                    AND deleted_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
            """, (plan_no,))
            duplicate_sql = """
                SELECT id
                FROM production_starts
                WHERE plan_no = %s
                    AND COALESCE(is_finished, 0) = 0
                    AND deleted_at IS NULL
            """
            duplicate_params = [plan_no]
            if start_id:
                duplicate_sql += " AND id <> %s"
                duplicate_params.append(start_id)
            duplicate_sql += " LIMIT 1"
            cursor.execute(duplicate_sql, tuple(duplicate_params))
            if cursor.fetchone():
                return jsonify({
                    "success": False,
                    "message": "Plan No. นี้มี Production Start อยู่แล้ว ไม่สามารถบันทึกซ้ำได้"
                })

            if start_id:
                cursor.execute("""
                    UPDATE production_starts SET
                        plan_id=%s, part_id=%s, plan_no=%s, lot_no=%s, part_no=%s, die_no=%s, qty=%s, time_start=%s
                    WHERE id=%s
                """, (plan_id, part['id'], plan_no, lot_no, part['part_no'], die_no, qty, time_start, start_id))
            else:
                created_by_user_id, created_by_username = created_by_values()
                cursor.execute("""
                    INSERT INTO production_starts
                    (plan_id, part_id, plan_no, lot_no, part_no, die_no, qty, time_start, created_by_user_id, created_by_username)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (plan_id, part['id'], plan_no, lot_no, part['part_no'], die_no, qty, time_start, created_by_user_id, created_by_username))
        conn.commit()
        return jsonify({"success": True})
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/production_finishes', methods=['GET'])
def get_production_finishes():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_finishes_table(cursor)
            ensure_parts_schema(cursor)
            cursor.execute("SELECT * FROM production_finishes WHERE deleted_at IS NULL ORDER BY id DESC")
            return jsonify(cursor.fetchall())
    finally:
        conn.close()

@app.route('/api/production_finish/plans', methods=['GET'])
def get_production_finish_plans():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_parts_schema(cursor)
            cursor.execute("""
                SELECT
                    ps.plan_id,
                    ps.part_id,
                    ps.plan_no,
                    ps.lot_no,
                    ps.part_no,
                    ps.die_no,
                    ps.qty
                FROM production_starts ps
                LEFT JOIN production_plans p ON p.id = ps.plan_id
                WHERE ps.plan_no IS NOT NULL AND ps.plan_no <> ''
                    AND COALESCE(ps.is_finished, 0) = 0
                    AND LOWER(COALESCE(ps.confirm_status, '')) = 'confirmed'
                    AND ps.deleted_at IS NULL
                    AND (p.id IS NULL OR (COALESCE(p.is_finished, 0) = 0 AND p.deleted_at IS NULL))
                ORDER BY ps.id DESC
            """)
            rows = cursor.fetchall()
            plans = []
            seen = set()
            for row in rows:
                if row['plan_no'] in seen:
                    continue
                seen.add(row['plan_no'])
                plans.append(row)
            return jsonify(plans)
    finally:
        conn.close()

@app.route('/api/production_finish/plan', methods=['GET'])
def get_production_finish_plan_detail():
    plan_no = request.args.get('plan_no', '')
    if not plan_no:
        return jsonify({"success": False, "message": "กรุณาเลือก Plan No."})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_parts_schema(cursor)
            cursor.execute("""
                SELECT
                    ps.plan_id,
                    ps.part_id,
                    ps.plan_no,
                    ps.lot_no,
                    ps.part_no,
                    ps.die_no,
                    ps.qty
                FROM production_starts ps
                LEFT JOIN production_plans p ON p.id = ps.plan_id
                WHERE ps.plan_no = %s
                    AND COALESCE(ps.is_finished, 0) = 0
                    AND LOWER(COALESCE(ps.confirm_status, '')) = 'confirmed'
                    AND ps.deleted_at IS NULL
                    AND (p.id IS NULL OR (COALESCE(p.is_finished, 0) = 0 AND p.deleted_at IS NULL))
                ORDER BY ps.id DESC
                LIMIT 1
            """, (plan_no,))
            plan = cursor.fetchone()
            if not plan:
                return jsonify({"success": False, "message": "ไม่พบข้อมูล Plan No. ที่พร้อม Finish"})
            return jsonify({"success": True, "plan": plan})
    finally:
        conn.close()

@app.route('/api/production_finish', methods=['POST'])
def save_production_finish():
    form = request.form
    plan_no = form.get('finish-plan-no')
    lot_no = form.get('finish-lot-no')
    actual_qty = form.get('finish-actual-qty')
    note = form.get('finish-note')
    time_finish = format_datetime(form.get('finish-time-finish'))
    hold_time = format_datetime(form.get('finish-hold-time'))

    if not all([plan_no, lot_no, actual_qty, time_finish]):
        return jsonify({"success": False, "message": "ข้อมูล Production Finish ยังไม่ครบ ไม่สามารถบันทึกได้"})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_production_finishes_table(cursor)
            ensure_parts_schema(cursor)
            ensure_workflow_created_by_columns(cursor)
            cursor.execute("""
                SELECT plan_id, part_id, plan_no, lot_no, part_no, die_no, qty, confirm_status
                FROM production_starts
                WHERE plan_no = %s
                    AND COALESCE(is_finished, 0) = 0
                    AND deleted_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
            """, (plan_no,))
            active_start = cursor.fetchone()
            if not active_start:
                return jsonify({"success": False, "message": "ไม่พบ Production Start ที่พร้อม Finish"})
            if (active_start.get('confirm_status') or '').lower() != 'confirmed':
                return jsonify({"success": False, "message": "กรุณา Confirm Production Start ก่อนบันทึก Finish"})

            plan = get_production_start_plan(cursor, plan_no) or {}

            if not plan:
                plan = active_start

            part_no = plan.get('part_no')
            die_no = plan.get('die_no')
            planned_qty = plan.get('qty')
            plan_id = plan.get('plan_id')
            part, _plan = validate_plan_part_consistency(cursor, plan_id, part_no)

            created_by_user_id, created_by_username = created_by_values()
            cursor.execute("""
                INSERT INTO production_finishes
                (plan_id, part_id, plan_no, lot_no, part_no, die_no, planned_qty, actual_qty, note, time_finish, hold_time, finish_status, created_by_user_id, created_by_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
            """, (plan_id, part['id'], plan_no, lot_no, part['part_no'], die_no, planned_qty, actual_qty, note, time_finish, hold_time, created_by_user_id, created_by_username))

        conn.commit()
        return jsonify({"success": True})
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/production_finish/<int:finish_id>/confirm', methods=['POST'])
def confirm_production_finish(finish_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_production_finishes_table(cursor)
            ensure_parts_schema(cursor)
            cursor.execute("SELECT * FROM production_finishes WHERE id = %s AND deleted_at IS NULL", (finish_id,))
            finish = cursor.fetchone()
            if not finish:
                return jsonify({"success": False, "message": "ไม่พบข้อมูล Production Finish"})

            update_production_finish_snapshot(cursor, finish_id, finish)
            clear_active_work_for_plan(cursor, finish['plan_no'])
            cursor.execute("UPDATE production_finishes SET finish_status = 'confirmed' WHERE id = %s", (finish_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/production_finish/bulk_delete', methods=['POST'])
def bulk_delete_production_finish():
    password = request.form.get('admin_password')
    ids = request.form.getlist('ids[]') or request.form.getlist('ids')
    ids = [int(item_id) for item_id in ids if str(item_id).isdigit()]

    if not ids:
        return jsonify({"success": False, "message": "กรุณาเลือกรายการที่ต้องการลบ"})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_finishes_table(cursor)
            if not verify_admin_password(cursor, password):
                return jsonify({"success": False, "message": "รหัสผ่าน admin ไม่ถูกต้อง"})

            placeholders = ','.join(['%s'] * len(ids))
            ensure_parts_schema(cursor)
            cursor.execute(f"UPDATE production_finishes SET deleted_at = NOW() WHERE id IN ({placeholders})", tuple(ids))
        conn.commit()
        return jsonify({"success": True, "deleted": len(ids)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/production_start/from_qc', methods=['POST'])
def create_production_start_from_qc():
    plan_no = request.form.get('plan_no')
    if not plan_no:
        return jsonify({"success": False, "message": "ไม่พบ Plan No. สำหรับเริ่มการผลิต"})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_parts_schema(cursor)
            ensure_workflow_created_by_columns(cursor)
            plan = get_production_start_plan(cursor, plan_no) or {}
            lot_no = plan.get('lot_no') or request.form.get('lot_no')
            part_no = plan.get('part_no') or request.form.get('part_no')
            die_no = plan.get('die_no')
            qty = plan.get('qty')
            plan_id = plan.get('plan_id')
            part, _plan = validate_plan_part_consistency(cursor, plan_id, part_no)

            cursor.execute("SELECT id FROM production_starts WHERE plan_no = %s AND COALESCE(is_finished, 0) = 0 AND deleted_at IS NULL ORDER BY id DESC LIMIT 1", (plan_no,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute("""
                    UPDATE production_starts SET
                        plan_id=%s, part_id=%s, lot_no=%s, part_no=%s, die_no=%s, qty=%s, time_start=NOW()
                    WHERE id=%s
                """, (plan_id, part['id'], lot_no, part['part_no'], die_no, qty, existing['id']))
            else:
                created_by_user_id, created_by_username = created_by_values()
                cursor.execute("""
                    INSERT INTO production_starts
                    (plan_id, part_id, plan_no, lot_no, part_no, die_no, qty, time_start, created_by_user_id, created_by_username)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s)
                """, (plan_id, part['id'], plan_no, lot_no, part['part_no'], die_no, qty, created_by_user_id, created_by_username))
        conn.commit()
        return jsonify({"success": True})
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/qc', methods=['POST'])
def add_qc():
    form = request.form
    image_path = None
    try:
        image_path = save_uploaded_file(request.files.get('qc-image'))
    except UploadValidationError as e:
        return error_response(str(e), 400)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_parts_schema(cursor)
            ensure_workflow_created_by_columns(cursor)
            plan = get_production_start_plan(cursor, form.get('qc-plan-no')) or {}
            plan_id = plan.get('plan_id')
            part_no = form.get('qc-part-no') or plan.get('part_no')
            part, _plan = validate_plan_part_consistency(cursor, plan_id, part_no)
            created_by_user_id, created_by_username = created_by_values()
            cursor.execute("""
                INSERT INTO qc_inspections 
                (plan_id, part_id, lot_no, plan_no, part_no, time_start, time_end, percent_result, status, problem_area, problem_point, image_path, cause, solution, created_by_user_id, created_by_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                plan_id, part['id'], form.get('qc-lot-no'), form.get('qc-plan-no'), part['part_no'],
                format_datetime(form.get('qc-time-start')), format_datetime(form.get('qc-time-end')),
                empty_to_none(form.get('qc-percent')), form.get('qc-status'), form.get('qc-problem-area'), form.get('qc-problem-point'),
                image_path, form.get('qc-cause'), form.get('qc-solution'),
                created_by_user_id, created_by_username
            ))
        conn.commit()
        return jsonify({"success": True})
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/qc/<int:qc_id>/update', methods=['POST'])
def update_qc(qc_id):
    form = request.form
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_parts_schema(cursor)
            cursor.execute("SELECT image_path FROM qc_inspections WHERE id = %s AND deleted_at IS NULL", (qc_id,))
            existing = cursor.fetchone()
            if not existing:
                return jsonify({"success": False, "message": "ไม่พบข้อมูล QC"})

            image_path = existing.get('image_path')
            try:
                uploaded_image_path = save_uploaded_file(request.files.get('qc-image'))
                if uploaded_image_path:
                    image_path = uploaded_image_path
            except UploadValidationError as e:
                return error_response(str(e), 400)

            plan = get_production_start_plan(cursor, form.get('qc-plan-no')) or {}
            plan_id = plan.get('plan_id')
            part_no = form.get('qc-part-no') or plan.get('part_no')
            part, _plan = validate_plan_part_consistency(cursor, plan_id, part_no)

            cursor.execute("""
                UPDATE qc_inspections SET
                    plan_id=%s, part_id=%s, lot_no=%s, plan_no=%s, part_no=%s, time_start=%s, time_end=%s,
                    percent_result=%s, status=%s, problem_area=%s, problem_point=%s,
                    image_path=%s, cause=%s, solution=%s
                WHERE id=%s
            """, (
                plan_id, part['id'], form.get('qc-lot-no'), form.get('qc-plan-no'), part['part_no'],
                format_datetime(form.get('qc-time-start')), format_datetime(form.get('qc-time-end')),
                empty_to_none(form.get('qc-percent')), form.get('qc-status'), form.get('qc-problem-area'),
                form.get('qc-problem-point'), image_path, form.get('qc-cause'),
                form.get('qc-solution'), qc_id
            ))
        conn.commit()
        return jsonify({"success": True})
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/qc/<int:qc_id>/delete', methods=['POST'])
def delete_qc(qc_id):
    password = request.form.get('admin_password')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if not verify_admin_password(cursor, password):
                return jsonify({"success": False, "message": "รหัสผ่าน admin ไม่ถูกต้อง"})

            ensure_parts_schema(cursor)
            cursor.execute("UPDATE qc_inspections SET deleted_at = NOW() WHERE id = %s", (qc_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/qc/bulk_delete', methods=['POST'])
def bulk_delete_qc():
    password = request.form.get('admin_password')
    ids = request.form.getlist('ids[]') or request.form.getlist('ids')
    ids = [int(item_id) for item_id in ids if str(item_id).isdigit()]

    if not ids:
        return jsonify({"success": False, "message": "กรุณาเลือกรายการที่ต้องการลบ"})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if not verify_admin_password(cursor, password):
                return jsonify({"success": False, "message": "รหัสผ่าน admin ไม่ถูกต้อง"})

            placeholders = ','.join(['%s'] * len(ids))
            ensure_parts_schema(cursor)
            cursor.execute(f"UPDATE qc_inspections SET deleted_at = NOW() WHERE id IN ({placeholders})", tuple(ids))
        conn.commit()
        return jsonify({"success": True, "deleted": len(ids)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

# --- ดึงตาราง QC (ทั้งหมด + ระบบค้นหา) ---
@app.route('/api/qc_list', methods=['GET'])
def get_qc_list():
    part_no = normalize_part_no(request.args.get('part_no', ''))
    lot_no = request.args.get('lot_no', '')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_active_visibility_columns(cursor)
            sql = "SELECT * FROM qc_inspections WHERE COALESCE(is_finished, 0) = 0 AND deleted_at IS NULL"
            params = []
            
            if part_no:
                sql += " AND UPPER(TRIM(part_no)) LIKE %s"
                params.append(f"%{part_no}%")
            if lot_no:
                sql += " AND lot_no LIKE %s"
                params.append(f"%{lot_no}%")
                
            sql += " ORDER BY id DESC"
            cursor.execute(sql, tuple(params))
            return jsonify(cursor.fetchall())
    finally:
        conn.close()

# --- [ใหม่] ดึงข้อมูล QC เชิงลึกตาม ID ---
@app.route('/api/qc/<int:qc_id>', methods=['GET'])
def get_qc_detail(qc_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_parts_schema(cursor)
            cursor.execute("SELECT * FROM qc_inspections WHERE id = %s AND deleted_at IS NULL", (qc_id,))
            qc = cursor.fetchone()
            if qc:
                return jsonify({"success": True, "qc": qc})
            return jsonify({"success": False, "message": "ไม่พบข้อมูล QC"})
    finally:
        conn.close()

@app.route('/api/parts/relations', methods=['GET'])
def get_part_relations_api():
    part_no = request.args.get('part_no', '')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_parts_schema(cursor)
            relations = get_part_with_relations(cursor, part_no)
            return jsonify({"success": True, "data": relations})
    except PartValidationError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except PartNotFoundError as e:
        return jsonify({"success": False, "message": str(e)}), 404
    finally:
        conn.close()

@app.route('/api/parts/update', methods=['POST'])
def update_part_by_part_no_api():
    part_no = request.form.get('part_no')
    payload = {}
    if 'new_part_no' in request.form:
        payload['part_no'] = request.form.get('new_part_no')
    if 'description' in request.form:
        payload['description'] = request.form.get('description')

    conn = get_db_connection()
    try:
        def operation(cursor):
            ensure_parts_schema(cursor)
            return update_part_by_part_no(cursor, part_no, payload)

        part = run_part_transaction(conn, operation)
        return jsonify({"success": True, "part": part})
    except (PartValidationError, PartNotFoundError) as e:
        conn.rollback()
        status_code = 404 if isinstance(e, PartNotFoundError) else 400
        return jsonify({"success": False, "message": str(e)}), status_code
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/parts/delete', methods=['POST'])
def soft_delete_part_by_part_no_api():
    part_no = request.form.get('part_no')
    conn = get_db_connection()
    try:
        def operation(cursor):
            ensure_parts_schema(cursor)
            return soft_delete_part_by_part_no(cursor, part_no)

        part = run_part_transaction(conn, operation)
        return jsonify({"success": True, "part": part})
    except (PartValidationError, PartNotFoundError) as e:
        conn.rollback()
        status_code = 404 if isinstance(e, PartNotFoundError) else 400
        return jsonify({"success": False, "message": str(e)}), status_code
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/users', methods=['GET'])
def get_users():
    admin_password = request.args.get('admin_password', '')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            # Listing is used by the admin-only screen. Mutations below still require
            # the admin password because this app does not have server-side sessions yet.
            if admin_password and not verify_admin_password(cursor, admin_password):
                return jsonify({"success": False, "message": "Invalid admin password"}), 403

            cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY id DESC")
            users = cursor.fetchall()
            for user in users:
                user['role'] = normalize_user_role(user.get('role'))
            return jsonify({"success": True, "users": users})
    finally:
        conn.close()

@app.route('/api/users/<int:user_id>/role', methods=['POST'])
def update_user_role(user_id):
    admin_password = request.form.get('admin_password')
    role = normalize_user_role(request.form.get('role'))

    if role not in ALLOWED_USER_ROLES:
        return jsonify({"success": False, "message": f"Role must be one of: {', '.join(ALLOWED_USER_ROLES)}"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            if not verify_admin_password(cursor, admin_password):
                return jsonify({"success": False, "message": "Invalid admin password"})

            cursor.execute("SELECT id, username, role FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({"success": False, "message": "User not found"}), 404
            current_role = normalize_user_role(user.get('role'))
            if current_role == 'Admin' and role != 'Admin':
                last_admin_error = require_not_last_admin_before_delete_or_demote(cursor, user, 'demote')
                if last_admin_error:
                    return last_admin_error

            cursor.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
        conn.commit()
        if session.get('user_id') == user_id:
            session['role'] = role
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    admin_password = request.form.get('admin_password')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            if not verify_admin_password(cursor, admin_password):
                return jsonify({"success": False, "message": "Invalid admin password"})

            cursor.execute("SELECT id, username, role FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({"success": False, "message": "User not found"}), 404
            if user.get('username') == 'admin':
                return jsonify({"success": False, "message": "Cannot delete the main admin user"})
            last_admin_error = require_not_last_admin_before_delete_or_demote(cursor, user, 'delete')
            if last_admin_error:
                return last_admin_error

            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        deleted_current_user = session.get('user_id') == user_id or session.get('username') == user.get('username')
        if deleted_current_user:
            session.clear()
        return jsonify({
            "success": True,
            "logged_out": deleted_current_user,
            "message": "Session expired or account was removed. Please login again." if deleted_current_user else "User deleted"
        })
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
def reset_user_password(user_id):
    payload = request.get_json(silent=True) or request.form
    new_password = payload.get('new_password') or ''
    confirm_password = payload.get('confirm_password') or ''

    if not new_password:
        return jsonify({"success": False, "message": "New password is required"}), 400
    if len(new_password) < 8:
        return jsonify({"success": False, "message": "New password must be at least 8 characters"}), 400
    if new_password != confirm_password:
        return jsonify({"success": False, "message": "Password confirmation does not match"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            cursor.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({"success": False, "message": "User not found"}), 404

            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hash_password(new_password), user_id))
        conn.commit()

        reset_current_user = session.get('user_id') == user_id
        if reset_current_user:
            session.clear()

        return jsonify({
            "success": True,
            "message": "Password reset successfully.",
            "logged_out": reset_current_user,
        })
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/users', methods=['POST'])
def create_user():
    admin_password = request.form.get('admin_password')
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    role = normalize_user_role(request.form.get('role'))

    if not username or not password or role not in ALLOWED_USER_ROLES:
        return jsonify({"success": False, "message": f"Username, password, and a valid role are required. Roles: {', '.join(ALLOWED_USER_ROLES)}"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_users_table(cursor)
            if not verify_admin_password(cursor, admin_password):
                return jsonify({"success": False, "message": "Invalid admin password"})

            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                return jsonify({"success": False, "message": "Username already exists"})

            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (username, hash_password(password), role)
            )
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(
        host=os.environ.get('FLASK_RUN_HOST', '127.0.0.1'),
        port=int(os.environ.get('FLASK_RUN_PORT', '5000')),
        debug=os.environ.get('FLASK_DEBUG') == '1',
    )
