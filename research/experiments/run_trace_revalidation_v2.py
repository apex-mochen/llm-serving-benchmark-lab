"""Bounded fresh trace calibration; no core changes or expansion."""
import asyncio, datetime as dt, hashlib, json, os, signal, statistics, subprocess, sys, time
from pathlib import Path
ROOT=Path('/home/dcl/projects/llm-serving-benchmark-lab')
sys.path.insert(0,str(ROOT/'research/experiments'))
import run_trace_revalidation as old
import run_environment_stability as stability
x=old.existing
out=ROOT/'research/experiments/results'/('trace-revalidation-v2-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
out.mkdir();write=stability.durable
cfg=json.loads((ROOT/'config.local.json').read_text());inputs=x.workload(20261013,512)
command=cfg['engines']['vllm']['server_command']+['--host','127.0.0.1','--max-num-seqs','4','--max-num-batched-tokens','2048','--enable-chunked-prefill','--uvicorn-log-level','warning']
env={**os.environ,**cfg['engines']['vllm']['server_environment']}
removed=[]
for k in list(env):
    if k.startswith(('VLLM_TORCH_PROFILER','OTEL_','NSYS_')) or k in ('TORCH_LOGS','CUDA_LAUNCH_BLOCKING'):
        removed.append(k);env.pop(k)
env.update(VLLM_SERVER_DEV_MODE='0',VLLM_LOGGING_LEVEL='INFO',TORCH_CPP_LOG_LEVEL='WARNING')
overrides=cfg['engines']['vllm']['server_environment']|{k:env[k] for k in ('VLLM_SERVER_DEV_MODE','VLLM_LOGGING_LEVEL','TORCH_CPP_LOG_LEVEL')}
core={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('lab.py','study.py','tail_report.py','README.md')}
write(out/'specification.json',dict(config=cfg,base_command=command,overrides=overrides,removed_names=removed,core_sha256=core,repeats=3,requests_per_variant=64,episodes=8,rate=4,cap=8,input_tokens=512,output_tokens=128,payload_seed=20261013,sampling_seed=20261012,gate='All five median paired overhead percentages strictly below 5; complete three repeats; no compiler/foreign compute/OOM.',scope='Stats enabled in BOTH arms; not the earlier disable-log-stats baseline. No component expansion automatically.'))
write(out/'fixed-payload.json',inputs)
for source in (Path(__file__),Path(old.__file__),Path(x.__file__),Path(stability.__file__)):
    (out/('source-'+source.name)).write_bytes(source.read_bytes())
helper=Path('/mnt/d/myknowledge/research/capture_host_stability.ps1')
(out/'source-capture_host_stability.ps1').write_bytes(helper.read_bytes())
import vllm, torch, importlib.metadata
write(out/'runtime.json',dict(python=sys.version,executable=sys.executable,vllm_version=vllm.__version__,vllm_path=vllm.__file__,torch=torch.__version__,cuda=torch.version.cuda,packages={n:importlib.metadata.version(n) for n in ('httpx','triton')},head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),gpu=subprocess.check_output(['nvidia-smi'],text=True),kernel=subprocess.check_output(['uname','-a'],text=True)))
lock=ROOT/'.benchmark.lock';owned=False;rows=[];error=None;comparison={}
try:
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,str(os.getpid()).encode());os.close(fd);owned=True
    initial=stability.snap();write(out/'initial.json',initial)
    assert not initial['compute_apps'].strip(),'Foreign compute app: stop'
    assert not old.snapshot()['compiler_jobs'],'Parallel compiler: stop'
    for repeat in range(3):
        for traced in ((False,True) if repeat%2==0 else (True,False)):
            label=('on' if traced else 'off')+f'-r{repeat}';d=out/label;d.mkdir()
            before=stability.snap();write(d/'before.json',before)
            assert before['boot_id']==initial['boot_id'],'Boot changed'
            assert not before['compute_apps'].strip(),'Foreign compute app'
            import socket
            with socket.socket() as s:assert s.connect_ex(('127.0.0.1',8019))!=0,'Endpoint occupied'
            args=command+(sum(old.FLAGS.values(),[]) if traced else [])
            write(d/'command.json',dict(argv=args,cwd=str(ROOT),environment_overrides=overrides))
            print('START '+label,flush=True);p=None;records=[]
            try:
                with (d/'server.log').open('w') as log:
                    p=subprocess.Popen(args,env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                    write(d/'ownership.json',dict(pid=p.pid,pgid=p.pid))
                    x.wait_until_ready(p,cfg['engines']['vllm']['base_url'],'vllm',d/'server.log')
                    warm,elapsed=asyncio.run(x.episode_http(cfg['engines']['vllm']['base_url'],cfg['served_model_name'],inputs,128,8,label+'-warm',traced,rate=4))
                    write(d/'warmup.json',dict(requests=warm,duration_s=elapsed));assert all(r['success'] for r in warm)
                    for ep in range(8):
                        assert not old.snapshot()['compiler_jobs'],'Compiler contamination'
                        write(d/f'resource-{ep}.json',stability.snap(include_host=ep in (0,7)))
                        rr,elapsed=asyncio.run(x.episode_http(cfg['engines']['vllm']['base_url'],cfg['served_model_name'],inputs,128,8,f'{label}-e{ep}',traced,rate=4))
                        write(d/f'episode-{ep}.json',dict(requests=rr,duration_s=elapsed))
                        assert len(rr)==8 and all(r['success'] for r in rr),'Request failure'
                        assert traced or all(r['native_metrics'] is None for r in rr),'Trace OFF emitted metrics'
                        records.append(dict(duration_s=elapsed,**{f'mean_{k}_ms':statistics.mean(r[f'{k}_ms'] for r in rr) for k in ('ttft','tpot','e2e')}))
            finally:
                if p is not None and p.poll() is None:
                    os.killpg(p.pid,signal.SIGTERM)
                    try:p.wait(timeout=20)
                    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10)
                time.sleep(2);write(d/'after.json',stability.snap())
            item=dict(variant='full' if traced else 'off',repeat=repeat,summary=old.summarize(records));rows.append(item);write(out/'progress.json',rows)
            print('DONE '+label+' '+json.dumps(item['summary']),flush=True)
    comparison=old.compare(rows,'off','full');write(out/'comparison.json',comparison)
except BaseException as e:
    error=repr(e);print('STOP '+error,flush=True)
finally:
    if owned and lock.exists() and lock.read_text()==str(os.getpid()):lock.unlink()
    unchanged=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in core.items())
    passed=error is None and len(rows)==6 and unchanged and all(v['median_overhead_percent']<5 for v in comparison.values())
    write(out/'outcome.json',dict(status='PASS' if passed else 'HOLD',error=error,completed_variants=len(rows),core_unchanged=unchanged,phase2_expansion_executed=False))
    print('OUT='+str(out)+' STATUS='+('PASS' if passed else 'HOLD'),flush=True)
