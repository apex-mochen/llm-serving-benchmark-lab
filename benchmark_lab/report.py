"""Markdown evidence report for the current filtered view. Read-only; no inference."""
import hashlib
import statistics

from . import vllm_import

METRICS = (('mean_ttft_ms', '平均 TTFT', 'ms'), ('mean_tpot_ms', '平均 TPOT', 'ms'),
           ('output_tokens_per_s', '输出吞吐', 'tokens/s'))
ENGINE_NAMES = {'vllm': 'vLLM', 'sglang': 'SGLang'}


def compare_groups(runs, field):
    """Same rule as the browser: baseline repeats of one configuration are the noise reference;
    only non-overlapping min-max ranges count as a difference beyond repeat variation."""
    base = [r for r in runs if r['kind'] == 'baseline']
    rows = []
    for concurrency in sorted({r['concurrency'] for r in base}):
        groups = {e: [r[field] for r in base if r['engine'] == e and r['concurrency'] == concurrency]
                  for e in ('vllm', 'sglang')}
        a, b = groups['vllm'], groups['sglang']
        if not a or not b:
            continue
        separated = max(a) < min(b) or max(b) < min(a)
        rows.append(dict(concurrency=concurrency, separated=separated,
            ratio=statistics.median(a) / statistics.median(b),
            vllm=dict(median=statistics.median(a), min=min(a), max=max(a), n=len(a)),
            sglang=dict(median=statistics.median(b), min=min(b), max=max(b), n=len(b))))
    return rows


def number(value):
    return f'{value:,.2f}'


def table(head, rows):
    lines = ['| ' + ' | '.join(head) + ' |', '| ' + ' | '.join('---' for _ in head) + ' |']
    lines += ['| ' + ' | '.join(str(cell) for cell in row) + ' |' for row in rows]
    return lines


def render(root, runs, filters, generated_utc):
    baseline_manifest = (root / 'reports/001-raw-sha256.json').read_bytes()
    imported = vllm_import.load_manifest(root)
    scope = '，'.join(f'{k}={v}' for k, v in filters.items() if v is not None) or '全部数据'
    text = ['# 证据报告：LLM 推理服务性能对比', '',
        f'- 生成时间（UTC）：{generated_utc}',
        f'- 数据范围：{scope}',
        f'- 运行数：{len(runs)}；请求数：{sum(r["requests"] for r in runs):,}',
        f'- 历史基线清单 `reports/001-raw-sha256.json` 的 SHA256：`{hashlib.sha256(baseline_manifest).hexdigest()}`',
        f'- 本机导入结果：{sum(1 for k in imported if k.endswith("/result.json"))} 个（`imports/manifest.json`，不随仓库发布）',
        '- 生成方式：只读取已校验的原始文件并重新计算，没有启动模型或发起推理请求。', '',
        '## 结论边界', '',
        '- 历史基线来自单机实验（RTX 4060 Laptop，Qwen2.5-0.5B），每个配置 3 次重复、每次 64 个请求；不代表线上稳态容量。',
        '- 引擎比较是描述性判断，不是显著性检验；结论只适用于这组模型、硬件和配置。',
        '- 客户端等待不等于服务端调度排队；P99 只作描述。',
        '- 导入结果不含模型、硬件和引擎版本，引擎类型由导入者声明，不并入基线比较。', '']
    text += ['## 引擎差异是否超过重复波动', '',
        '同一配置重复运行的最小–最大范围作为噪声参照：两组范围不重叠才写“差异超出重复波动”，重叠则写“不判定快慢”。', '']
    for field, title, unit in METRICS:
        rows = compare_groups(runs, field)
        text.append(f'### {title}（{unit}）')
        text.append('')
        if not rows:
            text += ['当前数据范围内没有同一并发下同时包含 vLLM 和 SGLang 的历史基线。', '']
            continue
        span = lambda g: f'{number(g["median"])} [{number(g["min"])}–{number(g["max"])}]'
        text += table(['并发', '判断', '比值 vLLM/SGLang', 'vLLM 中位 [范围]', 'SGLang 中位 [范围]'],
            [(f'C{r["concurrency"]}', '差异超出重复波动' if r['separated'] else '范围重叠 · 不判定快慢',
              f'{r["ratio"]:.2f}', span(r['vllm']), span(r['sglang'])) for r in rows])
        text.append('')
    text += ['## 运行明细', '',
        '每行对应一个原始结果文件；SHA256 可用 `sha256sum` 对仓库中的文件复核。', '']
    text += table(['来源', '引擎', '并发', '重复/标签', 'TTFT 均值 ms', 'TPOT 均值 ms', '输出 tokens/s', 'E2E P99 ms', '原始文件', 'SHA256'],
        [('基线' if r['kind'] == 'baseline' else '导入', ENGINE_NAMES[r['engine']], r['concurrency'] if r['concurrency'] is not None else '—',
          f'#{r["repeat"] + 1}' if r['kind'] == 'baseline' else (r.get('label') or '—'),
          number(r['mean_ttft_ms']), number(r['mean_tpot_ms']), number(r['output_tokens_per_s']),
          number(r['p99_latency_ms']), f'`{r["source"]}`', f'`{r["source_sha256"]}`') for r in runs])
    text += ['', '## 指标口径', '',
        '- 客户端等待：请求到达压测客户端 → 发出（含客户端并发上限排队和逐个发请求的延迟）。',
        '- TTFT：发出 → 第一个输出 token；E2E：发出 → 最后一个 token。',
        '- TPOT：每个请求 (E2E − TTFT) ÷ (输出 token 数 − 1)，再在请求间取平均。',
        '- 输出吞吐：全部输出 token ÷ 整批时长。',
        '- 依据：vLLM 源码 `vllm/benchmarks/lib/endpoint_request_func.py` 与 `vllm/benchmarks/serve.py`。', '',
        '## 如何复核', '',
        '```bash',
        'python scripts/check-demo-data.py      # 重新核对 128 个原始文件哈希与 24 次运行的数值',
        'python -m unittest discover -s tests   # CPU 单元测试',
        '```', '']
    return '\n'.join(text)
