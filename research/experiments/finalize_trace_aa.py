"""Audit an A/A run without turning partial pairs into a completed control."""
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path('/home/dcl/projects/llm-serving-benchmark-lab')
sys.path.insert(0, str(ROOT/'research/experiments'))
import run_trace_revalidation as old


def main():
    run = Path(sys.argv[1]).resolve()
    assert run.is_relative_to(ROOT/'research/experiments/results')
    outcome = json.loads((run/'outcome.json').read_text())
    spec = json.loads((run/'specification.json').read_text())
    payload = json.loads((run/'fixed-payload.json').read_text())
    count = warmup = 0; ids = set(); complete = []; commands = []; warnings = []; errors = []
    for directory in sorted(run.glob('[AB]-r[0-2]')):
        commands.append(json.loads((directory/'command.json').read_text()))
        episodes = []
        for path in sorted(directory.glob('episode-*.json')):
            value = json.loads(path.read_text()); rr = value['requests']; assert len(rr) == 8
            for row in rr:
                assert row['success'] and row['native_metrics'] is None
                assert row['request_id'] not in ids; ids.add(row['request_id'])
                assert row['usage']['prompt_tokens'] == 512 and row['usage']['completion_tokens'] == 128
                assert row['prompt_sha256'] == hashlib.sha256(json.dumps(payload[row['index']]).encode()).hexdigest()
                assert abs(row['ttft_ms']-(row['first_content_s']-row['sent_s'])*1000) < 1e-6
                assert abs(row['tpot_ms']-(row['last_content_s']-row['first_content_s'])*1000/127) < 1e-6
                assert abs(row['e2e_ms']-(row['end_s']-row['sent_s'])*1000) < 1e-6
                count += 1
            episodes.append(dict(duration_s=value['duration_s'], **{f'mean_{k}_ms':statistics.mean(r[f'{k}_ms'] for r in rr) for k in ('ttft','tpot','e2e')}))
        if len(episodes) == 8:
            complete.append(dict(variant=directory.name[0],repeat=int(directory.name[-1]),summary=old.summarize(episodes)))
        if (directory/'warmup.json').exists():
            rr = json.loads((directory/'warmup.json').read_text())['requests']; warmup += len(rr)
            assert all(r['success'] and r['native_metrics'] is None for r in rr)
        log = (directory/'server.log').read_text(errors='replace')
        if 'leaked semaphore' in log: warnings.append(directory.name+': semaphore warning')
        if any(t in log for t in ('OutOfMemoryError','CUDA out of memory','memory allocation failed with OOM')): errors.append(directory.name+': OOM')
    assert all(command == commands[0] for command in commands)
    assert not any(x in commands[0]['argv'] for x in old.FLAGS['metrics']+old.FLAGS['headers']+old.FLAGS['details'])
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n,h in spec['core_sha256'].items())
    comparison = old.compare(complete, 'A', 'B') if len(complete) == 6 else {}
    for value in comparison.values():
        value['median_absolute_deviation_percent'] = statistics.median(abs(x) for x in value['paired_overhead_percent'])
    if comparison: assert comparison == json.loads((run/'comparison.json').read_text())
    samples = [json.loads(x) for x in (run/'resources.jsonl').read_text().splitlines()]
    contaminated = [s for s in samples if s.get('violations')]
    metrics = ('mean_ttft_ms','mean_tpot_ms','mean_e2e_ms','requests_per_s','output_tokens_per_s')
    pooled_cv = {k:statistics.stdev(r['summary'][k] for r in complete)/statistics.mean(r['summary'][k] for r in complete) for k in metrics} if len(complete)>1 else {}
    audit = dict(requests=count,warmup_requests=warmup,complete_variants=len(complete),commands_identical=True,
        all_saved_requests_trace_off=True,errors=errors,warnings=warnings,comparison=comparison,
        run_to_run_cv_all_complete_runs=pooled_cv,resource_samples=len(samples),contaminated_samples=len(contaminated),
        outcome=outcome,verdict=outcome['status'] if not errors else 'HOLD')
    (run/'offline-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    table = '\n'.join('| '+k+' | '+' / '.join(f'{x:.3f}' for x in v['paired_overhead_percent'])+f" | {v['median_absolute_deviation_percent']:.3f} |" for k,v in comparison.items())
    cv_text = '\n'.join(f'- {k}: {v:.3%}' for k,v in pooled_cv.items())
    report = f'''# A/A负控实际结果

日期2026-10-15；运行`{run.name}`；阶段 **{audit['verdict']}**。

## 设置与证据

RTX4060 Laptop / Qwen2.5-0.5B / vLLM，FP16/eager、cache OFF、chunked prefill、512/128 tokens、cap8、4 requests/s、每组8×8请求、8预热单列，三轮A-B/B-A/A-B。两组均trace OFF、stats ON，共用同采样器。已从实际command.json核查各组argv/cwd/环境覆盖一致，全部已保存请求native_metrics均为空；固定payload、usage、唯一ID和client公式已复算，核心hash未变。

实际保存{count}测量请求、{warmup}预热单列、完整组{len(complete)}/6，资源采样{len(samples)}条、检测污染采样{len(contaminated)}条。原始outcome错误：`{outcome['error']}`。审核错误：{errors}。记录污染：{outcome['observed_interference']}。

## 运行差异

以下表仅在6组完整时生成；不从残缺/受污染运行挑出一对冒充完成。带符号延迟差异=(B/A−1)×100，吞吐差异=(1−B/A)×100；负值不是优化收益。验收看绝对差异，各指标绝对配对差异中位数<5%，并要求逐轮绝对值<5%。该门是操作筛查，不是统计等价检验。

| 指标 | 三轮带符号差异 % | 绝对差异中位 % |
| --- | --- | --- |
{table if table else '| 未形成完整三轮 | N/A | N/A |'}

完整组均值的运行间CV（仅描述，受污染或不完整时不作为有效稳定性结论）：
{cv_text}

吞吐分母为8个episode时长之和，不含启动/预热/组间采样；不能当连续饱和吞吐。请求不是独立重复，三对也不足证明等价。比较较早ON/OFF时存在时间与环境差异，A/A不能直接扣除为trace净开销。

## 解释与停止边界

若检测污染或组数不足，只能说明本次负控未完成；若完整且绝对差异超门，则说明在本协议下运行波动仍不可忽略，不证明具体host/GPU根因；若通过，也不替代trace开销门和正式诊断对照。semaphore日志警告：{warnings}，不宣称无host泄漏。完整继承环境与输出文本/SSE未存，准确环境重放仍有边界。没有训练或诊断算法，没有核心改动。

## 阶段审查

1. 本阶段实际完成了什么：本目录真实运行与离线审计，数量见上。
2. 原目标 vs 实际结果：检验同设置运行波动，不把未完成结果当通过。
3. Correctness Review：已核查命令/trace OFF/payload/计时；未验证GPU kernel精度；风险为背景变化。
4. Architecture Review：复用v3低成本；重启/采样仍可扰动；隔离环境为替代。
5. Performance Review：只报告A/A差异，不声称优化。
6. Bottleneck Analysis：波动/污染→候选运行环境→单一可控复核→成立才修正。
7. 10× Scale Test：未开展，不能用扩样替代控制。
8. Alternative Design：当前外部配对维护低/内存低/成本低/可重跑；A长进程内交错窗口减少重启但改变边界、维护中；B隔离机器资源控制较好但迁移成本高且硬件不同。新性能未测。
9. Optimization Opportunities：P0若HOLD先恢复可控环境；P1再检查计量；P2正式诊断暂不做；P3算法Parking Lot。
10. 与基础知识的联系：负控、绝对偏差、run重复与选择偏差。
11. 与其他开源项目的联系：原生vLLM接口，无上游修改。
12. 新产生的想法：可验证观测窗口/运行顺序；其余Parking Lot。
13. Resume Value Review：负控证据，不写收益或准确率。
14. Interview Review：为何相同命令仍波动？为何不用请求作重复？如何判外部编译？负值如何解释？为何不扣A/A得到净效应？
15. Failure / Mistake Review：旧预检与中断保留；不跨run拼接。
16. 独立能力检查：A Codex执行；B用户理解未验收；C独立实验能力未评；D无创新成立声明。
17. 下一步最有价值实验：若HOLD仅选择恢复静默或核查固定运行窗口的一项计量补救，先看本次具体结果再冻结协议；30–120分钟启动窗口非完成保证，不进入诊断。
18. 是否允许进入下一阶段：本轮仅负控结论，不自动开展正式对照；实际门见上。
'''
    (run/'TRACE_AA_CONTROL_MEASURED_RESULT.md').write_text(report)
    print(json.dumps({k:audit[k] for k in ('requests','warmup_requests','complete_variants','commands_identical','contaminated_samples','verdict')}))


if __name__ == '__main__': main()
