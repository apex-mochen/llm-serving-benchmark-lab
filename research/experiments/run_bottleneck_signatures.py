"""Single-GPU screening experiments, no diagnosis or engine modifications."""
import asyncio
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import re
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from lab import gpu,write_json
from study import wait_until_ready
import httpx


def quantile(values,p):
    a=sorted(values);position=(len(a)-1)*p/100
    i=int(position);j=min(i+1,len(a)-1)
    return a[i]+(a[j]-a[i])*(position-i)


def prompts(seed,length,n=8,shared=0):
    rng=random.Random(seed);prefix=rng.choices(range(1000,20000),k=shared)
    return [prefix+rng.choices(range(1000,20000),k=length-shared) for _ in range(n)]


def prom(base):
    with urllib.request.urlopen(base+'/metrics',timeout=10) as response: return response.read().decode()


def parse_prom(text):
    values={}
    for line in text.splitlines():
        m=re.match(r'([^\s{]+)(?:\{[^}]*\})?\s+([-+\d.eE]+)$',line)
        if m: values[m[1]]=values.get(m[1],0)+float(m[2])
    return values


async def run_requests(base,model,inputs,output,concurrency,rate=None):
    rows=[];semaphore=asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=120,limits=httpx.Limits(max_connections=32)) as client:
        start=time.monotonic()
        async def one(i,tokens):
            planned=i/rate if rate else 0.
            while planned>time.monotonic()-start:
                await asyncio.sleep(planned-(time.monotonic()-start))
            arrived=time.monotonic()-start
            async with semaphore:
                sent=time.monotonic()-start
                row=dict(id=i,planned_s=planned,arrival_s=arrived,sent_s=sent,
                    client_queue_s=sent-arrived,dispatch_delay_s=sent-planned,input_tokens=len(tokens),
                    prompt_sha256=hashlib.sha256(json.dumps(tokens).encode()).hexdigest())
                usage=None;first=None;last=None;chunks=[]
                try:
                    async with client.stream('POST',base+'/v1/completions',json=dict(model=model,prompt=tokens,
                        max_tokens=output,temperature=0,seed=20261012,ignore_eos=True,stream=True,
                        stream_options={'include_usage':True})) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.startswith('data: ') or line=='data: [DONE]': continue
                            item=json.loads(line[6:])
                            if any(c.get('text') for c in item.get('choices',[])):
                                now=time.monotonic()-start
                                if first is None: first=now
                                last=now;chunks.append(now)
                            if item.get('usage'): usage=item['usage']
                    assert first is not None and usage and usage['prompt_tokens']==len(tokens) and usage['completion_tokens']==output, usage
                    row.update(success=True,usage=usage,ttft_s=first-sent,tpot_s=(last-first)/(output-1) if output>1 else None,
                        e2e_s=time.monotonic()-start-sent,content_chunk_times_s=chunks)
                except Exception as exc: row.update(success=False,error=repr(exc))
                row['end_s']=time.monotonic()-start;rows.append(row)
        await asyncio.gather(*(one(i,t) for i,t in enumerate(inputs)))
    duration=time.monotonic()-start
    return rows,duration


def cell(base,cfg,folder,group,level,repeat,inputs,output,concurrency,rate,state):
    folder.mkdir(parents=True,exist_ok=False)
    configuration=dict(group=group,level=level,repeat=repeat,seed=20261012+repeat,
        input_length=len(inputs[0]),output_length=output,requests=len(inputs),concurrency=concurrency,
        arrival_rate=rate,load_mode='scheduled open arrival + client cap' if rate else 'finite burst + client cap',cache_state=state,
        model_revision=cfg['model_revision'],served_model=cfg['served_model_name'])
    write_json(folder/'configuration.json',configuration);write_json(folder/'workload.json',inputs)
    before=prom(base);(folder/'metrics-before.txt').write_text(before)
    stopped=threading.Event();samples=[];cache_samples=[]
    def sample():
        while not stopped.is_set():
            now=time.monotonic()
            try: samples.append(dict(monotonic_s=now,**gpu(0)))
            except Exception as exc: samples.append(dict(monotonic_s=now,error=repr(exc)))
            try:
                v=parse_prom(prom(base))
                cache_samples.append(dict(monotonic_s=time.monotonic(),metrics={k:x for k,x in v.items() if
                    any(t in k for t in ('kv_cache_usage_perc','num_requests_waiting','num_requests_running','num_preemptions_total'))}))
            except Exception as exc: cache_samples.append(dict(error=repr(exc)))
            stopped.wait(.5)
    worker=threading.Thread(target=sample);worker.start()
    try: rows,duration=asyncio.run(run_requests(base,cfg['served_model_name'],inputs,output,concurrency,rate))
    finally: stopped.set();worker.join()
    write_json(folder/'requests.json',rows);write_json(folder/'gpu.json',samples);write_json(folder/'server-samples.json',cache_samples)
    assert len(rows)==len(inputs) and all(r['success'] for r in rows), 'Incomplete cell: raw failures preserved'
    b=parse_prom(before);after=prom(base)
    # Histograms can update asynchronously; don't report partial intervals as complete.
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        a=parse_prom(after)
        if all(a.get(f'vllm:request_{phase}_time_seconds_count',0)-b.get(f'vllm:request_{phase}_time_seconds_count',0)==len(inputs)
               for phase in ('queue','prefill','decode')): break
        time.sleep(.25);after=prom(base)
    (folder/'metrics-after.txt').write_text(after);a=parse_prom(after)
    summary=dict(**configuration,duration_s=duration,requests_per_s=len(rows)/duration,output_tokens_per_s=output*len(rows)/duration,
        mean_ttft_ms=statistics.mean(r['ttft_s'] for r in rows)*1000,mean_tpot_ms=statistics.mean(r['tpot_s'] for r in rows)*1000,
        mean_client_queue_ms=statistics.mean(r['client_queue_s'] for r in rows)*1000,
        max_dispatch_delay_ms=max(r['dispatch_delay_s'] for r in rows)*1000)
    for p in (50,95,99): summary[f'p{p}_e2e_ms']=quantile([r['e2e_s'] for r in rows],p)*1000
    valid=[s for s in samples if 'memory.used' in s]
    assert valid,'No usable GPU samples'
    summary.update(gpu_memory_peak_mib=max(s['memory.used'] for s in valid),gpu_utilization_mean_pct=statistics.mean(s['utilization.gpu'] for s in valid),
        telemetry_error_count=sum('error' in s for s in samples))
    for phase in ('queue','prefill','decode'):
        prefix=f'vllm:request_{phase}_time_seconds'
        count=a.get(prefix+'_count',0)-b.get(prefix+'_count',0)
        summary[phase+'_histogram_count']=count
        summary[phase+'_mean_ms']=(a[prefix+'_sum']-b[prefix+'_sum'])/count*1000 if count==len(rows) else None
    for name in ('prefix_cache_queries_total','prefix_cache_hits_total','num_preemptions_total'):
        key='vllm:'+name
        summary[name+'_delta']=a[key]-b[key] if key in a and key in b else None
    write_json(folder/'summary.json',summary)
    (folder/'run.log').write_text(json.dumps(summary,ensure_ascii=False)+'\nAll payload/output counts validated.\n')
    print(json.dumps(summary),flush=True)
    return summary


def main():
    cfg=json.loads((ROOT/'config.local.json').read_text());entry=cfg['engines']['vllm'];base=entry['base_url']
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'research/experiments/results'/('signatures-'+stamp);out.mkdir(parents=True,exist_ok=False)
    core={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('lab.py','study.py','tail_report.py','README.md')}
    metadata=dict(status='running',evidence_kind='real_gpu_synthetic_workload_screening',config=cfg,gpu=gpu(0),
        core_sha256=core,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),repeats=3,requests_per_cell=8,
        registered_design_deviation='resource-bounded screening: 8 not 64 requests, fewer levels; formal stability/P99 gate not met',
        fixed_server_overrides=dict(max_num_seqs=4,max_num_batched_tokens=2048,chunked_prefill=True))
    lock=ROOT/'.benchmark.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,str(os.getpid()).encode());os.close(fd)
    all_results=[]
    write_json(out/'metadata.json',metadata)
    try:
        url=urlparse(base)
        with socket.socket() as s: assert s.connect_ex((url.hostname,url.port))!=0,'Existing service will not be replaced'
        build=subprocess.check_output([entry['python'],'-c','from vllm._version import __commit_id__; print(__commit_id__)'],text=True).strip().removeprefix('g')
        commit=json.loads(subprocess.check_output(['gh','api','repos/vllm-project/vllm/commits/'+build],text=True))['sha'];assert commit.startswith(build)
        metadata['engine_commit']=commit
        metadata['packages']=json.loads(subprocess.check_output([entry['python'],'-c','import json,importlib.metadata as m; print(json.dumps({d.metadata["Name"]:d.version for d in m.distributions()}))'],text=True))
        for enabled in (False,True):
            args=list(entry['server_command']);args[args.index('--no-enable-prefix-caching')]='--enable-prefix-caching' if enabled else '--no-enable-prefix-caching'
            args+=['--host','127.0.0.1','--max-num-seqs','4','--max-num-batched-tokens','2048','--enable-chunked-prefill']
            overrides={**entry.get('server_environment',{}),'VLLM_SERVER_DEV_MODE':'1'}
            metadata.setdefault('servers',[]).append(dict(prefix_cache=enabled,command=args,environment=overrides))
            write_json(out/'metadata.json',metadata)
            log=out/f'server-cache-{enabled}.log'
            with log.open('w') as stream:
                proc=subprocess.Popen(args,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,**overrides})
                print(f'Owned server pid={proc.pid}; cache={enabled}; results={out}',flush=True)
                try:
                    wait_until_ready(proc,base,'vllm',log)
                    for repeat in range(3):
                        seed=20261012+repeat
                        experiments=[]
                        if not enabled:
                            experiments += [('prefill',v,v,128,1,None,'disabled') for v in (128,512,1536)]
                            experiments += [('decode',v,512,v,1,None,'disabled') for v in (32,128,256)]
                            experiments += [('queue',v,512,128,v,4.,'disabled') for v in (1,4,8)]
                            experiments += [('cache','disabled',1024,128,4,4.,'disabled')]
                        else:
                            experiments += [('cache',v,1024,128,4,4.,v) for v in ('cold','warm')]
                        if repeat%2: experiments.reverse()
                        for group,level,length,output,conc,rate,state in experiments:
                            folder=out/f'{group}-{level}-r{repeat}'
                            inputs=prompts(seed,length,shared=256 if group=='cache' else 0)
                            warm_inputs=prompts(seed+99999,length,n=16)
                            warm,duration=asyncio.run(run_requests(base,cfg['served_model_name'],warm_inputs,16,4))
                            write_json(out/f'warmup-{group}-{level}-r{repeat}.json',dict(requests=warm,duration_s=duration,seed=seed+99999))
                            assert all(r['success'] for r in warm)
                            if enabled:
                                request=urllib.request.Request(base+'/reset_prefix_cache',method='POST')
                                with urllib.request.urlopen(request,timeout=10) as response: reset=json.load(response)
                                assert reset['success'] is True
                                write_json(out/f'reset-{group}-{level}-r{repeat}.json',reset)
                            if state=='warm':
                                prep,elapsed=asyncio.run(run_requests(base,cfg['served_model_name'],inputs,16,4))
                                write_json(out/f'preload-{group}-{level}-r{repeat}.json',dict(requests=prep,duration_s=elapsed))
                                assert all(r['success'] for r in prep)
                            result=cell(base,cfg,folder,group,level,repeat,inputs,output,conc,rate,state)
                            all_results.append(result);write_json(out/'aggregate.json',all_results)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid,signal.SIGTERM)
                        try: proc.wait(timeout=20)
                        except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
        metadata['status']='completed'
    except Exception as exc:
        metadata.update(status='failed_or_blocked',error=repr(exc));print(repr(exc),flush=True)
    finally:
        write_json(out/'metadata.json',metadata);write_json(out/'aggregate.json',all_results)
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in core.items())
        if lock.exists() and lock.read_text()==str(os.getpid()):lock.unlink()
        print('RESULTS='+str(out),flush=True)
    return 0 if metadata['status']=='completed' else 1

if __name__=='__main__':raise SystemExit(main())
