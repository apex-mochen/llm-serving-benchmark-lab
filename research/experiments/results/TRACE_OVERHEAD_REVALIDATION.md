# Trace Overhead Re-validation

日期：2026-10-13。**结论：BLOCKED**。仅执行Phase 2 HOLD的trace测量补救；不开展大规模扩样、诊断算法或核心架构修改。

## 实验设计与配置

运行：`trace-revalidation-20261013T001356Z`。RTX4060 Laptop 8GB；Qwen2.5-0.5B-Instruct snapshot `7ae557604adf67be50417f59c2c2f167def9a775`；实际vLLM 0.30.0 / gced6857af（server日志及实际模块一致）；完整配置/软件版本/源hash另存。FP16、TP1、eager、max_model_len2048、max_num_seqs4、max_num_batched_tokens2048、chunked prefill、cache禁用、GPU memory utilization0.45。

环境存在两套vLLM dist-info（0.30.0和遗留0.1.dev1）；importlib.metadata可能返回旧版，因此不作为实际运行版本。verification.json同时保留metadata值与实际_version.py内容/hash，运行版本以模块和server启动日志为准；未修改该环境。

Baseline关闭3个原生trace相关开关；Treatment同时开启 `--enable-per-request-metrics`、`--enable-request-id-headers`、`--enable-prompt-tokens-details`。两组保留相同client SSE解析、GPU/Prometheus采样，不开启OTLP详细tracing。

固定payload SHA256：`a85d217f3e47e8945e9ecb1b913978b0aabc8f69199f755a3c4171c91bb8daf5`。同8个512-token输入重复8个episode=每variant64请求，output128、ignore_eos、temperature0、采样seed固定、根到达率4/s、client cap8。3轮顺序off/full、full/off、off/full；每服务独立启动，预热8请求单列，episode之间排空。正式有效完成256请求；warmup不计入。

## 环境有效性

检测到编译任务：False；非自有进程树compute进程：[]；本次运行boot ID数量：1。环境before/live/timeline记录GPU温度、时钟、占用、CPU负载、进程和内存；compute PID按保存的自有runner PID及进程父子关系核验。桌面WDDM显存/轻微GPU活动仍存在，不能宣称完全隔离生产硬件；监测无法覆盖不可见的Windows进程。

首次运行 `trace-revalidation-20261013T001153Z` 因WSL非正常重启中断，完整配对未完成，部分日志含NUL/零字节/未刷盘；已落盘原始文件、interruption与reboot-observation原样保留，丢失内容无法恢复，不修补或混入本次统计。未主动重启WSL或停止其他人的服务。

本次运行off-r2初次启动及同配置重试均在2.49GiB KV分配OOM，尚未开启trace、没有测量请求；日志/配置/旧outcome保留。只在同boot ID、相同配置/payload、已完成配对不重测的条件下重试缺失第三轮。runner初版与resume版源文件均保留，变更仅调度恢复/日志，不改核心采集函数；不能将OOM定位为trace组件问题。

失败后只读Windows资源快照：可用物理内存631124KiB（约0.60GiB），可用虚拟内存3741980KiB（约3.57GiB），总物理内存约15.63GiB。host-memory.json保存原始CIM结果。这是主机内存压力候选证据，采样发生在失败后，不能证明是OOM根因，也不把“剩余VRAM”当作全部可分配资源。未关闭其他应用、修改页文件或重启系统。

## 指标与验收

TTFT=client send→first nonempty SSE content；TPOT=(last-first)/(128−1)；latency=send→response结束；request/s=64/8个正式episode时间之和，output token/s=128×request/s。不是整机全时段吞吐，不包含启动/预热/episode间隔。原生阶段不等于纯GPU kernel时间。

时间开销%=100×(on/off−1)，吞吐损失%=100×(1−on/off)。按实验前冻结规则：3轮配对百分比中位数，所有指标严格<5%方为点估计PASS；不改变5%门槛，不扣除估计开销。负值仅表示该次比较on更快，不能宣称trace带来性能优化。三重复为pilot，不提供普遍统计等价证明。

| variant | repeat | TTFT mean ms | TPOT mean ms | latency mean ms | req/s | output token/s |
|---|---:|---:|---:|---:|---:|---:|
| off | 0 | 514.890 | 14.800 | 2394.836 | 1.7509 | 224.11 |
| full | 0 | 573.579 | 15.813 | 2582.272 | 1.6545 | 211.78 |
| full | 1 | 577.324 | 15.481 | 2543.747 | 1.6893 | 216.23 |
| off | 1 | 586.150 | 15.908 | 2606.768 | 1.6411 | 210.06 |

### 配对开销

仅完成两轮；下面中位数为描述统计，不参与预登记三轮验收，不丢弃失败第三轮以换取PASS。

| 指标 | 已完成各轮开销/损失 % | 中位 % | 三轮验收 |
|---|---|---:|---|
| mean_ttft_ms | +11.398, -1.506 | +4.946 | 未完成 |
| mean_tpot_ms | +6.849, -2.685 | +2.082 | 未完成 |
| mean_e2e_ms | +7.827, -2.418 | +2.705 | 未完成 |
| requests_per_s | +5.503, -2.935 | +1.284 | 未完成 |
| output_tokens_per_s | +5.503, -2.935 | +1.284 | 未完成 |

## 组件定位及最小缓解

尚无完整三轮的overhead FAIL证据；当前是执行BLOCKED，不能识别trace责任组件，更不能把中断/OOM归咎于trace。没有启动组件拆分，因为baseline已经无法正常启动。最小缓解：先在不更改模型/缓存预算的条件下检查WSL/CUDA分配及Windows内存/commit状态，稳定环境后补第三轮；如果环境重启，新建运行目录、重做配对，不跨boot拼接。保持Phase 2 HOLD；不缩小缓存来伪装同条件成功，不修改引擎。

## 结果范围与下一步

测量补救未通过，Phase 2继续HOLD；不开展扩样、矩阵或归因研究。

## 阶段审查

1. 实际完成：事实，固定payload小配对、环境监测和原始数据核验；中断另存。
2. 原目标vs实际：以以上实测状态为准，不将未完成配对标PASS。
3. Correctness：已核payload、usage、ID和128条native请求与histogram均值；未核完整Windows隔离；风险是逻辑阶段与GPU真值混淆。
4. Architecture：优势复用；弱点设备/VM共享；替代独占实验环境，当前不购买。
5. Performance：以上配对值仅适用于当前配置；无引擎优化收益。
6. Bottleneck：开销超过门槛→组件/波动候选→remove-one配对→仅最小观测开关缓解，不设计算法。
7. 10× Scale：本轮禁止，未执行。
8. Alternatives：当前native flags低复杂度、已测开销；无trace低成本但少阶段信息；OTLP复杂度/内存/维护成本高且性能未测。共享环境容错靠原始checkpoint，独占资源成本更高。
9. Optimization：P0测量可信度；P1后续扩样，P2事件链，P3模型扩展均暂不实施。
10. 基础联系：observer effect、共享CPU/GPU、stream边界、配对设计。
11. 开源联系：复用vLLM已有原生指标，不包装算法创新，不形成PR主张。
12. 新想法：Parking Lot只保留独立环境验证，当前不新增架构。
13. 求职证据：可展示配对/测量质量门，不能写自动根因准确率。
14. 五问：TTFT边界？吞吐分母？为何固定payload？负开销意味着什么？为何重启前后不能混并？
15. 失败：首次WSL重启中断保留，不确定原因；完整trace是否失败按配对表。
16. 独立能力：A用户背景；B助手执行；C用户独立统计未验收；D科研创新未验证。
17. 下一唯一实验：s=测量可信度未恢复；a=最小组件/环境补救配对，30–120分钟、现有GPU；收益是避免扩大无效数据；本轮不再进入其他研究阶段。
18. 阶段门：HOLD（仅测量补救）。
