"""Offline audit and report for the fresh calibration; never launches GPU work."""
import hashlib,json,re,statistics,sys,zipfile
from pathlib import Path
root=Path('/home/dcl/projects/llm-serving-benchmark-lab')
sys.path.insert(0,str(root/'research/experiments'))
import run_diagnosis_phase2 as x
import run_trace_revalidation as old
out=Path(sys.argv[1]);get=lambda p:json.loads(p.read_text())
spec=get(out/'specification.json');outcome=get(out/'outcome.json')
checks=[];count=0;native=0;ids=set();rows=[]
for repeat in range(3):
    for traced in (False,True):
        d=out/(('on' if traced else 'off')+f'-r{repeat}')
        if not d.exists():continue
        rr=[];episodes=[]
        for p in sorted(d.glob('episode-*.json')):
            v=get(p);episodes.append(v);rr+=v['requests']
        for r in rr:
            assert r['request_id'] not in ids;ids.add(r['request_id'])
            assert r['success'] and r['input_tokens']==512 and r['usage']['completion_tokens']==128
            assert r['prompt_sha256']==hashlib.sha256(json.dumps(get(out/'fixed-payload.json')[r['index']]).encode()).hexdigest()
            assert abs(r['ttft_ms']-(r['first_content_s']-r['sent_s'])*1000)<1e-6
            assert abs(r['tpot_ms']-(r['last_content_s']-r['first_content_s'])*1000/127)<1e-6
            if traced:
                x.validate_native(r['native_metrics'],128);assert r['response_header_request_id']==r['request_id'];native+=1
            else:assert r['native_metrics'] is None
        count+=len(rr)
        logs=(d/'server.log').read_text(errors='replace')
        oom=bool(re.search('OutOfMemoryError|CUDA out of memory|allocation failed with OOM',logs))
        checks.append(dict(variant=d.name,requests=len(rr),episodes=len(episodes),oom=oom))
        if len(rr)==64:
            records=[dict(duration_s=e['duration_s'],**{f'mean_{k}_ms':statistics.mean(r[f'{k}_ms'] for r in e['requests']) for k in ('ttft','tpot','e2e')}) for e in episodes]
            rows.append(dict(variant='full' if traced else 'off',repeat=repeat,summary=old.summarize(records)))
comparison=old.compare(rows,'off','full') if len(rows)==6 else {}
resources=[]
for d in sorted(out.glob('*-r*')):
    if not d.is_dir():continue
    if (d/'before.json').exists() and (d/'after.json').exists():
        before=get(d/'before.json');after=get(d/'after.json')
        resources.append(dict(variant=d.name,gpu_before_mib=before['gpu']['memory.used'],gpu_after_mib=after['gpu']['memory.used'],gpu_observed_max_mib=max([get(p)['gpu']['memory.used'] for p in d.glob('resource-*.json')],default=None),host_free_virtual_after_kib=after['host']['memory']['FreeVirtualMemory']))
audit=dict(requests=count,native_requests=native,checks=checks,recomputed_comparison=comparison,
           resources=resources,
           core_unchanged=all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in spec['core_sha256'].items()),
           limitation='Periodic resource snapshots cannot exclude unobserved transient contention; no full response text/SSE archive; three pairs do not establish equivalence confidence interval.')
(out/'offline-audit.json').write_text(json.dumps(audit,indent=2))
decision='PASS' if outcome['status']=='PASS' and len(rows)==6 and not any(c['oom'] for c in checks) and audit['core_unchanged'] else 'HOLD'
table='| 指标 | 三轮开销 % | 中位数 % |\n|---|---|---|\n'
for k,v in comparison.items():table+=f"| {k} | "+' / '.join(f'{n:.3f}' for n in v['paired_overhead_percent'])+f" | {v['median_overhead_percent']:.3f} |\n"
resource_table='| Variant | GPU before/after MiB | 采样观察最大 MiB |\n|---|---|---|\n'
for r in resources:resource_table+=f"| {r['variant']} | {r['gpu_before_mib']}/{r['gpu_after_mib']} | {r['gpu_observed_max_mib']} |\n"
next_action=('仅重做同配置trace OFF/ON配对：先验证无后台GPU任务，并将runner stdout/stderr写入持久运行目录' if decision=='PASS' else ('固定统计开启且trace关闭的资源稳定性复验' if outcome['error'] is not None else '仅per-request metrics组件的OFF/ON三轮小配对（共同开启stats，其他两组件共同关闭）'))
text=f'''# Trace Overhead Revalidation v2

实验日期：2026-10-13；离线核验日期：2026-10-14。数值门槛：**{decision}**；阶段放行：**HOLD**。原始运行：`{out.name}`。

## 实验与配置

RTX4060 Laptop / Qwen2.5-0.5B-Instruct / 实际安装 vLLM，版本、CUDA和路径见 runtime.json。FP16、eager、GPU budget 0.45、max-model-len 2048、max-num-seqs 4、chunked prefill、prefix cache OFF。
固定512输入/128输出、cap8、4 requests/s；8请求episode×8=64/variant；OFF→ON、ON→OFF、OFF→ON，预热单列。负载seed20261013，采样seed20261012。
两组共同开启引擎统计、DEV_MODE=0、uvicorn warning、INFO非debug；无外部profiler。ON增加per-request metrics/request-id headers/prompt-token details三项。
安装源码 cli_args.py 明确禁止 per-request metrics 与 disable-log-stats 并用，因此此配置不能视作先前统计关闭的稳定性组。没有修改原config或核心。

## 实测结果

完整variant：{len(rows)}/6；已保存测量请求：{count}；native timing：{native}。异常：`{outcome['error']}`。

{table}
{resource_table}
GPU观察最大值来自episode间快照，不能称为连续峰值；主机资源原值见 before/after/resource JSON。桌面GPU活动及未采样瞬时竞争不能排除。
延迟开销=(ON/OFF−1)×100；吞吐损失=(1−ON/OFF)×100。吞吐分母为8个episode测量时长之和，不含启动/预热/采集间隙，不能当成连续饱和吞吐。所有五项中位数必须严格<5%，三轮须完整；负值只表示这次测量的方向，不能声称trace提升性能。

## 证据与边界

配置、固定payload、执行时runtime、脚本副本、server命令/日志、请求时序/usage、资源快照、server stdout/stderr与离线复算保留在运行目录。
真实性：实际运行且请求级核验；可复现性：命令/关键runtime已记录，但完整继承环境、瞬时系统活动和完整SSE未保存，精确环境重放UNKNOWN；结论边界：仅此模型/卡/负载，不证明一般无开销或其他机器表现。
missing：runner控制台重定向到/tmp/trace-v2-console.log，续接时文件已不存在，不能补造；server stdout/stderr已保留。第一轮全部指标超过5%，中位数通过不等于各轮稳定通过。\n三对独立server启动仅小样本，未达到统计等价性研究标准；不将384请求当384个独立实验重复。未运行Phase2扩样、混合矩阵、自动归因或KV可靠性模块。历史OOM/中断证据未覆盖。

## 阶段审查

### 1. 本阶段实际完成了什么
新鲜配对运行、计时/ID/usage离线检查、配置版本留档；完整数见上。
### 2. 原目标 vs 实际结果
目标3轮trace门槛；实际{decision}，不等于科研假设已验证。
### 3. Correctness Review
已验证：请求公式/固定payload/native字段；未验证：完整SSE、独立服务端时钟精度；风险：流式chunk与token边界不同。
### 4. Architecture Review
收益：仅实验脚本复用；弱点：主机快照周期性；替代：独立采样sidecar，本轮不实现。
### 5. Performance Review
仅上表描述；不外推性能提升。
### 6. Bottleneck Analysis
若差异超门槛→候选观测路径/环境波动→新配对关闭单一组件→证据成立才最小缓解；未定位根因。
### 7. 10× Scale Test
未执行；当前不允许扩样代替门槛。
### 8. Alternative Design
Current同步周期快照：复杂度低/性能扰动未量化/内存低/扩展低/维护低/故障隔离低/成本低；A独立sidecar：中/待测/低/中/中/中/中；B外部profiler：高/开销待测/中/高/高/中/高。未实施A/B。
### 9. Optimization Opportunities
P0补齐持久日志与静默环境证据，三轮完整且干扰门可核验为成功指标；P1若超门槛仅组件配对；P2再扩矩阵；P3质量模块Parking Lot。无本轮调优。
### 10. 与基础知识的联系
配对实验控制、OS内存回收、流式网络测量边界、GPU分配生命周期。
### 11. 与其他开源项目的联系
vLLM原生stats与请求metrics依赖；SGLang并未纳入此实验。
### 12. 新产生的想法
立即可验证：单组件开销配对；未来研究：跨版本trace契约；Parking Lot：相位可靠性。
### 13. Resume Value Review
可展示可审计实验流程；不能写瓶颈定位算法/性能收益。
### 14. Interview Review
为何两组统计必须一致？为何chunk不等于token？为何请求数不是重复数？为何负开销非提升？如何保护外部服务？
### 15. Failure / Mistake Review
初始脚本传输shell引号错误已在执行前重写并编译检查；不将该错误解释为GPU问题。旧OOM不隐去。
### 16. 独立能力检查
A可读原始证据；B可复算百分比；C需用户复现命令检验；D独立诊断/优化能力未验证。
### 17. 下一步最有价值实验
唯一实验：{next_action}。s=小样本校准结果，a=上述最小验证，30–120分钟，无租卡；Q最高因为减少错误归因风险。
### 18. 是否允许进入下一阶段
HOLD。数值门通过，但后台GPU竞争无法完整排除、首轮差异显著、runner日志missing；不能据此恢复大规模Phase2，也不放行对外定量声明。唯一补救同第17节。
'''
report=root/'research/experiments/results/TRACE_OVERHEAD_REVALIDATION_V2.md';report.write_text(text)
idx=root/'experiments'/out.name;idx.mkdir(parents=True,exist_ok=True)
(idx/'README.md').write_text(f'# Evidence index\n\nRaw authority: ../../research/experiments/results/{out.name}/\n\nReport: ../../research/experiments/results/TRACE_OVERHEAD_REVALIDATION_V2.md\n\nExact reproduction command: /home/dcl/projects/vllm-v2-gpu-venv/bin/python -u research/experiments/run_trace_revalidation_v2.py\n\nNo core edits. Historical data retained.\n')
export=Path('/mnt/c/Users/ASUS/.codex/visualizations/2026/10/09/01a12005-1f89-7b31-8f8e-dadb3e0b1b7e')
(export/report.name).write_text(text)
with zipfile.ZipFile(export/'Trace-Revalidation-V2-Evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
    z.write(report,report.name)
    for p in out.rglob('*'):
        if p.is_file():z.write(p,str(p.relative_to(out.parent)))
print(text)


