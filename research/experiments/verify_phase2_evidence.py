import hashlib
import json
from pathlib import Path

root = Path('/home/dcl/projects/llm-serving-benchmark-lab')
run = root/'research/experiments/results/phase2-20261012T145433Z'
load = lambda p: json.loads(p.read_text())
meta = load(run/'metadata-preflight.json')
assert meta['status'] == 'completed'
for name, digest in meta['core_sha256'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest
preflight = [load(p) for p in run.glob('preflight-r*-trace-*/requests.json')]
assert len(preflight) == 6 and sum(len(rs) for rs in preflight) == 48
traced = 0
for rows in preflight:
    for r in rows:
        assert r['success'] and r['input_tokens'] == 512 and r['output_tokens'] == 128
        if r['native_metrics']:
            assert r['response_header_request_id'] == r['request_id']
            assert r['sse_response_ids'] == ['cmpl-'+r['request_id']]
            traced += 1
assert traced == 24
summaries = list(run.glob('cache-expand-*/episode-*/summary.json'))
assert len(summaries) == 5
for p in summaries:
    summary = load(p)
    assert summary['requests'] == 8
    for stage in ('queue','prefill','decode'):
        assert abs(summary[stage+'_reconciliation_ms']) < 5
    rows = load(p.parent/'requests.json')
    assert len(rows) == 8 and all(r['success'] for r in rows)
assert not (root/'.benchmark.lock').exists()
analysis = load(run/'phase2-descriptive-analysis.json')
assert len(analysis['cells']) == 1
assert analysis['cells'][0]['requests'] == 40 and not analysis['cells'][0]['graded_level_completed']
assert load(run/'metadata-cache-expand.json')['status'] == 'hold_environment_confounding'
manifest = {str(p.relative_to(root/'research/experiments/results')):
            hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in ('phase2-20261012T101158Z','phase2-20261012T101552Z','phase2-20261012T145433Z')
            for p in (root/'research/experiments/results'/directory).rglob('*')
            if p.is_file() and p.name not in ('integrity-manifest.json','verification.log')}
(run/'integrity-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(f'PASS: 48 preflight + 40 complete quarantined pilot; 64 native request IDs checked; {len(manifest)} evidence files hashed; core unchanged; graded/mixed work NOT completed.')
