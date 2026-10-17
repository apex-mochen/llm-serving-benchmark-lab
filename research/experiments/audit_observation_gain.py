"""Offline evidence audit; no classifier, diagnosis rules or GPU execution."""
import argparse
import datetime as dt
import hashlib
import itertools
import json
from pathlib import Path
import statistics


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(a, b):
    return abs(a-b)/max(abs(a), abs(b), 1e-12)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    source = args.root/'research/experiments/results/signatures-20261012T053318Z'
    aggregate = source/'aggregate.json'
    cells = json.loads(aggregate.read_text())
    files = {str(aggregate.relative_to(args.root)): digest(aggregate)}
    grouped = {}
    requests = 0
    stage_request_records = 0
    stage_aggregate_cells = 0
    errors = []
    effective = ('input_length', 'output_length', 'concurrency', 'arrival_rate', 'cache_state')
    features = ('mean_ttft_ms', 'mean_tpot_ms', 'p95_e2e_ms', 'mean_client_queue_ms',
                'queue_mean_ms', 'prefill_mean_ms', 'decode_mean_ms',
                'gpu_utilization_mean_pct', 'gpu_memory_peak_mib')
    for cell in cells:
        folder = source/f"{cell['group']}-{cell['level']}-r{cell['repeat']}"
        path = folder/'requests.json'
        files[str(path.relative_to(args.root))] = digest(path)
        rows = json.loads(path.read_text())
        requests += len(rows)
        if not all(row.get('success') for row in rows):
            errors.append(str(path)+': failed requests')
        for raw, summary in (('ttft_s', 'mean_ttft_ms'), ('tpot_s', 'mean_tpot_ms'),
                             ('client_queue_s', 'mean_client_queue_ms')):
            observed = statistics.mean(row[raw] for row in rows)*1000
            if not abs(observed-cell[summary]) < 1e-6:
                errors.append(str(path)+': '+summary+' mismatch')
        stage_request_records += sum(isinstance(row.get('native_metrics'), dict) for row in rows)
        stage_aggregate_cells += all(cell.get(k) is not None for k in
                                     ('queue_mean_ms', 'prefill_mean_ms', 'decode_mean_ms'))
        key = (cell['group'], str(cell['level']))
        grouped.setdefault(key, []).append(cell)
    conditions = []
    for key, repeats in sorted(grouped.items()):
        item = dict(name='/'.join(key), repeats=len(repeats),
                    effective_configuration={k: repeats[0][k] for k in effective},
                    symptom_and_observation_medians={})
        for field in features:
            values = [row[field] for row in repeats if row.get(field) is not None]
            item['symptom_and_observation_medians'][field] = statistics.median(values) if values else None
        conditions.append(item)
    pairs = []
    # Exploratory screen only. A different group name is NOT a different cause.
    # Do not pick the tolerance using stage/resource separability.
    for left, right in itertools.combinations(conditions, 2):
        a, b = left['effective_configuration'], right['effective_configuration']
        if a == b or a['cache_state'] != b['cache_state'] or a['output_length'] != b['output_length']:
            continue
        x, y = left['symptom_and_observation_medians'], right['symptom_and_observation_medians']
        gaps = {k: relative(x[k], y[k]) for k in ('mean_ttft_ms', 'mean_tpot_ms', 'p95_e2e_ms')}
        if max(gaps.values()) <= .2:
            pairs.append(dict(left=left['name'], right=right['name'], symptom_relative_gaps=gaps,
                              left_observations=x, right_observations=y,
                              interpretation='candidate workload similarity; no ground-truth cause'))
    traces = args.root/'research/experiments/results/trace-revalidation-v2-20261013T121015Z'
    native_configs = set()
    native_count = 0
    for path in sorted(traces.glob('on-r*/episode-*.json')):
        files[str(path.relative_to(args.root))] = digest(path)
        for row in json.loads(path.read_text())['requests']:
            if row.get('native_metrics'):
                native_count += 1
                native_configs.add((row['input_tokens'], row['output_tokens']))
    verdict = dict(
        status='INSUFFICIENT_EVIDENCE',
        hypothesis='Stage/resource observations reduce misdiagnosis under similar aggregate symptoms',
        supported=None, refuted=None, diagnostic_accuracy=None,
        reasons=['Phase1 has aggregate stages but no linked per-request stage measurements',
                 'Trace v2 remains HOLD and covers only one input/output workload setting',
                 'Workload group names are interventions, not verified mechanism labels',
                 'No held-out, independent labelled diagnosis trials exist'],
        new_gpu_experiment_executed=False, classifier_or_diagnosis_algorithm_built=False,
        warning='Symptom screen is retrospective, eight requests/cell; P95 is descriptive, not robust tail evidence')
    output = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), source_sha256=files,
                  scope='offline audit of historical real-GPU synthetic workload records',
                  cells=len(cells), requests=requests, conditions=conditions,
                  per_request_stage_records_in_phase1=stage_request_records,
                  cells_with_aggregate_stages=stage_aggregate_cells,
                  trace_v2_native_measurement_requests=native_count,
                  trace_v2_input_output_settings=sorted(native_configs),
                  exploration_tolerance=.2, similar_symptom_candidates=pairs,
                  integrity_errors=errors, verdict=verdict)
    (args.out/'audit.json').write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps(dict(cells=len(cells), requests=requests, candidate_pairs=len(pairs),
                          integrity_errors=errors, status=verdict['status'])))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
