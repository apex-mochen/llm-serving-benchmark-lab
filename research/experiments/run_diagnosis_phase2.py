"""Native timing preflight and checkpointed fixed-episode GPU experiments.

Not a diagnosis algorithm. Never edits engine/core files or replaces services.
"""
import argparse
import asyncio
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import random
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
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from lab import gpu,write_json
from study import wait_until_ready
from run_bottleneck_signatures import parse_prom,prom,quantile
import httpx


def workload(seed,length,shared=0):
    rng=random.Random(seed)
    prefix=rng.choices(range(1000,20000),k=shared)
    # Longest pool then truncate: paired lengths really are nested.
    return [(prefix+rng.choices(range(1000,20000),k=1536-shared))[:length] for _ in range(8)]


def validate_native(m,output):
    required=('queue_time_ms','time_to_first_token_ms','generation_time_ms','mean_itl_ms')
    if not isinstance(m,dict):raise ValueError('Missing native per-request metrics')
    for key in required:
        if not isinstance(m.get(key),(int,float)) or not math.isfinite(m[key]) or m[key]<0:
            raise ValueError(f'Invalid native field {key}: {m.get(key)}')
    if abs(m['generation_time_ms']/(output-1)-m['mean_itl_ms'])>1e-6:
        raise ValueError('Native generation/mean_itl formula mismatch')


async def episode_http(base,model,inputs,output,cap,tag,trace,rate=4.,timing=None,partial_path=None):
    rows=[];sem=asyncio.Semaphore(cap)
    async with httpx.AsyncClient(timeout=120,limits=httpx.Limits(max_connections=32)) as client:
        start=time.monotonic()
        if timing is not None:
            timing.update(start_monotonic_s=start,utc_anchor=dt.datetime.now(dt.timezone.utc).isoformat(),client_pid=os.getpid(),boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip())
        async def one(i,tokens):
            planned=i/rate if rate else 0.
            while time.monotonic()-start<planned:await asyncio.sleep(planned-(time.monotonic()-start))
            arrived=time.monotonic()-start
            async with sem:
                sent=time.monotonic()-start;rid=f'{tag}-q{i}'
                row=dict(request_id=rid,index=i,planned_s=planned,arrival_s=arrived,sent_s=sent,
                    client_queue_ms=(sent-arrived)*1000,input_tokens=len(tokens),output_tokens=output,
                    prompt_sha256=hashlib.sha256(json.dumps(tokens).encode()).hexdigest())
                first=last=None;usage=native=None;ids=set();chunks=[]
                try:
                    async with client.stream('POST',base+'/v1/completions',headers={'X-Request-Id':rid},json=dict(
                        model=model,prompt=tokens,max_tokens=output,ignore_eos=True,temperature=0,seed=20261012,
                        n=1,stream=True,stream_options={'include_usage':True})) as response:
                        response.raise_for_status();row['response_header_request_id']=response.headers.get('x-request-id')
                        async for line in response.aiter_lines():
                            if not line.startswith('data: ') or line=='data: [DONE]':continue
                            item=json.loads(line[6:])
                            if item.get('id'):ids.add(item['id'])
                            if any(c.get('text') for c in item.get('choices',[])):
                                now=time.monotonic()-start;first=now if first is None else first;last=now;chunks.append(now)
                            if item.get('usage'):
                                usage=item['usage'];native=item.get('metrics')
                    assert first is not None and usage and usage['prompt_tokens']==len(tokens) and usage['completion_tokens']==output,usage
                    assert len(ids)==1,'SSE IDs inconsistent'
                    if trace:
                        assert row['response_header_request_id']==rid,'Request ID header mismatch'
                        validate_native(native,output)
                    row.update(success=True,usage=usage,native_metrics=native,sse_response_ids=sorted(ids),
                        first_content_s=first,last_content_s=last,chunk_times_s=chunks,
                        ttft_ms=(first-sent)*1000,tpot_ms=(last-first)/(output-1)*1000,
                        end_s=time.monotonic()-start)
                    row['e2e_ms']=(row['end_s']-sent)*1000
                    row['planned_e2e_ms']=(row['end_s']-planned)*1000
                    if trace:
                        row['queue_ms']=native['queue_time_ms']
                        row['prefill_ms']=native['time_to_first_token_ms']
                        row['decode_ms']=native['generation_time_ms']
                        row['ttft_boundary_residual_ms']=row['ttft_ms']-row['queue_ms']-row['prefill_ms']
                except Exception as exc:row.update(success=False,error=repr(exc),end_s=time.monotonic()-start)
                rows.append(row)
                if partial_path is not None:
                    with Path(partial_path).open("a") as partial:
                        partial.write(json.dumps(row)+"\n");partial.flush()
        await asyncio.gather(*(one(i,x) for i,x in enumerate(inputs)))
    end=time.monotonic()
    if timing is not None: timing.update(end_monotonic_s=end)
    return rows,end-start


def observed_episode(cfg,path,inputs,cap,tag,trace,output=128):
    path.mkdir(parents=True,exist_ok=False);base=cfg['engines']['vllm']['base_url']
    write_json(path/'workload.json',inputs)
    before=prom(base);(path/'metrics-before.txt').write_text(before)
    stopped=threading.Event();samples=[];server=[]
    def sample():
        while not stopped.is_set():
            now=time.monotonic()
            try:samples.append(dict(monotonic_s=now,**gpu(0)))
            except Exception as exc:samples.append(dict(monotonic_s=now,error=repr(exc)))
            try:
                v=parse_prom(prom(base));server.append(dict(monotonic_s=time.monotonic(),metrics={k:x for k,x in v.items() if any(
                    word in k for word in ('num_requests_running','num_requests_waiting','kv_cache_usage_perc','num_preemptions_total'))}))
            except Exception as exc:server.append(dict(error=repr(exc)))
            stopped.wait(.5)
    thread=threading.Thread(target=sample);thread.start()
    try:rows,duration=asyncio.run(episode_http(base,cfg['served_model_name'],inputs,output,cap,tag,trace))
    finally:stopped.set();thread.join()
    write_json(path/'requests.json',rows);write_json(path/'gpu.json',samples);write_json(path/'server.json',server)
    assert len(rows)==8 and all(r['success'] for r in rows),'Incomplete/invalid episode; raw failures preserved'
    b=parse_prom(before);deadline=time.monotonic()+10;after=prom(base)
    while time.monotonic()<deadline:
        a=parse_prom(after)
        if all(a.get(f'vllm:request_{phase}_time_seconds_count',0)-b.get(f'vllm:request_{phase}_time_seconds_count',0)==8 for phase in ('queue','prefill','decode')):break
        time.sleep(.2);after=prom(base)
    (path/'metrics-after.txt').write_text(after);a=parse_prom(after)
    result=dict(requests=8,duration_s=duration,trace=trace,cap=cap,
        mean_ttft_ms=statistics.mean(r['ttft_ms'] for r in rows),mean_tpot_ms=statistics.mean(r['tpot_ms'] for r in rows),
        mean_e2e_ms=statistics.mean(r['e2e_ms'] for r in rows))
    for phase in ('queue','prefill','decode'):
        prefix=f'vllm:request_{phase}_time_seconds'
        count=a[prefix+'_count']-b[prefix+'_count'];assert count==8,'Incomplete stage interval'
        hist=(a[prefix+'_sum']-b[prefix+'_sum'])/8*1000
        result[phase+'_hist_mean_ms']=hist
        if trace:
            actual=statistics.mean(r[phase+'_ms'] for r in rows)
            result[phase+'_request_mean_ms']=actual
            result[phase+'_reconciliation_ms']=actual-hist
            assert abs(actual-hist)<5.,f'{phase} request/histogram mismatch'
    if trace:
        result['min_ttft_residual_ms']=min(r['ttft_boundary_residual_ms'] for r in rows)
        assert result['min_ttft_residual_ms']>=-5,'Client/native TTFT inconsistent'
    for name in ('prefix_cache_queries_total','prefix_cache_hits_total','num_preemptions_total'):
        key='vllm:'+name;result[name+'_delta']=a[key]-b[key] if key in a and key in b else None
    write_json(path/'summary.json',result);(path/'run.log').write_text(json.dumps(result)+'\n')
    return result


def drain(base):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        v=parse_prom(prom(base))
        if all(v.get('vllm:'+key)==0 for key in ('num_requests_running','num_requests_waiting')):return
        time.sleep(.2)
    raise RuntimeError('Engine did not drain; refusing episode-state drift')


def reset(base,path):
    with urllib.request.urlopen(urllib.request.Request(base+'/reset_prefix_cache',method='POST'),timeout=10) as response:value=json.load(response)
    write_json(path,value);assert value['success'] is True


@contextmanager
def server(cfg,out,trace,cache,label):
    entry=cfg['engines']['vllm'];url=urlparse(entry['base_url'])
    with socket.socket() as s:assert s.connect_ex((url.hostname,url.port))!=0,'Existing endpoint service protected'
    args=list(entry['server_command']);args[args.index('--no-enable-prefix-caching')]='--enable-prefix-caching' if cache else '--no-enable-prefix-caching'
    args+=['--host','127.0.0.1','--max-num-seqs','4','--max-num-batched-tokens','2048','--enable-chunked-prefill']
    if trace:args+=['--enable-per-request-metrics','--enable-request-id-headers','--enable-prompt-tokens-details']
    env={**entry.get('server_environment',{}),'VLLM_SERVER_DEV_MODE':'1'}
    write_json(out/f'{label}-server-config.json',dict(command=args,environment_overrides=env,trace=trace,cache=cache))
    path=out/f'{label}-server.log'
    with path.open('a') as logfile:
        proc=subprocess.Popen(args,stdout=logfile,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,**env})
        try:
            print(f'Owned server {proc.pid}: {label}',flush=True);wait_until_ready(proc,entry['base_url'],'vllm',path)
            warm,elapsed=asyncio.run(episode_http(entry['base_url'],cfg['served_model_name'],workload(20260101,512),128,4,label+'-warm',trace,rate=None))
            write_json(out/f'{label}-warm.json',dict(requests=warm,duration_s=elapsed));assert all(r['success'] for r in warm)
            drain(entry['base_url']);yield
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=20)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)


def preflight(cfg,out):
    results=[]
    for repeat in range(3):
        for traced in ((False,True) if repeat%2==0 else (True,False)):
            label=f'preflight-r{repeat}-trace-{traced}'
            with server(cfg,out,traced,False,label):
                record=observed_episode(cfg,out/label,workload(20261012+repeat,512),8,label,traced)
                record.update(repeat=repeat);results.append(record);write_json(out/'preflight-progress.json',results)
    comparisons={}
    for key in ('mean_ttft_ms','mean_tpot_ms','mean_e2e_ms'):
        ratios=[next(r[key] for r in results if r['repeat']==i and r['trace'])/next(r[key] for r in results if r['repeat']==i and not r['trace']) for i in range(3)]
        comparisons[key]=dict(paired_ratios=ratios,median_ratio=statistics.median(ratios),within_5pct=abs(statistics.median(ratios)-1)<=.05)
    value=dict(accuracy_pass=True,overhead=comparisons,
        overhead_5pct_pass=all(v['within_5pct'] for v in comparisons.values()),
        policy='Expansion trace group remains instrumented; never merge with trace-off or Phase1 uninstrumented performance samples.')
    write_json(out/'preflight-result.json',value);print(json.dumps(value),flush=True)


def cell_schedule(mode):
    if mode=='expand':
        # Nested cumulative prefixes: genuine 64 ->256 ->1024 observations,
        # same episodes, not three independent cohorts.
        return [('expand',f'cap{cap}',512,cap,'disabled',repeat,128) for repeat in range(5) for cap in ((4,8) if repeat%2==0 else (8,4))]
    if mode=='cache-expand':
        return [('cache-expand',state,1024,4,state,repeat,8) for repeat in range(5) for state in (('cold','warm') if repeat%2==0 else ('warm','cold'))]
    if mode=='matrix-a':
        return [('matrix-a',f'len{length}-cap{cap}',length,cap,'disabled',repeat,8) for repeat in range(3) for length in (512,1536) for cap in (4,8)]
    if mode=='matrix-b':
        return [('matrix-b',f'{state}-cap{cap}',1024,cap,state,repeat,8) for repeat in range(3) for state in ('cold','warm') for cap in (4,8)]
    raise ValueError(mode)


def experiments(cfg,out,mode,budget):
    specs=cell_schedule(mode);start=time.monotonic();base=cfg['engines']['vllm']['base_url']
    # Drain/reset flags ensure cache state is reproducible per fixed episode.
    with server(cfg,out,True,mode in ('cache-expand','matrix-b'),mode+'-trace-on'):
        for group,condition,length,cap,state,repeat,episodes in specs:
            directory=out/f'{group}-{condition}-r{repeat}';directory.mkdir(exist_ok=True)
            config=dict(group=group,condition=condition,input_length=length,output_length=128,cap=cap,cache=state,repeat=repeat,
                episodes=episodes,episode_requests=8,arrival_rate=4,seed_base=20261012,
                native_prefill_boundary='scheduled -> first output token; same as vLLM phase histogram, not GPU-only kernel time')
            write_json(directory/'configuration.json',config)
            for episode in range(episodes):
                destination=directory/f'episode-{episode:03d}'
                if (destination/'summary.json').exists():continue
                assert not destination.exists(),'Partial episode exists: preserve and investigate before resuming'
                if (time.monotonic()-start)/60>=budget:return 'partial_budget_checkpoint'
                seed=20261012+repeat*10000+episode;inputs=workload(seed,length,256 if state!='disabled' else 0)
                drain(base)
                if state!='disabled':reset(base,directory/f'episode-{episode:03d}-reset.json')
                if state=='warm':
                    prep,duration=asyncio.run(episode_http(base,cfg['served_model_name'],inputs,16,4,
                        f'{mode}-{condition}-r{repeat}-e{episode}-prep',True,rate=None))
                    write_json(directory/f'episode-{episode:03d}-preload.json',dict(requests=prep,duration_s=duration));assert all(r['success'] for r in prep)
                    drain(base)
                observed_episode(cfg,destination,inputs,cap,f'{out.name}-{group}-{condition}-r{repeat}-e{episode}',True)
                drain(base)
                done=episode+1
                if done in (8,32,128):
                    write_json(directory/f'checkpoint-{done*8}.json',dict(requests=done*8,episodes=done,nested_prefix=True))
                if done%8==0:print(f'{group}/{condition}/r{repeat}: {done*8}/{episodes*8} requests checkpointed',flush=True)
    return 'completed'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['preflight','expand','cache-expand','matrix-a','matrix-b'],required=True)
    parser.add_argument('--out');parser.add_argument('--budget-minutes',type=float,default=45);args=parser.parse_args()
    cfg=json.loads((ROOT/'config.local.json').read_text())
    if args.out:out=Path(args.out).resolve();assert out.is_relative_to(ROOT/'research/experiments/results')
    else:out=ROOT/'research/experiments/results'/('phase2-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    metadata_path=out/f'metadata-{args.mode}.json'
    previous=json.loads(metadata_path.read_text()) if metadata_path.exists() else None
    core={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('lab.py','study.py','tail_report.py','README.md')}
    script_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if previous:assert previous['script_sha256']==script_hash and previous['core_sha256']==core,'Cannot silently resume altered source'
    lock=ROOT/'.benchmark.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,str(os.getpid()).encode());os.close(fd)
    meta=dict(status='running',config=cfg,mode=args.mode,core_sha256=core,script_sha256=script_hash,gpu=gpu(0),budget_minutes=args.budget_minutes,
        evidence_kind='real_gpu_fixed_episode_native_request_metrics')
    write_json(metadata_path,meta)
    try:
        build=subprocess.check_output([cfg['client_python'],'-c','from vllm._version import __commit_id__;print(__commit_id__)'],text=True).strip().removeprefix('g')
        commit=json.loads(subprocess.check_output(['gh','api','repos/vllm-project/vllm/commits/'+build],text=True))['sha'];assert commit.startswith(build)
        meta['engine_commit']=commit
        if args.mode=='preflight':preflight(cfg,out);meta['status']='completed'
        else:
            assert json.loads((out/'preflight-result.json').read_text())['accuracy_pass'] is True,'Native timing preflight required'
            meta['status']=experiments(cfg,out,args.mode,args.budget_minutes)
    except Exception as exc:meta.update(status='failed_or_blocked',error=repr(exc));print(repr(exc),flush=True)
    finally:
        write_json(metadata_path,meta)
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in core.items())
        if lock.exists() and lock.read_text()==str(os.getpid()):lock.unlink()
        print(f'PHASE2_OUT={out}; mode={args.mode}; status={meta["status"]}',flush=True)
    return 0 if meta['status'] in ('completed','partial_budget_checkpoint') else 1

if __name__=='__main__':raise SystemExit(main())
