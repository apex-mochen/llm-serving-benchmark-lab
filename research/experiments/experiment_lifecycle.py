"""Linux experiment-only watchdog: terminate registered owned groups, never foreign ones."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def identity(pid):
    try:
        p=Path('/proc')/str(pid)
        text=(p/'stat').read_text(); fields=text[text.rfind(')')+2:].split()
        return dict(pid=pid,start_ticks=fields[19],uid=p.stat().st_uid,
                    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    except (FileNotFoundError,ProcessLookupError): return None


def matches(item):
    return item is not None and identity(item['pid'])==item


def atomic(path,value):
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value,indent=2)+'\n'); tmp.replace(path)


def stop_group(item):
    if not matches(item): return
    pid=item['pid']
    if item['uid']!=os.getuid() or os.getpgid(pid)!=pid: raise RuntimeError('Refuse unowned/nonleader group')
    try: os.killpg(pid,signal.SIGTERM)
    except ProcessLookupError: return
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        try: os.killpg(pid,0)
        except ProcessLookupError: return
        time.sleep(.1)
    # Same validated group may retain workers even when leader has exited.
    try: os.killpg(pid,signal.SIGKILL)
    except ProcessLookupError: pass


def watchdog(out,lock,parent,limit=1800):
    started=time.monotonic()
    atomic(out/'watchdog-ready.json',dict(pid=os.getpid(),parent=parent,limit_s=limit))
    while True:
        if (out/'watchdog-done').exists(): return
        if not matches(parent) or time.monotonic()-started>limit: break
        time.sleep(.2)
    errors=[]
    if (out/'children.json').exists():
        children=json.loads((out/'children.json').read_text())
        for child in reversed(children):
            try: stop_group(child)
            except Exception as exc: errors.append(repr(exc))
    # Delete only the unchanged lock belonging to this exact registered parent.
    if lock.exists() and lock.read_text()==str(parent['pid']): lock.unlink()
    atomic(out/'watchdog-recovery.json',dict(parent=parent,errors=errors,reason='parent_disappeared_or_deadline'))


def terminate_handler(signum,frame):
    raise SystemExit('SIGTERM received; owned cleanup required')


def stop_child(proc):
    try: proc.wait(timeout=40)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=10)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);p.add_argument('lock',type=Path);p.add_argument('parent')
    a=p.parse_args(); watchdog(a.out,a.lock,json.loads(a.parent))
