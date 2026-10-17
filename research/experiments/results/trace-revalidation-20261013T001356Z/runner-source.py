"""Small fixed-payload trace overhead study; never runs Phase 2 expansion."""
import asyncio
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(Path(__file__).parent))
import run_diagnosis_phase2 as existing

FLAGS = {'metrics':['--enable-per-request-metrics'],
         'headers':['--enable-request-id-headers'],
         'details':['--enable-prompt-tokens-details']}
COMPILERS = {'rustc','cargo','ninja','cc1','cc1plus','nvcc','gcc','g++','clang','clang++','cmake','make'}


def snapshot():
    raw = subprocess.check_output(['ps','-eo','pid,ppid,pcpu,comm'],text=True)
    builds = [line for line in raw.splitlines()[1:] if line.split()[-1] in COMPILERS]
    apps = subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True)
    return dict(monotonic_s=time.monotonic(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),processes=raw,compiler_jobs=builds,
                compute_apps=apps,gpu=existing.gpu(0),
                cpu_load=os.getloadavg(),memory=Path('/proc/meminfo').read_text())


def summarize(records):
    keys=('mean_ttft_ms','mean_tpot_ms','mean_e2e_ms')
    totals={key:statistics.mean(r[key] for r in records) for key in keys}
    duration=sum(r['duration_s'] for r in records)
    totals.update(requests=64,duration_s=duration,requests_per_s=64/duration,output_tokens_per_s=64*128/duration)
    return totals


def compare(rows,baseline,treatment):
    answer={}
    for key in ('mean_ttft_ms','mean_tpot_ms','mean_e2e_ms','requests_per_s','output_tokens_per_s'):
        ratios=[next(r['summary'][key] for r in rows if r['variant']==treatment and r['repeat']==i)/
                next(r['summary'][key] for r in rows if r['variant']==baseline and r['repeat']==i) for i in range(3)]
        slowdown=key not in ('requests_per_s','output_tokens_per_s')
        overhead=[(ratio-1)*100 if slowdown else (1-ratio)*100 for ratio in ratios]
        answer[key]=dict(paired_ratios=ratios,paired_overhead_percent=overhead,
                        median_overhead_percent=statistics.median(overhead))
    return answer


def main():
    cfg=json.loads((ROOT/'config.local.json').read_text())
    out=ROOT/'research/experiments/results'/('trace-revalidation-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir()
    core={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('lab.py','study.py','tail_report.py','README.md')}
    inputs=existing.workload(20261013,512)
    existing.write_json(out/'fixed-payload.json',inputs)
    spec=dict(requests_per_variant=64,repeats=3,input_tokens=512,output_tokens=128,
              client_cap=8,episode_requests=8,arrival_rate=4,seed=20261013,
              payload_sha256=hashlib.sha256(json.dumps(inputs).encode()).hexdigest(),
              core_sha256=core,config=cfg,threshold_percent=5,
              acceptance='All median paired latency overheads and throughput losses strictly below 5%; reject detected compiler/foreign compute contamination. Three repeats are a pilot, not proof of general equivalence.',
              component_followup='Only if full trace fails: paired full versus remove-one-component variants, same payload/config. These are experiments, not a diagnosis algorithm.')
    existing.write_json(out/'specification.json',spec)
    lock=ROOT/'.benchmark.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    samples=[];stopped=threading.Event();results=[];status='running';error=None
    initial=snapshot();existing.write_json(out/'environment-before.json',initial)
    assert not initial['compiler_jobs'],'Parallel compiler found; no GPU experiment started'
    assert not initial['compute_apps'].strip(),'Existing compute app found; no service replaced'
    def monitor():
        while not stopped.is_set():
            try:
                samples.append(snapshot())
                existing.write_json(out/'environment-live.json',samples)
            except Exception as exc:samples.append(dict(error=repr(exc)))
            stopped.wait(3)
    thread=threading.Thread(target=monitor);thread.start()
    def run_variant(variant,repeat,components):
        chosen=copy.deepcopy(cfg)
        for component in components:chosen['engines']['vllm']['server_command']+=FLAGS[component]
        label=f'{variant}-r{repeat}'
        print(f'START {label}',flush=True)
        records=[]
        with existing.server(chosen,out,False,False,label):
            for episode in range(8):
                assert not any(s.get('compiler_jobs') for s in samples),'Compiler contamination: stop and preserve evidence'
                existing.drain(chosen['engines']['vllm']['base_url'])
                path=out/label/f'episode-{episode:02d}'
                path.parent.mkdir(exist_ok=True)
                summary=existing.observed_episode(chosen,path,inputs,8,f'{out.name}-{label}-e{episode}',False)
                rs=json.loads((path/'requests.json').read_text())
                if 'metrics' in components:
                    for r in rs:existing.validate_native(r['native_metrics'],128)
                if 'headers' in components:
                    assert all(r['response_header_request_id']==r['request_id'] for r in rs)
                records.append(summary)
        item=dict(variant=variant,repeat=repeat,components=components,summary=summarize(records))
        results.append(item);existing.write_json(out/'progress.json',results)
        print(f'DONE {label}: {item["summary"]}',flush=True)
    try:
        for repeat in range(3):
            for variant in (('off','full') if repeat%2==0 else ('full','off')):
                run_variant(variant,repeat,[] if variant=='off' else list(FLAGS))
        comparison=compare(results,'off','full')
        passed=all(v['median_overhead_percent']<5 for v in comparison.values())
        existing.write_json(out/'paired-comparison.json',dict(comparison=comparison,pass_threshold=passed))
        if not passed:
            for repeat in range(3):
                for removed in (list(FLAGS) if repeat%2==0 else list(reversed(FLAGS))):
                    run_variant('without-'+removed,repeat,[k for k in FLAGS if k!=removed])
            existing.write_json(out/'component-ablation.json',{
                removed:dict(against_off=compare(results,'off','without-'+removed),
                             removal_effect=compare(results,'full','without-'+removed)) for removed in FLAGS})
        status='PASS' if passed else 'FAIL'
    except BaseException as exc:
        status='BLOCKED';error=repr(exc);print(error,flush=True)
    finally:
        stopped.set();thread.join()
        existing.write_json(out/'environment-timeline.json',samples)
        existing.write_json(out/'outcome.json',dict(status=status,error=error,completed_variants=len(results),
            compiler_contamination=any(s.get('compiler_jobs') for s in samples),
            scope='Only trace remediation; no Phase2 expansion/diagnosis algorithm'))
        assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in core.items())
        if lock.exists() and lock.read_text()==str(os.getpid()):lock.unlink()
        print(f'OUT={out}; STATUS={status}',flush=True)
    return 0 if status in ('PASS','FAIL') else 1


if __name__=='__main__':raise SystemExit(main())
