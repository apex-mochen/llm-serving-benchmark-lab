"""CPU-only environment replay and real dummy-process signal tests. No GPU service."""
import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import within_process_control as w
import experiment_lifecycle as life


def running(pid):
    try:
        s=Path(f'/proc/{pid}/stat').read_text()
        return s[s.rfind(')')+2:].split()[0]!='Z'
    except FileNotFoundError: return False


class Remediation(unittest.TestCase):
    def test_real_venv_same_source_version(self):
        old=json.loads((w.ROOT/'research/experiments/results/trace-aa-control-20261015T090240Z/runtime.json').read_text())
        current=w.runtime_evidence(); w.check_runtime(current,old)
        self.assertGreaterEqual(len(current['vllm_distributions']),2)
    def test_runtime_rejects_commit_change(self):
        old=dict(vllm_version='v',vllm_path='p',torch='t',packages={})
        with self.assertRaises(RuntimeError): w.check_runtime(dict(vllm_version='v',vllm_path='p',vllm_commit='other',packages={}),old)
    def test_historical_host_replay(self):
        answer=[]
        for name in ('trace-revalidation-v3-20261015T083228Z','trace-aa-control-20261015T090240Z'):
            p=w.ROOT/'research/experiments/results'/name/'host-resources.jsonl'
            rows=[json.loads(line) for line in p.read_text().splitlines()]
            self.assertTrue(rows)
            self.assertTrue(all('host_physical_below_3GiB' in w.host_problems(r) for r in rows))
            self.assertTrue(all('host_physical_below_3GiB' not in w.host_problems(r,running=True) for r in rows))
            self.assertTrue(all('host_virtual_below_6GiB' not in w.host_problems(r,running=True) for r in rows))
            answer.append(dict(run=name,count=len(rows),physical_min_kib=min(r['memory']['FreePhysicalMemory'] for r in rows),physical_max_kib=max(r['memory']['FreePhysicalMemory'] for r in rows)))
        print('HISTORY_REPLAY',json.dumps(answer),flush=True)
    def test_runtime_virtual_gate_still_applies(self):
        self.assertIn('host_virtual_below_6GiB',w.host_problems(dict(memory=dict(FreePhysicalMemory=1,FreeVirtualMemory=1),processes=[]),running=True))
    def test_real_labeled_prom_boundary(self):
        text='vllm:num_requests_running{model_name="fixture"} 0\nvllm:num_requests_waiting{model_name="fixture"} 0\n'
        w.check_boundary(w.x.parse_prom(text))
    def test_hazard_cancels_active_episode(self):
        async def trial():
            ended=[]
            async def fake(**kwargs):
                try: await asyncio.sleep(10)
                finally: ended.append(True)
            with tempfile.TemporaryDirectory() as d,patch.object(w.x,'episode_http',fake):
                out=Path(d); (out/'monitor-hazard.json').write_text('{}')
                with self.assertRaises(RuntimeError): await w.run_episode(out,None,timing={})
            self.assertTrue(ended)
        asyncio.run(trial())
    def test_stop_child_kill_escalation(self):
        from unittest.mock import Mock
        child=Mock(); child.wait.side_effect=[subprocess.TimeoutExpired('dummy',1),subprocess.TimeoutExpired('dummy',1),0]
        life.stop_child(child); child.terminate.assert_called_once(); child.kill.assert_called_once()
    def test_stale_monitor_detected(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);life.atomic(out/'monitor-heartbeat.json',dict(monotonic_s=time.monotonic()-16))
            sampler=Mock();sampler.poll.return_value=None
            with self.assertRaisesRegex(RuntimeError,'heartbeat stale'): w.healthy(out,sampler)
    def check_signal(self,sig):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); lock=out/'lock'
            parent=subprocess.Popen([sys.executable,str(Path(__file__)),'--fixture',str(out)],start_new_session=True)
            manifest=None
            try:
                deadline=time.monotonic()+10
                while not (out/'fixture-ready.json').exists():
                    if parent.poll() is not None or time.monotonic()>deadline: self.fail('Fixture did not start')
                    time.sleep(.05)
                manifest=json.loads((out/'fixture-ready.json').read_text())
                parent.send_signal(sig); parent.wait(timeout=15)
                deadline=time.monotonic()+20
                while time.monotonic()<deadline and (lock.exists() or any(running(p) for p in manifest['children'])): time.sleep(.1)
                self.assertFalse(lock.exists())
                self.assertTrue(all(not running(p) for p in manifest['children']))
                self.assertTrue((out/('watchdog-recovery.json' if sig==signal.SIGKILL else 'parent-finally')).exists())
            finally:
                if parent.poll() is None: parent.kill(); parent.wait()
                if manifest:
                    for pid in manifest['children']:
                        if running(pid):
                            try: os.killpg(pid,signal.SIGKILL)
                            except ProcessLookupError: pass
    def test_sigterm_real_dummy_cleanup(self): self.check_signal(signal.SIGTERM)
    def test_sigkill_registered_groups_recovered(self): self.check_signal(signal.SIGKILL)


def fixture(out):
    signal.signal(signal.SIGTERM,life.terminate_handler)
    lock=out/'lock';lock.write_text(str(os.getpid())); children=[]
    guard=subprocess.Popen([sys.executable,str(Path(life.__file__)),str(out),str(lock),json.dumps(life.identity(os.getpid()))],start_new_session=True)
    try:
        for _ in range(2):
            p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)'],start_new_session=True)
            children.append(p);life.atomic(out/'children.json',[life.identity(p.pid) for p in children])
        while not (out/'watchdog-ready.json').exists(): time.sleep(.02)
        life.atomic(out/'fixture-ready.json',dict(children=[p.pid for p in children]))
        while True: time.sleep(.1)
    finally:
        for p in children:
            life.stop_group(life.identity(p.pid));p.wait(timeout=5)
        if lock.exists(): lock.unlink()
        (out/'parent-finally').touch();(out/'watchdog-done').touch();guard.wait(timeout=5)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--fixture': fixture(Path(sys.argv[2]))
    else: unittest.main(verbosity=2)
