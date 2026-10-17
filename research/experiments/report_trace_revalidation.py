"""Verify raw records, report descriptive paired overhead, preserve all evidence."""
import argparse
import hashlib
import importlib.metadata
import json
import re
from pathlib import Path
import shutil
import statistics
import zipfile

ROOT=Path('/home/dcl/projects/llm-serving-benchmark-lab')
load=lambda p:json.loads(p.read_text())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);args=parser.parse_args()
    run=args.run.resolve();spec=load(run/'specification.json');outcome=load(run/'outcome.json')
    progress=load(run/'progress.json') if (run/'progress.json').exists() else []
    comparisons=load(run/'paired-comparison.json') if (run/'paired-comparison.json').exists() else None
    partial=False
    if comparisons is None and progress:
        repeats=sorted({r['repeat'] for r in progress if r['variant']=='off'} &
                       {r['repeat'] for r in progress if r['variant']=='full'})
        partial=True;comparisons=dict(comparison={},pass_threshold=False,completed_repeats=repeats)
        for key in ('mean_ttft_ms','mean_tpot_ms','mean_e2e_ms','requests_per_s','output_tokens_per_s'):
            ratios=[next(r['summary'][key] for r in progress if r['variant']=='full' and r['repeat']==i)/
                    next(r['summary'][key] for r in progress if r['variant']=='off' and r['repeat']==i) for i in repeats]
            overhead=[100*(1-x) if key.endswith('per_s') else 100*(x-1) for x in ratios]
            comparisons['comparison'][key]=dict(paired_ratios=ratios,paired_overhead_percent=overhead,
                median_overhead_percent=statistics.median(overhead))
        (run/'partial-paired-comparison.json').write_text(json.dumps(comparisons,indent=2)+'\n')
    for name,h in spec['core_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h
    flags={'--enable-per-request-metrics','--enable-request-id-headers','--enable-prompt-tokens-details'}
    normalized=[]
    for config in run.glob('*-server-config.json'):
        command=load(config)['command']
        normalized.append([x for x in command if x not in flags])
    assert normalized and all(c==normalized[0] for c in normalized),'Server config drift'
    inputs=load(run/'fixed-payload.json');episodes=0;validated_native=0
    for p in run.glob('*/episode-*/summary.json'):
        path=p.parent;rows=load(path/'requests.json');summary=load(p)
        assert load(path/'workload.json')==inputs
        assert len(rows)==8 and all(r['success'] and r['input_tokens']==512 and r['output_tokens']==128 for r in rows)
        for r in rows:
            assert r['sse_response_ids']==['cmpl-'+r['request_id']]
        native=[r for r in rows if r['native_metrics']]
        if native:
            assert len(native)==8
            for phase,key in [('queue','queue_time_ms'),('prefill','time_to_first_token_ms'),('decode','generation_time_ms')]:
                assert abs(statistics.mean(r['native_metrics'][key] for r in rows)-summary[phase+'_hist_mean_ms'])<5
            validated_native+=8
        episodes+=1
    env=load(run/'environment-timeline.json')
    compilers=any(s.get('compiler_jobs') for s in env)
    bootids={s['boot_id'] for s in env if 'boot_id' in s}
    gpu_ids={s['gpu']['uuid'] for s in env if 'gpu' in s}
    assert len(gpu_ids)==1,'Hardware drift'
    foreign=[]
    owned_pids={int(p.read_text()) for p in run.glob('runner*pid.txt')}
    for s in env:
        parents={int(parts[0]):int(parts[1]) for line in s.get('processes','').splitlines()[1:]
                 if len(parts:=line.split())>=4 and parts[0].isdigit()}
        allowed=set(owned_pids)
        for _ in range(10):
            added={pid for pid,parent in parents.items() if parent in allowed}
            if added<=allowed:break
            allowed|=added
        for line in s.get('compute_apps','').splitlines():
            if line.strip():
                pid=line.split(',')[0].strip()
                if not pid.isdigit() or int(pid) not in allowed:foreign.append(line)
    assert not (ROOT/'.benchmark.lock').exists()
    effective=outcome['status']
    if compilers or foreign or len(bootids)!=1:effective='BLOCKED_ENVIRONMENT'
    valid=effective=='PASS'
    readme_version=Path('/home/dcl/projects/vllm-v2-gpu-venv/lib/python3.12/site-packages/vllm/_version.py')
    source_version=re.search(r"__version__ = version = '([^']+)'",readme_version.read_text()).group(1)
    source_commit=re.search(r"__commit_id__ = commit_id = '([^']+)'",readme_version.read_text()).group(1)
    verification=dict(status=effective,completed_requests=episodes*8,validated_native_requests=validated_native,
        fixed_payload_verified=True,core_hash_verified=True,compiler_jobs_observed=compilers,
        normalized_server_configs_verified=True,gpu_uuids=sorted(gpu_ids),
        foreign_compute_observed=foreign,boot_ids=sorted(bootids),
        environment_limit='WSL process and NVIDIA compute-process visibility only; desktop WDDM activity remains, no guarantee of complete Windows process visibility.',
        versions={name:importlib.metadata.version(name) for name in ('vllm','torch','httpx')},
        version_source=readme_version.read_text(),
        version_source_sha256=hashlib.sha256(readme_version.read_bytes()).hexdigest(),
        actual_vllm_version=source_version,actual_vllm_build_commit=source_commit,
        next_phase_executed=False)
    (run/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
    report=['# Trace Overhead Re-validation','',f'日期：2026-10-13。**结论：{effective}**。仅执行Phase 2 HOLD的trace测量补救；不开展大规模扩样、诊断算法或核心架构修改。','',
      '## 实验设计与配置','',
      f'运行：`{run.name}`。RTX4060 Laptop 8GB；Qwen2.5-0.5B-Instruct snapshot `{spec["config"]["model_revision"]}`；实际vLLM '+source_version+' / '+source_commit+'（server日志及实际模块一致）；完整配置/软件版本/源hash另存。FP16、TP1、eager、max_model_len2048、max_num_seqs4、max_num_batched_tokens2048、chunked prefill、cache禁用、GPU memory utilization0.45。','',
      '环境存在两套vLLM dist-info（0.30.0和遗留0.1.dev1）；importlib.metadata可能返回旧版，因此不作为实际运行版本。verification.json同时保留metadata值与实际_version.py内容/hash，运行版本以模块和server启动日志为准；未修改该环境。','',
      'Baseline关闭3个原生trace相关开关；Treatment同时开启 `--enable-per-request-metrics`、`--enable-request-id-headers`、`--enable-prompt-tokens-details`。两组保留相同client SSE解析、GPU/Prometheus采样，不开启OTLP详细tracing。','',
      f'固定payload SHA256：`{spec["payload_sha256"]}`。同8个512-token输入重复8个episode=每variant64请求，output128、ignore_eos、temperature0、采样seed固定、根到达率4/s、client cap8。3轮顺序off/full、full/off、off/full；每服务独立启动，预热8请求单列，episode之间排空。正式有效完成{episodes*8}请求；warmup不计入。','',
      '## 环境有效性','',
      f'检测到编译任务：{compilers}；非自有进程树compute进程：{foreign}；本次运行boot ID数量：{len(bootids)}。环境before/live/timeline记录GPU温度、时钟、占用、CPU负载、进程和内存；compute PID按保存的自有runner PID及进程父子关系核验。桌面WDDM显存/轻微GPU活动仍存在，不能宣称完全隔离生产硬件；监测无法覆盖不可见的Windows进程。','',
      '首次运行 `trace-revalidation-20261013T001153Z` 因WSL非正常重启中断，完整配对未完成，部分日志含NUL/零字节/未刷盘；已落盘原始文件、interruption与reboot-observation原样保留，丢失内容无法恢复，不修补或混入本次统计。未主动重启WSL或停止其他人的服务。','',
      '本次运行off-r2初次启动及同配置重试均在2.49GiB KV分配OOM，尚未开启trace、没有测量请求；日志/配置/旧outcome保留。只在同boot ID、相同配置/payload、已完成配对不重测的条件下重试缺失第三轮。runner初版与resume版源文件均保留，变更仅调度恢复/日志，不改核心采集函数；不能将OOM定位为trace组件问题。','',
      '失败后只读Windows资源快照：可用物理内存631124KiB（约0.60GiB），可用虚拟内存3741980KiB（约3.57GiB），总物理内存约15.63GiB。host-memory.json保存原始CIM结果。这是主机内存压力候选证据，采样发生在失败后，不能证明是OOM根因，也不把“剩余VRAM”当作全部可分配资源。未关闭其他应用、修改页文件或重启系统。','',
      '## 指标与验收','',
      'TTFT=client send→first nonempty SSE content；TPOT=(last-first)/(128−1)；latency=send→response结束；request/s=64/8个正式episode时间之和，output token/s=128×request/s。不是整机全时段吞吐，不包含启动/预热/episode间隔。原生阶段不等于纯GPU kernel时间。','',
      '时间开销%=100×(on/off−1)，吞吐损失%=100×(1−on/off)。按实验前冻结规则：3轮配对百分比中位数，所有指标严格<5%方为点估计PASS；不改变5%门槛，不扣除估计开销。负值仅表示该次比较on更快，不能宣称trace带来性能优化。三重复为pilot，不提供普遍统计等价证明。','',
      '| variant | repeat | TTFT mean ms | TPOT mean ms | latency mean ms | req/s | output token/s |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for r in progress:
        s=r['summary'];report.append(f'| {r["variant"]} | {r["repeat"]} | {s["mean_ttft_ms"]:.3f} | {s["mean_tpot_ms"]:.3f} | {s["mean_e2e_ms"]:.3f} | {s["requests_per_s"]:.4f} | {s["output_tokens_per_s"]:.2f} |')
    report+=['','### 配对开销','',
             ('仅完成两轮；下面中位数为描述统计，不参与预登记三轮验收，不丢弃失败第三轮以换取PASS。' if partial else '完整三轮配对。'),'',
             '| 指标 | 已完成各轮开销/损失 % | 中位 % | 三轮验收 |','|---|---|---:|---|']
    if comparisons:
        for key,v in comparisons['comparison'].items():
            report.append(f'| {key} | '+', '.join(f'{x:+.3f}' for x in v['paired_overhead_percent'])+f' | {v["median_overhead_percent"]:+.3f} | '+('未完成' if partial else str(v['median_overhead_percent']<5))+' |')
    else:report+=['未获得完整3轮配对；不能计算验收开销。']
    report+=['','## 组件定位及最小缓解','']
    ablation=load(run/'component-ablation.json') if (run/'component-ablation.json').exists() else None
    if valid:
        report+=['当前固定工作负载的点估计通过，不需要进行额外组件试验。无法凭上次8请求pilot的失败判定哪个组件有开销；也不声称所有工作负载/引擎版本均<5%。']
    elif ablation:
        report+=['进行remove-one-component拆分；结果属于组件候选证据，不能忽略时间漂移和组件交互。','',
                 '| 移除组件 | TTFT中位开销% vs off | TPOT中位开销% | latency中位开销% | 所有点估计<5% |', '|---|---:|---:|---:|---|']
        for component,v in ablation.items():
            values=v['against_off'];ok=all(m['median_overhead_percent']<5 for m in values.values())
            report.append(f'| {component} | {values["mean_ttft_ms"]["median_overhead_percent"]:+.3f} | {values["mean_tpot_ms"]["median_overhead_percent"]:+.3f} | {values["mean_e2e_ms"]["median_overhead_percent"]:+.3f} | {ok} |')
        report+=['','最小缓解候选：优先移除存在一致改善且通过门槛的非必要headers/details组件；request ID仍可检查SSE id，cache details可使用server aggregate但不可冒充request字段。如果必须移除原生metrics才能满足门槛，维持性能组与trace组独立；尚不实施引擎改动或声称真实根因已确定。完整三轮remove-one与相对full效应见component-ablation.json。']
    else:report+=['尚无完整三轮的overhead FAIL证据；当前是执行BLOCKED，不能识别trace责任组件，更不能把中断/OOM归咎于trace。没有启动组件拆分，因为baseline已经无法正常启动。最小缓解：先在不更改模型/缓存预算的条件下检查WSL/CUDA分配及Windows内存/commit状态，稳定环境后补第三轮；如果环境重启，新建运行目录、重做配对，不跨boot拼接。保持Phase 2 HOLD；不缩小缓存来伪装同条件成功，不修改引擎。']
    report+=['','## 结果范围与下一步','',
      ('测量补救点估计PASS；只解除本配置的trace开销门。尚未证明稳定bottleneck signature、尾部可靠性或自动归因价值，本轮不继续Phase 2。' if valid else '测量补救未通过，Phase 2继续HOLD；不开展扩样、矩阵或归因研究。'),'',
      '## 阶段审查','',
      '1. 实际完成：事实，固定payload小配对、环境监测和原始数据核验；中断另存。',
      '2. 原目标vs实际：以以上实测状态为准，不将未完成配对标PASS。',
      f'3. Correctness：已核payload、usage、ID和{validated_native}条native请求与histogram均值；未核完整Windows隔离；风险是逻辑阶段与GPU真值混淆。',
      '4. Architecture：优势复用；弱点设备/VM共享；替代独占实验环境，当前不购买。',
      '5. Performance：以上配对值仅适用于当前配置；无引擎优化收益。',
      '6. Bottleneck：开销超过门槛→组件/波动候选→remove-one配对→仅最小观测开关缓解，不设计算法。',
      '7. 10× Scale：本轮禁止，未执行。',
      '8. Alternatives：当前native flags低复杂度、已测开销；无trace低成本但少阶段信息；OTLP复杂度/内存/维护成本高且性能未测。共享环境容错靠原始checkpoint，独占资源成本更高。',
      '9. Optimization：P0测量可信度；P1后续扩样，P2事件链，P3模型扩展均暂不实施。',
      '10. 基础联系：observer effect、共享CPU/GPU、stream边界、配对设计。',
      '11. 开源联系：复用vLLM已有原生指标，不包装算法创新，不形成PR主张。',
      '12. 新想法：Parking Lot只保留独立环境验证，当前不新增架构。',
      '13. 求职证据：可展示配对/测量质量门，不能写自动根因准确率。',
      '14. 五问：TTFT边界？吞吐分母？为何固定payload？负开销意味着什么？为何重启前后不能混并？',
      '15. 失败：首次WSL重启中断保留，不确定原因；完整trace是否失败按配对表。',
      '16. 独立能力：A用户背景；B助手执行；C用户独立统计未验收；D科研创新未验证。',
      '17. 下一唯一实验：'+('s=当前配置开销点估计通过；a=后续另行执行既定小规模阶段验证，30–120分钟、现有GPU；收益为验证阶段可解释性，Q最高因保留工程基础；本轮不执行。' if valid else 's=测量可信度未恢复；a=最小组件/环境补救配对，30–120分钟、现有GPU；收益是避免扩大无效数据；本轮不再进入其他研究阶段。'),
      '18. 阶段门：'+('PASS（仅固定配置pilot，不自动继续Phase 2）。' if valid else 'HOLD（仅测量补救）。')]
    target=ROOT/'research/experiments/results/TRACE_OVERHEAD_REVALIDATION.md'
    target.write_text('\n'.join(report)+'\n')
    manifest={str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest() for p in run.rglob('*') if p.is_file() and p.name!='integrity-manifest.json'}
    (run/'integrity-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    export=Path('/mnt/c/Users/ASUS/.codex/visualizations/2026/10/09/01a12005-1f89-7b31-8f8e-dadb3e0b1b7e')
    shutil.copyfile(target,export/'Trace-Overhead-Revalidation.md')
    with zipfile.ZipFile(export/'Trace-Overhead-Revalidation-Evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
        for directory in (run,ROOT/'research/experiments/results/trace-revalidation-20261013T001153Z'):
            for p in directory.rglob('*'):
                if p.is_file():z.write(p,'research/experiments/results/'+str(p.relative_to(run.parent)))
        z.write(target,'research/experiments/results/'+target.name)
        for name in ('run_trace_revalidation.py','test_trace_revalidation.py','report_trace_revalidation.py'):
            z.write(ROOT/'research/experiments'/name,'research/experiments/'+name)
    with zipfile.ZipFile(export/'Trace-Overhead-Revalidation-Evidence.zip') as z:assert z.testzip() is None
    print(target.read_text())


if __name__=='__main__':main()
