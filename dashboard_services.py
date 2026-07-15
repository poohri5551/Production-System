def dashboard_bucket_for_item(item):
    """Return exactly one non-Total Dashboard bucket from workflow stage."""
    current_step = str(item.get('current_step') or '').strip().lower()
    if item.get('is_finished') or current_step == 'completed':
        return 'completed'
    if current_step == 'qc':
        return 'qc'
    if current_step == 'not started':
        return 'waiting'
    return 'in_progress'


def dashboard_summary(items):
    summary = {
        'total': len(items),
        'waiting': 0,
        'in_progress': 0,
        'qc': 0,
        'completed': 0,
    }
    for item in items:
        summary[item['dashboard_bucket']] += 1
    return summary


def dashboard_setting_die_progress(process_die_count, completed_process_numbers):
    try:
        total = max(int(process_die_count or 1), 1)
    except (TypeError, ValueError):
        total = 1
    completed = min(len(set(completed_process_numbers or [])), total)
    return {'completed': completed, 'total': total}
