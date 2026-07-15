APPROVER_ROLES = frozenset({'Admin', 'Sup'})


def normalize_qc_status(value):
    return ' '.join(str(value or '').strip().lower().split())


def qc_has_started(qc):
    if not qc:
        return False
    return bool(
        qc.get('time_start')
        or qc.get('time_end')
        or qc.get('percent_result') not in (None, '')
        or normalize_qc_status(qc.get('status')) not in ('', 'waiting')
    )


def qc_passed(qc):
    return normalize_qc_status((qc or {}).get('status')) in {'pass', 'passed'}


def downstream_stage(qc=None, production_start=None, production_finish=None):
    if production_finish:
        return 'production_finish'
    if production_start:
        return 'production_start'
    if qc_passed(qc):
        return 'qc_passed'
    if qc_has_started(qc):
        return 'qc_in_progress'
    return 'qc_not_started'


def correction_requires_approval(stage):
    return stage in {'qc_passed', 'production_start', 'production_finish'}


def can_approve_correction(role):
    return role in APPROVER_ROLES


def qc_revision_current(qc, current_revision):
    if not qc:
        return False
    try:
        return int(qc.get('setting_die_revision') or 1) == int(current_revision or 1)
    except (TypeError, ValueError):
        return False
