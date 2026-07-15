import os
import sys
import uuid
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, session, g, has_request_context
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import pymysql
from dashboard_services import dashboard_bucket_for_item, dashboard_setting_die_progress, dashboard_summary
from setting_die_services import setting_die_process_eligible, setting_die_record_complete
from qc_services import (
    QC_TIMESTAMP_FIELDS,
    QCTimestampValidationError,
    stamp_locked_qc_timestamp,
    validate_qc_identity_request,
    validate_qc_timestamp_field,
)
from production_start_services import (
    ProductionStartValidationError,
    production_start_confirmed,
    stamp_locked_production_start_time,
    validate_production_start_identity,
)
from production_finish_services import (
    PRODUCTION_FINISH_TIMESTAMP_FIELDS,
    ProductionFinishValidationError,
    stamp_locked_production_finish_timestamp,
    validate_production_finish_identity,
    validate_production_finish_timestamp_field,
)
from workflow_services import (
    can_approve_correction,
    correction_requires_approval,
    downstream_stage,
    qc_passed,
    qc_revision_current,
)
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
from forecast_services import (
    ForecastValidationError,
    choose_default_month,
    month_key,
    serialize_forecast_entry,
    validate_month_key,
    validate_lot_batch,
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

PROCESS_DIE_COUNT_ERROR = "Process Die ต้องเป็นตัวเลขจำนวนเต็มมากกว่า 0"
SETTING_DIE_TIME_START_REQUIRED = "กรุณา Stamp เวลา Time Start Setting Die ก่อนบันทึก"

def parse_positive_int(value, default=None, message=PROCESS_DIE_COUNT_ERROR):
    if value in (None, ''):
        if default is not None:
            return default
        raise ValueError(message)
    text = str(value).strip()
    if not text.isdigit():
        raise ValueError(message)
    parsed = int(text)
    if parsed <= 0:
        raise ValueError(message)
    return parsed

def normalize_timestamp_value(value):
    if value in (None, ''):
        return None
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    text = str(value).replace('T', ' ').replace(' GMT', '').strip()
    if not text:
        return None
    if len(text) == 16:
        return f"{text}:00"
    return text

def protect_locked_timestamp(existing_value, incoming_value, label):
    existing_timestamp = normalize_timestamp_value(existing_value)
    incoming_timestamp = normalize_timestamp_value(incoming_value)
    if existing_timestamp:
        if not incoming_timestamp:
            return existing_timestamp
        if incoming_timestamp != existing_timestamp:
            raise ValueError(f"{label} ถูก Stamp แล้ว แก้ไขไม่ได้")
        return existing_timestamp
    return incoming_timestamp

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
            lot_no VARCHAR(100) NOT NULL,
            part_no VARCHAR(100),
            die_no VARCHAR(100),
            qty VARCHAR(50),
            time_start DATETIME,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_production_starts_lot_no (lot_no)
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
            lot_no VARCHAR(100) NOT NULL,
            part_no VARCHAR(100),
            die_no VARCHAR(100),
            planned_qty VARCHAR(50),
            actual_qty VARCHAR(50),
            note TEXT,
            time_finish DATETIME,
            hold_time DATETIME,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_production_finishes_lot_no (lot_no)
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

def ensure_index(cursor, table_name, index_name, columns_sql):
    cursor.execute(f"SHOW INDEX FROM {table_name} WHERE Key_name = %s", (index_name,))
    if not cursor.fetchone():
        cursor.execute(f"CREATE INDEX {index_name} ON {table_name} ({columns_sql})")

def ensure_notifications_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            target_role VARCHAR(30) NOT NULL,
            type VARCHAR(80) NOT NULL,
            title VARCHAR(255) NOT NULL,
            message TEXT,
            plan_id INT NULL,
            lot_no VARCHAR(100) NULL,
            part_no VARCHAR(100) NULL,
            source_table VARCHAR(80) NULL,
            source_id INT NULL,
            action_menu VARCHAR(80) NULL,
            is_read TINYINT NOT NULL DEFAULT 0,
            read_at DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    ensure_index(cursor, 'notifications', 'idx_notifications_role_read_created', 'target_role, is_read, created_at')
    ensure_index(cursor, 'notifications', 'idx_notifications_action_menu', 'action_menu')
    ensure_index(cursor, 'notifications', 'idx_notifications_dedupe', 'target_role, type, lot_no, is_read')

def create_notification(cursor, target_role, type, title, message, plan_id=None, lot_no=None, part_no=None, source_table=None, source_id=None, action_menu=None, event_key=None, ensure_schema=True):
    target_role = normalize_user_role(target_role)
    if not target_role:
        return None

    if ensure_schema:
        ensure_notifications_table(cursor)
    if event_key:
        cursor.execute("SELECT id FROM notifications WHERE event_key = %s LIMIT 1", (event_key,))
        existing = cursor.fetchone()
        if existing:
            return {"id": existing.get('id'), "created": False}
    elif lot_no:
        cursor.execute("""
            SELECT id
            FROM notifications
            WHERE target_role = %s
                AND type = %s
                AND lot_no = %s
                AND is_read = 0
            ORDER BY id DESC
            LIMIT 1
        """, (target_role, type, lot_no))
        existing = cursor.fetchone()
        if existing:
            return {"id": existing.get('id'), "created": False}

    cursor.execute("""
        INSERT INTO notifications
        (target_role, type, title, message, plan_id, lot_no, part_no, source_table, source_id, action_menu, event_key)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (target_role, type, title, message, plan_id, lot_no, part_no, source_table, source_id, action_menu, event_key))
    return {"id": cursor.lastrowid, "created": True}


def workflow_actor():
    user = getattr(g, 'current_user', {}) or {}
    return user.get('id'), user.get('username'), normalize_user_role(user.get('role'))


def record_workflow_event(cursor, plan_id, event_key, event_type, revision=None, reason=None, metadata_text=None):
    user_id, username, _role = workflow_actor()
    cursor.execute("""
        INSERT IGNORE INTO workflow_events
        (plan_id, event_key, event_type, setting_die_revision, actor_user_id, actor_username, reason, metadata_text)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (plan_id, event_key, event_type, revision, user_id, username, reason, metadata_text))
    return cursor.rowcount == 1


def fetch_workflow_plan(cursor, plan_id=None, lot_no=None, for_update=False):
    suffix = " FOR UPDATE" if for_update else ""
    if plan_id:
        cursor.execute(f"SELECT * FROM production_plans WHERE id = %s AND deleted_at IS NULL{suffix}", (plan_id,))
    else:
        cursor.execute(f"SELECT * FROM production_plans WHERE lot_no = %s AND deleted_at IS NULL ORDER BY id DESC LIMIT 1{suffix}", (lot_no,))
    return cursor.fetchone()


def fetch_latest_workflow_row(cursor, table_name, plan_id):
    cursor.execute(f"""
        SELECT * FROM {table_name}
        WHERE plan_id = %s AND deleted_at IS NULL
        ORDER BY id DESC LIMIT 1
    """, (plan_id,))
    return cursor.fetchone()


def fetch_active_correction(cursor, plan_id, for_update=False):
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(f"""
        SELECT * FROM setting_die_corrections
        WHERE plan_id = %s AND status IN ('pending_approval', 'open')
        ORDER BY id DESC LIMIT 1{suffix}
    """, (plan_id,))
    return cursor.fetchone()


def build_setting_die_workflow_state(cursor, plan):
    plan_id = plan.get('id')
    revision = int(plan.get('setting_die_revision') or 1)
    correction = fetch_active_correction(cursor, plan_id)
    qc = fetch_latest_workflow_row(cursor, 'qc_inspections', plan_id)
    production_start = fetch_latest_workflow_row(cursor, 'production_starts', plan_id)
    production_finish = fetch_latest_workflow_row(cursor, 'production_finishes', plan_id)
    stage = downstream_stage(qc, production_start, production_finish)
    qc_is_current = qc_revision_current(qc, revision)
    current_qc_pass = qc_is_current and qc_passed(qc)
    start_revision_current = not production_start or int(production_start.get('setting_die_revision') or 1) == revision
    finish_revision_current = not production_finish or int(production_finish.get('setting_die_revision') or 1) == revision
    historical_downstream_requires_review = bool(
        (production_start or production_finish) and (not start_revision_current or not finish_revision_current)
    )
    sent = bool(plan.get('setting_die_sent_at'))
    correction_status = (correction or {}).get('status')
    return {
        'plan_id': plan_id,
        'setting_die_revision': revision,
        'setting_die_sent': sent,
        'setting_die_sent_at': plan.get('setting_die_sent_at'),
        'setting_die_locked': sent and correction_status != 'open',
        'correction': correction,
        'correction_status': correction_status,
        'downstream_stage': stage,
        'approval_required': correction_requires_approval(stage),
        'qc_reviewed_revision': (qc or {}).get('setting_die_revision'),
        'qc_revision_current': qc_is_current,
        'qc_current_pass': current_qc_pass,
        'qc_recheck_required': sent and not current_qc_pass,
        'historical_downstream_requires_review': historical_downstream_requires_review,
        'operator_notified': bool(plan.get('operator_notified_at')),
        'operator_notified_at': plan.get('operator_notified_at'),
        'next_action': (
            'Await correction approval' if correction_status == 'pending_approval'
            else 'Finish correction' if correction_status == 'open'
            else 'Downstream review required' if historical_downstream_requires_review
            else 'QC must recheck revision' if sent and not current_qc_pass
            else 'Notify Operator' if current_qc_pass and not plan.get('operator_notified_at')
            else 'Production Start' if plan.get('operator_notified_at')
            else 'Send to QC Line'
        ),
    }


def attach_setting_die_workflow_states(cursor, plans):
    for plan in plans:
        plan['workflow'] = build_setting_die_workflow_state(cursor, plan)
    return plans


def current_revision_qc_pass(cursor, plan_id, for_update=False):
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(f"""
        SELECT q.*
        FROM production_plans p
        JOIN qc_inspections q
          ON q.plan_id = p.id AND q.setting_die_revision = p.setting_die_revision
        WHERE p.id = %s
          AND p.deleted_at IS NULL
          AND q.deleted_at IS NULL
          AND LOWER(TRIM(COALESCE(q.status, ''))) IN ('pass', 'passed')
        ORDER BY q.id DESC LIMIT 1{suffix}
    """, (plan_id,))
    return cursor.fetchone()

def ensure_production_process_schema(cursor):
    ensure_column(cursor, 'production_plans', 'lot_no', 'lot_no VARCHAR(100) NULL')
    ensure_column(cursor, 'production_plans', 'process_die_count', 'process_die_count INT NOT NULL DEFAULT 1')
    ensure_column(cursor, 'setting_dies', 'process_die_no', 'process_die_no INT NULL')
    ensure_index(cursor, 'production_plans', 'idx_production_plans_lot_no', 'lot_no')
    ensure_index(cursor, 'setting_dies', 'idx_setting_dies_plan_process', 'plan_id, process_die_no')
    cursor.execute("""
        UPDATE production_plans
        SET process_die_count = 1
        WHERE process_die_count IS NULL OR process_die_count < 1
    """)
    cursor.execute("""
        UPDATE setting_dies
        SET process_die_no = 1
        WHERE process_die_no IS NULL
    """)
    cursor.execute("""
        UPDATE production_plans p
        JOIN (
            SELECT plan_id, MAX(lot_no) AS lot_no
            FROM setting_dies
            WHERE plan_id IS NOT NULL
                AND lot_no IS NOT NULL
                AND TRIM(lot_no) <> ''
                AND deleted_at IS NULL
            GROUP BY plan_id
        ) s ON s.plan_id = p.id
        SET p.lot_no = s.lot_no
        WHERE (p.lot_no IS NULL OR TRIM(p.lot_no) = '')
            AND s.lot_no IS NOT NULL
            AND TRIM(s.lot_no) <> ''
    """)

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
    ensure_parts_schema(cursor)
    ensure_production_process_schema(cursor)
    ensure_column(cursor, 'production_plans', 'is_finished', 'is_finished TINYINT DEFAULT 0')
    ensure_column(cursor, 'setting_dies', 'is_finished', 'is_finished TINYINT DEFAULT 0')
    ensure_column(cursor, 'qc_inspections', 'is_finished', 'is_finished TINYINT DEFAULT 0')
    ensure_production_starts_table(cursor)
    ensure_production_finishes_table(cursor)
    ensure_workflow_created_by_columns(cursor)

def clear_active_work_for_plan(cursor, lot_no):
    ensure_active_visibility_columns(cursor)
    cursor.execute("SELECT plan_id FROM setting_dies WHERE lot_no = %s", (lot_no,))
    plan_ids = [row['plan_id'] for row in cursor.fetchall() if row.get('plan_id')]

    cursor.execute("UPDATE qc_inspections SET is_finished = 1 WHERE lot_no = %s", (lot_no,))
    cursor.execute("UPDATE production_starts SET is_finished = 1 WHERE lot_no = %s", (lot_no,))
    cursor.execute("UPDATE setting_dies SET is_finished = 1 WHERE lot_no = %s", (lot_no,))

    if plan_ids:
        placeholders = ','.join(['%s'] * len(plan_ids))
        cursor.execute(f"UPDATE production_plans SET is_finished = 1 WHERE id IN ({placeholders})", tuple(plan_ids))

def plan_process_count(plan):
    try:
        return max(int(plan.get('process_die_count') or 1), 1)
    except (TypeError, ValueError):
        return 1

def normalized_process_die_no(row):
    try:
        return max(int(row.get('process_die_no') or row.get('process_die_no_normalized') or 1), 1)
    except (TypeError, ValueError):
        return 1

def fetch_active_settings_by_plan_ids(cursor, plan_ids):
    settings_by_plan = {}
    if not plan_ids:
        return settings_by_plan
    placeholders = ','.join(['%s'] * len(plan_ids))
    cursor.execute(f"""
        SELECT *, COALESCE(process_die_no, 1) AS process_die_no_normalized
        FROM setting_dies
        WHERE plan_id IN ({placeholders})
            AND deleted_at IS NULL
        ORDER BY plan_id ASC, process_die_no_normalized ASC, id ASC
    """, tuple(plan_ids))
    for row in cursor.fetchall():
        settings_by_plan.setdefault(row.get('plan_id'), []).append(row)
    return settings_by_plan

def build_process_dies_for_plan(plan, settings):
    latest_by_process = {}
    for row in settings or []:
        latest_by_process[normalized_process_die_no(row)] = row

    process_dies = []
    for process_no in range(1, plan_process_count(plan) + 1):
        setting = latest_by_process.get(process_no)
        if not setting:
            process_dies.append({
                'process_die_no': process_no,
                'status': 'not_started',
                'setting_die_id': None,
                'is_saved': False,
                'is_finished': False,
            })
            continue
        is_saved = setting_die_record_complete(setting)
        is_finished = bool(setting.get('is_finished')) and is_saved
        process_dies.append({
            'process_die_no': process_no,
            'status': 'incomplete' if not is_saved else ('finished' if is_finished else 'done'),
            'setting_die_id': setting.get('id'),
            'is_saved': is_saved,
            'is_finished': is_finished,
        })
    return process_dies

def attach_process_dies_to_plans(cursor, plans):
    settings_by_plan = fetch_active_settings_by_plan_ids(cursor, [plan['id'] for plan in plans])
    for plan in plans:
        settings = settings_by_plan.get(plan.get('id'), [])
        if not plan.get('lot_no'):
            fallback = next((row.get('lot_no') for row in reversed(settings) if row.get('lot_no')), None)
            if fallback:
                plan['lot_no'] = fallback
        plan['process_die_count'] = plan_process_count(plan)
        plan['process_dies'] = build_process_dies_for_plan(plan, settings)
    return plans

def setting_die_processes_complete(plan):
    return all(process.get('status') in ('done', 'finished') for process in plan.get('process_dies') or [])

def setting_plan_payload(plan):
    process_one = next((row for row in (plan.get('_settings') or []) if normalized_process_die_no(row) == 1), None)
    latest = (plan.get('_settings') or [])[-1] if plan.get('_settings') else None
    setting = process_one or latest or {}
    return {
        'plan_id': plan.get('id'),
        'part_id': plan.get('part_id') or setting.get('part_id'),
        'lot_no': plan.get('lot_no') or setting.get('lot_no'),
        'part_no': plan.get('part_no') or setting.get('part_no'),
        'die_no': plan.get('die_no') or setting.get('die_no'),
        'qty': plan.get('qty'),
        'process_die_count': plan_process_count(plan),
        'setting_die_revision': int(plan.get('setting_die_revision') or 1),
    }


def attach_current_qc_state(cursor, plans):
    plan_ids = [plan.get('plan_id') for plan in plans if plan.get('plan_id')]
    if not plan_ids:
        return plans
    placeholders = ','.join(['%s'] * len(plan_ids))
    cursor.execute(f"""
        SELECT id, plan_id, setting_die_revision, time_start, time_end, status
        FROM qc_inspections
        WHERE plan_id IN ({placeholders})
          AND deleted_at IS NULL
          AND COALESCE(is_finished, 0) = 0
        ORDER BY plan_id ASC, id DESC
    """, tuple(plan_ids))
    current_by_plan = {}
    revisions = {plan.get('plan_id'): int(plan.get('setting_die_revision') or 1) for plan in plans}
    for row in cursor.fetchall():
        plan_id = row.get('plan_id')
        if plan_id in current_by_plan:
            continue
        if int(row.get('setting_die_revision') or 1) != revisions.get(plan_id, 1):
            continue
        current_by_plan[plan_id] = row
    for plan in plans:
        qc = current_by_plan.get(plan.get('plan_id')) or {}
        plan.update({
            'qc_id': qc.get('id'),
            'qc_time_start': qc.get('time_start'),
            'qc_time_end': qc.get('time_end'),
            'qc_status': qc.get('status'),
        })
    return plans

def get_ready_setting_plans(cursor, exclude_active_start=False):
    ensure_active_visibility_columns(cursor)
    cursor.execute("""
        SELECT *
        FROM production_plans
        WHERE COALESCE(is_finished, 0) = 0
            AND deleted_at IS NULL
        ORDER BY id DESC
    """)
    plans = cursor.fetchall()
    settings_by_plan = fetch_active_settings_by_plan_ids(cursor, [plan['id'] for plan in plans])
    ready_plans = []
    seen = set()
    for plan in plans:
        settings = settings_by_plan.get(plan.get('id'), [])
        plan['_settings'] = settings
        if not plan.get('lot_no'):
            fallback = next((row.get('lot_no') for row in reversed(settings) if row.get('lot_no')), None)
            if fallback:
                plan['lot_no'] = fallback
        plan['process_dies'] = build_process_dies_for_plan(plan, settings)
        if not plan.get('lot_no') or not setting_die_processes_complete(plan):
            continue
        if plan['lot_no'] in seen:
            continue
        if exclude_active_start:
            cursor.execute("""
                SELECT id
                FROM production_starts
                WHERE lot_no = %s
                    AND COALESCE(is_finished, 0) = 0
                    AND deleted_at IS NULL
                LIMIT 1
            """, (plan['lot_no'],))
            if cursor.fetchone():
                continue
        seen.add(plan['lot_no'])
        ready_plans.append(setting_plan_payload(plan))
    return ready_plans

def get_production_start_plan(cursor, lot_no):
    ready_plans = get_ready_setting_plans(cursor)
    return next((plan for plan in ready_plans if plan.get('lot_no') == lot_no), None)

def first_value(*values):
    for value in values:
        if value not in (None, ''):
            return value
    return None

def collect_finish_snapshot(cursor, finish):
    lot_no = finish.get('lot_no')
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
        WHERE s.lot_no = %s
        ORDER BY s.id DESC
        LIMIT 1
    """, (lot_no,))
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
        WHERE lot_no = %s
        ORDER BY id DESC
        LIMIT 1
    """, (lot_no,))
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
        WHERE lot_no = %s
        ORDER BY id DESC
        LIMIT 1
    """, (lot_no,))
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

def require_exact_role(required_role):
    current_user = getattr(g, 'current_user', {}) or {}
    if normalize_user_role(current_user.get('role')) == required_role:
        return None
    return jsonify({
        "success": False,
        "message": "You do not have permission to access FORECAST.",
        "permission_denied": True,
        "required_role": required_role,
    }), 403

ENDPOINT_REQUIRED_PERMISSION = {
    'verify_admin_password_api': 'users.manage',
    'add_production': 'production.create',
    'accept_job': 'production.accept',
    'delete_job': 'production.delete',
    'bulk_delete_jobs': 'production.delete',
    'add_setting_die': 'setting_die.manage',
    'create_qc_from_setting_die': 'setting_die.send_to_qc',
    'reopen_setting_die_correction': 'setting_die.manage',
    'request_setting_die_correction': 'setting_die.manage',
    'finish_setting_die_correction': 'setting_die.manage',
    'approve_setting_die_correction': 'setting_die.manage',
    'reject_setting_die_correction': 'setting_die.manage',
    'delete_production_start': 'production_start.manage',
    'confirm_production_start': 'production_start.manage',
    'stamp_production_start_timestamp': 'production_start.manage',
    'bulk_delete_production_start': 'production_start.manage',
    'save_production_start': 'production_start.manage',
    'save_production_finish': 'production_finish.manage',
    'stamp_production_finish_timestamp': 'production_finish.manage',
    'confirm_production_finish': 'production_finish.manage',
    'bulk_delete_production_finish': 'production_finish.manage',
    'create_production_start_from_qc': 'qc.manage',
    'add_qc': 'qc.manage',
    'update_qc': 'qc.manage',
    'stamp_qc_timestamp': 'qc.manage',
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
    'get_setting_die_corrections': ('setting_die.view', 'setting_die.manage'),
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
        'workflow_events': {},
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
    lot_no_to_id = {}
    for row in settings:
        related['setting_dies'].setdefault(row.get('plan_id'), []).append(row)
        if row.get('lot_no') and row.get('plan_id'):
            lot_no_to_id[row['lot_no']] = row['plan_id']

    lot_no_placeholders = ','.join(['%s'] * len(lot_no_to_id))
    lot_no_values = tuple(lot_no_to_id.keys())
    for table_name in ['qc_inspections', 'production_starts', 'production_finishes']:
        sql = f"""
            SELECT *
            FROM {table_name}
            WHERE deleted_at IS NULL
                AND (plan_id IN ({placeholders})
        """
        params = list(plan_ids)
        if lot_no_values:
            sql += f" OR lot_no IN ({lot_no_placeholders})"
            params.extend(lot_no_values)
        sql += ") ORDER BY id ASC"
        cursor.execute(sql, tuple(params))
        for row in cursor.fetchall():
            plan_id = row.get('plan_id') or lot_no_to_id.get(row.get('lot_no'))
            if plan_id:
                related[table_name].setdefault(plan_id, []).append(row)
    cursor.execute(f"""
        SELECT * FROM workflow_events
        WHERE plan_id IN ({placeholders})
        ORDER BY id ASC
    """, tuple(plan_ids))
    for row in cursor.fetchall():
        related['workflow_events'].setdefault(row.get('plan_id'), []).append(row)
    return related

def dashboard_derive_item(plan, related):
    plan_id = plan.get('id')
    settings = related['setting_dies'].get(plan_id, [])
    setting = dashboard_latest(settings)
    qc = dashboard_latest(related['qc_inspections'].get(plan_id, []))
    start = dashboard_latest(related['production_starts'].get(plan_id, []))
    finish = dashboard_latest(related['production_finishes'].get(plan_id, []))

    completed_setting_processes = {
        normalized_process_die_no(row)
        for row in settings
        if setting_die_record_complete(row)
    }
    has_partial_setting = bool(settings)
    has_setting = len(completed_setting_processes) >= plan_process_count(plan)
    has_qc = qc is not None
    has_start = start is not None
    has_finish = finish is not None
    finish_status = (finish.get('finish_status') if finish else '') or ''
    start_status = (start.get('confirm_status') if start else '') or ''
    is_completed = bool(plan.get('is_finished')) or finish_status.lower() == 'confirmed'
    current_revision = int(plan.get('setting_die_revision') or 1)
    qc_is_current = qc_revision_current(qc, current_revision)
    start_revision_current = not start or int(start.get('setting_die_revision') or 1) == current_revision
    finish_revision_current = not finish or int(finish.get('setting_die_revision') or 1) == current_revision
    stale_downstream = bool(
        (start or finish)
        and (not qc_is_current or not qc_passed(qc) or not start_revision_current or not finish_revision_current)
    )

    if stale_downstream:
        current_step = 'QC'
        status = 'downstream_review_required' if qc_is_current and qc_passed(qc) else 'recheck_required'
    elif is_completed:
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
    elif has_partial_setting:
        current_step = 'Setting Die'
        status = 'in_progress'
    else:
        current_step = 'Not Started'
        status = plan.get('status') or 'pending'

    setting_die_progress = dashboard_setting_die_progress(plan_process_count(plan), completed_setting_processes)
    item = {
        'plan_id': plan_id,
        'lot_no': dashboard_value(
            (finish or {}).get('lot_no') or (start or {}).get('lot_no') or (qc or {}).get('lot_no') or plan.get('lot_no') or (setting or {}).get('lot_no')
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
        'setting_die_progress': setting_die_progress,
        'flags': {
            'has_setting_die': has_setting,
            'has_partial_setting_die': has_partial_setting,
            'setting_die_complete': has_setting,
            'has_qc': has_qc,
            'has_production_start': has_start,
            'has_production_finish': has_finish,
            'qc_revision_current': qc_is_current,
            'qc_recheck_required': bool(plan.get('setting_die_sent_at')) and not (qc_is_current and qc_passed(qc)),
            'historical_downstream_requires_review': stale_downstream,
        }
    }
    item['dashboard_bucket'] = dashboard_bucket_for_item(item)
    return item

def dashboard_plan_detail(plan):
    return [
        dashboard_detail_entry('Lot No.', plan.get('lot_no')),
        dashboard_detail_entry('Process Die Count', plan_process_count(plan)),
        dashboard_detail_entry('Part No.', plan.get('part_no')),
        dashboard_detail_entry('Die No.', plan.get('die_no')),
        dashboard_detail_entry('Zone', plan.get('zone')),
        dashboard_detail_entry('Status', plan.get('status') or 'pending'),
        dashboard_detail_entry('Setting Die Revision', plan.get('setting_die_revision') or 1),
        dashboard_detail_entry('Sent to QC Line At', plan.get('setting_die_sent_at')),
        dashboard_detail_entry('Operator Notified At', plan.get('operator_notified_at')),
        dashboard_detail_entry('Is Finished', 'Yes' if plan.get('is_finished') else 'No'),
        dashboard_detail_entry('Created At', plan.get('created_at')),
        dashboard_detail_entry('Updated At', plan.get('updated_at')),
        dashboard_detail_entry('Recorded by', dashboard_recorded_by(plan)),
        dashboard_detail_entry('Source', f"production_plans #{dashboard_value(plan.get('id'))}"),
    ]

def dashboard_setting_detail(row):
    return [
        dashboard_detail_entry('Lot No.', row.get('lot_no')),
        dashboard_detail_entry('Process Die No.', normalized_process_die_no(row)),
        dashboard_detail_entry('Part No.', row.get('part_no')),
        dashboard_detail_entry('Die No.', row.get('die_no')),
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
        dashboard_detail_entry('Lot No.', row.get('lot_no')),
        dashboard_detail_entry('Part No.', row.get('part_no')),
        dashboard_detail_entry('Result / Status', row.get('status') or 'pending'),
        dashboard_detail_entry('Setting Die Revision Reviewed', row.get('setting_die_revision') or 1),
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
        dashboard_detail_entry('Lot No.', row.get('lot_no')),
        dashboard_detail_entry('Part No.', row.get('part_no')),
        dashboard_detail_entry('Die No.', row.get('die_no')),
        dashboard_detail_entry('Qty', row.get('qty')),
        dashboard_detail_entry('Confirm Status', row.get('confirm_status') or 'waiting'),
        dashboard_detail_entry('Setting Die Revision', row.get('setting_die_revision') or 1),
        dashboard_detail_entry('Time Start', row.get('time_start')),
        dashboard_detail_entry('Recorded by', dashboard_recorded_by(row)),
        dashboard_detail_entry('Created At', row.get('created_at')),
        dashboard_detail_entry('Updated At', row.get('updated_at')),
        dashboard_detail_entry('Is Finished', 'Yes' if row.get('is_finished') else 'No'),
        dashboard_detail_entry('Source', f"production_starts #{dashboard_value(row.get('id'))}"),
    ]

def dashboard_production_finish_detail(row):
    return [
        dashboard_detail_entry('Lot No.', row.get('lot_no')),
        dashboard_detail_entry('Part No.', row.get('part_no')),
        dashboard_detail_entry('Die No.', row.get('die_no')),
        dashboard_detail_entry('Planned Qty', row.get('planned_qty')),
        dashboard_detail_entry('Actual Qty', row.get('actual_qty')),
        dashboard_detail_entry('Finish Status', row.get('finish_status') or 'pending'),
        dashboard_detail_entry('Setting Die Revision', row.get('setting_die_revision') or 1),
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
        process_no = normalized_process_die_no(row)
        timeline.append({
            'step': f'Setting Die - Process {process_no}',
            'status': 'incomplete' if not setting_die_record_complete(row) else ('finished' if row.get('is_finished') else 'done'),
            'time_start': row.get('time_start'),
            'time_end': row.get('time_end'),
            'time_finish': None,
            'created_at': row.get('created_at'),
            'updated_at': None,
            'user': dashboard_recorded_by(row),
            'source_table': 'setting_dies',
            'source_id': row.get('id'),
            'process_die_no': process_no,
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

    for row in related['workflow_events'].get(plan_id, []):
        timeline.append({
            'step': row.get('event_type', '').replace('_', ' ').title(),
            'status': 'recorded',
            'time_start': None,
            'time_end': None,
            'time_finish': None,
            'created_at': row.get('created_at'),
            'updated_at': None,
            'user': row.get('actor_username') or 'System',
            'source_table': 'workflow_events',
            'source_id': row.get('id'),
            'metadata': dashboard_source_metadata('workflow_events', row.get('id')),
            'detail': [
                dashboard_detail_entry('Revision', row.get('setting_die_revision')),
                dashboard_detail_entry('Actor', row.get('actor_username') or 'System'),
                dashboard_detail_entry('Reason', row.get('reason')),
                dashboard_detail_entry('Context', row.get('metadata_text')),
                dashboard_detail_entry('Created At', row.get('created_at')),
            ],
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

def fetch_forecast_months(cursor):
    cursor.execute(
        """
        SELECT DATE_FORMAT(forecast_month, '%Y-%m') AS month,
            source_label AS label
        FROM forecast_months
        WHERE is_active = 1
        ORDER BY forecast_month
        """
    )
    return cursor.fetchall()


def fetch_forecast_rows(cursor, selected_month=None, entry_month_pairs=None):
    sql = """
        SELECT e.id, e.part_no, e.source_row,
            m.forecast_month, m.source_label, m.quantity, m.lot_count
        FROM forecast_entries e
        INNER JOIN forecast_monthly_values m ON m.forecast_entry_id = e.id
        INNER JOIN forecast_months fm
            ON fm.forecast_month = m.forecast_month AND fm.is_active = 1
    """
    params = []
    if entry_month_pairs is not None:
        conditions = []
        for entry_id, forecast_month in entry_month_pairs:
            conditions.append("(e.id = %s AND m.forecast_month = %s)")
            params.extend((entry_id, forecast_month))
        sql += " WHERE " + " OR ".join(conditions)
    else:
        sql += " WHERE m.forecast_month = %s"
        params.append(validate_month_key(selected_month))
    sql += " ORDER BY e.source_row ASC, e.id ASC"
    cursor.execute(sql, tuple(params))
    return cursor.fetchall()


def lock_forecast_month_activity(cursor, forecast_months):
    unique_months = sorted(set(forecast_months))
    placeholders = ",".join(["%s"] * len(unique_months))
    cursor.execute(
        f"SELECT forecast_month, is_active FROM forecast_months "
        f"WHERE forecast_month IN ({placeholders}) FOR UPDATE",
        tuple(unique_months),
    )
    return {
        month_key(row['forecast_month']): bool(row['is_active'])
        for row in cursor.fetchall()
    }


@app.route('/api/forecast/months', methods=['GET'])
def get_forecast_months():
    denied = require_exact_role('PC')
    if denied:
        return denied
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            rows = fetch_forecast_months(cursor)
        return jsonify({"success": True, "months": rows})
    except Exception:
        return error_response()
    finally:
        conn.close()

@app.route('/api/forecast', methods=['GET'])
def get_forecast():
    denied = require_exact_role('PC')
    if denied:
        return denied

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            available = fetch_forecast_months(cursor)
            available_keys = [row['month'] for row in available]
            selected_month = request.args.get('month')
            if selected_month is None:
                selected_month = choose_default_month(available_keys)
            else:
                try:
                    selected_month = month_key(selected_month)
                except ForecastValidationError as error:
                    return jsonify({"success": False, "message": str(error)}), 400
            if selected_month is None:
                rows = []
            elif selected_month not in available_keys:
                return jsonify({
                    "success": False,
                    "message": f"FORECAST month is not available: {selected_month}",
                }), 400
            else:
                rows = fetch_forecast_rows(cursor, selected_month=selected_month)
        return jsonify({
            "success": True,
            "month": selected_month,
            "items": [serialize_forecast_entry(row) for row in rows],
        })
    except Exception:
        return error_response()
    finally:
        conn.close()

@app.route('/api/forecast/lots', methods=['POST'])
def save_forecast_lots():
    denied = require_exact_role('PC')
    if denied:
        return denied

    try:
        items = validate_lot_batch(request.get_json(silent=True))
    except ForecastValidationError as error:
        return jsonify({"success": False, "message": str(error)}), 400

    pairs = [(item['id'], item['forecast_month']) for item in items]
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            month_activity = lock_forecast_month_activity(
                cursor,
                [item['forecast_month'] for item in items],
            )
            inactive_months = sorted({
                item['month'] for item in items
                if not month_activity.get(item['month'], False)
            })
            if inactive_months:
                return jsonify({
                    "success": False,
                    "code": "forecast_month_inactive",
                    "message": (
                        "FORECAST month is no longer active: "
                        + ", ".join(inactive_months)
                        + ". Reload active months before saving."
                    ),
                    "inactive_months": inactive_months,
                }), 409
            current_rows = fetch_forecast_rows(cursor, entry_month_pairs=pairs)
            current_by_pair = {
                (int(row['id']), month_key(row['forecast_month'])): row
                for row in current_rows
            }
            missing = [
                (item['id'], item['month']) for item in items
                if (item['id'], item['month']) not in current_by_pair
            ]
            if missing:
                return jsonify({
                    "success": False,
                    "message": f"FORECAST record/month not found: {missing[0][0]}/{missing[0][1]}",
                }), 404

            current_user = getattr(g, 'current_user', {}) or {}
            updated_count = 0
            for item in items:
                existing_lot = current_by_pair[(item['id'], item['month'])].get('lot_count')
                if existing_lot is not None:
                    existing_lot = int(existing_lot)
                if existing_lot == item['lot_count']:
                    continue
                cursor.execute(
                    """
                    UPDATE forecast_monthly_values
                    SET lot_count = %s,
                        lot_updated_at = NOW(),
                        lot_updated_by_user_id = %s,
                        lot_updated_by_username = %s
                    WHERE forecast_entry_id = %s AND forecast_month = %s
                    """,
                    (
                        item['lot_count'],
                        current_user.get('id'),
                        current_user.get('username'),
                        item['id'],
                        item['forecast_month'],
                    ),
                )
                updated_count += 1

            authoritative_rows = fetch_forecast_rows(cursor, entry_month_pairs=pairs)
        conn.commit()
        return jsonify({
            "success": True,
            "updated_count": updated_count,
            "items": [serialize_forecast_entry(row) for row in authoritative_rows],
        })
    except Exception:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

def current_notification_role():
    user = getattr(g, 'current_user', {}) or {}
    return normalize_user_role(user.get('role'))

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    target_role = current_notification_role()
    if not target_role:
        return auth_error()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_notifications_table(cursor)
            cursor.execute("""
                SELECT COUNT(*) AS count
                FROM notifications
                WHERE target_role = %s AND is_read = 0
            """, (target_role,))
            unread_count = (cursor.fetchone() or {}).get('count') or 0

            cursor.execute("""
                SELECT action_menu, COUNT(*) AS count
                FROM notifications
                WHERE target_role = %s
                    AND is_read = 0
                    AND action_menu IS NOT NULL
                    AND action_menu <> ''
                GROUP BY action_menu
            """, (target_role,))
            unread_by_menu = {row.get('action_menu'): row.get('count') or 0 for row in cursor.fetchall()}

            cursor.execute("""
                SELECT id, target_role, type, title, message, plan_id, lot_no, part_no,
                    source_table, source_id, action_menu, is_read, read_at, created_at
                FROM notifications
                WHERE target_role = %s
                ORDER BY is_read ASC, created_at DESC, id DESC
                LIMIT 30
            """, (target_role,))
            return jsonify({
                "success": True,
                "notifications": cursor.fetchall(),
                "unread_count": unread_count,
                "unread_by_menu": unread_by_menu,
            })
    finally:
        conn.close()

@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    target_role = current_notification_role()
    if not target_role:
        return auth_error()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_notifications_table(cursor)
            cursor.execute("""
                UPDATE notifications
                SET is_read = 1, read_at = NOW()
                WHERE id = %s
                    AND target_role = %s
                    AND is_read = 0
            """, (notification_id, target_role))
            if cursor.rowcount == 0:
                cursor.execute("SELECT id FROM notifications WHERE id = %s AND target_role = %s", (notification_id, target_role))
                if not cursor.fetchone():
                    return jsonify({"success": False, "message": "Notification not found"}), 404
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/notifications/read_all', methods=['POST'])
def mark_all_notifications_read():
    target_role = current_notification_role()
    if not target_role:
        return auth_error()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_notifications_table(cursor)
            cursor.execute("""
                UPDATE notifications
                SET is_read = 1, read_at = NOW()
                WHERE target_role = %s AND is_read = 0
            """, (target_role,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

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
                    p.lot_no,
                    p.process_die_count,
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
            summary = dashboard_summary(items)
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
                    p.lot_no,
                    p.process_die_count,
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
                    "lot_no": item['lot_no'],
                    "part_id": item['part_id'],
                    "part_no": item['part_no'],
                    "die_no": item['die_no'],
                    "zone": item['zone'],
                },
                "current_step": item['current_step'],
                "status": item['status'],
                "is_finished": item['is_finished'],
                "dashboard_bucket": item['dashboard_bucket'],
                "setting_die_progress": item['setting_die_progress'],
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
            jobs = cursor.fetchall()
            attach_process_dies_to_plans(cursor, jobs)
            attach_setting_die_workflow_states(cursor, jobs)
            return jsonify(jobs)
    finally:
        conn.close()

# --- [ใหม่] ดึงข้อมูล Production เชิงลึกตาม ID (รวม Setting Die) ---
@app.route('/api/jobs/<int:job_id>', methods=['GET'])
def get_job_detail(job_id):
    process_die_no_arg = request.args.get('process_die_no')
    process_die_no = None
    if process_die_no_arg not in (None, ''):
        try:
            process_die_no = parse_positive_int(process_die_no_arg)
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # ดึงข้อมูลงาน
            ensure_active_visibility_columns(cursor)
            cursor.execute("SELECT * FROM production_plans WHERE id = %s AND deleted_at IS NULL", (job_id,))
            job = cursor.fetchone()
            if not job:
                return jsonify({"success": False, "message": "ไม่พบข้อมูล"})
            
            # ดึงข้อมูล Setting Die (ถ้ามี)
            attach_process_dies_to_plans(cursor, [job])
            job['workflow'] = build_setting_die_workflow_state(cursor, job)
            if process_die_no is not None:
                cursor.execute("""
                    SELECT *
                    FROM setting_dies
                    WHERE plan_id = %s
                        AND COALESCE(process_die_no, 1) = %s
                        AND deleted_at IS NULL
                    ORDER BY id DESC
                    LIMIT 1
                """, (job_id, process_die_no))
            else:
                cursor.execute("SELECT * FROM setting_dies WHERE plan_id = %s AND deleted_at IS NULL ORDER BY id DESC LIMIT 1", (job_id,))
            setting = cursor.fetchone()
            
            response_process_die_no = process_die_no or (normalized_process_die_no(setting) if setting else None)
            return jsonify({"success": True, "job": job, "setting": setting, "process_die_no": response_process_die_no, "workflow": job['workflow']})
    except Exception as e:
        return error_response()
    finally:
        conn.close()

@app.route('/api/production', methods=['POST'])
def add_production():
    lot_no = (request.form.get('prod-lot-no') or '').strip()
    date = request.form.get('prod-date')
    zone = request.form.get('prod-zone')
    part_no = request.form.get('prod-part-no')
    die_no = request.form.get('prod-die-no')
    qty = request.form.get('prod-qty')

    if not lot_no:
        return jsonify({"success": False, "message": "Lot No. is required"}), 400
    try:
        process_die_count = parse_positive_int(request.form.get('prod-process-die-count'), default=1)
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400

    image_path = None
    try:
        image_path = save_uploaded_file(request.files.get('prod-image'))
    except UploadValidationError as e:
        return error_response(str(e), 400)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_parts_schema(cursor)
            ensure_production_process_schema(cursor)
            ensure_workflow_created_by_columns(cursor)
            part = find_or_create_part_by_part_no(cursor, part_no)
            created_by_user_id, created_by_username = created_by_values()
            cursor.execute("""
                INSERT INTO production_plans
                (lot_no, process_die_count, prod_date, zone, part_no, part_id, image_path, die_no, qty, created_by_user_id, created_by_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (lot_no, process_die_count, date, zone, part['part_no'], part['id'], image_path, die_no, qty, created_by_user_id, created_by_username))
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
    try:
        process_die_no = parse_positive_int(form.get('process_die_no'), default=1)
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # ตรวจสอบก่อนว่าเคยมีการบันทึก Setting Die ของ plan_id นี้ไปหรือยัง?
            ensure_active_visibility_columns(cursor)
            ensure_workflow_created_by_columns(cursor)
            part, _plan = validate_plan_part_consistency(cursor, plan_id, form.get('set-part-no'))
            cursor.execute("""
                SELECT id, lot_no, die_no, process_die_count, setting_die_sent_at, setting_die_revision
                FROM production_plans
                WHERE id = %s AND deleted_at IS NULL
                LIMIT 1
                FOR UPDATE
            """, (plan_id,))
            plan = cursor.fetchone()
            if not plan:
                return jsonify({"success": False, "message": "Production plan was not found"}), 404
            if plan.get('setting_die_sent_at'):
                correction = fetch_active_correction(cursor, plan_id, for_update=True)
                if not correction or correction.get('status') != 'open':
                    return jsonify({
                        "success": False,
                        "message": "Setting Die is locked after the initial QC handoff. Reopen a correction before editing.",
                        "setting_die_locked": True,
                    }), 423
            process_count = plan_process_count(plan)
            if process_die_no > process_count:
                return jsonify({"success": False, "message": "Process Die No. is outside the production plan range"}), 400
            previous_process = None
            if process_die_no > 1:
                cursor.execute("""
                    SELECT id, time_start
                    FROM setting_dies
                    WHERE plan_id = %s
                        AND COALESCE(process_die_no, 1) = %s
                        AND deleted_at IS NULL
                    ORDER BY id DESC
                    LIMIT 1
                    FOR UPDATE
                """, (plan_id, process_die_no - 1))
                previous_process = cursor.fetchone()
            if not setting_die_process_eligible(process_die_no, previous_process):
                return jsonify({
                    "success": False,
                    "message": f"Complete Process Die {process_die_no - 1} first",
                }), 409
            is_last_process = process_die_no == process_count
            adjust_fields_submitted = any(empty_to_none(form.get(field)) is not None for field in ('custom-time-3', 'custom-time-4'))
            if not is_last_process and adjust_fields_submitted:
                return jsonify({
                    "success": False,
                    "message": "Adjust Accuracy Part timestamps are allowed only on the last process",
                }), 400

            lot_no = (plan.get('lot_no') or form.get('set-lot-no') or '').strip()
            if not lot_no:
                return jsonify({"success": False, "message": "Lot No. is required"}), 400
            if not plan.get('lot_no'):
                cursor.execute("UPDATE production_plans SET lot_no = %s WHERE id = %s", (lot_no, plan_id))

            cursor.execute("""
                SELECT id, process_die, time_start, time_end, custom_time_1, custom_time_2, custom_time_3, custom_time_4
                FROM setting_dies
                WHERE plan_id = %s
                    AND COALESCE(process_die_no, 1) = %s
                    AND deleted_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
            """, (plan_id, process_die_no))
            existing = cursor.fetchone()
            incoming_setting_time_start = format_datetime(form.get('set-time-start'))

            if existing:
                try:
                    setting_time_start = protect_locked_timestamp(existing.get('time_start'), incoming_setting_time_start, 'Time Start Setting Die')
                    setting_time_end = protect_locked_timestamp(existing.get('time_end'), format_datetime(form.get('set-time-end')), 'Time End Setting Die')
                    material_time_start = protect_locked_timestamp(existing.get('custom_time_1'), format_datetime(form.get('custom-time-1')), 'Time Start Setting Material')
                    material_time_end = protect_locked_timestamp(existing.get('custom_time_2'), format_datetime(form.get('custom-time-2')), 'Time End Setting Material')
                    if is_last_process:
                        adjust_time_start = protect_locked_timestamp(existing.get('custom_time_3'), format_datetime(form.get('custom-time-3')), 'Time Start Adjust Accuracy Part')
                        adjust_time_end = protect_locked_timestamp(existing.get('custom_time_4'), format_datetime(form.get('custom-time-4')), 'Time End Adjust Accuracy Part')
                    else:
                        adjust_time_start = existing.get('custom_time_3')
                        adjust_time_end = existing.get('custom_time_4')
                except ValueError as e:
                    return jsonify({"success": False, "message": str(e)}), 400
                if not setting_time_start:
                    return jsonify({"success": False, "message": SETTING_DIE_TIME_START_REQUIRED}), 400
                process_die_value = form.get('set-process-die') if 'set-process-die' in form else existing.get('process_die')

                # ถ้า "มีข้อมูลเก่าอยู่แล้ว" -> ให้ทำการอัปเดต (UPDATE) ทับของเดิม
                cursor.execute("""
                    UPDATE setting_dies SET
                    part_id=%s, part_no=%s, lot_no=%s, die_no=%s, process_die_no=%s, process_die=%s, dh=%s, spm=%s,
                    time_start=%s, time_end=%s, material=%s,
                    custom_time_1=%s, custom_time_2=%s, custom_time_3=%s, custom_time_4=%s,
                    technician=%s
                    WHERE id=%s
                """, (
                    part['id'], part['part_no'], lot_no, form.get('set-die-no') or plan.get('die_no'), process_die_no, process_die_value,
                    empty_to_none(form.get('set-dh')), empty_to_none(form.get('set-spm')),
                    setting_time_start, setting_time_end,
                    form.get('set-material'), 
                    material_time_start, material_time_end,
                    adjust_time_start, adjust_time_end,
                    form.get('set-technician'),
                    existing['id']
                ))
            else:
                # ถ้า "ยังไม่เคยมีข้อมูล" -> ให้เพิ่มข้อมูลใหม่ (INSERT)
                if not incoming_setting_time_start:
                    return jsonify({"success": False, "message": SETTING_DIE_TIME_START_REQUIRED}), 400
                created_by_user_id, created_by_username = created_by_values()
                adjust_time_start = format_datetime(form.get('custom-time-3')) if is_last_process else None
                adjust_time_end = format_datetime(form.get('custom-time-4')) if is_last_process else None
                cursor.execute("""
                    INSERT INTO setting_dies 
                    (plan_id, part_id, part_no, lot_no, die_no, process_die_no, process_die, dh, spm, time_start, time_end, material, custom_time_1, custom_time_2, custom_time_3, custom_time_4, technician, created_by_user_id, created_by_username)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    plan_id, part['id'], part['part_no'], lot_no, form.get('set-die-no') or plan.get('die_no'), process_die_no, form.get('set-process-die'),
                    empty_to_none(form.get('set-dh')), empty_to_none(form.get('set-spm')), incoming_setting_time_start, format_datetime(form.get('set-time-end')),
                    form.get('set-material'), format_datetime(form.get('custom-time-1')), format_datetime(form.get('custom-time-2')),
                    adjust_time_start, adjust_time_end, form.get('set-technician'),
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
            plans = get_ready_setting_plans(cursor, exclude_active_start=True)
            return jsonify(plans)
    finally:
        conn.close()

@app.route('/api/production_start/plan', methods=['GET'])
def get_production_start_plan_detail():
    lot_no = request.args.get('lot_no', '')
    if not lot_no:
        return jsonify({"success": False, "message": "กรุณาเลือก Lot No."})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_parts_schema(cursor)
            plan = get_production_start_plan(cursor, lot_no)
            if not plan:
                return jsonify({"success": False, "message": "ไม่พบข้อมูล Lot No. นี้"})
            return jsonify({"success": True, "plan": plan})
    finally:
        conn.close()

@app.route('/api/qc/plans', methods=['GET'])
def get_qc_plans():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            plans = attach_current_qc_state(cursor, get_ready_setting_plans(cursor))
            return jsonify(plans)
    finally:
        conn.close()

@app.route('/api/qc/plan', methods=['GET'])
def get_qc_plan_detail():
    lot_no = request.args.get('lot_no', '')
    if not lot_no:
        return jsonify({"success": False, "message": "กรุณาเลือก Lot No."})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_active_visibility_columns(cursor)
            plan = get_production_start_plan(cursor, lot_no)
            if not plan:
                return jsonify({"success": False, "message": "ไม่พบข้อมูล Lot No. นี้"})

            cursor.execute("""
                SELECT
                    COALESCE(s.is_finished, 0) AS setting_finished,
                    COALESCE(p.is_finished, 0) AS plan_finished
                FROM setting_dies s
                LEFT JOIN production_plans p ON p.id = s.plan_id
                WHERE s.lot_no = %s
                    AND s.deleted_at IS NULL
                    AND p.deleted_at IS NULL
                ORDER BY s.id DESC
                LIMIT 1
            """, (lot_no,))
            visibility = cursor.fetchone() or {}
            if visibility.get('setting_finished') or visibility.get('plan_finished'):
                return jsonify({"success": False, "message": "Lot No. นี้ถูก Finish แล้ว"})

            plan = attach_current_qc_state(cursor, [plan])[0]
            return jsonify({"success": True, "plan": plan})
    finally:
        conn.close()

@app.route('/api/qc/from_setting_die', methods=['POST'])
def create_qc_from_setting_die():
    lot_no = (request.form.get('lot_no') or '').strip()
    plan_id = request.form.get('plan_id')
    if not lot_no and not plan_id:
        return jsonify({"success": False, "message": "Plan ID or Lot No. is required"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            plan = fetch_workflow_plan(cursor, plan_id=plan_id, lot_no=lot_no, for_update=True)
            if not plan:
                return jsonify({"success": False, "message": "Production plan was not found"}), 404

            if plan.get('setting_die_sent_at'):
                state = build_setting_die_workflow_state(cursor, plan)
                conn.commit()
                return jsonify({
                    "success": True,
                    "created": False,
                    "already_sent": True,
                    "handoff_state": "sent",
                    "message": "This initial QC Line handoff was already sent.",
                    "workflow": state,
                })

            settings = fetch_active_settings_by_plan_ids(cursor, [plan['id']]).get(plan['id'], [])
            plan['_settings'] = settings
            plan['process_dies'] = build_process_dies_for_plan(plan, settings)
            if not plan.get('lot_no') or not setting_die_processes_complete(plan):
                return jsonify({"success": False, "message": "Setting Die is not complete for every process"}), 409

            part, _plan = validate_plan_part_consistency(cursor, plan.get('id'), plan.get('part_no'))

            created_by_user_id, created_by_username = created_by_values()
            revision = int(plan.get('setting_die_revision') or 1)
            cursor.execute("""
                INSERT INTO qc_inspections
                (plan_id, part_id, lot_no, part_no, time_start, time_end, percent_result, status, problem_area, problem_point, image_path, cause, solution, setting_die_revision, created_by_user_id, created_by_username)
                VALUES (%s, %s, %s, %s, NULL, NULL, NULL, %s, %s, NULL, NULL, NULL, NULL, %s, %s, %s)
            """, (
                plan.get('id'),
                part['id'],
                plan.get('lot_no'),
                part['part_no'],
                'Waiting',
                'none',
                revision,
                created_by_user_id,
                created_by_username,
            ))
            qc_id = cursor.lastrowid
            cursor.execute("""
                UPDATE production_plans
                SET setting_die_sent_at = NOW(),
                    setting_die_sent_by_user_id = %s,
                    setting_die_sent_by_username = %s
                WHERE id = %s AND setting_die_sent_at IS NULL
            """, (created_by_user_id, created_by_username, plan['id']))
            notification = create_notification(
                cursor,
                target_role='QC Line',
                type='qc_waiting',
                title='New job waiting for QC',
                message=f"Lot No. {plan.get('lot_no')} / Part {part['part_no']} was sent to QC Line.",
                plan_id=plan.get('id'),
                lot_no=plan.get('lot_no'),
                part_no=part['part_no'],
                source_table='qc_inspections',
                source_id=qc_id,
                action_menu='qc',
                event_key=f"setting-die-qc-initial:{plan['id']}",
                ensure_schema=False,
            )
            record_workflow_event(
                cursor, plan['id'], f"setting-die-qc-initial:{plan['id']}",
                'setting_die_sent_to_qc', revision,
            )
        conn.commit()
        return jsonify({
            "success": True,
            "created": True,
            "already_sent": False,
            "handoff_state": "sent",
            "qc_id": qc_id,
            "notification": notification,
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


def request_value(name, default=None):
    payload = request.get_json(silent=True) or {}
    return payload.get(name, request.form.get(name, default))


def create_setting_die_correction_session(direct_reopen):
    plan_id = request_value('plan_id')
    reason = str(request_value('reason', '') or '').strip()
    if not plan_id:
        return jsonify({"success": False, "message": "Plan ID is required"}), 400
    if not reason:
        return jsonify({"success": False, "message": "Reason for correction is required"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            plan = fetch_workflow_plan(cursor, plan_id=plan_id, for_update=True)
            if not plan:
                return jsonify({"success": False, "message": "Production plan was not found"}), 404
            if not plan.get('setting_die_sent_at'):
                return jsonify({"success": False, "message": "Setting Die has not been sent to QC Line"}), 409

            active = fetch_active_correction(cursor, plan['id'], for_update=True)
            if active:
                conn.commit()
                return jsonify({
                    "success": True,
                    "created": False,
                    "already_active": True,
                    "correction": active,
                    "workflow": build_setting_die_workflow_state(cursor, plan),
                })

            qc = fetch_latest_workflow_row(cursor, 'qc_inspections', plan['id'])
            production_start = fetch_latest_workflow_row(cursor, 'production_starts', plan['id'])
            production_finish = fetch_latest_workflow_row(cursor, 'production_finishes', plan['id'])
            stage = downstream_stage(qc, production_start, production_finish)
            approval_required = correction_requires_approval(stage)
            if direct_reopen and approval_required:
                return jsonify({
                    "success": False,
                    "message": "Downstream work has progressed. Submit Request Correction for Admin or Sup approval.",
                    "approval_required": True,
                    "downstream_stage": stage,
                }), 409

            status = 'pending_approval' if approval_required else 'open'
            user_id, username, _role = workflow_actor()
            base_revision = int(plan.get('setting_die_revision') or 1)
            cursor.execute("""
                INSERT INTO setting_die_corrections
                (plan_id, base_revision, target_revision, reason, status, downstream_stage,
                 approval_required, requested_by_user_id, requested_by_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                plan['id'], base_revision, base_revision + 1, reason, status, stage,
                int(approval_required), user_id, username,
            ))
            correction_id = cursor.lastrowid
            event_type = 'setting_die_correction_requested' if approval_required else 'setting_die_correction_reopened'
            record_workflow_event(
                cursor, plan['id'], f"setting-die-correction-{correction_id}-created",
                event_type, base_revision, reason, stage,
            )
            cursor.execute("SELECT * FROM setting_die_corrections WHERE id = %s", (correction_id,))
            correction = cursor.fetchone()
        conn.commit()
        return jsonify({
            "success": True,
            "created": True,
            "approval_required": approval_required,
            "correction": correction,
            "workflow": build_setting_die_workflow_state_after_commit(plan['id']),
        })
    except pymysql.err.IntegrityError:
        conn.rollback()
        with conn.cursor() as cursor:
            active = fetch_active_correction(cursor, plan_id)
        return jsonify({
            "success": True,
            "created": False,
            "already_active": True,
            "correction": active,
        })
    except Exception:
        conn.rollback()
        return error_response()
    finally:
        conn.close()


def build_setting_die_workflow_state_after_commit(plan_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            plan = fetch_workflow_plan(cursor, plan_id=plan_id)
            return build_setting_die_workflow_state(cursor, plan) if plan else None
    finally:
        conn.close()


@app.route('/api/setting_die/corrections/reopen', methods=['POST'])
def reopen_setting_die_correction():
    return create_setting_die_correction_session(direct_reopen=True)


@app.route('/api/setting_die/corrections/request', methods=['POST'])
def request_setting_die_correction():
    return create_setting_die_correction_session(direct_reopen=False)


@app.route('/api/setting_die/corrections', methods=['GET'])
def get_setting_die_corrections():
    plan_id = request.args.get('plan_id')
    if not plan_id:
        return jsonify({"success": False, "message": "Plan ID is required"}), 400
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM setting_die_corrections
                WHERE plan_id = %s
                ORDER BY id DESC
            """, (plan_id,))
            return jsonify({"success": True, "corrections": cursor.fetchall()})
    finally:
        conn.close()


@app.route('/api/setting_die/corrections/<int:correction_id>/approve', methods=['POST'])
def approve_setting_die_correction(correction_id):
    _user_id, _username, role = workflow_actor()
    if not can_approve_correction(role):
        return jsonify({"success": False, "message": "Only Admin or Sup may approve this correction"}), 403
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT plan_id FROM setting_die_corrections WHERE id = %s", (correction_id,))
            reference = cursor.fetchone()
            if not reference:
                return jsonify({"success": False, "message": "Correction request was not found"}), 404
            plan = fetch_workflow_plan(cursor, plan_id=reference['plan_id'], for_update=True)
            cursor.execute("SELECT * FROM setting_die_corrections WHERE id = %s FOR UPDATE", (correction_id,))
            correction = cursor.fetchone()
            if correction.get('status') == 'open':
                conn.commit()
                return jsonify({"success": True, "already_approved": True, "correction": correction})
            if correction.get('status') != 'pending_approval':
                return jsonify({"success": False, "message": "Only a pending correction may be approved"}), 409
            user_id, username, _role = workflow_actor()
            cursor.execute("""
                UPDATE setting_die_corrections
                SET status = 'open', approved_by_user_id = %s,
                    approved_by_username = %s, approved_at = NOW()
                WHERE id = %s AND status = 'pending_approval'
            """, (user_id, username, correction_id))
            record_workflow_event(
                cursor, plan['id'], f"setting-die-correction-{correction_id}-approved",
                'setting_die_correction_approved', correction.get('base_revision'), correction.get('reason'),
            )
            cursor.execute("SELECT * FROM setting_die_corrections WHERE id = %s", (correction_id,))
            correction = cursor.fetchone()
        conn.commit()
        return jsonify({"success": True, "correction": correction})
    except Exception:
        conn.rollback()
        return error_response()
    finally:
        conn.close()


@app.route('/api/setting_die/corrections/<int:correction_id>/reject', methods=['POST'])
def reject_setting_die_correction(correction_id):
    _user_id, _username, role = workflow_actor()
    if not can_approve_correction(role):
        return jsonify({"success": False, "message": "Only Admin or Sup may reject this correction"}), 403
    rejection_reason = str(request_value('reason', '') or '').strip()
    if not rejection_reason:
        return jsonify({"success": False, "message": "Rejection reason is required"}), 400
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT plan_id FROM setting_die_corrections WHERE id = %s", (correction_id,))
            reference = cursor.fetchone()
            if not reference:
                return jsonify({"success": False, "message": "Correction request was not found"}), 404
            plan = fetch_workflow_plan(cursor, plan_id=reference['plan_id'], for_update=True)
            cursor.execute("SELECT * FROM setting_die_corrections WHERE id = %s FOR UPDATE", (correction_id,))
            correction = cursor.fetchone()
            if correction.get('status') == 'rejected':
                conn.commit()
                return jsonify({"success": True, "already_rejected": True, "correction": correction})
            if correction.get('status') != 'pending_approval':
                return jsonify({"success": False, "message": "Only a pending correction may be rejected"}), 409
            user_id, username, _role = workflow_actor()
            cursor.execute("""
                UPDATE setting_die_corrections
                SET status = 'rejected', rejected_by_user_id = %s,
                    rejected_by_username = %s, rejected_at = NOW(), rejection_reason = %s
                WHERE id = %s AND status = 'pending_approval'
            """, (user_id, username, rejection_reason, correction_id))
            record_workflow_event(
                cursor, plan['id'], f"setting-die-correction-{correction_id}-rejected",
                'setting_die_correction_rejected', correction.get('base_revision'), rejection_reason,
            )
            cursor.execute("SELECT * FROM setting_die_corrections WHERE id = %s", (correction_id,))
            correction = cursor.fetchone()
        conn.commit()
        return jsonify({"success": True, "correction": correction})
    except Exception:
        conn.rollback()
        return error_response()
    finally:
        conn.close()


@app.route('/api/setting_die/corrections/<int:correction_id>/finish', methods=['POST'])
def finish_setting_die_correction(correction_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT plan_id FROM setting_die_corrections WHERE id = %s", (correction_id,))
            reference = cursor.fetchone()
            if not reference:
                return jsonify({"success": False, "message": "Correction request was not found"}), 404
            plan = fetch_workflow_plan(cursor, plan_id=reference['plan_id'], for_update=True)
            cursor.execute("SELECT * FROM setting_die_corrections WHERE id = %s FOR UPDATE", (correction_id,))
            correction = cursor.fetchone()
            if correction.get('status') == 'completed':
                conn.commit()
                return jsonify({
                    "success": True,
                    "already_completed": True,
                    "revision": correction.get('target_revision'),
                    "correction": correction,
                })
            if correction.get('status') != 'open':
                return jsonify({"success": False, "message": "Correction must be open before it can be finished"}), 409
            if int(plan.get('setting_die_revision') or 1) != int(correction.get('base_revision')):
                return jsonify({"success": False, "message": "Setting Die revision changed while this correction was open"}), 409

            settings = fetch_active_settings_by_plan_ids(cursor, [plan['id']]).get(plan['id'], [])
            plan['_settings'] = settings
            if not setting_die_processes_complete(plan):
                return jsonify({"success": False, "message": "Setting Die is not complete for every process"}), 409

            target_revision = int(correction.get('target_revision'))
            user_id, username, _role = workflow_actor()
            cursor.execute("""
                UPDATE production_plans
                SET setting_die_revision = %s
                WHERE id = %s AND setting_die_revision = %s
            """, (target_revision, plan['id'], correction.get('base_revision')))
            if cursor.rowcount != 1:
                return jsonify({"success": False, "message": "Setting Die revision changed while finishing correction"}), 409
            cursor.execute("""
                UPDATE setting_die_corrections
                SET status = 'completed', completed_by_user_id = %s,
                    completed_by_username = %s, completed_at = NOW()
                WHERE id = %s AND status = 'open'
            """, (user_id, username, correction_id))

            cursor.execute("""
                UPDATE qc_inspections
                SET is_finished = 1
                WHERE plan_id = %s AND deleted_at IS NULL
                  AND setting_die_revision < %s AND COALESCE(is_finished, 0) = 0
            """, (plan['id'], target_revision))
            part, _plan = validate_plan_part_consistency(cursor, plan['id'], plan.get('part_no'))
            cursor.execute("""
                INSERT INTO qc_inspections
                (plan_id, part_id, lot_no, part_no, status, problem_area,
                 setting_die_revision, created_by_user_id, created_by_username)
                VALUES (%s, %s, %s, %s, 'Waiting', 'none', %s, %s, %s)
            """, (
                plan['id'], part['id'], plan.get('lot_no'), part['part_no'],
                target_revision, user_id, username,
            ))
            qc_id = cursor.lastrowid
            notification = create_notification(
                cursor,
                target_role='QC Line',
                type='qc_setting_die_updated',
                title='Setting Die update requires QC review',
                message=f"Lot No. {plan.get('lot_no')} Setting Die information was updated to revision {target_revision}. QC review is required.",
                plan_id=plan['id'], lot_no=plan.get('lot_no'), part_no=part['part_no'],
                source_table='setting_die_corrections', source_id=correction_id,
                action_menu='qc', event_key=f"setting-die-qc-update:{plan['id']}:{target_revision}",
                ensure_schema=False,
            )
            record_workflow_event(
                cursor, plan['id'], f"setting-die-correction-{correction_id}-completed",
                'setting_die_correction_completed', target_revision, correction.get('reason'),
                'QC recheck required',
            )
            record_workflow_event(
                cursor, plan['id'], f"setting-die-qc-update:{plan['id']}:{target_revision}",
                'qc_notified_of_setting_die_update', target_revision,
            )
        conn.commit()
        return jsonify({
            "success": True,
            "already_completed": False,
            "revision": target_revision,
            "qc_id": qc_id,
            "notification": notification,
            "initial_handoff_sent": True,
            "qc_recheck_required": True,
        })
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception:
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
            cursor.execute("""
                SELECT id, plan_id, setting_die_revision, confirm_status
                FROM production_starts
                WHERE id = %s AND deleted_at IS NULL
            """, (start_id,))
            reference = cursor.fetchone()
            if not reference:
                return jsonify({"success": False, "message": "Production Start was not found"}), 404
            if production_start_confirmed(reference.get('confirm_status')):
                conn.commit()
                return jsonify({"success": True, "already_confirmed": True, "confirm_status": "confirmed"})

            plan = fetch_workflow_plan(cursor, plan_id=reference.get('plan_id'), for_update=True)
            cursor.execute("""
                SELECT id, plan_id, setting_die_revision, confirm_status
                FROM production_starts
                WHERE id = %s AND deleted_at IS NULL
                FOR UPDATE
            """, (start_id,))
            start = cursor.fetchone()
            if not start:
                return jsonify({"success": False, "message": "Production Start was not found"}), 404
            if production_start_confirmed(start.get('confirm_status')):
                conn.commit()
                return jsonify({"success": True, "already_confirmed": True, "confirm_status": "confirmed"})
            if not plan or int(start.get('setting_die_revision') or 1) != int(plan.get('setting_die_revision') or 1):
                return jsonify({"success": False, "message": "Production Start is based on an obsolete Setting Die revision"}), 409
            if fetch_active_correction(cursor, plan['id'], for_update=True) or not current_revision_qc_pass(cursor, plan['id'], for_update=True):
                return jsonify({"success": False, "message": "Current Setting Die revision requires a current QC Pass"}), 409
            cursor.execute("""
                UPDATE production_starts
                SET confirm_status = 'confirmed'
                WHERE id = %s AND deleted_at IS NULL
                  AND COALESCE(confirm_status, 'waiting') <> 'confirmed'
            """, (start_id,))
        conn.commit()
        return jsonify({"success": True, "already_confirmed": False, "confirm_status": "confirmed"})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()


@app.route('/api/production_start/<int:start_id>/timestamps/time_start/stamp', methods=['POST'])
def stamp_production_start_timestamp(start_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_parts_schema(cursor)
            cursor.execute("""
                SELECT id, plan_id
                FROM production_starts
                WHERE id = %s AND deleted_at IS NULL
            """, (start_id,))
            reference = cursor.fetchone()
            if not reference:
                return jsonify({"success": False, "message": "Production Start was not found"}), 404

            plan = fetch_workflow_plan(cursor, plan_id=reference.get('plan_id'), for_update=True)
            if not plan:
                return jsonify({"success": False, "message": "Production plan was not found"}), 404
            cursor.execute("""
                SELECT id, plan_id, part_id, lot_no, part_no, setting_die_revision,
                       confirm_status, time_start
                FROM production_starts
                WHERE id = %s AND deleted_at IS NULL
                FOR UPDATE
            """, (start_id,))
            start = cursor.fetchone()
            if not start or start.get('plan_id') != plan.get('id'):
                return jsonify({"success": False, "message": "Production Start workflow identity changed; reload and try again"}), 409
            if not production_start_confirmed(start.get('confirm_status')):
                return jsonify({
                    "success": False,
                    "error": "production_start_not_confirmed",
                    "message": "Confirm Production Start first",
                }), 409
            if int(start.get('setting_die_revision') or 1) != int(plan.get('setting_die_revision') or 1):
                return jsonify({"success": False, "message": "Production Start is based on an obsolete Setting Die revision"}), 409
            if fetch_active_correction(cursor, plan['id'], for_update=True):
                return jsonify({"success": False, "message": "Production Start is blocked while a Setting Die correction is active"}), 409
            if not current_revision_qc_pass(cursor, plan['id'], for_update=True):
                return jsonify({"success": False, "message": "Current Setting Die revision requires a current QC Pass"}), 409

            part, _plan = validate_plan_part_consistency(cursor, plan['id'], plan.get('part_no'))
            validate_production_start_identity(start, plan, part)
            if start.get('time_start'):
                conn.commit()
                return jsonify({
                    "success": False,
                    "already_stamped": True,
                    "message": "Production Start Time was already stamped",
                    "production_start_id": start_id,
                    "field": "time_start",
                    "timestamp": normalize_timestamp_value(start.get('time_start')),
                }), 409

            stamped, timestamp = stamp_locked_production_start_time(cursor, start_id)
            if not timestamp:
                raise RuntimeError("Production Start timestamp write did not return a stored value")
        conn.commit()
        return jsonify({
            "success": stamped,
            "already_stamped": not stamped,
            "production_start_id": start_id,
            "field": "time_start",
            "timestamp": normalize_timestamp_value(timestamp),
        }), 200 if stamped else 409
    except (PartValidationError, ProductionStartValidationError) as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception:
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

def update_confirmed_production_start(start_id, form):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_parts_schema(cursor)
            cursor.execute("""
                SELECT id, plan_id
                FROM production_starts
                WHERE id = %s AND deleted_at IS NULL
            """, (start_id,))
            reference = cursor.fetchone()
            if not reference:
                return jsonify({"success": False, "message": "Production Start was not found"}), 404

            plan = fetch_workflow_plan(cursor, plan_id=reference.get('plan_id'), for_update=True)
            if not plan:
                return jsonify({"success": False, "message": "Production plan was not found"}), 404
            cursor.execute("""
                SELECT id, plan_id, part_id, lot_no, part_no, die_no, qty,
                       time_start, confirm_status, setting_die_revision, qc_inspection_id
                FROM production_starts
                WHERE id = %s AND deleted_at IS NULL
                FOR UPDATE
            """, (start_id,))
            start = cursor.fetchone()
            if not start:
                return jsonify({"success": False, "message": "Production Start was not found"}), 404
            if not production_start_confirmed(start.get('confirm_status')):
                return jsonify({
                    "success": False,
                    "error": "production_start_not_confirmed",
                    "message": "Confirm Production Start first",
                }), 409
            if int(start.get('setting_die_revision') or 1) != int(plan.get('setting_die_revision') or 1):
                return jsonify({"success": False, "message": "Production Start is based on an obsolete Setting Die revision"}), 409
            if not plan.get('operator_notified_at'):
                return jsonify({"success": False, "message": "QC must notify Operator before Production Start"}), 409
            if fetch_active_correction(cursor, plan['id'], for_update=True):
                return jsonify({"success": False, "message": "Production Start is blocked while a Setting Die correction is active"}), 409
            current_qc = current_revision_qc_pass(cursor, plan['id'], for_update=True)
            if not current_qc:
                return jsonify({"success": False, "message": "Current Setting Die revision requires a current QC Pass"}), 409

            part, _plan = validate_plan_part_consistency(cursor, plan['id'], plan.get('part_no'))
            validate_production_start_identity(
                start, plan, part,
                requested_lot_no=form.get('start-lot-no'),
                requested_part_no=form.get('start-part-no'),
            )
            for requested_plan_id in (form.get('start-plan-id'), form.get('plan_id')):
                validate_production_start_identity(start, plan, part, requested_plan_id=requested_plan_id)
            for requested_part_id in (form.get('start-part-id'), form.get('part_id')):
                validate_production_start_identity(start, plan, part, requested_part_id=requested_part_id)

            cursor.execute("""
                UPDATE production_starts
                SET die_no = %s, qty = %s, qc_inspection_id = %s
                WHERE id = %s AND deleted_at IS NULL
            """, (plan.get('die_no'), plan.get('qty'), current_qc['id'], start_id))
        conn.commit()
        return jsonify({"success": True, "production_start_id": int(start_id)})
    except (PartValidationError, ProductionStartValidationError) as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception:
        conn.rollback()
        return error_response()
    finally:
        conn.close()


@app.route('/api/production_start', methods=['POST'])
def save_production_start():
    form = request.form
    start_id = form.get('start-id')
    if start_id:
        if not str(start_id).isdigit():
            return jsonify({"success": False, "message": "Invalid Production Start ID"}), 400
        return update_confirmed_production_start(start_id, form)
    lot_no = form.get('start-lot-no')
    if not lot_no:
        return jsonify({"success": False, "message": "กรุณาเลือก Lot No."})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_parts_schema(cursor)
            ensure_workflow_created_by_columns(cursor)
            plan_record = fetch_workflow_plan(cursor, lot_no=lot_no, for_update=True) or {}
            plan = setting_plan_payload(plan_record) if plan_record else {}
            if not plan_record:
                return jsonify({"success": False, "message": "Production plan was not found"}), 404
            if not plan_record.get('operator_notified_at'):
                return jsonify({"success": False, "message": "QC must notify Operator before Production Start"}), 409
            if fetch_active_correction(cursor, plan_record['id'], for_update=True):
                return jsonify({"success": False, "message": "Production Start is blocked while a Setting Die correction is active"}), 409
            current_qc = current_revision_qc_pass(cursor, plan_record['id'], for_update=True)
            if not current_qc:
                return jsonify({"success": False, "message": "Current Setting Die revision requires a current QC Pass"}), 409
            lot_no = plan.get('lot_no')
            part_no = plan.get('part_no')
            die_no = plan.get('die_no')
            qty = plan.get('qty')

            if not all([lot_no, part_no, die_no, qty]):
                return jsonify({"success": False, "message": "ข้อมูล Production Start ยังไม่ครบ ไม่สามารถบันทึกได้"})

            plan_id = plan_record['id']
            part, _plan = validate_plan_part_consistency(cursor, plan_id, part_no)
            cursor.execute("""
                SELECT id
                FROM setting_dies
                WHERE lot_no = %s
                    AND deleted_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
            """, (lot_no,))
            duplicate_sql = """
                SELECT id
                FROM production_starts
                WHERE lot_no = %s
                    AND COALESCE(is_finished, 0) = 0
                    AND deleted_at IS NULL
            """
            duplicate_params = [lot_no]
            duplicate_sql += " LIMIT 1"
            cursor.execute(duplicate_sql, tuple(duplicate_params))
            if cursor.fetchone():
                return jsonify({
                    "success": False,
                    "message": "Lot No. นี้มี Production Start อยู่แล้ว ไม่สามารถบันทึกซ้ำได้"
                })

            created_by_user_id, created_by_username = created_by_values()
            cursor.execute("""
                INSERT INTO production_starts
                (plan_id, part_id, lot_no, part_no, die_no, qty, time_start,
                 setting_die_revision, qc_inspection_id, created_by_user_id, created_by_username)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s)
            """, (
                plan_id, part['id'], lot_no, part['part_no'], die_no, qty,
                plan_record.get('setting_die_revision') or 1, current_qc['id'],
                created_by_user_id, created_by_username,
            ))
            saved_start_id = cursor.lastrowid
        conn.commit()
        return jsonify({"success": True, "production_start_id": saved_start_id})
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
                    ps.lot_no,
                    ps.part_no,
                    ps.die_no,
                    ps.qty
                FROM production_starts ps
                LEFT JOIN production_plans p ON p.id = ps.plan_id
                WHERE ps.lot_no IS NOT NULL AND ps.lot_no <> ''
                    AND COALESCE(ps.is_finished, 0) = 0
                    AND LOWER(COALESCE(ps.confirm_status, '')) = 'confirmed'
                    AND ps.deleted_at IS NULL
                    AND (p.id IS NULL OR (COALESCE(p.is_finished, 0) = 0 AND p.deleted_at IS NULL))
                    AND (p.id IS NULL OR ps.setting_die_revision = p.setting_die_revision)
                ORDER BY ps.id DESC
            """)
            rows = cursor.fetchall()
            plans = []
            seen = set()
            for row in rows:
                if row['lot_no'] in seen:
                    continue
                seen.add(row['lot_no'])
                plans.append(row)
            return jsonify(plans)
    finally:
        conn.close()

@app.route('/api/production_finish/plan', methods=['GET'])
def get_production_finish_plan_detail():
    lot_no = request.args.get('lot_no', '')
    if not lot_no:
        return jsonify({"success": False, "message": "กรุณาเลือก Lot No."})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_parts_schema(cursor)
            cursor.execute("""
                SELECT
                    ps.plan_id,
                    ps.part_id,
                    ps.lot_no,
                    ps.part_no,
                    ps.die_no,
                    ps.qty
                FROM production_starts ps
                LEFT JOIN production_plans p ON p.id = ps.plan_id
                WHERE ps.lot_no = %s
                    AND COALESCE(ps.is_finished, 0) = 0
                    AND LOWER(COALESCE(ps.confirm_status, '')) = 'confirmed'
                    AND ps.deleted_at IS NULL
                    AND (p.id IS NULL OR (COALESCE(p.is_finished, 0) = 0 AND p.deleted_at IS NULL))
                    AND (p.id IS NULL OR ps.setting_die_revision = p.setting_die_revision)
                ORDER BY ps.id DESC
                LIMIT 1
            """, (lot_no,))
            plan = cursor.fetchone()
            if not plan:
                return jsonify({"success": False, "message": "ไม่พบข้อมูล Lot No. ที่พร้อม Finish"})
            return jsonify({"success": True, "plan": plan})
    finally:
        conn.close()

@app.route('/api/production_finish', methods=['POST'])
def save_production_finish():
    form = request.form
    lot_no = form.get('finish-lot-no')
    actual_qty = form.get('finish-actual-qty')
    note = form.get('finish-note')

    if not all([lot_no, actual_qty]):
        return jsonify({"success": False, "message": "ข้อมูล Production Finish ยังไม่ครบ ไม่สามารถบันทึกได้"})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_starts_table(cursor)
            ensure_production_finishes_table(cursor)
            ensure_parts_schema(cursor)
            ensure_workflow_created_by_columns(cursor)
            cursor.execute("""
                SELECT plan_id, part_id, lot_no, part_no, die_no, qty, confirm_status, setting_die_revision
                FROM production_starts
                WHERE lot_no = %s
                    AND COALESCE(is_finished, 0) = 0
                    AND deleted_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
            """, (lot_no,))
            active_start = cursor.fetchone()
            if not active_start:
                return jsonify({"success": False, "message": "ไม่พบ Production Start ที่พร้อม Finish"})
            if (active_start.get('confirm_status') or '').lower() != 'confirmed':
                return jsonify({"success": False, "message": "กรุณา Confirm Production Start ก่อนบันทึก Finish"})

            workflow_plan = fetch_workflow_plan(cursor, plan_id=active_start.get('plan_id'), for_update=True)
            if not workflow_plan or int(active_start.get('setting_die_revision') or 1) != int(workflow_plan.get('setting_die_revision') or 1):
                return jsonify({"success": False, "message": "Production Finish is blocked by a newer Setting Die revision"}), 409
            current_qc = current_revision_qc_pass(cursor, workflow_plan['id'], for_update=True)
            if fetch_active_correction(cursor, workflow_plan['id'], for_update=True) or not current_qc:
                return jsonify({"success": False, "message": "Current Setting Die revision requires a current QC Pass"}), 409

            plan = setting_plan_payload(workflow_plan)

            part_no = plan.get('part_no')
            die_no = plan.get('die_no')
            planned_qty = plan.get('qty')
            plan_id = plan.get('plan_id')
            part, _plan = validate_plan_part_consistency(cursor, plan_id, part_no)

            created_by_user_id, created_by_username = created_by_values()
            cursor.execute("""
                INSERT INTO production_finishes
                (plan_id, part_id, lot_no, part_no, die_no, planned_qty, actual_qty, note,
                 time_finish, hold_time, finish_status, setting_die_revision, qc_inspection_id,
                 created_by_user_id, created_by_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, 'pending', %s, %s, %s, %s)
            """, (
                plan_id, part['id'], lot_no, part['part_no'], die_no, planned_qty,
                actual_qty, note,
                workflow_plan.get('setting_die_revision') or 1, current_qc['id'],
                created_by_user_id, created_by_username,
            ))
            finish_id = cursor.lastrowid

        conn.commit()
        return jsonify({"success": True, "production_finish_id": finish_id})
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
            if not finish.get('time_finish'):
                return jsonify({"success": False, "message": "Stamp Production Finish Time before confirmation"}), 409

            workflow_plan = fetch_workflow_plan(cursor, plan_id=finish.get('plan_id'), for_update=True)
            if not workflow_plan or int(finish.get('setting_die_revision') or 1) != int(workflow_plan.get('setting_die_revision') or 1):
                return jsonify({"success": False, "message": "Production Finish is based on an obsolete Setting Die revision"}), 409
            if fetch_active_correction(cursor, workflow_plan['id'], for_update=True) or not current_revision_qc_pass(cursor, workflow_plan['id'], for_update=True):
                return jsonify({"success": False, "message": "Current Setting Die revision requires a current QC Pass"}), 409

            update_production_finish_snapshot(cursor, finish_id, finish)
            clear_active_work_for_plan(cursor, finish['lot_no'])
            cursor.execute("UPDATE production_finishes SET finish_status = 'confirmed' WHERE id = %s", (finish_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()

@app.route('/api/production_finish/<int:finish_id>/timestamps/<field_name>/stamp', methods=['POST'])
def stamp_production_finish_timestamp(finish_id, field_name):
    try:
        field_name = validate_production_finish_timestamp_field(field_name)
    except ProductionFinishValidationError as e:
        return jsonify({"success": False, "message": str(e)}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_production_finishes_table(cursor)
            ensure_parts_schema(cursor)
            cursor.execute("""
                SELECT id, plan_id
                FROM production_finishes
                WHERE id = %s AND deleted_at IS NULL
            """, (finish_id,))
            reference = cursor.fetchone()
            if not reference:
                return jsonify({"success": False, "message": "Production Finish was not found"}), 404

            plan = fetch_workflow_plan(cursor, plan_id=reference.get('plan_id'), for_update=True)
            if not plan:
                return jsonify({"success": False, "message": "Production plan was not found"}), 404
            cursor.execute("""
                SELECT id, plan_id, part_id, lot_no, part_no, setting_die_revision,
                       time_finish, hold_time
                FROM production_finishes
                WHERE id = %s AND deleted_at IS NULL
                FOR UPDATE
            """, (finish_id,))
            finish = cursor.fetchone()
            if not finish or finish.get('plan_id') != plan.get('id'):
                return jsonify({"success": False, "message": "Production Finish workflow identity changed; reload and try again"}), 409
            if int(finish.get('setting_die_revision') or 1) != int(plan.get('setting_die_revision') or 1):
                return jsonify({"success": False, "message": "Production Finish is based on an obsolete Setting Die revision"}), 409
            if fetch_active_correction(cursor, plan['id'], for_update=True):
                return jsonify({"success": False, "message": "Production Finish is blocked while a Setting Die correction is active"}), 409
            if not current_revision_qc_pass(cursor, plan['id'], for_update=True):
                return jsonify({"success": False, "message": "Current Setting Die revision requires a current QC Pass"}), 409

            part, _plan = validate_plan_part_consistency(cursor, plan['id'], plan.get('part_no'))
            validate_production_finish_identity(finish, plan, part)
            existing_timestamp = finish.get(field_name)
            if existing_timestamp:
                conn.commit()
                return jsonify({
                    "success": False,
                    "already_stamped": True,
                    "message": f"{PRODUCTION_FINISH_TIMESTAMP_FIELDS[field_name]} was already recorded",
                    "production_finish_id": finish_id,
                    "field": field_name,
                    "timestamp": normalize_timestamp_value(existing_timestamp),
                }), 409

            stamped, timestamp = stamp_locked_production_finish_timestamp(cursor, finish_id, field_name)
            if not timestamp:
                raise RuntimeError("Production Finish timestamp write did not return a stored value")
        conn.commit()
        return jsonify({
            "success": stamped,
            "already_stamped": not stamped,
            "production_finish_id": finish_id,
            "field": field_name,
            "timestamp": normalize_timestamp_value(timestamp),
        }), 200 if stamped else 409
    except (PartValidationError, ProductionFinishValidationError) as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception:
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
    lot_no = (request.form.get('lot_no') or '').strip()
    requested_plan_id = request.form.get('plan_id')
    if not lot_no:
        return jsonify({"success": False, "message": "ไม่พบ Lot No. สำหรับเริ่มการผลิต"})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            plan = fetch_workflow_plan(cursor, plan_id=requested_plan_id, lot_no=lot_no, for_update=True)
            if not plan:
                return jsonify({"success": False, "message": "Production plan was not found"}), 404
            plan_id = plan['id']
            lot_no = plan.get('lot_no')
            part_no = plan.get('part_no')
            part, _plan = validate_plan_part_consistency(cursor, plan_id, part_no)

            if plan.get('operator_notified_at'):
                conn.commit()
                return jsonify({
                    "success": True,
                    "created": False,
                    "already_sent": True,
                    "handoff_state": "sent",
                    "message": "This initial Operator handoff was already sent.",
                })
            if fetch_active_correction(cursor, plan_id, for_update=True):
                return jsonify({"success": False, "message": "Cannot notify Operator while a Setting Die correction is active"}), 409
            qc = current_revision_qc_pass(cursor, plan_id, for_update=True)
            if not qc:
                return jsonify({
                    "success": False,
                    "message": "Current Setting Die revision requires a current QC Pass before notifying Operator",
                    "qc_recheck_required": True,
                }), 409

            cursor.execute("SELECT id FROM production_starts WHERE plan_id = %s AND deleted_at IS NULL ORDER BY id ASC LIMIT 1", (plan_id,))
            existing = cursor.fetchone()
            if existing:
                production_start_id = existing['id']
            else:
                created_by_user_id, created_by_username = created_by_values()
                cursor.execute("""
                    INSERT INTO production_starts
                    (plan_id, part_id, lot_no, part_no, die_no, qty, time_start,
                     setting_die_revision, qc_inspection_id, created_by_user_id, created_by_username)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s)
                """, (
                    plan_id, part['id'], lot_no, part['part_no'], plan.get('die_no'), plan.get('qty'),
                    plan.get('setting_die_revision') or 1, qc['id'], created_by_user_id, created_by_username,
                ))
                production_start_id = cursor.lastrowid
            user_id, username, _role = workflow_actor()
            cursor.execute("""
                UPDATE production_plans
                SET operator_notified_at = NOW(), operator_notified_by_user_id = %s,
                    operator_notified_by_username = %s
                WHERE id = %s AND operator_notified_at IS NULL
            """, (user_id, username, plan_id))
            notification = create_notification(
                cursor,
                target_role='Operator',
                type='production_start_waiting',
                title='New job waiting for Production Start',
                message=f"Lot No. {lot_no} / Part {part['part_no']} passed QC and is ready for Production Start.",
                plan_id=plan_id,
                lot_no=lot_no,
                part_no=part['part_no'],
                source_table='production_starts',
                source_id=production_start_id,
                action_menu='production-start',
                event_key=f"qc-operator-initial:{plan_id}",
                ensure_schema=False,
            )
            record_workflow_event(
                cursor, plan_id, f"qc-operator-initial:{plan_id}",
                'operator_notified', plan.get('setting_die_revision') or 1,
            )
        conn.commit()
        return jsonify({
            "success": True,
            "created": True,
            "already_sent": False,
            "handoff_state": "sent",
            "production_start_id": production_start_id,
            "notification": notification,
        })
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
            requested_plan_id = form.get('qc-plan-id')
            plan = fetch_workflow_plan(
                cursor,
                plan_id=requested_plan_id,
                lot_no=form.get('qc-lot-no'),
                for_update=True,
            ) or {}
            plan_id = plan.get('id')
            if not plan_id:
                return jsonify({"success": False, "message": "Production plan was not found"}), 404
            if fetch_active_correction(cursor, plan_id, for_update=True):
                return jsonify({"success": False, "message": "QC is paused while a Setting Die correction is active"}), 409
            validate_qc_identity_request(
                plan,
                requested_plan_id=requested_plan_id,
                requested_lot_no=form.get('qc-lot-no'),
                requested_part_no=form.get('qc-part-no'),
            )
            part, _plan = validate_plan_part_consistency(cursor, plan_id, plan.get('part_no'))
            created_by_user_id, created_by_username = created_by_values()
            revision = int(plan.get('setting_die_revision') or 1)
            cursor.execute("""
                SELECT id, status FROM qc_inspections
                WHERE plan_id = %s AND setting_die_revision = %s
                  AND deleted_at IS NULL AND COALESCE(is_finished, 0) = 0
                ORDER BY id DESC LIMIT 1 FOR UPDATE
            """, (plan_id, revision))
            existing = cursor.fetchone()
            if existing and str(existing.get('status') or '').strip().lower() not in ('', 'waiting'):
                return jsonify({"success": False, "message": "Current revision already has an active QC inspection"}), 409
            values = (
                part['id'], plan.get('lot_no'), part['part_no'],
                empty_to_none(form.get('qc-percent')), form.get('qc-status'), form.get('qc-problem-area'),
                form.get('qc-problem-point'), image_path, form.get('qc-cause'), form.get('qc-solution'),
            )
            if existing:
                cursor.execute("""
                    UPDATE qc_inspections SET
                        part_id=%s, lot_no=%s, part_no=%s,
                        percent_result=%s, status=%s, problem_area=%s, problem_point=%s,
                        image_path=%s, cause=%s, solution=%s
                    WHERE id=%s
                """, values + (existing['id'],))
                qc_id = existing['id']
            else:
                cursor.execute("""
                    INSERT INTO qc_inspections
                    (plan_id, part_id, lot_no, part_no, time_start, time_end, percent_result,
                     status, problem_area, problem_point, image_path, cause, solution,
                     setting_die_revision, created_by_user_id, created_by_username)
                    VALUES (%s, %s, %s, %s, NULL, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (plan_id,) + values + (revision, created_by_user_id, created_by_username))
                qc_id = cursor.lastrowid
        conn.commit()
        return jsonify({"success": True, "qc_id": qc_id, "setting_die_revision": revision})
    except (PartValidationError, QCTimestampValidationError) as e:
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
            cursor.execute("""
                SELECT image_path, plan_id, setting_die_revision
                FROM qc_inspections
                WHERE id = %s AND deleted_at IS NULL
            """, (qc_id,))
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

            plan_id = existing.get('plan_id')
            plan = fetch_workflow_plan(cursor, plan_id=plan_id, for_update=True) or {}
            if not plan:
                return jsonify({"success": False, "message": "Production plan was not found"}), 404
            cursor.execute("""
                SELECT image_path, plan_id, setting_die_revision
                FROM qc_inspections
                WHERE id = %s AND deleted_at IS NULL
                FOR UPDATE
            """, (qc_id,))
            existing = cursor.fetchone()
            if not existing:
                return jsonify({"success": False, "message": "QC inspection was not found"}), 404
            if fetch_active_correction(cursor, plan_id, for_update=True):
                return jsonify({"success": False, "message": "QC is paused while a Setting Die correction is active"}), 409
            if int(existing.get('setting_die_revision') or 1) != int(plan.get('setting_die_revision') or 1):
                return jsonify({
                    "success": False,
                    "message": "This QC inspection reviewed an older Setting Die revision and is read-only history",
                    "qc_stale": True,
                }), 409
            validate_qc_identity_request(
                plan,
                requested_plan_id=form.get('qc-plan-id'),
                requested_lot_no=form.get('qc-lot-no'),
                requested_part_no=form.get('qc-part-no'),
            )
            part, _plan = validate_plan_part_consistency(cursor, plan_id, plan.get('part_no'))

            cursor.execute("""
                UPDATE qc_inspections SET
                    plan_id=%s, part_id=%s, lot_no=%s, part_no=%s,
                    percent_result=%s, status=%s, problem_area=%s, problem_point=%s,
                    image_path=%s, cause=%s, solution=%s
                WHERE id=%s
            """, (
                plan_id, part['id'], plan.get('lot_no'), part['part_no'],
                empty_to_none(form.get('qc-percent')), form.get('qc-status'), form.get('qc-problem-area'),
                form.get('qc-problem-point'), image_path, form.get('qc-cause'),
                form.get('qc-solution'), qc_id
            ))
        conn.commit()
        return jsonify({"success": True})
    except (PartValidationError, QCTimestampValidationError) as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        conn.rollback()
        return error_response()
    finally:
        conn.close()


@app.route('/api/qc/<int:qc_id>/timestamps/<field_name>/stamp', methods=['POST'])
@app.route('/api/qc/plan/<int:plan_id>/timestamps/<field_name>/stamp', methods=['POST'])
def stamp_qc_timestamp(field_name, qc_id=None, plan_id=None):
    try:
        field_name = validate_qc_timestamp_field(field_name)
    except QCTimestampValidationError as e:
        return jsonify({"success": False, "message": str(e)}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if qc_id:
                cursor.execute("""
                    SELECT id, plan_id
                    FROM qc_inspections
                    WHERE id = %s AND deleted_at IS NULL
                """, (qc_id,))
                identity = cursor.fetchone()
                if not identity:
                    return jsonify({"success": False, "message": "QC inspection was not found"}), 404
                plan_id = identity.get('plan_id')

            plan = fetch_workflow_plan(cursor, plan_id=plan_id, for_update=True)
            if not plan:
                return jsonify({"success": False, "message": "Production plan was not found"}), 404
            if fetch_active_correction(cursor, plan['id'], for_update=True):
                return jsonify({"success": False, "message": "QC is paused while a Setting Die correction is active"}), 409

            part, _plan = validate_plan_part_consistency(cursor, plan['id'], plan.get('part_no'))
            if not qc_id:
                revision = int(plan.get('setting_die_revision') or 1)
                cursor.execute("""
                    SELECT id
                    FROM qc_inspections
                    WHERE plan_id = %s AND setting_die_revision = %s
                      AND deleted_at IS NULL AND COALESCE(is_finished, 0) = 0
                    ORDER BY id DESC LIMIT 1
                    FOR UPDATE
                """, (plan['id'], revision))
                existing_qc = cursor.fetchone()
                if existing_qc:
                    qc_id = existing_qc['id']
                else:
                    created_by_user_id, created_by_username = created_by_values()
                    cursor.execute("""
                        INSERT INTO qc_inspections
                        (plan_id, part_id, lot_no, part_no, time_start, time_end,
                         percent_result, status, problem_area, problem_point, image_path,
                         cause, solution, setting_die_revision, created_by_user_id, created_by_username)
                        VALUES (%s, %s, %s, %s, NULL, NULL, NULL, %s, %s, NULL, NULL, NULL, NULL, %s, %s, %s)
                    """, (
                        plan['id'], part['id'], plan.get('lot_no'), part['part_no'],
                        'Waiting', 'none', revision, created_by_user_id, created_by_username,
                    ))
                    qc_id = cursor.lastrowid

            cursor.execute("""
                SELECT id, plan_id, part_id, lot_no, part_no, setting_die_revision,
                       time_start, time_end
                FROM qc_inspections
                WHERE id = %s AND deleted_at IS NULL
                FOR UPDATE
            """, (qc_id,))
            qc = cursor.fetchone()
            if not qc or qc.get('plan_id') != plan.get('id'):
                return jsonify({"success": False, "message": "QC workflow identity changed; reload and try again"}), 409
            if int(qc.get('setting_die_revision') or 1) != int(plan.get('setting_die_revision') or 1):
                return jsonify({
                    "success": False,
                    "message": "This QC inspection reviewed an older Setting Die revision and is read-only history",
                    "qc_stale": True,
                }), 409

            if (
                (qc.get('part_id') is not None and int(qc['part_id']) != int(part['id']))
                or str(qc.get('lot_no') or '').strip() != str(plan.get('lot_no') or '').strip()
                or normalize_part_no(qc.get('part_no')) != normalize_part_no(part['part_no'])
            ):
                return jsonify({"success": False, "message": "QC identity does not match its production plan"}), 409
            if qc.get('part_id') is None:
                cursor.execute(
                    "UPDATE qc_inspections SET part_id = %s WHERE id = %s AND part_id IS NULL",
                    (part['id'], qc_id),
                )

            existing_timestamp = qc.get(field_name)
            if existing_timestamp:
                conn.commit()
                return jsonify({
                    "success": False,
                    "already_stamped": True,
                    "message": f"{QC_TIMESTAMP_FIELDS[field_name]} was already stamped",
                    "qc_id": qc_id,
                    "field": field_name,
                    "timestamp": normalize_timestamp_value(existing_timestamp),
                }), 409

            stamped, timestamp = stamp_locked_qc_timestamp(cursor, qc_id, field_name)
            if not timestamp:
                raise RuntimeError("QC timestamp write did not return a stored value")
        conn.commit()
        return jsonify({
            "success": stamped,
            "already_stamped": not stamped,
            "qc_id": qc_id,
            "field": field_name,
            "timestamp": normalize_timestamp_value(timestamp),
        }), 200 if stamped else 409
    except PartValidationError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception:
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
            sql = """
                SELECT q.*,
                    p.setting_die_revision AS current_setting_die_revision,
                    p.operator_notified_at,
                    (q.setting_die_revision = p.setting_die_revision) AS qc_revision_current
                FROM qc_inspections q
                LEFT JOIN production_plans p ON p.id = q.plan_id
                WHERE COALESCE(q.is_finished, 0) = 0 AND q.deleted_at IS NULL
            """
            params = []
            
            if part_no:
                sql += " AND UPPER(TRIM(q.part_no)) LIKE %s"
                params.append(f"%{part_no}%")
            if lot_no:
                sql += " AND q.lot_no LIKE %s"
                params.append(f"%{lot_no}%")
                
            sql += " ORDER BY q.id DESC"
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
            cursor.execute("""
                SELECT q.*,
                    p.setting_die_revision AS current_setting_die_revision,
                    p.operator_notified_at,
                    (q.setting_die_revision = p.setting_die_revision) AS qc_revision_current
                FROM qc_inspections q
                LEFT JOIN production_plans p ON p.id = q.plan_id
                WHERE q.id = %s AND q.deleted_at IS NULL
            """, (qc_id,))
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
