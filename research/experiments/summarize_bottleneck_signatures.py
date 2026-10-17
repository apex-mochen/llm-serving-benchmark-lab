"""Descriptive screening report. No classifier or root-cause algorithm."""
from pathlib import Path
import hashlib
import json
import statistics
import sys
import shutil

root=Path.cwd();run=Path(sys.argv[1]).resolve()
assert root.name=='llm-serving-benchmark-lab'
meta=json.loads((run/'metadata.json').read_text());assert meta['status']=='completed'
cells=json.loads((run/'aggregate.json').read_text());assert len(cells)==36
assert all(r['requests']==8 for r in cells)
assert all(r[phase+'_histogram_count']==8 for r in cells for phase in ('queue','prefill','decode')),'Incomplete stage histograms'
for folder in run.iterdir():
    if folder.is_dir():
        rows=json.loads((folder/'requests.json').read_text())
        config=json.loads((folder/'configuration.json').read_text())
        assert len(rows)==8 and all(r['success'] for r in rows)
        assert all(r['usage']['completion_tokens']==config['output_length'] and r['usage']['prompt_tokens']==config['input_length'] for r in rows)
        assert all(r['sent_s']>=r['planned_s'] and r['client_queue_s']>=0 for r in rows)
for repeat in range(3):
    for group,values in [('decode',[32,128,256]),('queue',[1,4,8]),('cache',['disabled','cold','warm'])]:
        workloads=[json.loads((run/f'{group}-{level}-r{repeat}/workload.json').read_text()) for level in values]
        assert all(workload==workloads[0] for workload in workloads), 'Uncontrolled payload mismatch'

levels={'prefill':[128,512,1536],'decode':[32,128,256],'queue':[1,4,8],'cache':['disabled','cold','warm']}
medians={};performance=[];stages=[];ranges=[]
for group,values in levels.items():
    for level in values:
        s=[r for r in cells if r['group']==group and r['level']==level]
        assert len(s)==3
        keys=['mean_ttft_ms','mean_tpot_ms','p50_e2e_ms','p95_e2e_ms','p99_e2e_ms','requests_per_s','output_tokens_per_s',
              'mean_client_queue_ms','queue_mean_ms','prefill_mean_ms','decode_mean_ms','gpu_memory_peak_mib','gpu_utilization_mean_pct']
        d={k:statistics.median(r[k] for r in s) for k in keys};medians[(group,level)]=d
        prefix=f'| {group} | {level} | '
        performance.append(prefix+' | '.join(f'{d[k]:.3f}' for k in keys[:7])+' |')
        queries=statistics.median(r['prefix_cache_queries_total_delta'] for r in s)
        hits=statistics.median(r['prefix_cache_hits_total_delta'] for r in s)
        hit=f'{hits/queries:.4f}' if queries>0 else 'unknown/无查询'
        stages.append(prefix+' | '.join(f'{d[k]:.4f}' for k in keys[7:])+' | '+hit+' |')
        ranges.append(prefix+' | '.join(f'{min(r[k] for r in s):.3f}–{max(r[k] for r in s):.3f}' for k in ['mean_ttft_ms','mean_tpot_ms','p95_e2e_ms'])+' |')

def ratios(group,low,high,key):
    return [next(r[key] for r in cells if r['group']==group and r['level']==high and r['repeat']==repeat)/
            next(r[key] for r in cells if r['group']==group and r['level']==low and r['repeat']==repeat) for repeat in range(3)]
effects=dict(prefill_TTFT_ratios=ratios('prefill',128,1536,'mean_ttft_ms'),
    prefill_stage_ratios=ratios('prefill',128,1536,'prefill_mean_ms'),
    decode_stage_ratios=ratios('decode',32,256,'decode_mean_ms'),
    decode_TPOT_ratios=ratios('decode',32,256,'mean_tpot_ms'),
    queue_server_ratios=ratios('queue',1,8,'queue_mean_ms'),
    cache_warm_vs_cold_prefill_ratios=ratios('cache','cold','warm','prefill_mean_ms'),
    cache_warm_vs_cold_TTFT_ratios=ratios('cache','cold','warm','mean_ttft_ms'))
(run/'descriptive-comparisons.json').write_text(json.dumps(effects,indent=2)+'\n')
short=lambda key:', '.join(f'{x:.3f}' for x in effects[key])
queue_extra=[]
for level in (1,4,8):
    values=[]
    for repeat in range(3):
        rows=json.loads((run/f'queue-{level}-r{repeat}/requests.json').read_text())
        raw=sorted((r['end_s']-r['planned_s'])*1000 for r in rows)
        position=(len(raw)-1)*.95;i=int(position);j=min(i+1,len(raw)-1)
        values.append(raw[i]+(raw[j]-raw[i])*(position-i))
    queue_extra.append(f'| {level} | {statistics.median(values):.3f} |')
target=root/'research/experiments/results/BOTTLENECK_SIGNATURE_RESULT.md';assert not target.exists()
relative=run.relative_to(root/'research/experiments/results')
report=f'''# Bottleneck Signature Result

2026-10-12；本机真实GPU合成工作负载筛查。4类、12水平、每水平3次独立重复、每cell8请求：36有效cell、288正式请求。预热/缓存准备请求单独保存，不混入正式统计。没有诊断算法、优化或核心架构修改。

## 1. 是否观察到稳定signature？

**可检查三次重复的方向一致性；尚未通过已登记的正式稳定性门槛。** 当前8请求/3重复低于64请求pilot，更低于5重复/1000请求的正式设计。下面只报告观察和逐重复比值，不给显著性、可靠P99、可泛化根因或识别准确率。

| 响应候选 | 三重复比值 | 怎样阅读 |
| --- | --- | --- |
| input1536/128，client TTFT | {short('prefill_TTFT_ratios')} | >1代表增加；不是自动认定prefill成为主瓶颈 |
| input1536/128，server prefill | {short('prefill_stage_ratios')} | 服务端阶段均值响应，结合queue/decode检查 |
| output256/32，server decode total | {short('decode_stage_ratios')} | 工作量增长的总成本，不能称性能回归 |
| output256/32，TPOT | {short('decode_TPOT_ratios')} | 每输出Token平均边界，和总decode时间分开 |
| concurrency8/1，server WAITING | {short('queue_server_ratios')} | 本实验固定max_num_seqs=4；分母很小时比值巨大，绝对ms更重要 |
| warm/cold，server prefill | {short('cache_warm_vs_cold_prefill_ratios')} | <1代表阶段时间减少，与实际命中计数联核 |
| warm/cold，client TTFT | {short('cache_warm_vs_cold_TTFT_ratios')} | 只比较同一cached server的冷/暖组 |

输入、输出、排队、缓存可影响多个指标，不是互斥类别。趋势存在与“正式稳定signature成立”分开判断；指标正常响应也不是优化策略失效。

## 2. 配置与controlled workload

模型Qwen2.5-0.5B-Instruct，revision `{meta['config']['model_revision']}`；vLLM `{meta['packages'].get('vllm','unknown')}`、wheel SHA `{meta['engine_commit']}`；GPU `{meta['gpu']['name']}`、{meta['gpu']['memory.total']}MiB，driver `{meta['gpu']['driver_version']}`。FP16、TP1、上下文2048、gpu_memory_utilization0.45、enforce_eager、max_num_seqs4、max_num_batched_tokens2048、chunked prefill开启。实际启动命令/环境、软件依赖、设备初态及核心hash见metadata/服务日志。

- Prefill：input128/512/1536，output128、client cap1，cache关闭，有限批次信号量执行。长度改变使用同seed/随机token分布；实现不是所有request的嵌套前缀，内容变化是限制，后续严格length测试需预先生成最长token池再截断。
- Decode：output32/128/256，input512、client cap1、cache关闭；同repeat输入完全相同，输出usage逐请求核对，ignore_eos、temperature0、seed固定。
- Queue：client cap1/4/8，input512/output128、cache关闭，同请求序列计划4/s；记录planned、arrival、send和客户端等待；服务端max_num_seqs4固定，仅这个人工服务容量边界下验证WAITING。
- Cache：disabled/cold/warm，input1024/output128，shared prefix256、计划4/s、cap4；同repeat相同输入。冷组重置成功后自然流入，组内可逐步热；warm预加载每个完整输入（不只是256公共前缀），准备阶段输出16。这是不同复用深度/状态对照，不仅比较缓存开关。
- 各cell16个不同seed输入/output16作预热；3个seed20261012/13/14；repeat1反转水平与组顺序。缓存关闭服务与开启服务分块顺序固定，disabled对cold/warm仍有服务重启/顺序混杂；cold对warm为同服务、同重复对照。

用户现有8080服务保留；实验只在空闲8019启动localhost服务，DEV_MODE用于reset。两次自有server均在finally停止，未接管其它服务。资源采集设备级，Windows桌面共享无法完全隔离。

## 3. 实测性能表

表为3个cell统计值的中位数；P50/P95/P99均基于每cell8请求线性插值，尾部分位数仅描述。原始分布为requests.json的逐请求时间。

| 组 | 水平 | mean TTFT ms | mean TPOT ms | P50 E2E ms | P95 E2E ms | P99 E2E ms | requests/s | output Tokens/s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
'''+ '\n'.join(performance)+'''

## 4. 服务端阶段、GPU与缓存

stage为Prometheus前后sum/count差的请求均值；36个cell每阶段count差均8才验收。GPU每约0.5秒采样，util是device busy指标，不是SM效率/带宽。VRAM为设备用量而非单请求/引擎分配。

| 组 | 水平 | client queue mean ms | server WAIT mean ms | server prefill mean ms | server decode mean ms | peak GPU memory MiB | GPU util mean % | hit-token/query-token ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
'''+ '\n'.join(stages)+'''

prefix比例来自实际公布token counters；无查询时unknown。原始KV usage、running/waiting/preemption时序在server-samples.json，完整metrics-before/after保留，末端usage不充当压力峰值。

## 5. 哪些指标有效？

- Prefill响应：TTFT与server prefill的共同变化比TTFT单独更有证据；若decode仍占绝大多数总服务成本，只能说输入计算成本变化，不叫prefill主瓶颈。
- Decode响应：decode总时间 + 输出计数能解释长输出；TPOT是每Token平均成本。总时间增长但TPOT近似不变属于正常工作量增大。
- Queue响应：planned→send客户端等待与server WAITING分开后，才能知道等待位置。较大concurrency可能把等待从客户端移至服务端；TTFT通常从send起算，会遗漏此前等待。
- Cache响应：实际hit/query + computed prefill Token/阶段时间支持复用解释；不能用前缀长度或GPU显存替代实测命中。原生服务端这些计数/阶段能力已有，利用它们不构成算法创新。

排队实验从计划到完成的P95另列，避免只看send后E2E误解用户等待：

| client cap | P95 planned-to-complete ms（3次中位数） |
| --- | --- |
'''+ '\n'.join(queue_extra)+'''

## 6. 波动、不可区分与失败边界

| 组 | 水平 | mean TTFT range ms | mean TPOT range ms | P95 E2E range ms |
| --- | --- | --- | --- | --- |
'''+ '\n'.join(ranges)+f'''

只有TTFT/P99无法区分queue、prefill、cold cache与网络；只有TPOT无法区分长KV、batch竞争、桌面GPU或抢占。GPU利用率高不证明compute-bound，显存高不证明KV压力，未采集带宽counter不称memory-bound。阶段直方图为边际集合，不能关联具体P99请求，也不能把阶段P99相加。

当前不能区分未注入的网络/资源/调度故障，不能覆盖复合因素、真实Agent质量、多租户或其它硬件。队列由固定max_num_seqs4控制，不能泛化为原生调度Bug。独立重复仍共享本机与顺序，且样本很小；随机输入内容和GPU热状态都是混杂。

有限批次吞吐包括arrival窗口/drain，不是稳态容量；客户端E2E定义send→流结束，TPOT按最后非空内容chunk计算，chunk合并或不可见末Token可能改变边界。采集错误保留，未用0替代；若部分cell缺有效计数/请求，本分析会拒绝生成报告。

## 7. 是否值得继续研究自动归因？

**值得继续验证可观测边界和独立场景，当前不进入自动归因算法开发。** 下一门槛是更充分重复/样本、同payload与顺序控制、正常工作量负样本、未知干预位置和request级证据。先比较原生阶段计时与简单人工解释是否已经足够；若足够，只作为毕设工程证据，不包装研究创新。

本轮给出候选响应而非准确率或新机制。下一最小实验可扩大Queue的同计划/同payload对照，校准client/server等待与request事件，之后再决定归因问题是否仍有文献差异。

## 8. 原始证据与复现

[结果目录]({relative}/metadata.json)：36个cell各有configuration/workload/requests/run.log/summary、GPU和server时序、metrics原文；全局配置、启动日志、独立warmup/preload/reset记录和aggregate保留。raw-sha256记录文件摘要；本轮核心hash不变。

```bash
/home/dcl/projects/vllm-v2-gpu-venv/bin/python research/experiments/test_bottleneck_runner.py
/home/dcl/projects/vllm-v2-gpu-venv/bin/python research/experiments/run_bottleneck_signatures.py
python3 research/experiments/summarize_bottleneck_signatures.py research/experiments/results/NEW_RUN_DIRECTORY
```

执行会创建新时间戳结果并拒绝占用端口，不覆盖历史；依赖、模型和机器路径必须按实际环境核验。四项HTTP mock验证通过，但mock数据未混入本报告的GPU结果。没有购租GPU、写论文或提交上游。

## 阶段复核

1. 本阶段实际完成了什么：4类/36cell/288请求真实GPU筛查与原始证据。
2. 原目标 vs 实际结果：候选响应测量完成；正式稳定性/自动归因未验收。
3. Correctness Review：已核payload/usage/计时/36阶段计数、4mock、核心hash；风险为小样本及混杂。
4. Architecture Review：优势为只增research脚本复用采集/进程管理；弱点为独立request trace不足；替代为完整现成bench适配，工程成本较大。
5. Performance Review：本机有实测数据，无正式性能回归或因果优化声明。
6. Bottleneck Analysis：观察→阶段/负样本解释→更充分对照验证→证据足够才考虑归因。
7. 10× Scale Test：未做；样本、模型及设备不泛化。
8. Alternative Design：阶段metrics成本低且边际；request trace成本中可关联；kernel profile成本高。内存/规模/容错代价需实测。
9. Optimization Opportunities：P0重复/顺序与输入一致性；P1请求关联；此期不优化。
10. 与基础知识的联系：客户端与服务端排队、工作量归一化、缓存状态、边际分布。
11. 与其他开源项目的联系：使用vLLM已存在指标，未改引擎，StriaTrace等仍需排除重复。
12. 新产生的想法：Parking Lot，复合因素，暂不展开。
13. Resume Value Review：可展示真实受控测量，不能写自动归因准确率或原创算法。
14. Interview Review：TTFT遗漏什么等待？长输出为何不证明decode失效？冷与暖如何准备？stage count为何校验？小样本P99怎样报告？
15. Failure / Mistake Review：资源筛查缩减注册样本/水平，事先说明并记录；不把低N称正式稳定。
16. 独立能力检查：A用户贡献背景；B助手执行实验；C用户独立操作未新增验收；D研究创新未验证。
17. 下一步最有价值实验：30–120分钟Queue配对/事件边界重复，s=有候选模式而稳定未知，a=强化单路径证据，收益高于立即诊断算法。
18. 是否允许进入下一阶段：PASS（测量交付）；正式signature与自动归因算法门槛未通过。
'''
target.write_text(report)
manifest={str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest() for p in run.rglob('*') if p.is_file() and p.name!='raw-sha256.json'}
(run/'raw-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==v for p,v in meta['core_sha256'].items())
export=Path('/mnt/c/Users/ASUS/.codex/visualizations/2026/10/09/01a12005-1f89-7b31-8f8e-dadb3e0b1b7e')
shutil.copyfile(target,export/'Bottleneck-Signature-Result.md')
print(report)
