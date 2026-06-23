ALL_PERMISSIONS = (
    'dashboard.view',
    'users.manage',
    'production.view',
    'production.manage',
    'setting_die.view',
    'setting_die.manage',
    'qc.view',
    'qc.manage',
    'production_start.view',
    'production_start.manage',
    'production_finish.view',
    'production_finish.manage',
)

ROLE_PERMISSIONS = {
    'Admin': ALL_PERMISSIONS,
    'Sup': (
        'dashboard.view',
        'production.view',
        'production.manage',
        'setting_die.view',
        'setting_die.manage',
        'qc.view',
        'production_start.view',
        'production_finish.view',
    ),
    'Manager': (
        'dashboard.view',
        'production.view',
        'setting_die.view',
        'qc.view',
        'production_start.view',
        'production_finish.view',
    ),
    'PC': (
        'dashboard.view',
        'production.view',
        'production.manage',
        'setting_die.view',
        'qc.view',
        'production_start.view',
        'production_finish.view',
    ),
    'Technician': (
        'dashboard.view',
        'production.view',
        'setting_die.view',
        'setting_die.manage',
        'qc.view',
        'production_start.view',
        'production_finish.view',
    ),
    'QC Line': (
        'dashboard.view',
        'production.view',
        'setting_die.view',
        'qc.view',
        'qc.manage',
        'production_start.view',
        'production_finish.view',
    ),
    'Operator': (
        'dashboard.view',
        'production.view',
        'production_start.view',
        'production_start.manage',
        'production_finish.view',
        'production_finish.manage',
    ),
}

VALID_ROLES = tuple(ROLE_PERMISSIONS.keys())

ROLE_ALIASES = {
    'admin': 'Admin',
    'sup': 'Sup',
    'manager': 'Manager',
    'pc': 'PC',
    'technician': 'Technician',
    'qc line': 'QC Line',
    'qcline': 'QC Line',
    'qc_line': 'QC Line',
    'operator': 'Operator',
}


def normalize_user_role(role):
    normalized = ' '.join(str(role or '').strip().split()).lower()
    return ROLE_ALIASES.get(normalized, '')


def permissions_for_role(role):
    role = normalize_user_role(role)
    role_permissions = set(ROLE_PERMISSIONS.get(role, ()))
    return [permission for permission in ALL_PERMISSIONS if permission in role_permissions]


def has_permission(role, permission):
    return permission in ROLE_PERMISSIONS.get(normalize_user_role(role), ())


def has_any_permission(role, permissions):
    return any(has_permission(role, permission) for permission in permissions or ())
