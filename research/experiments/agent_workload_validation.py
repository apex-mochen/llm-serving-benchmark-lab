"""Bounded real-GPU pilot. Owns only its server; keeps core lab unchanged.

Agent is a frozen two-stage synthetic trace, not autonomous tool reasoning.
Traditional replays identical token IDs at Agent's actual send offsets.
"""
import asyncio
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import statistics
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lab import gpu, write_json
from study import wait_until_ready
import httpx
from guidellm.scheduler import TraceReplayStrategy
from guidellm.schemas import RequestInfo, RequestSettings
from multiprocessing import get_context


def trace(seed, sessions=24):
    rng = random.Random(seed)
    shared = rng.choices(range(1000, 20000), k=256)
    rows = []
    for i in range(sessions):
        session = f'session-{i}'
        first = shared + rng.choices(range(1000, 20000), k=768)
        for stage in (0, 1):
            rows.append(dict(request_id=f'{session}-{stage}', session_id=session,
                stage=stage, parent=None if stage==0 else f'{session}-0',
                root_at=i/4., pause_s=0.25 if i%2 else 0.75,
                tokens=first if stage==0 else first+rng.choices(range(1000,20000),k=128)))
    return rows


def percentile(values, p):
    a = sorted(values)
    pos = (len(a)-1)*p/100
    lo, hi = int(pos), min(int(pos)+1,len(a)-1)
    return a[lo]+(a[hi]-a[lo])*(pos-lo)


async def requests_run(rows, base, model, directory, replay=None):
    start = time.monotonic()
    wall = time.time()
    events, records = [], []
    strategy = TraceReplayStrategy(schedule_turn='idle_gap')
    strategy.init_processes_timings(worker_count=1,max_concurrency=1,mp_context=get_context())
    strategy.init_processes_start(wall)
    # Strategy only supplies target times; actual socket execution uses httpx.
    # Recorded durations will be the measured parent durations, so the original
    # synthetic child offset encodes exactly the configured tool gap.
    parents = {}
    async with httpx.AsyncClient(timeout=90,limits=httpx.Limits(max_connections=96)) as client:
        start=time.monotonic()
        wall=time.time()
        strategy.init_processes_start(wall)
        async def send(row, target):
            while target > time.monotonic()-start:
                await asyncio.sleep(target-(time.monotonic()-start))
            sent = time.monotonic()-start
            events.append(dict(request=row['request_id'],session=row['session_id'],event='resume' if row['stage'] else 'start',at_s=sent))
            payload = dict(model=model,prompt=row['tokens'],max_tokens=64,ignore_eos=True,
                temperature=0,seed=20261012,stream=True,stream_options={'include_usage':True})
            rec = dict(request_id=row['request_id'],session_id=row['session_id'],stage=row['stage'],
                parent=row['parent'],target_s=target,sent_s=sent,input_tokens=len(row['tokens']),
                prompt_sha256=hashlib.sha256(json.dumps(row['tokens']).encode()).hexdigest())
            first, last, usage, chunks = None,None,None,0
            try:
                async with client.stream('POST',base+'/v1/completions',json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith('data: '): continue
                        if line=='data: [DONE]': break
                        value=json.loads(line[6:])
                        if any(c.get('text') for c in value.get('choices',[])):
                            now=time.monotonic()-start
                            if first is None: first=now
                            last=now; chunks+=1
                        if value.get('usage'): usage=value['usage']
                if first is None or not usage or usage['prompt_tokens']!=len(row['tokens']) or usage['completion_tokens']!=64:
                    raise ValueError(f'Length/stream validation failed: {usage}')
                rec.update(success=True,usage=usage,ttft_s=first-sent,
                    tpot_s=(last-first)/63,e2e_s=time.monotonic()-start-sent,content_chunks=chunks)
            except Exception as exc:
                rec.update(success=False,error=repr(exc))
            rec['end_s']=time.monotonic()-start
            records.append(rec)
            events.append(dict(request=row['request_id'],session=row['session_id'],event='finish' if rec['success'] else 'failed',at_s=rec['end_s']))
            return rec

        async def session(first, second):
            parent=await send(first,first['root_at'])
            if not parent['success']:
                events.append(dict(request=second['request_id'],event='cancelled_dependency'))
                return
            events.append(dict(request=first['request_id'],session=first['session_id'],event='pause',at_s=parent['end_s'],duration_s=first['pause_s']))
            info=RequestInfo(request_id=first['request_id'],conversation_id=first['session_id'],node_id=first['request_id'],
                settings=RequestSettings(relative_timestamp=parent['sent_s'],trace_duration=parent['end_s']-parent['sent_s']))
            info.timings.request_end=wall+parent['end_s']
            strategy.request_completed(info)
            child=RequestInfo(request_id=second['request_id'],conversation_id=first['session_id'],node_id=second['request_id'],
                parent_node_ids=[first['request_id']],settings=RequestSettings(relative_timestamp=parent['end_s']+first['pause_s']))
            target=await strategy.resolve_dequeued_target_start(0,wall,child.settings,child)-wall
            assert abs(target-(parent['end_s']+first['pause_s']))<1e-5
            await send(second,target)
        if replay is None:
            await asyncio.gather(*(session(rows[i],rows[i+1]) for i in range(0,len(rows),2)))
        else:
            await asyncio.gather(*(send(row,replay[row['request_id']]) for row in rows))
    duration=time.monotonic()-start
    write_json(directory/'requests.json',records)
    write_json(directory/'events.json',events)
    success=[r for r in records if r['success']]
    if len(success)!=len(rows):
        raise RuntimeError('Incomplete workload; preserved requests and failure events')
    if replay is None:
        by_id={r['request_id']:r for r in records}
        for row in rows:
            if row['parent']:
                assert by_id[row['request_id']]['sent_s']+1e-5>=by_id[row['parent']]['end_s']+row['pause_s']
    summary=dict(requests=len(success),duration_s=duration,requests_per_s=len(success)/duration,
        output_tokens_per_s=sum(r['usage']['completion_tokens'] for r in success)/duration,
        ttft_mean_ms=statistics.mean(r['ttft_s'] for r in success)*1000,
        tpot_mean_ms=statistics.mean(r['tpot_s'] for r in success)*1000,
        p95_e2e_ms=percentile([r['e2e_s'] for r in success],95)*1000,
        p99_e2e_ms=percentile([r['e2e_s'] for r in success],99)*1000,
        max_dispatch_lag_ms=max(r['sent_s']-r['target_s'] for r in records)*1000)
    write_json(directory/'summary.json',summary)
    return records, summary


def main():
    cfg=json.loads((ROOT/'config.local.json').read_text())
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    evidence=ROOT/'research/experiments/validation-runs'/stamp
    evidence.mkdir(parents=True,exist_ok=False)
    core={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['lab.py','study.py','tail_report.py','README.md']}
    write_json(evidence/'core-before.json',core)
    lock=ROOT/'.benchmark.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    entry=cfg['engines']['vllm']
    base=entry['base_url']
    metadata=dict(status='running',evidence_kind='real_gpu_synthetic_frozen_agent_trace',
        model_revision=cfg['model_revision'],gpu=gpu(0),seed=20261012,sessions=24,stages=2,
        root_requests_per_s=4,output_tokens=64,input_lengths=[1024,1152],repeats=3,
        pauses_s=[0.25,0.75],shared_prefix_tokens=256,config=cfg,
        limitation='Tiny model; no protected tenant or full FairInference/Continuum baseline; desktop GPU shared; P99 descriptive only.')
    write_json(evidence/'metadata.json',metadata)
    all_results=[]
    try:
        import socket
        from urllib.parse import urlparse
        url=urlparse(base)
        with socket.socket() as s:
            if s.connect_ex((url.hostname,url.port))==0:
                raise RuntimeError('Endpoint occupied; will not replace service')
        build=subprocess.check_output([entry['python'],'-c','from vllm._version import __commit_id__; print(__commit_id__)'],text=True).strip().removeprefix('g')
        commit=json.loads(subprocess.check_output(['gh','api','repos/vllm-project/vllm/commits/'+build],text=True))['sha']
        assert commit.startswith(build)
        metadata['engine_commit']=commit
        metadata['engine_packages']=json.loads(subprocess.check_output([entry['python'],'-c','import importlib.metadata as m,json; print(json.dumps({d.metadata["Name"]:d.version for d in m.distributions()}))'],text=True))
        for cache in (False,True):
            args=list(entry['server_command'])
            args+=['--host','127.0.0.1']
            args[args.index('--no-enable-prefix-caching')]='--enable-prefix-caching' if cache else '--no-enable-prefix-caching'
            metadata.setdefault('launch_commands',[]).append(args)
            write_json(evidence/'metadata.json',metadata)
            serverlog=evidence/f'server-cache-{cache}.log'
            with serverlog.open('w') as logfile:
                overrides={**entry.get('server_environment',{}),'VLLM_SERVER_DEV_MODE':'1'}
                metadata['server_environment_overrides']=overrides
                write_json(evidence/'metadata.json',metadata)
                proc=subprocess.Popen(args,stdout=logfile,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,**overrides})
                try:
                    print(f'Started own server {proc.pid}, cache={cache}',flush=True)
                    wait_until_ready(proc,base,'vllm',serverlog)
                    # Warmup uses a separate seed/prefix, then reset cache before each cell.
                    warm=trace(20260901,sessions=2)
                    asyncio.run(requests_run(warm,base,cfg['served_model_name'],evidence/f'warm-cache-{cache}'))
                    for repeat in range(3):
                        rows=trace(20261012+repeat)
                        write_json(evidence/f'trace-cache-{cache}-r{repeat}.json',rows)
                        replay=None
                        for kind in ('agent','traditional'):
                            directory=evidence/f'cache-{cache}-r{repeat}-{kind}'
                            directory.mkdir()
                            if cache:
                                request=urllib.request.Request(base+'/reset_prefix_cache',method='POST')
                                with urllib.request.urlopen(request,timeout=10) as response:
                                    reset=response.read().decode()
                                    directory.joinpath('reset-response.txt').write_text(reset)
                                    assert json.loads(reset)['success'] is True, 'Cache reset not completed'
                            else:
                                directory.joinpath('reset-response.txt').write_text('Prefix cache disabled; no reset required.')
                            with urllib.request.urlopen(base+'/metrics',timeout=10) as response:
                                directory.joinpath('metrics-before.txt').write_text(response.read().decode())
                            samples=[]; stop=threading.Event()
                            def sample():
                                while not stop.is_set():
                                    try: samples.append(dict(monotonic_s=time.monotonic(),**gpu(0)))
                                    except Exception as exc: samples.append(dict(error=repr(exc)))
                                    stop.wait(.5)
                            worker=threading.Thread(target=sample);worker.start()
                            try:
                                records,summary=asyncio.run(requests_run(rows,base,cfg['served_model_name'],directory,replay))
                            finally:
                                stop.set();worker.join();write_json(directory/'gpu.json',samples)
                            with urllib.request.urlopen(base+'/metrics',timeout=10) as response:
                                directory.joinpath('metrics-after.txt').write_text(response.read().decode())
                            if kind=='agent': replay={r['request_id']:r['sent_s'] for r in records}
                            summary.update(cache=cache,repeat=repeat,kind=kind,
                                gpu_memory_peak_mib=max(s['memory.used'] for s in samples if 'memory.used' in s))
                            all_results.append(summary)
                            print(json.dumps(summary),flush=True)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid,signal.SIGTERM)
                        try: proc.wait(timeout=20)
                        except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
        metadata['status']='completed'
    except Exception as exc:
        metadata.update(status='blocked_or_failed',error=repr(exc))
        print(metadata['error'],flush=True)
    finally:
        write_json(evidence/'metadata.json',metadata)
        write_json(evidence/'aggregate.json',all_results)
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in core.items())
        if lock.exists() and lock.read_text()==str(os.getpid()): lock.unlink()
        print('EVIDENCE='+str(evidence),flush=True)
    return 0 if metadata['status']=='completed' else 1


if __name__=='__main__':
    raise SystemExit(main())
