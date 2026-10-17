"""One official benchmark client, two serving engines, auditable raw results."""
import argparse
import csv
import datetime as dt
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time
import urllib.request

CONCURRENCIES = [1, 8, 32, 64]
METRICS = ['mean_ttft_ms', 'mean_tpot_ms', 'mean_itl_ms', 'output_throughput']


def command(args, timeout=60):
    return subprocess.check_output(args, text=True, timeout=timeout).strip()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def gpu(index):
    fields = ['uuid', 'name', 'driver_version', 'memory.total', 'memory.used', 'utilization.gpu',
              'temperature.gpu', 'power.draw', 'clocks.sm', 'clocks.mem']
    line = command(['nvidia-smi', f'--id={index}', '--query-gpu=' + ','.join(fields),
                    '--format=csv,noheader,nounits'], timeout=10)
    values = next(csv.reader([line], skipinitialspace=True))
    if len(values) != len(fields):
        raise ValueError('Expected exactly one selected GPU')
    result = dict(zip(fields, values))
    for field in ['memory.total', 'memory.used', 'utilization.gpu']:
        result[field] = float(result[field])  # Reject N/A instead of inventing zero.
    return result


def validate(result, prompts):
    errors = []
    if result.get('completed') != prompts:
        errors.append('not all requests completed')
    for key, expected in [('input_lens', 1024), ('output_lens', 256)]:
        lengths = result.get(key, [])
        if not isinstance(lengths, list) or len(lengths) != prompts or any(n != expected for n in lengths):
            errors.append(f'{key} must contain exactly {prompts} values of {expected}')
    for key in METRICS:
        value = result.get(key)
        if not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            errors.append(f'invalid metric: {key}')
    return errors


def collect(cfg, engine):
    if cfg['num_prompts'] < 64 or cfg['repeats'] < 3:
        raise ValueError('Study requires >=64 prompts and >=3 repeats per cell')
    revision = cfg['model_revision']
    if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('Pin model_revision to a full Hugging Face commit SHA')
    entry = cfg['engines'][engine]
    for key in ['python', 'repo', 'base_url', 'server_command', 'server_parameters']:
        if not entry.get(key):
            raise ValueError(f'Missing engine metadata: {key}')
    if cfg['engines']['vllm']['server_parameters'] != cfg['engines']['sglang']['server_parameters']:
        raise ValueError('Common server parameters must match across engines')
    if entry['server_parameters'].get('prefix_cache') is not False:
        raise ValueError('Disable prefix caching for repeated random requests')
    with urllib.request.urlopen(entry['base_url'].rstrip('/') + '/v1/models', timeout=10) as response:
        models = json.load(response)
    if cfg['served_model_name'] not in [m['id'] for m in models['data']]:
        raise ValueError('Configured served model is not advertised by the endpoint')
    snapshot = Path(cfg['model_snapshot']).resolve()
    if snapshot.name != revision or not snapshot.is_dir():
        raise ValueError('model_snapshot must be an existing directory named by the pinned revision')
    package_file = command([entry['python'], '-c',
                            f'import {engine}; print({engine}.__file__)'])
    if Path(package_file).resolve().is_relative_to(Path(entry['repo']).resolve()):
        if command(['git', '-C', entry['repo'], 'status', '--porcelain']):
            raise ValueError('Engine source is dirty; commit changes before benchmarking')
        engine_commit = command(['git', '-C', entry['repo'], 'rev-parse', 'HEAD'])
        provenance = 'clean source checkout'
    elif engine == 'vllm':
        short = command([entry['python'], '-c', 'from vllm._version import __commit_id__; print(__commit_id__)'])
        short = short.removeprefix('g')
        if len(short) < 9 or any(c not in '0123456789abcdef' for c in short):
            raise ValueError('Wheel does not expose a verifiable build commit')
        # Resolve the embedded build ID, never substitute a nearby checkout HEAD.
        response = json.loads(command(['gh', 'api', 'repos/vllm-project/vllm/commits/' + short]))
        engine_commit = response['sha']
        if not engine_commit.startswith(short):
            raise ValueError('Wheel build ID does not match upstream commit')
        provenance = 'wheel embedded build ID resolved through upstream commit API'
    else:
        raise ValueError('Engine runtime is not loaded from the recorded repo; use a verified source environment')
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root = Path(cfg.get('results_dir', 'results')) / (stamp + '-' + engine)
    root.mkdir(parents=True, exist_ok=False)
    probe = (f'import torch,importlib.metadata as m,json,shutil,subprocess,{engine} as e; '
             'nvcc=shutil.which("nvcc"); '
             'print(json.dumps({"torch":m.version("torch"),"engine":e.__version__,'
             '"cuda":torch.version.cuda,"cuda_available":torch.cuda.is_available(),'
             '"nvcc":subprocess.check_output([nvcc,"--version"],text=True) if nvcc else None,'
             '"packages":{d.metadata["Name"]:d.version for d in m.distributions()}}))')
    env = json.loads(command([entry['python'], '-c', probe]))
    if not env['cuda_available']:
        raise ValueError('Engine environment does not have working CUDA')
    metadata = dict(engine=engine, engine_commit=engine_commit, provenance=provenance, runtime_module=package_file,
                    environment=env, gpu=gpu(cfg['gpu_index']), machine=platform.node(),
                    platform=platform.platform(), config=cfg, started_utc=stamp,
                    client_version=command([cfg['client_python'], '-c',
                                            'import importlib.metadata as m; print(m.version("vllm"))']))
    write_json(root / 'metadata.json', metadata)
    client = [cfg['client_python'], '-m', 'vllm.entrypoints.cli.main', 'bench', 'serve',
              '--backend', 'vllm', '--base-url', entry['base_url'], '--endpoint', '/v1/completions',
              '--model', cfg['served_model_name'], '--tokenizer', cfg['model_snapshot'],
              '--dataset-name', 'random', '--random-input-len', '1024',
              '--random-output-len', '256', '--random-range-ratio', '0', '--random-prefix-len', '0',
              '--request-rate', 'inf', '--seed', str(cfg['seed']), '--ignore-eos', '--temperature', '0',
              '--extra-body', json.dumps({'repetition_penalty': 1.0, 'top_k': -1, 'top_p': 1.0}),
              '--percentile-metrics', 'ttft,tpot,itl', '--metric-percentiles', '50,95,99',
              '--save-result', '--save-detailed', '--result-dir', str(root)]
    # A distinct seed avoids warming the measured random request prefixes.
    warm = client + ['--num-prompts', '16', '--max-concurrency', '1', '--seed', str(cfg['seed'] + 1),
                     '--result-filename', 'warmup.json']
    with (root / 'warmup.log').open('w') as log:
        subprocess.run(warm, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    for repeat in range(cfg['repeats']):
        order = CONCURRENCIES if repeat % 2 == 0 else CONCURRENCIES[::-1]
        for concurrency in order:
            name = f'c{concurrency}-r{repeat}'
            print(f'{engine}: {name} starting ({cfg["num_prompts"]} requests)', flush=True)
            samples, telemetry_errors = [], []
            stopped = threading.Event()

            def sample():
                while not stopped.is_set():
                    try:
                        samples.append(dict(monotonic_s=time.monotonic(), **gpu(cfg['gpu_index'])))
                    except Exception as exc:
                        telemetry_errors.append(str(exc))
                    stopped.wait(0.5)

            worker = threading.Thread(target=sample, daemon=True)
            worker.start()
            args = client + ['--num-prompts', str(cfg['num_prompts']), '--max-concurrency', str(concurrency),
                             '--result-filename', name + '.json']
            write_json(root / (name + '-command.json'), args)
            failure = None
            benchmark_start = None
            try:
                with (root / (name + '.log')).open('w') as log:
                    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, env={**os.environ, 'PYTHONUNBUFFERED': '1'})
                    timeout = threading.Timer(3600, proc.kill)
                    timeout.start()
                    try:
                        for line in proc.stdout:
                            if 'Starting main benchmark run...' in line:
                                benchmark_start = time.monotonic()
                            log.write(line)
                            log.flush()
                        if proc.wait() != 0:
                            raise RuntimeError('Benchmark client failed; see saved log')
                    finally:
                        timeout.cancel()
                        if proc.poll() is None:
                            proc.kill()
                            proc.wait(timeout=10)
                        proc.stdout.close()
            except Exception as exc:
                failure = str(exc)
            finally:
                stopped.set()
                worker.join(timeout=15)
            errors = [failure] if failure else []
            result_path = root / (name + '.json')
            if result_path.exists():
                result = json.loads(result_path.read_text())
                errors += validate(result, cfg['num_prompts'])
            else:
                result = {}
                errors.append('missing benchmark result')
            duration = result.get('duration', 0)
            active_samples = []
            if benchmark_start is not None and isinstance(duration, (int, float)) and math.isfinite(duration) and duration > 0:
                active_samples = [s for s in samples if benchmark_start <= s['monotonic_s'] <= benchmark_start + duration]
            write_json(root / (name + '-gpu.json'), dict(samples=active_samples, all_samples=samples,
                       benchmark_marker_monotonic_s=benchmark_start, reported_duration_s=duration, errors=telemetry_errors))
            if telemetry_errors or len(active_samples) < 2:
                errors.append('GPU telemetry incomplete')
            if any(s['uuid'] != metadata['gpu']['uuid'] for s in samples):
                errors.append('GPU UUID changed')
            write_json(root / (name + '-validation.json'), dict(valid=not errors, errors=errors))
            if errors:
                raise RuntimeError(f'{name}: {errors}; raw evidence saved in {root}')
            print(f'{engine}: {name} validated; TTFT={result["mean_ttft_ms"]:.2f}ms, '
                  f'output={result["output_throughput"]:.2f}tok/s', flush=True)
    print(root)


def report(roots, output):
    rows, metas = [], []
    for root in map(Path, roots):
        meta = json.loads((root / 'metadata.json').read_text())
        if meta['config']['repeats'] < 3 or meta['config']['num_prompts'] < 64:
            raise ValueError('Incomplete study: insufficient repetitions or prompts')
        metas.append(meta)
        for c in CONCURRENCIES:
            values, memories, utils = [], [], []
            for r in range(meta['config']['repeats']):
                stem = f'c{c}-r{r}'
                validation = json.loads((root / (stem + '-validation.json')).read_text())
                result = json.loads((root / (stem + '.json')).read_text())
                if not validation['valid'] or validate(result, meta['config']['num_prompts']):
                    raise ValueError(f'Refusing invalid cell {root}/{stem}')
                telemetry = json.loads((root / (stem + '-gpu.json')).read_text())
                samples = telemetry['samples']
                if telemetry['errors'] or len(samples) < 2 or any(s['uuid'] != meta['gpu']['uuid'] for s in samples):
                    raise ValueError('Invalid GPU telemetry')
                values.append(result)
                memories.append(max(s['memory.used'] for s in samples))
                utils.append(statistics.mean(s['utilization.gpu'] for s in samples))
            rows.append(dict(engine=meta['engine'], concurrency=c,
                             **{k: statistics.median(v[k] for v in values) for k in METRICS},
                             peak_memory_mib=max(memories), mean_util_pct=statistics.mean(utils)))
            for key in METRICS:
                rows[-1][key + '_min'] = min(v[key] for v in values)
                rows[-1][key + '_max'] = max(v[key] for v in values)
            rows[-1].update(peak_memory_mib_min=min(memories), peak_memory_mib_max=max(memories),
                            mean_util_pct_min=min(utils), mean_util_pct_max=max(utils))
    if len(metas) != 2 or {m['engine'] for m in metas} != {'vllm', 'sglang'}:
        raise ValueError('Report requires exactly one vLLM and one SGLang study')
    a, b = metas
    for key in ['machine', 'client_version']:
        if a[key] != b[key]:
            raise ValueError('Comparison mismatch: ' + key)
    if a.get('environment') and b.get('environment'):
        for key in ['torch', 'cuda']:
            if a['environment'][key] != b['environment'][key]:
                raise ValueError('Comparison mismatch: runtime ' + key)
    if a['gpu']['uuid'] != b['gpu']['uuid']:
        raise ValueError('Comparison mismatch: GPU UUID')
    for key in ['driver_version', 'memory.total']:
        if a['gpu'][key] != b['gpu'][key]:
            raise ValueError('Comparison mismatch: GPU ' + key)
    for key in ['model_revision', 'model_snapshot', 'seed', 'num_prompts', 'repeats', 'served_model_name']:
        if a['config'][key] != b['config'][key]:
            raise ValueError('Comparison mismatch: ' + key)
    pa = a['config']['engines']['vllm']['server_parameters']
    pb = b['config']['engines']['sglang']['server_parameters']
    if pa != pb or pa.get('prefix_cache') is not False:
        raise ValueError('Comparison mismatch: server parameters or enabled prefix cache')
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out.with_suffix('.json'), dict(metadata=metas, rows=rows))
    with out.with_suffix('.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# 001 Concurrency Study', '', 'Verified workload: input=1024, output=256; concurrency=1/8/32/64.',
             'Cell latency/throughput = median of repeated run means; GPU memory = sampled device peak.',
             'GPU samples are aligned approximately using the client main-run marker and duration; device-wide, not process-specific.',
             'This is a finite-request concurrency study, not proof of steady-state production capacity.', '',
             '| Engine | C | TTFT ms | TPOT ms | ITL ms | Output tok/s | VRAM MiB | GPU % |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append('| ' + row['engine'] + ' | ' + str(row['concurrency']) + ' | ' +
                     ' | '.join(f'{row[k]:.3f}' for k in METRICS + ['peak_memory_mib', 'mean_util_pct']) + ' |')
    lines += ['', '## Evidence and interpretation', '',
              'Raw run directories: ' + ', '.join(str(p) for p in roots),
              'Metadata and all commands are preserved; compare commits, server parameters and logs before attributing differences.',
              'This saturation workload uses synthetic random prompts and ignores EOS. It does not establish production SLA or model accuracy.',
              'Bottleneck attribution is not automatic: inspect queue/prefill/decode logs, KV pressure, GPU clocks and Windows/WSL memory pressure.',
              'A throughput plateau with increasing TTFT is a hypothesis of saturation, not proof of a specific kernel or scheduler bottleneck.',
              '', '![Output throughput](001-concurrency-study.svg)']
    out.write_text('\n'.join(lines) + '\n')
    plot_deps = Path(__file__).resolve().parent / '.report-deps'
    if plot_deps.is_dir():
        sys.path.insert(0, str(plot_deps))
    os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parent / '.mplconfig'))
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), layout='constrained')
    titles = ['TTFT (ms)', 'TPOT (ms)', 'ITL (ms)', 'Output throughput (tok/s)',
              'Sampled peak device memory (MiB)', 'Mean device GPU utilization (%)']
    for axis, key, title in zip(axes.flat, METRICS + ['peak_memory_mib', 'mean_util_pct'], titles):
        for engine in ['vllm', 'sglang']:
            series = sorted((r for r in rows if r['engine'] == engine), key=lambda r: r['concurrency'])
            axis.errorbar([r['concurrency'] for r in series], [r[key] for r in series],
                          yerr=[[max(0, r[key] - r[key+'_min']) for r in series],
                                [max(0, r[key+'_max'] - r[key]) for r in series]],
                          marker='o', capsize=3, label=engine)
        axis.set_xscale('log', base=2)
        axis.set_xticks(CONCURRENCIES, [str(c) for c in CONCURRENCIES])
        axis.set_xlabel('Concurrency cap')
        axis.set_title(title)
        axis.set_ylim(bottom=0)
        if key == 'mean_util_pct':
            axis.set_ylim(0, 100)
        if key == 'peak_memory_mib':
            axis.set_ylim(0, max(max(m['gpu']['memory.total'] for m in metas),
                                 max(r['peak_memory_mib_max'] for r in rows) * 1.05))
        axis.grid(alpha=0.25)
    axes.flat[0].legend()
    fig.suptitle('1024 input / 256 output; error bars = repeated-run range, not confidence intervals')
    fig.savefig(out.with_suffix('.svg'))
    svg = out.with_suffix('.svg')
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    fig.savefig(out.with_suffix('.png'), dpi=180)
    plt.close(fig)
    print(out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run')
    run.add_argument('config')
    run.add_argument('--engine', choices=['vllm', 'sglang'], required=True)
    render = sub.add_parser('report')
    render.add_argument('runs', nargs=2)
    render.add_argument('--output', default='reports/001-concurrency-study.md')
    args = parser.parse_args()
    if args.action == 'run':
        collect(json.loads(Path(args.config).read_text()), args.engine)
    else:
        report(args.runs, args.output)
