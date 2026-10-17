"""Report only completed measurements; retain failed attempts separately."""
from pathlib import Path
import hashlib
import json
import re
import statistics
import sys

root=Path.cwd()
assert root.name=='llm-serving-benchmark-lab'
run=Path(sys.argv[1]).resolve()
meta=json.loads((run/'metadata.json').read_text())
assert meta['status']=='completed', 'No completed run: cannot report benchmark results'
data=json.loads((run/'aggregate.json').read_text())
assert len(data)==12
checks=[]
kv=[]
for cache in (False,True):
    for repeat in range(3):
        paths=[run/f'cache-{cache}-r{repeat}-{kind}' for kind in ('agent','traditional')]
        a,b=[{r['request_id']:r for r in json.loads((p/'requests.json').read_text())} for p in paths]
        assert len(a)==len(b)==48 and a.keys()==b.keys()
        assert all(a[k]['success'] and b[k]['success'] for k in a)
        assert all(a[k]['input_tokens']==b[k]['input_tokens'] and a[k]['prompt_sha256']==b[k]['prompt_sha256'] and
                   a[k]['usage']['completion_tokens']==b[k]['usage']['completion_tokens']==64 for k in a)
        assert all(b[k]['target_s']==a[k]['sent_s'] for k in a)
        mismatch=max(abs(b[k]['sent_s']-a[k]['sent_s']) for k in a)
        checks.append(dict(cache=cache,repeat=repeat,identical_input_and_output_counts=True,max_arrival_mismatch_ms=mismatch*1000))
        for kind,p in zip(('agent','traditional'),paths):
            def metrics(file):
                found={}
                for line in file.read_text().splitlines():
                    if line.startswith('#'): continue
                    match=re.match(r'([^\s{]+)(?:\{[^}]*\})?\s+([-+\d.eE]+)$',line)
                    if match and any(word in match[1] for word in ('prefix_cache','kv_cache','preempt')):
                        key=match[1]
                        if key.endswith('_created'): continue
                        found[key]=found.get(key,0)+float(match[2])
                return found
            before,after=metrics(p/'metrics-before.txt'),metrics(p/'metrics-after.txt')
            kv.append(dict(cache=cache,repeat=repeat,kind=kind,after=after,
                counter_deltas={k:after[k]-before[k] for k in before.keys()&after.keys() if k.endswith('_total')}))
write=lambda p,obj:p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
write(run/'pairing-checks.json',checks)
write(run/'kv-observations.json',kv)
kv_rows=[]
for cell in kv:
    delta=cell['counter_deltas']
    queries=delta.get('vllm:prefix_cache_queries_total')
    hits=delta.get('vllm:prefix_cache_hits_total')
    ratio=hits/queries if queries is not None and hits is not None and queries>0 and hits>=0 else None
    kv_rows.append(f"| {cell['cache']} | {cell['repeat']} | {cell['kind']} | {queries if queries is not None else 'unknown'} | {hits if hits is not None else 'unknown'} | {f'{ratio:.4f}' if ratio is not None else 'unknown/无查询'} |")
kv_table='| Cache | repeat | workload | observed query-token delta | observed hit-token delta | ratio |\n| --- | --- | --- | --- | --- | --- |\n'+'\n'.join(kv_rows)
rows=[]
medians={}
for cache in (False,True):
    for kind in ('agent','traditional'):
        subset=[r for r in data if r['cache']==cache and r['kind']==kind]
        medians[(cache,kind)]={key:statistics.median(r[key] for r in subset) for key in
            ['ttft_mean_ms','tpot_mean_ms','p95_e2e_ms','p99_e2e_ms','requests_per_s','output_tokens_per_s','gpu_memory_peak_mib']}
        d=medians[(cache,kind)]
        rows.append('| '+str(cache)+' | '+kind+' | '+' | '.join(f'{d[k]:.3f}' for k in d)+' |')
effects={kind:100*(1-medians[(True,kind)]['ttft_mean_ms']/medians[(False,kind)]['ttft_mean_ms']) for kind in ('agent','traditional')}
ratios={str(cache):[next(r['p95_e2e_ms'] for r in data if r['cache']==cache and r['repeat']==i and r['kind']=='agent')/
                  next(r['p95_e2e_ms'] for r in data if r['cache']==cache and r['repeat']==i and r['kind']=='traditional') for i in range(3)] for cache in (False,True)}
write(run/'comparisons.json',dict(cache_ttft_reduction_pct=effects,paired_p95_ratios=ratios))
evidence_relative=run.relative_to(root/'research/experiments')
report=f'''# Agent Workload Validation Result

2026-10-12；真实GPU实验室测量，合成冻结Agent trace；不是生产业务或自主Agent质量评测。

## 结论与假设判断

完成两阶段session/dependency/pause/resume与Traditional配对回放，Prefix Cache关闭/开启、每组3次，共12个有效cell、576个成功请求。输入Token及输出规模完全相同，Traditional目标发送时刻逐请求等于Agent实际发送偏移；实际偏差见配对校验。

**本轮不能证明“Agent workload使现有优化策略失效”。** 即使配对尾延迟存在差异，也不能由单卡0.5B、低缓存压力、原生Prefix Cache对照证明所有KV调度策略失效。尚未测试受保护租户或完整Continuum/FairInference强组合。

本轮原生Prefix Cache对平均TTFT的变化：Agent降低 {effects['agent']:.2f}%，Traditional降低 {effects['traditional']:.2f}%；负值表示升高，不解释为优化收益已成立。三次配对P95比值 Agent/Traditional：cache关闭 {ratios['False']}，开启 {ratios['True']}。这些都是实测描述，3次重复和固定执行顺序不足以证明因果或等价。

决策：**停止基于“Agent会导致缓存优化失效”的预设开展A方向算法开发或提前优化。** 没有证据时不列新的优化机制。全局A假设为证据不足，不能把未检出当不存在；重新启动需要明确缓存压力/多租户场景和可复现强基线，而不是包装本轮差异。下一步可向导师讨论转B或是否批准更窄的压力证伪实验。

## 实验设计

- Agent：24个session，两阶段，根任务4/s；父请求成功完成后暂停0.25或0.75秒，再恢复子请求。失败则取消子轮；逐请求事件保存。GuideLLM固定版本的idle_gap目标计算被复用，不设计调度算法。
- 每session首轮1024 Token；第二轮首轮冻结输入追加128 Token，合计1152；各轮输出64，temperature=0、ignore_eos。共享256 Token前缀。工具结果和中间上下文为合成固定内容，没有把实际生成输出写入下一轮，因此不代表端到端Agent推理质量。
- Traditional：同一trace里的token IDs与payload，在Agent实际发送偏移独立提交；保留ID用于配对，不等待父节点。它是严格匹配负载的扁平回放，不是另造长度相近但前缀不同的数据。
- 每cache状态先用不同seed的2个session/4请求预热；cache开启时每cell重置成功后测量，关闭时无需重置。3个seed为20261012/13/14；每repeat先Agent后Traditional；关闭cache的3组先于开启cache，顺序效应是限制。

## 配置与复现

模型 Qwen2.5-0.5B-Instruct，revision `{meta['model_revision']}`；vLLM `{meta['engine_packages'].get('vllm','unknown')}`，wheel build解析到 `{meta['engine_commit']}`。GPU `{meta['gpu']['name']}`，{meta['gpu']['memory.total']}MiB，driver `{meta['gpu']['driver_version']}`。FP16、TP1、max_model_len2048、gpu_memory_utilization0.45、enforce_eager；实际命令/依赖/环境在metadata。实验服务仅localhost，启用DEV_MODE以访问cache reset，重置必须返回success=true；无核心代码修改。

```bash
PYTHONPATH=/home/dcl/.cache/lab-baselines/guidellm/src:/home/dcl/projects/vllm-v2-gpu-venv/lib/python3.12/site-packages \\
  /home/dcl/.cache/lab-baselines/cpu-env/bin/python research/experiments/agent_workload_validation.py
```

脚本只启停自有服务、拒绝覆盖已有服务、创建新时间戳目录；不重写结果。

## 数据和结果

表为三次重复各cell统计值的中位数；原始逐次结果见aggregate.json，不是合并请求后的统计。P95/P99是每48请求的经验插值分位数，**P99样本不足，只描述，不作稳定尾部结论**；没有报告统计显著性或置信区间。

| Prefix Cache | workload | mean TTFT ms | mean TPOT ms | P95 E2E ms | P99 E2E ms | requests/s | output tokens/s | peak device memory MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
'''+'\n'.join(rows)+f'''

实测配对发送偏移最大差值为 {max(c['max_arrival_mismatch_ms'] for c in checks):.3f}ms；逐对见pairing-checks.json。若差异对该硬件时间尺度重要，不能声称完全相同实际到达。全部请求输入ID摘要和计数已逐一核对，输出usage均64。

测量边界：TTFT为httpx发起到首非空内容chunk；TPOT=(最后非空chunk−首非空chunk)/63，chunk合并/不可见末token可能改变边界，非GPU kernel时间；E2E为实际发送到流结束。吞吐为有限批次成功请求/从测量开始到所有完成的时间，包含开放到达与尾部drain，不是稳态容量。工具等待不计入请求E2E，但影响任务完成；本轮未比较任务JCT。设备显存每0.5秒采样，包含Windows桌面，非引擎独占分配。采集错误保留，不用0代替。

## KV Cache观测

Prometheus前后原文已保存，提取实际prefix/KV/preemption计数见kv-observations.json。不把客户端prefix机会冒充真实命中。计数刷新/采样周期导致前后差值边界近似；末端usage不是峰值压力，不据此归因。服务端启动日志报告的KV容量也保留，检查是否远大于本trace需求；未制造缓存压力或调整容量去追求异常。

{kv_table}

表中ratio为服务端已公布token计数差值之比，不是请求命中概率，可能不覆盖最后一次统计刷新；无查询时unknown。session/dependency只在客户端维护，本轮没有向引擎注入session-aware缓存保留或暂停状态，不验证TTL/pin算法。

## 原始证据与失败运行

有效目录：[{evidence_relative}]({evidence_relative}/metadata.json)。其中包含config/version、完整启动日志、请求/events、trace、GPU采样、metrics原文、aggregate和配对校验。前两个目录为失败尝试：第一次等待校验失败，第二次reset API 404；没有正式cell统计，不混入结果。先修正实验脚本截止等待和版本接口，再通过2项本地HTTP mock测试重新测量；mock不计入GPU数据。

## 下一阶段边界

未验证：真实工具/多轮生成质量、多租户延迟隔离、KV高压/淘汰、其他调度策略、完整强基线、大模型/多卡/生产泛化。当前不设计新机制、不优化参数、不写论文。若导师选择重启A，应先批准具体压力/tenant假设与停止门；若选择B，复用已有请求/设备/metrics证据开展可核查干预，不假称根因已定位。
'''
target=root/'research/experiments/AGENT_WORKLOAD_VALIDATION_RESULT.md'
assert not target.exists()
target.write_text(report)
manifest={str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest() for p in run.rglob('*') if p.is_file()}
write(run/'raw-sha256.json',manifest)
print(report)
