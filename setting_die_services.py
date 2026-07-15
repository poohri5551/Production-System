def setting_die_record_complete(record):
    """A process is saved enough to proceed only after required start time exists."""
    return bool(record and record.get('id') and record.get('time_start'))


def setting_die_process_eligible(process_die_no, previous_record=None):
    try:
        process_no = int(process_die_no)
    except (TypeError, ValueError):
        return False
    if process_no < 1:
        return False
    return process_no == 1 or setting_die_record_complete(previous_record)
