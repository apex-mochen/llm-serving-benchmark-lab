"""CPU timing only: real AsyncClient initialization, synthetic in-memory SSE, no model/network."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import datetime as dt
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time
from unittest.mock import patch
import within_process_control as w
import experiment_lifecycle as life


ORDER=['sleep','client','client','sleep']*8


@asynccontextmanager
async def synthetic_stream(client,method,url,**kwargs):
    """Patch only stream(): preserve actual AsyncClient/TLS initialization."""
    payload=kwargs['json']
    chunks=[dict(id='cpu-synthetic',choices=[dict(text='x')]),
            dict(id='cpu-synthetic',choices=[dict(text='y')]),
            dict(usage=dict(prompt_tokens=len(payload['prompt']),completion_tokens=payload['max_tokens']))]
    text=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n'
    yield w.x.httpx.Response(200,text=text,request=w.x.httpx.Request(method,url))


def derived(arm,target,checked,clock,rows):
    result=dict(wakeup_check_lateness_ms=(checked-target)*1000,
        episode_start_lateness_ms=(clock['start_monotonic_s']-target)*1000 if clock else None,
        first_request_send_lateness_ms=(clock['start_monotonic_s']+min(r['sent_s'] for r in rows)-target)*1000 if rows else None,
        client_initialization_after_check_ms=(clock['start_monotonic_s']-checked)*1000 if clock else None)
    result['wakeup_over_50ms']=result['wakeup_check_lateness_ms']>50
    result['episode_start_over_50ms']=result['episode_start_lateness_ms']>50 if clock else None
    return result


def describe(values):
    return dict(n=len(values),min=min(values),median=statistics.median(values),max=max(values),mean=statistics.mean(values))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true',required=True);parser.parse_args()
    root=w.ROOT
    out=root/'research/experiments/results'/('cpu-timing-probe-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir();print('OUT='+str(out),flush=True)
    console=(out/'runner.log').open('a',buffering=1);os.dup2(console.fileno(),1);os.dup2(console.fileno(),2)
    signal.signal(signal.SIGTERM,life.terminate_handler)
    lock=root/'.benchmark.lock';acquired=False;sampler=None;error=None;cleanup=[];records=[]
    source=[Path(__file__),Path(w.__file__),Path(w.x.__file__),Path(life.__file__)]
    core={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('lab.py','study.py','tail_report.py','README.md')}
    inputs=w.x.workload(20261013,512)
    w.prior.write(out/'specification.json',dict(level='CPU timing + synthetic in-memory response; NOT inference benchmark',
        order=ORDER,measurement_trials=32,arm_trials=16,warmup_client_episodes=1,gap_s=2,budget_ms=50,
        episode_requests=8,rate=4,cap=8,payload_seed=20261013,sampling_seed=20261012,
        payload_sha256=hashlib.sha256(json.dumps(inputs).encode()).hexdigest(),
        primary='sleep post-check lateness and client episode start lateness; no p-values/no P99',
        rule='Continue through timing budget failures for fixed 32 trials; stop for monitor error/contamination; no optional extension',
        decision='Any >50ms budget failure: no GPU rerun; no failures: limited CPU feasibility only, not proof of GPU reliability',
        synthetic_response='two text chunks plus usage metadata; values are fixture data, not generated tokens',
        core_sha256=core,source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source},
        server_command=None,server_started=False,gpu_compute=False,torch_cuda_triton='not used'))
    for p in source:(out/('source-'+p.name)).write_bytes(p.read_bytes())
    w.prior.write(out/'runtime.json',dict(python=sys.version,executable=sys.executable,httpx=md.version('httpx'),
        git_head=w.prior.capture(['git','-C',str(root),'rev-parse','HEAD']),kernel=w.prior.capture(['uname','-a']),anchor=w.anchor()))
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,str(os.getpid()).encode());os.close(fd);acquired=True
        sampler=subprocess.Popen([sys.executable,str(Path(w.__file__)),'--monitor',str(out),'--owned','-1'],start_new_session=True,stdout=console,stderr=console)
        w.prior.write(out/'ownership.json',dict(client_pid=os.getpid(),monitor_pid=sampler.pid,monitor_identity=life.identity(sampler.pid)))
        deadline=time.monotonic()+15
        while not (out/'monitor-heartbeat.json').exists():
            if sampler.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Monitor startup failed')
            time.sleep(.05)
        async def episode(clock):
            return await w.run_episode(out,sampler,base='http://cpu-fixture.invalid',model='cpu-fixture',inputs=inputs,
                output=128,cap=8,tag='cpu-probe',trace=False,rate=4,timing=clock)
        with patch.object(w.x.httpx.AsyncClient,'stream',synthetic_stream):
            clock={};rows,duration=asyncio.run(episode(clock))
            w.prior.write(out/'warmup.json',dict(clock=clock,duration_s=duration,requests=len(rows),all_success=all(r['success'] for r in rows),phase='excluded predeclared warmup'))
            for i,arm in enumerate(ORDER):
                w.healthy(out,sampler)
                target=time.monotonic()+2
                time.sleep(max(0,target-time.monotonic()));checked=time.monotonic()
                clock={};rows=[];duration=None
                if arm=='client':
                    rows,duration=asyncio.run(episode(clock))
                    if len(rows)!=8 or not all(r['success'] for r in rows):raise RuntimeError('Synthetic episode failed')
                record=dict(index=i,arm=arm,target_monotonic_s=target,post_sleep_check_monotonic_s=checked,
                    clock=clock,episode_duration_s=duration,
                    request_timing=[dict(index=r['index'],planned_s=r['planned_s'],sent_s=r['sent_s'],
                        absolute_send_monotonic_s=clock['start_monotonic_s']+r['sent_s']) for r in sorted(rows,key=lambda r:r['index'])],
                    **derived(arm,target,checked,clock,rows))
                records.append(record)
                with (out/'trials.jsonl').open('a') as f:f.write(json.dumps(record)+'\n');f.flush()
                print('TRIAL',i,arm,record['wakeup_check_lateness_ms'],record['episode_start_lateness_ms'],flush=True)
                w.healthy(out,sampler)
    except BaseException as exc:error=repr(exc);print('STOP',error,flush=True)
    finally:
        (out/'monitor-stop').touch()
        if sampler:
            try:life.stop_child(sampler)
            except Exception as exc:cleanup.append(repr(exc))
        if acquired and lock.exists() and lock.read_text()==str(os.getpid()):lock.unlink()
        unchanged=all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in core.items())
        summary={}
        for arm in ('sleep','client'):
            subset=[r for r in records if r['arm']==arm]
            if subset:
                summary[arm]=dict(wakeup=describe([r['wakeup_check_lateness_ms'] for r in subset]),wakeup_failures=sum(r['wakeup_over_50ms'] for r in subset))
                if arm=='client':summary[arm].update(episode_start=describe([r['episode_start_lateness_ms'] for r in subset]),
                    initialization_after_check=describe([r['client_initialization_after_check_ms'] for r in subset]),
                    first_send=describe([r['first_request_send_lateness_ms'] for r in subset]),
                    episode_start_failures=sum(r['episode_start_over_50ms'] for r in subset))
        complete=len(records)==32 and error is None and not cleanup and unchanged
        failure=any(r['wakeup_over_50ms'] or r['episode_start_over_50ms'] for r in records)
        w.prior.write(out/'outcome.json',dict(status='PROBE_COMPLETE' if complete else 'HOLD',error=error,cleanup_errors=cleanup,
            completed_trials=len(records),summary=summary,core_unchanged=unchanged,
            timing_budget_observed_compatible=not failure if complete else None,
            gpu_decision='NO_GPU_RERUN' if failure or not complete else 'CONDITIONAL_ONLY_NOT_GPU_STABILITY_PROOF',
            real_inference_requests=0,server_started=False))


if __name__=='__main__':main()
