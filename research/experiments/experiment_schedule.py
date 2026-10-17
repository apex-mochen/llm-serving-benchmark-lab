"""Persist a scheduling gate failure without changing its fixed 50ms budget."""
def validate_wakeup(out,number,target,checked,writer,errors):
    delay=checked-target
    if delay<=.05: return
    try:
        writer(out/'schedule-abort.json',dict(episode_number=number,target_monotonic_s=target,
            check_monotonic_s=checked,lateness_ms=delay*1000,budget_ms=50,
            note='Post-sleep check, not exact kernel wakeup or request send time'))
    except Exception as exc: errors.append(dict(phase='schedule_abort_write',error=repr(exc)))
    raise RuntimeError('Episode start lateness >50ms')
