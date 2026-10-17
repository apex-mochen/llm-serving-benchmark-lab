"""Same-payload trace remediation with durable console and continuous telemetry.

Only --execute starts an owned server. --preflight-only records resources.
No diagnosis algorithm or core changes. Old evidence is never overwritten.
"""
import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import trace_cleanup

ROOT = Path('/home/dcl/projects/llm-serving-benchmark-lab')
COMPILERS = {'rustc', 'cargo', 'ninja', 'cc1', 'cc1plus', 'nvcc', 'gcc', 'g++', 'clang', 'clang++', 'cmake', 'make', 'cl', 'cl.exe'}


def write(path, value):
    with path.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def capture(argv):
    result = subprocess.run(argv, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'{argv[0]} failed: {result.stderr.decode(errors="replace")}')
    return result.stdout.decode('utf-8-sig', errors='replace').strip()


def local_snapshot():
    fields = 'name,uuid,memory.used,memory.total,utilization.gpu,clocks.sm,clocks.mem,temperature.gpu,power.draw'
    return dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), monotonic_s=time.monotonic(),
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                gpu_csv=capture(['nvidia-smi', '--query-gpu='+fields, '--format=csv,noheader,nounits']),
                compute_csv=capture(['nvidia-smi', '--query-compute-apps=pid,process_name', '--format=csv,noheader']),
                processes=capture(['ps', '-eo', 'pid,ppid,pgid,pcpu,rss,comm']),
                memory=Path('/proc/meminfo').read_text())


def violations(snapshot, owned_pgid=None):
    process_groups = {}
    problems = []
    for line in snapshot['processes'].splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        process_groups[int(parts[0])] = int(parts[2])
        if parts[-1] in COMPILERS:
            problems.append('compiler:'+parts[0]+':'+parts[-1])
    for line in snapshot['compute_csv'].splitlines():
        if not line.strip():
            continue
        token = line.split(',', 1)[0].strip()
        if not token.isdigit() or owned_pgid is None or process_groups.get(int(token)) != owned_pgid:
            problems.append('foreign_or_unresolved_compute:'+line)
    return problems


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--preflight-only', action='store_true')
    mode.add_argument('--observe-only', action='store_true')
    args = parser.parse_args()
    out = ROOT/'research/experiments/results'/('trace-revalidation-v3-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir()
    print('OUT='+str(out), flush=True)
    # fd-level redirection persists Python, subprocess and native diagnostic output.
    console = (out/'runner.log').open('a', buffering=1)
    os.dup2(console.fileno(), 1); os.dup2(console.fileno(), 2)
    print('BEGIN', dt.datetime.now(dt.timezone.utc).isoformat(), sys.argv, flush=True)
    sys.path.insert(0, str(ROOT/'research/experiments'))
    import run_trace_revalidation as old
    import run_environment_stability as stability
    x = old.existing
    core = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('lab.py','study.py','tail_report.py','README.md')}
    cfg = json.loads((ROOT/'config.local.json').read_text())
    inputs = x.workload(20261013, 512)
    command = cfg['engines']['vllm']['server_command']+['--host','127.0.0.1','--max-num-seqs','4','--max-num-batched-tokens','2048','--enable-chunked-prefill','--uvicorn-log-level','warning']
    env = {**os.environ, **cfg['engines']['vllm']['server_environment']}
    removed = []
    for key in list(env):
        if key.startswith(('VLLM_TORCH_PROFILER','OTEL_','NSYS_')) or key in ('TORCH_LOGS','CUDA_LAUNCH_BLOCKING'):
            removed.append(key); env.pop(key)
    env.update(VLLM_SERVER_DEV_MODE='0', VLLM_LOGGING_LEVEL='INFO', TORCH_CPP_LOG_LEVEL='WARNING')
    overrides = cfg['engines']['vllm']['server_environment'] | {key:env[key] for key in ('VLLM_SERVER_DEV_MODE','VLLM_LOGGING_LEVEL','TORCH_CPP_LOG_LEVEL')}
    spec = dict(config=cfg, base_command=command, overrides=overrides, removed_names=removed,
                repeats=3, requests_per_variant=64, episodes=8, rate=4, cap=8, input_tokens=512,
                output_tokens=128, payload_seed=20261013, sampling_seed=20261012,
                core_sha256=core, preflight_samples=5, preflight_interval_s=3,
                quiet_gate='five consecutive sampled GPU utilization <=5%, no compute/compiler; host free physical >=3GiB and virtual >=6GiB',
                memory_gate_note='Conservative operational margin, not measured model minimum; never terminate unrelated tasks',
                numeric_gate='all five median paired overhead percentages <5',
                stage_gate='numeric gate AND every paired overhead <5 AND no telemetry error/contamination/OOM AND owned resource release',
                telemetry='local every 2s, Windows host every 15s; same monitor for both arms; sampled, not proof of zero interference',
                scope='single remediation only; stats enabled in both arms; no matrix or component expansion')
    write(out/'specification.json', spec); write(out/'fixed-payload.json', inputs)
    for source in (Path(__file__), Path(old.__file__), Path(x.__file__), Path(stability.__file__), Path(trace_cleanup.__file__)):
        (out/('source-'+source.name)).write_bytes(source.read_bytes())
    helper = Path('/mnt/d/myknowledge/research/capture_host_stability.ps1')
    (out/'source-capture_host_stability.ps1').write_bytes(helper.read_bytes())
    rows = []; comparison = {}; error = None; primary_error = None; cleanup_errors = []; acquired = False; proc = None
    stopped = threading.Event(); contaminated = threading.Event(); monitor_errors = []; evidence_problems = []
    lock = ROOT/'.benchmark.lock'
    initial_boot = None
    def monitor():
        next_host = 0.
        while not stopped.is_set():
            try:
                sample = local_snapshot()
                reasons = violations(sample, proc.pid if proc is not None else None)
                if initial_boot and sample['boot_id'] != initial_boot:
                    reasons.append('boot_changed')
                if reasons:
                    evidence_problems.extend(reasons); contaminated.set()
                sample['violations'] = reasons
                with (out/'resources.jsonl').open('a') as log:
                    log.write(json.dumps(sample)+'\n'); log.flush(); os.fsync(log.fileno())
                if time.monotonic() >= next_host:
                    host = stability.host()
                    host_builds = [r for r in host['processes'] if r['ProcessName'] in COMPILERS]
                    if host_builds:
                        evidence_problems.append('host_compiler'); contaminated.set()
                    with (out/'host-resources.jsonl').open('a') as log:
                        log.write(json.dumps(host)+'\n'); log.flush(); os.fsync(log.fileno())
                    next_host = time.monotonic()+15
            except Exception as exc:
                monitor_errors.append(repr(exc)); contaminated.set()
            stopped.wait(2)
    thread = None
    try:
        fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
        os.write(fd, str(os.getpid()).encode()); os.close(fd); acquired = True
        host = stability.host(); write(out/'host-preflight.json', host)
        if args.observe_only:
            initial_boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            thread = threading.Thread(target=monitor, daemon=True); thread.start()
            print('OBSERVE ONLY: 30 seconds; no server or workload', flush=True)
            stopped.wait(30)
            return 0
        assert not [r for r in host['processes'] if r['ProcessName'] in COMPILERS], 'Host compiler active'
        samples = []
        for i in range(5):
            sample = local_snapshot(); samples.append(sample); write(out/'preflight.json', samples)
            assert not violations(sample), 'Non-quiet process preflight'
            assert float(sample['gpu_csv'].split(',')[4].strip()) <= 5, 'GPU is not quiet: '+sample['gpu_csv']
            if i < 4: time.sleep(3)
        initial_boot = samples[0]['boot_id']
        assert len({s['boot_id'] for s in samples}) == 1, 'Boot changed'
        assert host['memory']['FreePhysicalMemory'] >= 3*1024*1024, 'Host free physical below conservative 3GiB margin'
        assert host['memory']['FreeVirtualMemory'] >= 6*1024*1024, 'Host free virtual below conservative 6GiB margin'
        if args.preflight_only:
            print('PREFLIGHT PASS; no model started', flush=True)
        else:
            import vllm, torch, importlib.metadata
            write(out/'runtime.json', dict(python=sys.version, executable=sys.executable,
                  vllm_version=vllm.__version__, vllm_path=vllm.__file__, torch=torch.__version__,
                  cuda=torch.version.cuda, packages={n:importlib.metadata.version(n) for n in ('httpx','triton')},
                  git_head=capture(['git','-C',str(ROOT),'rev-parse','HEAD']),
                  kernel=capture(['uname','-a']), gpu=capture(['nvidia-smi'])))
            thread = threading.Thread(target=monitor, daemon=True); thread.start()
            for repeat in range(3):
                for traced in ((False, True) if repeat%2 == 0 else (True, False)):
                    assert not contaminated.is_set(), 'Monitor detected interference/error'
                    directory = out/(('on' if traced else 'off')+f'-r{repeat}'); directory.mkdir()
                    before = local_snapshot(); write(directory/'before.json', before)
                    assert not violations(before), 'Existing compute/compiler protected'
                    with socket.socket() as sock:
                        assert sock.connect_ex(('127.0.0.1',8019)) != 0, 'Occupied endpoint protected'
                    argv = command+(sum(old.FLAGS.values(), []) if traced else [])
                    write(directory/'command.json', dict(argv=argv, cwd=str(ROOT), environment_overrides=overrides))
                    records = []
                    try:
                        with (directory/'server.log').open('w') as log:
                            proc = subprocess.Popen(argv, env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                            write(directory/'ownership.json', dict(pid=proc.pid, pgid=proc.pid))
                            print('START', directory.name, proc.pid, flush=True)
                            x.wait_until_ready(proc, cfg['engines']['vllm']['base_url'], 'vllm', directory/'server.log')
                            warm, elapsed = asyncio.run(x.episode_http(cfg['engines']['vllm']['base_url'],cfg['served_model_name'],inputs,128,8,directory.name+'-warm',traced,rate=4))
                            write(directory/'warmup.json', dict(requests=warm,duration_s=elapsed)); assert all(r['success'] for r in warm)
                            for episode in range(8):
                                assert not contaminated.is_set(), 'Monitor detected interference/error'
                                rr, elapsed = asyncio.run(x.episode_http(cfg['engines']['vllm']['base_url'],cfg['served_model_name'],inputs,128,8,f'{directory.name}-e{episode}',traced,rate=4))
                                write(directory/f'episode-{episode}.json',dict(requests=rr,duration_s=elapsed))
                                assert len(rr)==8 and all(r['success'] for r in rr), 'Request failure'
                                assert traced or all(r['native_metrics'] is None for r in rr)
                                records.append(dict(duration_s=elapsed,**{f'mean_{k}_ms':statistics.mean(r[f'{k}_ms'] for r in rr) for k in ('ttft','tpot','e2e')}))
                    except BaseException as exc:
                        primary_error = repr(exc)
                        raise
                    finally:
                        cleanup_errors.extend(trace_cleanup.cleanup_owned(
                            proc, before, directory, local_snapshot, write, violations))
                        proc = None
                    if cleanup_errors:
                        raise RuntimeError('Cleanup checks failed; see cleanup_errors')
                    text = (directory/'server.log').read_text(errors='replace')
                    assert not any(term in text for term in ('OutOfMemoryError','CUDA out of memory','memory allocation failed with OOM')), 'OOM detected'
                    rows.append(dict(variant='full' if traced else 'off',repeat=repeat,summary=old.summarize(records)))
                    write(out/'progress.json', rows); print('DONE', directory.name, flush=True)
            comparison = old.compare(rows,'off','full'); write(out/'comparison.json',comparison)
    except BaseException as exc:
        error = repr(exc)
        if primary_error is None and not cleanup_errors: primary_error = error
        print('STOP', error, flush=True)
    finally:
        stopped.set()
        if thread is not None: thread.join(timeout=40)
        if thread is not None and thread.is_alive(): monitor_errors.append('sampler did not stop')
        if acquired and lock.exists() and lock.read_text()==str(os.getpid()): lock.unlink()
        unchanged = all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in core.items())
        numeric = bool(comparison) and all(v['median_overhead_percent']<5 for v in comparison.values())
        stable_pairs = bool(comparison) and all(all(p<5 for p in v['paired_overhead_percent']) for v in comparison.values())
        complete = len(rows)==6
        stage = args.execute and complete and numeric and stable_pairs and unchanged and error is None and not contaminated.is_set()
        cv = {}
        for arm in ('off','full'):
            for metric in ('mean_ttft_ms','mean_tpot_ms','mean_e2e_ms','requests_per_s','output_tokens_per_s'):
                values = [r['summary'][metric] for r in rows if r['variant']==arm]
                cv[arm+'/'+metric] = statistics.stdev(values)/statistics.mean(values) if len(values)>1 else None
        write(out/'outcome.json', dict(status='PASS' if stage else 'HOLD',numeric_pass=numeric if comparison else None,all_pairs_below_five=stable_pairs if comparison else None,
              error=error,primary_error=primary_error,cleanup_errors=cleanup_errors,completed_variants=len(rows),core_unchanged=unchanged,monitor_errors=monitor_errors,
              observed_interference=evidence_problems,run_to_run_cv=cv,
              preflight_only=args.preflight_only,observe_only=args.observe_only,phase2_expansion_executed=False))
        print('END', 'PASS' if stage else 'HOLD', flush=True)
    return 0 if error is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
