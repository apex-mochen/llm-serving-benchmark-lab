"""Identical trace-free startup/workload/shutdown cycles; resource telemetry only."""
import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
import run_diagnosis_phase2 as existing


def durable(path,value):
    with path.open('w') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())


def host():
    value=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',
        r'D:\myknowledge\research\capture_host_stability.ps1'],capture_output=True,timeout=30)
    if value.returncode:raise RuntimeError(value.stderr.decode('utf-8',errors='replace'))
    return json.loads(value.stdout.decode('utf-8-sig'))


def snap(include_host=True):
    result=dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),monotonic_s=time.monotonic(),
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),gpu=existing.gpu(0),
        linux_memory=Path('/proc/meminfo').read_text(),
        linux_processes=subprocess.check_output(['ps','-eo','pid,ppid,rss,pcpu,comm'],text=True),
        compute_apps=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True))
    if include_host:result['host']=host()
    return result


def evaluate(before,after,success,oom,released):
    gpu_delta=after['gpu']['memory.used']-before['gpu']['memory.used']
    commit_loss=(before['host']['memory']['FreeVirtualMemory']-after['host']['memory']['FreeVirtualMemory'])/1024
    return dict(workload_complete=success,oom_detected=oom,owned_resources_released=released,
        gpu_memory_delta_mib=gpu_delta,host_free_virtual_loss_mib=commit_loss,
        pass_cycle=bool(success and not oom and released and gpu_delta<=256 and commit_loss<=512))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--probe',action='store_true');args=parser.parse_args()
    if args.probe:print(json.dumps(snap()));return 0
    cfg=json.loads((ROOT/'config.local.json').read_text())
    out=ROOT/'research/experiments/results'/('environment-stability-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir()
    core={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('lab.py','study.py','tail_report.py','README.md')}
    inputs=existing.workload(20261013,512)
    command=cfg['engines']['vllm']['server_command']+['--host','127.0.0.1','--max-num-seqs','4',
        '--max-num-batched-tokens','2048','--enable-chunked-prefill','--disable-log-stats','--uvicorn-log-level','warning']
    forbidden=('--enable-per-request-metrics','--enable-request-id-headers','--enable-prompt-tokens-details',
               '--collect-detailed-traces','--otlp-traces-endpoint','--enable-layerwise-nvtx-tracing')
    assert not any(x in command for x in forbidden)
    env={**os.environ,**cfg['engines']['vllm'].get('server_environment',{})}
    removed={key:env.pop(key) for key in list(env) if key.startswith(('VLLM_TORCH_PROFILER','OTEL_','NSYS_')) or key in ('TORCH_LOGS','CUDA_LAUNCH_BLOCKING')}
    env.update(VLLM_LOGGING_LEVEL='INFO',VLLM_SERVER_DEV_MODE='0',TORCH_CPP_LOG_LEVEL='WARNING')
    durable(out/'specification.json',dict(config=cfg,command=command,environment_overrides={k:env[k] for k in
        ('VLLM_LOGGING_LEVEL','VLLM_SERVER_DEV_MODE','TORCH_CPP_LOG_LEVEL')},removed_profiling_variable_names=list(removed),
        cycles=3,requests_per_cycle=64,episode_requests=8,arrival_rate=4,cap=8,input_tokens=512,output_tokens=128,
        payload_seed=20261013,payload_sha256=hashlib.sha256(json.dumps(inputs).encode()).hexdigest(),
        core_sha256=core,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        gates=dict(no_oom=True,complete_requests=64,gpu_delta_mib_max=256,host_virtual_loss_mib_max=512,
                   shutdown_window_s=30,consecutive_post_samples=3,independent_cycles=3),
        scope='Resource observation only; no external profiler/debug/request trace. Built-in engine capacity profiling remains unchanged.'))
    durable(out/'fixed-payload.json',inputs)
    lock=ROOT/'.benchmark.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,str(os.getpid()).encode());os.close(fd)
    outcomes=[];initial=None;error=None
    try:
        initial=snap();durable(out/'initial-state.json',initial)
        assert not initial['compute_apps'].strip(),'Pre-existing compute service protected'
        for cycle in range(3):
            directory=out/f'cycle-{cycle}';directory.mkdir()
            before=snap();durable(directory/'before.json',before)
            assert before['boot_id']==initial['boot_id'],'Reboot detected; no cross-boot pooling'
            with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',8019))!=0,'Occupied endpoint protected'
            proc=None;complete=False;failure=None;stop=threading.Event();samples=[];owned_pids=set()
            def sample():
                i=0
                while not stop.is_set():
                    try:
                        v=snap(include_host=i%5==0);samples.append(v)
                        with (directory/'during.jsonl').open('a') as f:
                            f.write(json.dumps(v)+'\n');f.flush();os.fsync(f.fileno())
                    except Exception as exc:
                        with (directory/'sampler-errors.log').open('a') as f:f.write(repr(exc)+'\n')
                    i+=1;stop.wait(2)
            thread=threading.Thread(target=sample);thread.start()
            try:
                with (directory/'server.log').open('w') as log:
                    proc=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                    durable(directory/'ownership.json',dict(runner_pid=os.getpid(),server_pid=proc.pid,server_group=proc.pid))
                    print(f'CYCLE {cycle}: owned server {proc.pid}',flush=True)
                    existing.wait_until_ready(proc,'http://127.0.0.1:8019','vllm',directory/'server.log')
                    warm,duration=asyncio.run(existing.episode_http('http://127.0.0.1:8019',cfg['served_model_name'],inputs,128,8,
                        f'{out.name}-c{cycle}-warm',False,rate=4.))
                    durable(directory/'warmup.json',dict(requests=warm,duration_s=duration));assert all(r['success'] for r in warm)
                    for episode in range(8):
                        rows,duration=asyncio.run(existing.episode_http('http://127.0.0.1:8019',cfg['served_model_name'],inputs,128,8,
                            f'{out.name}-c{cycle}-e{episode}',False,rate=4.))
                        durable(directory/f'episode-{episode}.json',dict(requests=rows,duration_s=duration))
                        assert len(rows)==8 and all(r['success'] and r['native_metrics'] is None for r in rows)
                        assert not any('DEBUG' in (directory/'server.log').read_text(errors='replace') for _ in [0]),'Debug output present'
                    complete=True
            except BaseException as exc:failure=repr(exc);print(f'CYCLE {cycle} failed: {failure}',flush=True)
            finally:
                if proc is not None:
                    owned_pids.add(proc.pid)
                    if proc.poll() is None:
                        os.killpg(proc.pid,signal.SIGTERM)
                        try:proc.wait(timeout=20)
                        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
                stop.set();thread.join()
            # Observe release without resetting the GPU/OS or clearing caches.
            deadline=time.monotonic()+30;release=[];after=None;consecutive=0
            while time.monotonic()<deadline:
                after=snap();release.append(after);durable(directory/'release-observations.json',release)
                alive=False
                if proc is not None:
                    raw=subprocess.check_output(['ps','-eo','pid,pgid,comm'],text=True)
                    members=[line for line in raw.splitlines()[1:] if line.split()[1]==str(proc.pid)]
                    alive=bool(members)
                    durable(directory/'process-group-after.json',members)
                with socket.socket() as sock:occupied=sock.connect_ex(('127.0.0.1',8019))==0
                released=not alive and not occupied
                state_ok=bool(released and after['gpu']['memory.used']-before['gpu']['memory.used']<=256 and
                    (before['host']['memory']['FreeVirtualMemory']-after['host']['memory']['FreeVirtualMemory'])/1024<=512)
                consecutive=consecutive+1 if state_ok else 0
                if consecutive>=3:break
                time.sleep(2)
            assert after is not None;durable(directory/'after.json',after)
            logtext=(directory/'server.log').read_text(errors='replace')
            oom=bool(re.search(r'OutOfMemoryError|CUDA out of memory|memory allocation failed with OOM|Cannot allocate memory',logtext))
            verdict=evaluate(before,after,complete,oom,released)
            verdict['release_stable_samples']=consecutive
            verdict['pass_cycle']=verdict['pass_cycle'] and consecutive>=3
            verdict.update(cycle=cycle,error=failure,allocation_log_lines=[line for line in logtext.splitlines()
                if any(word in line.lower() for word in ('kv cache memory','gpu kv cache','model loading took','out of memory','allocation failed'))],
                during_sample_count=len(samples),gpu_peak_mib=max((s['gpu']['memory.used'] for s in samples),default=None))
            outcomes.append(verdict);durable(directory/'result.json',verdict);durable(out/'progress.json',outcomes)
            print(json.dumps(verdict),flush=True)
    except BaseException as exc:error=repr(exc);print(error,flush=True)
    finally:
        if lock.exists() and lock.read_text()==str(os.getpid()):lock.unlink()
        result=dict(status='PASS' if len(outcomes)==3 and all(r['pass_cycle'] for r in outcomes) and error is None else 'HOLD',
                    cycles=outcomes,error=error,trace_overhead_resumed=False,core_unchanged=all(
                        hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h for name,h in core.items()))
        durable(out/'outcome.json',result)
        print(f'OUT={out}; STATUS={result["status"]}',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
