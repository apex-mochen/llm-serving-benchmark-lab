"""Descriptive statistics only. Never creates missing measurements."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import statistics
import numpy as np


def load(p):
    return json.loads(p.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    cells = []
    for directory in sorted(run.iterdir()):
        if not (directory / 'configuration.json').exists():
            continue
        cfg = load(directory / 'configuration.json')
        episodes = []
        for episode in sorted(directory.glob('episode-*')):
            if not episode.is_dir() or not (episode / 'summary.json').exists():
                continue
            requests = load(episode / 'requests.json')
            assert len(requests) == 8 and all(r['success'] for r in requests)
            assert all(r['response_header_request_id'] == r['request_id'] and
                       r['sse_response_ids'] == ['cmpl-' + r['request_id']] for r in requests)
            episodes.append((episode, requests, load(episode / 'summary.json')))
        completed = len(episodes) * 8
        levels = (completed,) if 0 < completed < 64 else (64, 256, 1024)
        for n in levels:
            if len(episodes) * 8 < n:
                continue
            selected = episodes[:n // 8]
            rows = [r for _, rs, _ in selected for r in rs]
            result = dict(configuration=cfg, requests=n, episode_count=len(selected),
                          graded_level_completed=n in (64, 256, 1024),
                          nested_prefix=True, directory=directory.name, metrics={})
            for key in ('ttft_ms', 'tpot_ms', 'e2e_ms', 'planned_e2e_ms',
                        'client_queue_ms', 'queue_ms', 'prefill_ms', 'decode_ms'):
                values = np.array([r[key] for r in rows])
                result['metrics'][key] = dict(mean=float(values.mean()), **{
                    f'p{p}': float(np.percentile(values, p)) for p in (50, 95, 99)})
            # Conditional uncertainty: resample entire episodes, never independent requests.
            rng = np.random.default_rng(20261012)
            blocks = np.array([[r['e2e_ms'] for r in rs] for _, rs, _ in selected])
            tails = []
            for _ in range(1000):
                boot = blocks[rng.integers(0, len(blocks), len(blocks))].reshape(-1)
                tails.append(float(np.percentile(boot, 99)))
            lower, upper = np.percentile(tails, (2.5, 97.5))
            point = result['metrics']['e2e_ms']['p99']
            result['conditional_episode_bootstrap_p99'] = dict(lower_ms=float(lower), upper_ms=float(upper),
                relative_halfwidth=float((upper-lower)/2/point), samples=1000,
                limitation='Conditional on this repeat; not an across-run confidence interval.')
            duration = sum(s['duration_s'] for _, _, s in selected)
            result['measurement_duration_s'] = duration
            result['requests_per_s'] = n / duration
            result['output_tokens_per_s'] = sum(r['output_tokens'] for r in rows) / duration
            result['prefix_hits'] = sum(s.get('prefix_cache_hits_total_delta') or 0 for _, _, s in selected)
            result['prefix_queries'] = sum(s.get('prefix_cache_queries_total_delta') or 0 for _, _, s in selected)
            result['prefix_hit_token_ratio'] = result['prefix_hits'] / result['prefix_queries'] if result['prefix_queries'] else None
            result['preemptions'] = sum(s.get('num_preemptions_total_delta') or 0 for _, _, s in selected)
            samples = [s for p, _, _ in selected for s in load(p / 'gpu.json') if 'error' not in s]
            result['gpu'] = {key: dict(mean=statistics.mean(s[key] for s in samples),
                                      max=max(s[key] for s in samples))
                             for key in ('memory.used', 'utilization.gpu') if samples and all(key in s for s in samples)}
            server = [s for p, _, _ in selected for s in load(p / 'server.json') if 'metrics' in s]
            keys = {k for s in server for k in s['metrics']}
            result['server_sample_max'] = {k: max(s['metrics'].get(k, 0) for s in server) for k in keys}
            cells.append(result)
    statuses = {p.stem: load(p) for p in run.glob('metadata-*.json') if not p.stem.endswith('-interrupted-original')}
    statuses.update({p.stem: load(p) for p in run.glob('status-*.json')})
    preflight = load(run/'preflight-result.json') if (run/'preflight-result.json').exists() else None
    value = dict(generated_utc=dt.datetime.now(dt.timezone.utc).isoformat(), run=str(run),
                 statuses=statuses, preflight=preflight, cells=cells)
    (run/'phase2-descriptive-analysis.json').write_text(json.dumps(value, indent=2))
    physical = sum(1 for p in run.glob('*/episode-*/summary.json')) * 8
    report = ['# Bottleneck Diagnosis Phase 2 Result', '',
              '状态：仅报告已保存的真实数据；未完成项目明确标记，不将 CPU 测试或旧 Phase 1 数据充作新结果。', '',
              f'运行目录：`{run.name}`；正式扩样/矩阵请求数：{physical}；预检请求单列。', '',
              '## 配置与测量边界', '',
              'RTX4060 Laptop / Qwen2.5-0.5B-Instruct 固定 snapshot / vLLM 0.30.0，FP16、TP1、max_model_len2048、max_num_seqs4、max_num_batched_tokens2048、eager、chunked prefill。原始 server-config、metadata、workload、requests、GPU/server 采样和日志均随运行保存。', '',
              '固定8请求episode，根到达率4/s，output128；episode间排空，cold/warm每episode重置，warm独立preload。64/256/1024为同一运行累积前缀，不能作为三个独立实验。', '',
              'queue=queued→scheduled；prefill=scheduled→first output token；decode=first→last output token。prefill是vLLM逻辑阶段，非纯GPU kernel时间。client TTFT=send→first非空内容；client TPOT=(last-first)/(output_tokens-1)，客户端chunk时间不是原生token ITL。GPU指标为设备级，包含桌面活动。吞吐分母为正式episode时长之和，排除启动/warmup/reset/preload和间隔。', '',
              '## Trace 预检', '',
              '```json', json.dumps(preflight, indent=2, ensure_ascii=False), '```', '',
              '## 执行状态', '',
              '| 模式 | 状态 |', '|---|---|']
    report += [f'| {name} | {data["status"]} |' for name, data in sorted(statuses.items())]
    report += ['', '## 数据', '',
               '| 条件/重复 | 请求 | TTFT P50 ms | TPOT P50 ms | E2E P95/P99 ms | queue/prefill/decode 均值 ms | req/s | cache hit-token ratio |',
               '|---|---:|---:|---:|---|---|---:|---|']
    for c in cells:
        m = c['metrics']
        report.append(f'| {c["directory"]} | {c["requests"]} | {m["ttft_ms"]["p50"]:.2f} | {m["tpot_ms"]["p50"]:.2f} | {m["e2e_ms"]["p95"]:.2f}/{m["e2e_ms"]["p99"]:.2f} | '+
            '/'.join(f'{m[k]["mean"]:.2f}' for k in ('queue_ms','prefill_ms','decode_ms'))+
            f' | {c["requests_per_s"]:.3f} | {c["prefix_hit_token_ratio"]} |')
    report += ['', '完整P50/P95/P99、planned E2E、GPU均值/峰值、KV gauge、preemptions及每cell条件性episode bootstrap区间见 `phase2-descriptive-analysis.json`。Bootstrap固定seed20261012、1000次整episode重采样；不把请求视为独立样本，不把条件性区间当作跨重复稳定性证据。', '',
               '## 阶段判断', '',
               '必须在扩样和两个矩阵完成后，结合重复间效应、尾部区间及混合条件再判断解释能力和可区分性。原生阶段分解本身是已有vLLM能力，不是研究创新；变量干预响应不是根因真值。当前不开发自动归因。']
    target = run/'DESCRIPTIVE_STATISTICS.md'
    target.write_text('\n'.join(report)+'\n')
    print(f'ANALYZED={physical}; REPORT={target}')


if __name__ == '__main__':
    main()
