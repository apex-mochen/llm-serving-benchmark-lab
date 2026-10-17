"""Offline verification/reporting of a completed v3 trace remediation run."""
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
    spec = json.loads((run/'specification.json').read_text())
    outcome = json.loads((run/'outcome.json').read_text())
    rows = []; errors = []; measured = 0; native = 0; warmup = 0; request_ids = set()
    payload = json.loads((run/'fixed-payload.json').read_text())
    warnings = []; summaries = []
    for directory in sorted(run.glob('*-r[0-2]')):
        episodes = []
        traced = directory.name.startswith('on-')
        for path in sorted(directory.glob('episode-*.json')):
            data = json.loads(path.read_text()); rr = data['requests']
            assert len(rr) == 8
            for r in rr:
                assert r['success'] and r['usage']['prompt_tokens'] == 512 and r['usage']['completion_tokens'] == 128
                assert r['request_id'] not in request_ids
                request_ids.add(r['request_id'])
                assert r['prompt_sha256'] == hashlib.sha256(json.dumps(payload[r['index']]).encode()).hexdigest()
                assert abs(r['ttft_ms']-(r['first_content_s']-r['sent_s'])*1000) < 1e-6
                assert abs(r['tpot_ms']-(r['last_content_s']-r['first_content_s'])*1000/127) < 1e-6
                assert abs(r['e2e_ms']-(r['end_s']-r['sent_s'])*1000) < 1e-6
                if traced:
                    old.existing.validate_native(r['native_metrics'], 128)
                    assert r['request_id'] == r['response_header_request_id']
                    native += 1
                else:
                    assert r['native_metrics'] is None
                measured += 1
            episodes.append(dict(duration_s=data['duration_s'], **{f'mean_{k}_ms':statistics.mean(r[f'{k}_ms'] for r in rr) for k in ('ttft','tpot','e2e')}))
        if len(episodes) == 8:
            rows.append(dict(variant='full' if traced else 'off', repeat=int(directory.name[-1]), summary=old.summarize(episodes)))
        warm = directory/'warmup.json'
        if warm.exists(): warmup += len(json.loads(warm.read_text())['requests'])
        log = (directory/'server.log').read_text(errors='replace') if (directory/'server.log').exists() else ''
        if any(t in log for t in ('OutOfMemoryError','CUDA out of memory','memory allocation failed with OOM')):
            errors.append(directory.name+': OOM')
        if 'leaked semaphore' in log: warnings.append(directory.name+': leaked semaphore warning')
    comparison = old.compare(rows, 'off', 'full') if len(rows) == 6 else {}
    if comparison and comparison != json.loads((run/'comparison.json').read_text()):
        errors.append('raw recomputation differs from comparison')
    samples = [json.loads(s) for s in (run/'resources.jsonl').read_text().splitlines()]
    hosts = [json.loads(s) for s in (run/'host-resources.jsonl').read_text().splitlines()]
    assert len({s['boot_id'] for s in samples}) == 1
    if any(s.get('violations') for s in samples): errors.append('observed interference')
    if outcome['monitor_errors']: errors.append('telemetry errors')
    core_ok = all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n,h in spec['core_sha256'].items())
    assert core_ok
    previous = ROOT/'research/experiments/results/trace-revalidation-v2-20261013T121015Z'
    prevspec = json.loads((previous/'specification.json').read_text())
    configuration_matches_v2 = all(spec[k] == prevspec[k] for k in
        ('base_command','overrides','repeats','requests_per_variant','episodes','rate','cap','input_tokens','output_tokens','payload_seed','sampling_seed'))
    assert configuration_matches_v2
    assert json.loads((run/'fixed-payload.json').read_text()) == json.loads((previous/'fixed-payload.json').read_text())
    audit = dict(requests=measured,native_requests=native,warmup_requests=warmup,complete_variants=len(rows),
        resource_samples=len(samples),host_samples=len(hosts),errors=errors,warnings=warnings,
        core_unchanged=core_ok,configuration_and_payload_match_v2=configuration_matches_v2,
        comparison=comparison,runner_outcome=outcome,
        scope='offline checks do not prove clock accuracy, zero unsampled interference, or absence of semaphore leaks')
    (run/'offline-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    table = '\n'.join('| '+k+' | '+' / '.join(f'{v:.3f}' for v in x['paired_overhead_percent'])+f" | {x['median_overhead_percent']:.3f} |" for k,x in comparison.items())
    status = outcome['status'] if not errors else 'HOLD'
    report = f'''# Trace v3 同配置复验结果

运行：`{run.name}`；日期2026-10-15。阶段门 **{status}**，数值中位门 **{outcome['numeric_pass']}**，逐轮<5% **{outcome['all_pairs_below_five']}**。

## 实际执行与核验

RTX4060 Laptop / Qwen2.5-0.5B / vLLM，512输入128输出、cap8、4 requests/s、8×8请求每组，三轮交替顺序。固定配置和payload与v2逐项相同，公共资源采样协议新增并对两组一致。配置、runtime、命令、源码和原始请求在本目录。

已保存{measured}测量请求、{native}请求原生阶段字段、{warmup}预热单列，完整variant {len(rows)}/6。资源采样{len(samples)}条，Windows采样{len(hosts)}条。usage、client公式、native公式、请求ID和比较值离线复算；错误{errors}，核心hash未变{core_ok}。

| 指标 | 三轮开销/吞吐损失 % | 中位 % |
| --- | --- | --- |
{table}

延迟开销=(ON/OFF−1)×100，吞吐损失=(1−ON/OFF)×100；吞吐为64请求除8个episode时长之和，不含启动/预热/组间采样，不能当连续饱和吞吐。run-to-run CV保存在outcome.json，3轮仍不足以证明统计等价或一般硬件结论。

## 证据与局限

数值中位门与逐轮门分开报告，任何异常轮不剔除。server日志中semaphore警告：{warnings}，保留原文；进程组/GPU释放检查不能证明全部host semaphore已无泄漏。未检测干扰不等于证明零干扰，公共采样自身开销未单独量化。没有独立GPU kernel请求计时，native阶段仍是经过时间。

本报告只回答观测开销门，不回答瓶颈误判率。未运行正式混淆对照、扩样矩阵或诊断算法。若HOLD，仅分析本次波动/观测开销与环境，不能进入正式对照；若PASS，也仅在本配置下通过预登记门，需先阶段审查并冻结正式对照协议。

本轮TTFT OFF运行间CV={outcome['run_to_run_cv']['off/mean_ttft_ms']:.3%}，ON为{outcome['run_to_run_cv']['full/mean_ttft_ms']:.3%}。负开销不是性能提升，未定位具体trace组件责任，也不将波动直接归因于host/GPU温度。runtime只记录部分环境，完整继承环境与全部输出文本/SSE未存，精确环境重放仍有缺口，暂不对外发布一般定量主张。

## 阶段审查

1. 本阶段实际完成了什么：6组同配置真实运行、384测量、48预热单列及离线核验。
2. 原目标 vs 实际结果：完成复验，但逐轮5%门未全通过，正式对照未执行。
3. Correctness Review：已验证usage/ID/payload/计时公式；未验证GPU kernel精度及完整环境重放；风险为测量波动。
4. Architecture Review：保持核心、复用原采集；持续采样扰动待单独量化；替代隔离环境暂不实施。
5. Performance Review：只报告上表；不从负值推断优化，不外推硬件。
6. Bottleneck Analysis：配对变号→候选运行顺序/测量波动或trace效应→A/A负控检验→成立后再设计最小修正。
7. 10× Scale Test：未运行，不能扩样掩盖计量问题。
8. Alternative Design：当前外部进程配对复杂度低/内存低/维护低/可重跑但重启波动；A同flag A/A成本中且提供空效应参照；B完整profiler成本高且可能新扰动。三者新增性能收益未测。
9. Optimization Opportunities：P0同flag A/A验证运行间波动；P1确认稳定后才拆trace组件；P2正式对照；P3算法Parking Lot。
10. 与基础知识的联系：配对顺序、warmup、独立重复与异步计时边界。
11. 与其他开源项目的联系：vLLM原生metrics，无上游变更。
12. 新产生的想法：立即可验证A/A负控；其余新机制Parking Lot。
13. Resume Value Review：可审计实验能力；不写性能改善或准确率。
14. Interview Review：中位门为何不足？负开销为何不代表优化？CV如何解释？semaphore警告为何保留？为何不用增加请求数解决一切？
15. Failure / Mistake Review：未隐藏离群或删除负值，旧失败数据保留。
16. 独立能力检查：A Codex执行；B用户理解未验收；C独立运行能力本轮未测；D科研贡献未成立。
17. 下一步最有价值实验：s=三轮结果变号且OFF波动较大；a=冻结同flag/同配置A/A负控，区分空效应波动与trace差异；30–120分钟启动窗口非完成保证；Q高于马上做诊断对照。不自动追加运行。
18. 是否允许进入下一阶段：当前仅允许上述A/A计量补救，不进入正式对照。HOLD。
'''
    (run/'TRACE_REVALIDATION_V3_RESULT.md').write_text(report)
    print(json.dumps(dict(status=status,measured=measured,native=native,complete_variants=len(rows),errors=errors,warnings=warnings)))


if __name__ == '__main__': main()
