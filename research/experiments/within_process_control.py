"""Single-process descriptive negative control; experiment layer only."""
import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import socket
import signal
import statistics
import subprocess
import sys
import time

ROOT = Path('/home/dcl/projects/llm-serving-benchmark-lab')
sys.path.insert(0, str(ROOT/'research/experiments'))
import run_trace_aa_control as prior
import run_environment_stability as stability
import run_diagnosis_phase2 as x
import trace_cleanup
import experiment_lifecycle as life
import experiment_schedule


def anchor():
    return dict(monotonic_s=time.monotonic(), utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                pid=os.getpid(), boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())


def host_problems(host, running=False):
    issues=[]
    if not running and host['memory']['FreePhysicalMemory'] < 3*1024*1024: issues.append('host_physical_below_3GiB')
    if host['memory']['FreeVirtualMemory'] < 6*1024*1024: issues.append('host_virtual_below_6GiB')
    if any(p['ProcessName'] in prior.COMPILERS for p in host['processes']): issues.append('host_compiler')
    return issues


def runtime_evidence():
    import importlib.metadata as md
    import vllm
    from vllm import _version
    return dict(vllm_version=vllm.__version__,vllm_path=vllm.__file__,vllm_commit=getattr(_version,'__commit_id__',None),
        packages={n:md.version(n) for n in ('torch','httpx','triton')},
        vllm_distributions=[dict(version=d.version,path=str(d._path),direct_url=d.read_text('direct_url.json'))
            for d in md.distributions() if d.metadata.get('Name','').lower()=='vllm'])


def check_runtime(current,old):
    if current['vllm_version']!=old['vllm_version'] or current['vllm_path']!=old['vllm_path']:
        raise RuntimeError('Imported vLLM version/path changed')
    # Historical short commit separately established in the previous source audit.
    if current['vllm_commit']!='gced6857af': raise RuntimeError('Imported vLLM commit changed')
    if current['packages']!=dict(torch=old['torch'],**old['packages']): raise RuntimeError('Dependency version changed')


def check_boundary(metrics):
    for name in ('num_requests_running','num_requests_waiting'):
        key='vllm:'+name
        if key not in metrics or metrics[key] != 0: raise RuntimeError('Boundary missing/nonzero '+key)


def label(i):
    return 'ABBA'[(i//4)%4]


def summarize(rows):
    rows=sorted(rows,key=lambda r:r['index'])
    if len(rows)!=8 or not all(r['success'] for r in rows): raise RuntimeError('Incomplete episode')
    return dict(tpot_ms=statistics.mean(r['tpot_ms'] for r in rows),
        front_ttft_ms=statistics.mean(r['ttft_ms'] for r in rows[:4]),
        back_ttft_ms=statistics.mean(r['ttft_ms'] for r in rows[4:]),
        all_ttft_ms=statistics.mean(r['ttft_ms'] for r in rows),
        e2e_ms=statistics.mean(r['e2e_ms'] for r in rows))


def monitor(out, owned):
    """Separate OS process, no shared client GIL; sampled detection remains incomplete."""
    boot=anchor()['boot_id']; next_host=0; parent=os.getppid(); deadline=time.monotonic()+1800
    prior.write(out/'monitor-ready.json',anchor())
    life.atomic(out/'monitor-heartbeat.json',anchor())
    while not (out/'monitor-stop').exists():
        if os.getppid()!=parent or time.monotonic()>deadline: return
        record=dict(start=anchor(),kind='linux'); issues=[]
        try:
            snapshot=prior.local_snapshot()
            issues=prior.violations(snapshot,owned)
            if snapshot['boot_id'] != boot: issues.append('boot_changed')
            record['snapshot']=snapshot
            record['cpu_stat']=Path('/proc/stat').read_text()
            record['cpu_pressure']=Path('/proc/pressure/cpu').read_text() if Path('/proc/pressure/cpu').exists() else None
            record['cpu_frequency_khz']={str(p):p.read_text().strip() for p in Path('/sys/devices/system/cpu').glob('cpu*/cpufreq/scaling_cur_freq')}
        except Exception as exc: issues.append('sampler_error:'+repr(exc))
        record.update(end=anchor(),issues=issues)
        life.atomic(out/'monitor-heartbeat.json',anchor())
        with (out/'resources.jsonl').open('a') as f: f.write(json.dumps(record)+'\n'); f.flush()
        if issues: prior.write(out/'monitor-hazard.json',record); return
        if time.monotonic() >= next_host:
            record=dict(start=anchor(),kind='windows'); issues=[]
            try: record['host']=stability.host(); issues=host_problems(record['host'],running=True)
            except Exception as exc: issues.append('host_sampler_error:'+repr(exc))
            record.update(end=anchor(),issues=issues)
            life.atomic(out/'monitor-heartbeat.json',anchor())
            with (out/'host-resources.jsonl').open('a') as f: f.write(json.dumps(record)+'\n'); f.flush()
            if issues: prior.write(out/'monitor-hazard.json',record); return
            next_host=time.monotonic()+15
        until=time.monotonic()+2
        while time.monotonic()<until and not (out/'monitor-stop').exists(): time.sleep(.1)


def healthy(out, sampler):
    if (out/'monitor-hazard.json').exists(): raise RuntimeError('Monitor hazard; raw evidence saved')
    if sampler.poll() is not None: raise RuntimeError('Independent monitor exited')
    heartbeat=json.loads((out/'monitor-heartbeat.json').read_text())
    if time.monotonic()-heartbeat['monotonic_s']>15: raise RuntimeError('Monitor heartbeat stale >15s')


async def run_episode(out, sampler, **kwargs):
    task=asyncio.create_task(x.episode_http(**kwargs))
    try:
        while not task.done():
            await asyncio.sleep(.1)
            healthy(out,sampler)
        return await task
    finally:
        if not task.done():
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
            kwargs['timing']['aborted_monotonic_s']=time.monotonic()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--execute',action='store_true'); p.add_argument('--monitor',type=Path); p.add_argument('--owned',type=int)
    args=p.parse_args()
    if args.monitor: monitor(args.monitor,args.owned); return
    out=ROOT/'research/experiments/results'/('within-process-aa-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(); print('OUT='+str(out),flush=True)
    console=(out/'runner.log').open('a',buffering=1); os.dup2(console.fileno(),1); os.dup2(console.fileno(),2)
    signal.signal(signal.SIGTERM,life.terminate_handler)
    lock=ROOT/'.benchmark.lock'; acquired=False; server=sampler=guard=None; before=None; error=None; cleanup=[]; completed=[]; children=[]
    cfg=json.loads((ROOT/'config.local.json').read_text())
    historical=ROOT/'research/experiments/results/trace-aa-control-20261015T090240Z'
    spec=json.loads((historical/'specification.json').read_text())
    argv=spec['base_command']; inputs=x.workload(20261013,512)
    assert cfg==spec['config'], 'Historical configuration changed'
    assert json.loads((historical/'fixed-payload.json').read_text())==inputs
    env={**os.environ,**spec['overrides']}
    for key in list(env):
        if key.startswith(('VLLM_TORCH_PROFILER','OTEL_','NSYS_')) or key in ('TORCH_LOGS','CUDA_LAUNCH_BLOCKING'): env.pop(key)
    core={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('lab.py','study.py','tail_report.py','README.md')}
    prior.write(out/'specification.json',dict(protocol='within-process-descriptive-v2-memory-split-user-approved-20261016',historical_source=str(historical),
        memory_policy='preflight physical>=3GiB, virtual>=6GiB; running physical recorded only, virtual>=6GiB; user explicitly approved before run',
        monitor_heartbeat_budget_s=15,watchdog_deadline_s=1800,
        config=cfg,argv=argv,overrides=spec['overrides'],core_sha256=core,payload_seed=20261013,sampling_seed=20261012,
        warmup=1,burn_in=4,measurement=64,window_episodes=4,labels='ABBA'*4,gap_s=2,lateness_budget_s=.05,
        inference='descriptive only; no stability/equivalence PASS; no P99',execute=args.execute,
        source_sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__),Path(x.__file__),Path(prior.__file__),Path(trace_cleanup.__file__),Path(stability.__file__),Path(life.__file__),Path(experiment_schedule.__file__)]}))
    prior.write(out/'fixed-payload.json',inputs)
    for f in [Path(__file__),Path(x.__file__),Path(prior.__file__),Path(trace_cleanup.__file__),Path(stability.__file__),Path(life.__file__),Path(experiment_schedule.__file__)]: (out/('source-'+f.name)).write_bytes(f.read_bytes())
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.write(fd,str(os.getpid()).encode()); os.close(fd); acquired=True
        guard=subprocess.Popen([sys.executable,str(Path(life.__file__)),str(out),str(lock),json.dumps(life.identity(os.getpid()))],start_new_session=True,stdout=console,stderr=console)
        guard_deadline=time.monotonic()+10
        while not (out/'watchdog-ready.json').exists():
            if guard.poll() is not None or time.monotonic()>guard_deadline: raise RuntimeError('Watchdog startup failed')
            time.sleep(.05)
        host=stability.host(); prior.write(out/'host-preflight.json',host)
        if host_problems(host): raise RuntimeError(';'.join(host_problems(host)))
        samples=[]
        for i in range(5):
            snap=prior.local_snapshot(); samples.append(snap); prior.write(out/'preflight.json',samples)
            if prior.violations(snap) or float(snap['gpu_csv'].split(',')[4])>5: raise RuntimeError('GPU/compiler preflight not quiet')
            if i<4: time.sleep(3)
        if len({s['boot_id'] for s in samples})!=1: raise RuntimeError('Boot changed')
        before=samples[-1]
        historic_gpu=json.loads((historical/'preflight.json').read_text())[-1]['gpu_csv'].split(',')
        current_gpu=before['gpu_csv'].split(',')
        if any(historic_gpu[i].strip()!=current_gpu[i].strip() for i in (0,1,3)):
            raise RuntimeError('Historical GPU identity/capacity changed')
        if not args.execute: return
        runtime=runtime_evidence()
        old=json.loads((historical/'runtime.json').read_text())
        prior.write(out/'runtime.json',dict(**runtime,python=sys.version,kernel=prior.capture(['uname','-a']),gpu=prior.capture(['nvidia-smi']),git_head=prior.capture(['git','-C',str(ROOT),'rev-parse','HEAD'])))
        check_runtime(runtime,old)
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',8019))==0: raise RuntimeError('Endpoint occupied')
        with (out/'server.log').open('w') as f: server=subprocess.Popen(argv,env=env,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        children.append(life.identity(server.pid)); life.atomic(out/'children.json',children)
        prior.write(out/'ownership.json',dict(server_pid=server.pid,pgid=server.pid,client_pid=os.getpid()))
        sampler=subprocess.Popen([sys.executable,str(Path(__file__)),'--monitor',str(out),'--owned',str(server.pid)],stdout=console,stderr=console,start_new_session=True)
        children.append(life.identity(sampler.pid)); life.atomic(out/'children.json',children)
        deadline=time.monotonic()+20
        while not (out/'monitor-heartbeat.json').exists():
            if sampler.poll() is not None or time.monotonic()>deadline: raise RuntimeError('Monitor startup failed')
            time.sleep(.1)
        x.wait_until_ready(server,cfg['engines']['vllm']['base_url'],'vllm',out/'server.log')
        previous_end=None
        for number in range(69):
            healthy(out,sampler)
            if server.poll() is not None: raise RuntimeError('Server exited')
            target=previous_end+2 if previous_end is not None else None
            if target:
                if time.monotonic()>target: raise RuntimeError('Boundary work exceeded 2s')
                time.sleep(max(0,target-time.monotonic()))
                experiment_schedule.validate_wakeup(out,number,target,time.monotonic(),prior.write,cleanup)
            phase='warmup' if number==0 else 'burn-in' if number<5 else 'measurement'
            index=number-5; clock={}; partial=out/f'episode-{number:03d}-partial.jsonl'
            record=dict(number=number,phase=phase,label=label(index) if number>=5 else None,
                window=index//4 if number>=5 else None,start=anchor(),target_monotonic_s=target)
            try:
                rows,elapsed=asyncio.run(run_episode(out,sampler,base=cfg['engines']['vllm']['base_url'],model=cfg['served_model_name'],
                    inputs=inputs,output=128,cap=8,tag=f'control-e{number:03d}',trace=False,rate=4,timing=clock,partial_path=partial))
                previous_end=clock['end_monotonic_s']
                record.update(clock=clock,requests=rows,duration_s=elapsed)
                record['summary']=summarize(rows)
                if target and clock['start_monotonic_s']-target>.05: raise RuntimeError('Actual episode start lateness >50ms')
                if any(r['native_metrics'] is not None for r in rows): raise RuntimeError('Unexpected trace')
                boundary_start=anchor(); raw=x.prom(cfg['engines']['vllm']['base_url']); boundary_end=anchor()
                (out/f'episode-{number:03d}-metrics.txt').write_text(raw)
                metrics=x.parse_prom(raw); record['boundary']=dict(start=boundary_start,end=boundary_end,metrics=metrics)
                check_boundary(metrics)
                healthy(out,sampler)
                completed.append(record['summary']|dict(number=number,phase=phase,label=record['label'],window=record['window']))
            except BaseException as exc: record['error']=repr(exc); raise
            finally:
                record['end']=anchor(); record['clock']=clock
                try: prior.write(out/f'episode-{number:03d}.json',record)
                except Exception as exc: cleanup.append(dict(phase='episode_write',error=repr(exc)))
            prior.write(out/'progress.json',completed)
    except BaseException as exc: error=repr(exc); print('STOP',error,flush=True)
    finally:
        try: (out/'monitor-stop').touch()
        except Exception as exc: cleanup.append(dict(phase='monitor_stop_marker',error=repr(exc)))
        if sampler:
            try:
                life.stop_child(sampler)
            except Exception as exc: cleanup.append(dict(phase='monitor_cleanup',error=repr(exc)))
        if before is not None and server is not None: cleanup+=trace_cleanup.cleanup_owned(server,before,out,prior.local_snapshot,prior.write,prior.violations)
        try:
            if acquired and lock.exists() and lock.read_text()==str(os.getpid()): lock.unlink()
        except Exception as exc: cleanup.append(dict(phase='lock_cleanup',error=repr(exc)))
        if guard:
            try:
                if not cleanup: (out/'watchdog-done').touch()
                if not cleanup: life.stop_child(guard)
            except Exception as exc: cleanup.append(dict(phase='guard_cleanup',error=repr(exc)))
        unchanged=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in core.items())
        prior.write(out/'outcome.json',dict(status='PILOT_COMPLETE' if len(completed)==69 and not error and not cleanup and unchanged else 'HOLD',
            error=error,primary_error=error,cleanup_errors=cleanup,completed_episodes=len(completed),measurement_episodes=sum(r['phase']=='measurement' for r in completed),
            core_unchanged=unchanged,stability_pass=None,trace_overhead_pass=None,phase2_expansion_executed=False))
        print('END',len(completed),error,flush=True)


if __name__=='__main__': main()
