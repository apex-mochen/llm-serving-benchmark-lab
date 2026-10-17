"""Best-effort owned-server cleanup that never replaces a primary exception."""
import os
import signal
import subprocess
import time


def cleanup_owned(proc, before, directory, snapshot, writer, violations, sleep=time.sleep):
    errors = []

    def attempt(phase, action):
        try:
            return action()
        except Exception as exc:
            errors.append(dict(phase=phase, error=repr(exc)))
            return None

    def stop():
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=10)

    attempt('terminate_owned_group', stop)
    attempt('release_delay', lambda: sleep(2))
    after = attempt('snapshot_after', snapshot)
    if after is None:
        return errors
    attempt('write_after', lambda: writer(directory/'after.json', after))

    def check_processes():
        findings = violations(after)
        if findings:
            errors.append(dict(phase='post_run_activity', findings=findings,
                               note='May be external activity, not proof of owned-resource leakage'))
        if proc is not None and any(len(parts)>2 and parts[2]==str(proc.pid)
                                    for parts in (line.split() for line in after['processes'].splitlines()[1:])):
            errors.append(dict(phase='owned_process_group_still_alive', pgid=proc.pid))

    attempt('process_release_check', check_processes)
    if proc is not None:
        def check_memory():
            delta = float(after['gpu_csv'].split(',')[2])-float(before['gpu_csv'].split(',')[2])
            if delta > 256:
                errors.append(dict(phase='global_gpu_memory_delta', delta_mib=delta,
                                   note='Global GPU memory includes unrelated applications'))
        attempt('gpu_release_check', check_memory)
    return errors
