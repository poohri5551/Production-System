export const ALL_PERMISSIONS = [
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
]

export const ROLE_PERMISSIONS = {
  Admin: ALL_PERMISSIONS,
  Sup: [
    'dashboard.view',
    'production.view',
    'production.manage',
    'setting_die.view',
    'setting_die.manage',
    'qc.view',
    'production_start.view',
    'production_finish.view',
  ],
  Manager: [
    'dashboard.view',
    'production.view',
    'setting_die.view',
    'qc.view',
    'production_start.view',
    'production_finish.view',
  ],
  PC: [
    'dashboard.view',
    'production.view',
    'production.manage',
    'setting_die.view',
    'qc.view',
    'production_start.view',
    'production_finish.view',
  ],
  Technician: [
    'dashboard.view',
    'production.view',
    'setting_die.view',
    'setting_die.manage',
    'qc.view',
    'production_start.view',
    'production_finish.view',
  ],
  'QC Line': [
    'dashboard.view',
    'production.view',
    'setting_die.view',
    'qc.view',
    'qc.manage',
    'production_start.view',
    'production_finish.view',
  ],
  Operator: [
    'dashboard.view',
    'production.view',
    'production_start.view',
    'production_start.manage',
    'production_finish.view',
    'production_finish.manage',
  ],
}

export const VALID_ROLES = Object.keys(ROLE_PERMISSIONS)

export function getAvailableRoles() {
  return [...VALID_ROLES]
}

export function can(permissions, permission) {
  return Array.isArray(permissions) && permissions.includes(permission)
}

export function canAny(permissions, requiredPermissions) {
  return Array.isArray(requiredPermissions) && requiredPermissions.some((permission) => can(permissions, permission))
}

export function permissionsForRole(role) {
  return ROLE_PERMISSIONS[role] ? [...ROLE_PERMISSIONS[role]] : []
}
