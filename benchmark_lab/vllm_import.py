"""Import `vllm bench serve --save-result` JSON as hash-addressed, re-verifiable evidence.

The original bytes are copied unchanged into imports/<id>/result.json. Nothing is trusted
from provenance.json at read time: the catalog re-hashes and re-inspects the result.
"""
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

from tail_report import percentile, summarize

SCHEMA = 'vllm-bench-serve-result'
MANIFEST = 'imports/manifest.json'
# Kept by `vllm bench serve` only with --save-detailed (vllm/benchmarks/serve.py).
DETAILED = ('ttfts', 'errors', 'start_times', 'queue_times', 'latencies')
REPORTED = ('mean_ttft_ms', 'mean_tpot_ms', 'output_throughput', 'request_throughput')


class ImportRejected(ValueError):
    pass


def finite(value, positive=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def close(a, b):
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))


def inspect(result):
    """Validate one result; return (detail_level, checks). Raises ImportRejected."""
    if not isinstance(result, dict):
        raise ImportRejected('Result must be a JSON object')
    completed, prompts = result.get('completed'), result.get('num_prompts')
    if type(completed) is not int or completed <= 0 or completed != prompts:
        raise ImportRejected('completed must equal num_prompts (> 0); partial batches are not indexed')
    if result.get('failed', 0) != 0:
        raise ImportRejected('Run reports failed requests; failures are not hidden in latency tails')
    if not finite(result.get('duration'), positive=True):
        raise ImportRejected('Invalid duration')
    for key in REPORTED:
        if not finite(result.get(key), positive=True):
            raise ImportRejected('Missing or invalid reported metric: ' + key)
    latencies = result.get('latencies')
    if not isinstance(latencies, list) or len(latencies) != completed or not all(map(finite, latencies)):
        raise ImportRejected('latencies must hold one finite value per completed request')
    concurrency = result.get('max_concurrency')
    if concurrency is not None and (type(concurrency) is not int or concurrency <= 0):
        raise ImportRejected('max_concurrency must be a positive integer or null')
    checks = ['completed == num_prompts and failed == 0',
              f'{completed} finite per-request latencies present']
    if not all(key in result for key in DETAILED):
        return 'summary', checks + ['Saved without --save-detailed: per-request TTFT/errors unavailable']
    try:
        summarize(result, completed)
    except ValueError as exc:
        raise ImportRejected('Per-request evidence rejected: ' + str(exc)) from exc
    ttfts = result['ttfts']
    pairs = [('mean_ttft_ms', sum(ttfts) / len(ttfts) * 1000)]
    pairs += [(f'p{p}_ttft_ms', percentile(ttfts, p) * 1000) for p in (50, 95, 99)
              if f'p{p}_ttft_ms' in result]
    for key, recomputed in pairs:
        if not close(result[key], recomputed):
            raise ImportRejected(f'Reported {key}={result[key]} disagrees with per-request data ({recomputed})')
    checks.append('Recomputed from per-request data: ' + ', '.join(k for k, _ in pairs))
    return 'detailed', checks


def load_manifest(root):
    path = Path(root) / MANIFEST
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def import_file(root, source, engine, label=None, now=None):
    """Copy a verified result into imports/; returns a summary dict. Never edits the source."""
    root, source = Path(root).resolve(), Path(source)
    if engine not in ('vllm', 'sglang'):
        raise ImportRejected('engine must be vllm or sglang (the server that was benchmarked)')
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    baseline = json.loads((root / 'reports/001-raw-sha256.json').read_text(encoding='utf-8'))
    if digest in baseline.values():
        raise ImportRejected('Identical bytes are already part of the historical baseline')
    try:
        result = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportRejected('Not valid JSON: ' + str(exc)) from exc
    level, checks = inspect(result)
    run_id = 'imp-' + digest[:16]
    folder = f'imports/{run_id}'
    manifest = load_manifest(root)
    if f'{folder}/result.json' in manifest:
        return dict(id=run_id, status='already_imported', sha256=digest)
    provenance = dict(
        schema=SCHEMA, id=run_id, source_name=source.name, sha256=digest, bytes=len(data),
        imported_utc=(now or dt.datetime.now(dt.timezone.utc)).isoformat(),
        declared=dict(engine=engine, label=label),
        detail_level=level, checks=checks,
        reported=dict((k, result.get(k)) for k in (
            'date', 'backend', 'endpoint_type', 'model_id', 'num_prompts',
            'request_rate', 'burstiness', 'max_concurrency', 'duration')),
        limitations=['Model, hardware and engine version are not contained in the result file and are not verified.',
                     'Engine is declared by the importer, not detected.'])
    provenance_bytes = (json.dumps(provenance, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    write_atomic(root / folder / 'result.json', data)
    write_atomic(root / folder / 'provenance.json', provenance_bytes)
    if hashlib.sha256((root / folder / 'result.json').read_bytes()).hexdigest() != digest:
        raise ImportRejected('Copied bytes do not match the source hash')
    manifest[f'{folder}/result.json'] = digest
    manifest[f'{folder}/provenance.json'] = hashlib.sha256(provenance_bytes).hexdigest()
    write_atomic(root / MANIFEST, (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8'))
    return dict(id=run_id, status='imported', sha256=digest, detail_level=level, checks=checks)
