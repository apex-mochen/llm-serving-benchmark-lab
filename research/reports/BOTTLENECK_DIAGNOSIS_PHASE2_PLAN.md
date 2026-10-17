# Bottleneck Diagnosis Research Validation — Phase 2 Plan

2026-10-12；主研究方向B。**本轮分析现有数据并设计增强实验，没有运行新GPU实验或开发自动归因算法。** A仍为“当前实验条件下未验证出问题，暂停作为主研究方向”。

## 1. 当前证据

基础为[Phase 1报告](../experiments/results/BOTTLENECK_SIGNATURE_RESULT.md)和[完整运行配置](../experiments/results/signatures-20261012T053318Z/metadata.json)：RTX4060 Laptop 8GB、Qwen2.5-0.5B、vLLM0.30.0固定wheel，4类/12水平/3重复/每cell8请求，共36cell、288正式请求。服务端max_num_seqs4固定；暖cache预加载完整输入，冷组256-token共享前缀自然复用。

| 现有响应 | 实测范围/关键数据 | 当前最有区分力的证据组合 | 不能推出什么 |
| --- | --- | --- | --- |
| input1536相对128 | TTFT三重复2.02–2.58倍；server prefill2.12–2.49倍 | TTFT + server prefill + 实际未缓存输入Token + queue未增加 | 未证明prefill主瓶颈或compute-bound；decode仍占主要服务时间 |
| output256相对32 | decode总时间7.72–8.81倍；TPOT比0.94–1.07 | 总decode + 实际output count + 每Token时间 | 主要是工作量增加，不是同负载性能回归 |
| client cap1/4/8 | server WAIT均值中位数约0.014/0.008/581ms；client等待位置改变 | planned→send + server queue + client TTFT | 固定容量边界的排队，不是调度Bug；TTFT单独遗漏客户端等待 |
| cold/warm cache | token命中比21.88%/98.44%；warm/cold prefill0.61–0.66，TTFT0.70–0.75 | 命中计数 + computed prefill/阶段时间 + exact prefix | 总E2E未一致改善，不能宣称整体加速；不代表高KV压力 |

以上为同设备候选响应，不是分类准确率或已成立科研贡献。原生vLLM阶段计时已经解释部分变化，Phase 2必须先判断是否仍存在解释缺口。

## 2. 不足与指标混淆

### 2.1 当前区分力排序

优先保留 **请求工作量/缓存状态与client/server时间边界的联合证据**，其次是阶段直方图，最后是设备级GPU指标。这里是证据优先级，不是学习得到的特征排序或诊断算法。

- TTFT升高：queue、prefill、cold cache、API/网络均可能；必须核时间边界。
- TPOT升高：上下文变长、batch竞争、GPU干扰或抢占都可能；output变长不保证TPOT升高。
- P95/P99：反映结果严重程度，单独不能标根因；阶段P99不能相加成请求P99。
- throughput：受发送计划、client cap、drain及输入输出量影响；当前有限批次不是稳态容量。
- GPU利用率/VRAM：只辅助环境与资源变化；不能证明显存带宽瓶颈、KV容量不足或请求级资源贡献。
- 命中率：冷组会逐步变热，warm预加载深度不同；token比例不是请求命中概率。cache、input、concurrency影响并非互斥。

### 2.2 样本和设计限制

每cell8请求，理论上只有0.08个样本落在总体最慢1%；P99几乎由最大值决定。3次重复不能可靠建立正式稳定性。原Prefill请求除首条外不是嵌套token输入，存在内容混杂；cached与disabled服务分块，存在顺序/重启混杂；native max_num_seqs4是人为容量控制。只有客户端chunk时间和server阶段直方图，缺单请求阶段关联。不能以相邻请求为独立重复。

## 3. 下一轮增强实验：C预检→A样本扩充→B混合负载

### C0：先验证请求级trace边界（前置门）

本轮只读核查固定安装源码，确认：

- `entrypoints/launchers/cli_args.py` 有 `enable_per_request_metrics` 和 `enable_request_id_headers`。
- `entrypoints/openai/completion/serving.py` 在单prompt、n=1、`stream_options.include_usage=true` 时，将请求计时放进最后usage chunk；字段可能为null。
- `entrypoints/generate/base/serving.py::build_per_request_timing_metrics`：`queue_time_ms=(scheduled_ts−queued_ts)`；`time_to_first_token_ms=(first_token_ts−scheduled_ts)`，**排除queue**；`generation_time_ms=(last−first)`为decode区间；`mean_itl_ms=decode/(output_tokens−1)`。字段名不能替代实际定义。
- `config/observability.py` 提供OTLP及detailed tracing选项，并明确详细计时可能有性能开销；本期先不启用完整detailed tracing。

这是**源码能力核查**，尚未开启服务并验证返回；不得把尚未采到的请求字段写成实测。Phase 1未启用这些开关，不能追补不存在的历史request trace。

下一次执行时，先用8请求验证：`--enable-per-request-metrics`、`--enable-request-id-headers`，保留发送的X-Request-Id、返回header、SSE id和末usage/metrics；不假定这些ID字符串相同，建立显式映射。若字段缺失，保存null与原因；不使用聚合直方图伪造请求值。

| trace字段 | 来源与边界 | 用途 |
| --- | --- | --- |
| run/block/episode/request ID、payload hash、长度、cache状态 | client记录，实验真值另存 | 请求配对与留出；真值不得当待归因输入 |
| planned、arrival、send、first-content、last-content、end、取消/错误 | client单调时钟，原始chunk时间 | client queue、TTFT、TPOT、send和planned两种E2E |
| queue_time_ms、server非queue TTFT、generation_time_ms、mean_itl_ms | 原生末usage chunk，固定版本公式 | 请求级等待与生成证据；不是kernel时间 |
| prefix details（若开启后实际提供） | server usage，有数据才记录 | 不能从相同token长度补猜单请求命中 |
| GPU及server gauges/histograms | 独立采样，时间映射与误差校准 | 背景证据，不冒充单请求分配 |

对齐时不直接相减client/server绝对时钟：优先对比各自同域duration，以queue+server非queue TTFT和client TTFT的差作**边界残差**，不是自动当网络耗时。保留时钟/单位、SSE合并和时间分辨率局限。server queue是否累计抢占等待需单独核实现；未知不得泛化。

开销对照：trace开/关用相同配置、payload和episode顺序交替，3个pilot重复，保存原始数据。若主要时间指标中位数偏差超过预登记5%，或波动无法分离开销，将trace分析组与主性能组分开，不校正/减去未知开销。

### A：增加每cell请求数，保持负载语义

优先扩充Queue cap4/8、Cache cold/warm四个关键条件；Prefill/Decode的正常工作量响应已经较明确，先不对全部12水平等量放大。

**不能简单把原8请求延长为4/s持续1024请求。** 该到达率可能高于服务能力，队列随时间积累，增加N同时改变了相位与压力。采用重复固定8请求episode：相同计划4/s/固定容量，每episode结束先确认请求完成及running/waiting归零，再恢复登记的cold/warm状态。相同比较使用同一token池和发送计划；把episode作为cluster，而非把请求当独立重复。跨episode空闲/重置使其成为重复有限突发，不能称连续生产稳态。

| 级别 | 每cell每重复 | 独立重复 | 范围与允许结论 |
| --- | --- | --- | --- |
| A1 | 8episode×8=64请求 | 5 | 四关键条件，共1280正式请求；核重复方向和P95，P99仍探索性 |
| A2 | 32episode×8=256请求 | 5 | 只晋级有意义的成对条件；P99平均约2.56个尾样本/每重复，不称可靠 |
| A3 | 128episode×8=1024请求 | 5 | 仅selected pair；每重复约10.24个最慢1%样本，仍须区间和漂移检查，不自动可靠 |

保存逐请求原始时延、每episode与每独立重复的P50/P95/P99及摘要。量化每个条件重复内/间波动；对**成对episode/block**进行cluster bootstrap，报告95%区间。4/5重复同向和预登记10%实际意义门槛用于趋势晋级，不替代显著性/等价检验。

P99精度门：至少A3样本，只有独立采样设计成立时才使用order-statistic/binomial区间；episode内相关数据使用cluster方法并明确尾样本的有限分辨率，不把二项iid公式直接套到相依请求。若区间半宽相对估计超过20%或端点对独立重复/重采样设定敏感，结论“精度不足”。不把相依请求直接当iid套窄区间，不用合并5重复掩盖单次样本不足；预算到顶仍不够就停止P99声明。10%/20%/5%均为本阶段预登记门槛，运行前冻结，不按结果改。

### B1：concurrency × long context

2×2：input512/1536 × client cap4/8；output128、cache关闭、server max_num_seqs4、max_num_batched_tokens2048、chunked prefill固定。先最长1536-token池逐request生成后截断512，修正Phase 1非嵌套输入；同repeat所有格子使用匹配payload/episode到达计划。

64请求（8episode）×3重复先筛查，按相同seed成对比较；有信号再5重复。观察短请求/长请求、client queue、server queue、server非queue TTFT、decode分别变化。2×2交互对比是描述性实验，不称新因果分解算法。

额外有限混合验证：固定每episode4短+4长（50/50），固定请求位置并轮换短长顺序，比较cap4/8；不改变平均长度后直接拿全短为纯调度baseline。按长度分层报告tail，检查短请求是否被长输入拖累；不要用全部请求混合P99给“每类根因”。

### B2：cache × concurrency

2×2：cold/warm × client cap4/8；input1024/output128、共享prefix256、同一trace与发送计划、server cap4。每episode前恢复状态：cold reset成功；warm预加载同样完整输入且准备流量单列。冷组自然逐步复用，warm预加载深度保持一致，不把冷态当每个请求都无命中。

64请求×3重复筛查，有信号再5重复；按请求序号、cache实际命中与长度分层，观察暖缓存是否减少prefill，却因queue/decode占比使总tail不下降。不要自动升级为KV pressure实验；现有容量很大，usage/preemption没有压力证据时明确未测。

## 4. 成功标准和验收顺序

| Gate | 成功标准 | 不通过怎么办 |
| --- | --- | --- |
| G0记录正确 | 请求ID/usage/payload/时钟校验；缺失原因标清；trace不凭空补值 | 先修记录，不跑大矩阵 |
| G1边界可信 | client/server等待区分；trace开销按规则验收；histogram计数覆盖本cell | 分开性能与trace组，保留不可观测项 |
| G2重复响应 | 5独立重复至少4同向，主要效应按预登记门槛与区间报告，健康sham不同时漂移 | 候选signature撤回/降级，不挑指标 |
| G3尾部精度 | 达到样本与区间精度，按负载族分层，不以单个极值认定P99机制 | 标精度不足/仅P95 |
| G4混合可解释 | 单因素与混合对照均可核查，保留反例；边界/阶段证据能支持或否定候选解释 | 结论为指标混淆，不造根因 |
| G5研究继续条件 | 正常工作量负样本、独立留出trace、未知干预位置与强已有方法排除后仍有重要缺口 | 仅作为毕设分析能力，不开发自动归因算法 |

当前只完成计划。不会训练classifier、定义root-cause打分或开发诊断器；request trace接入与统计验证属于实验基础设施。

## 5. 失败停止条件

1. 字段缺失/ID无法映射/时间边界错误、统计刷新count不覆盖请求：停止归因结论，先修观测。
2. timeout/失败/OOM、健康状态无法恢复、其它GPU任务/热漂移不可控：停止当前block，保留全部失败和环境；不删异常重跑到好看。
3. trace开销过大、序列改变后模式消失、对照间payload不一致：撤回稳定性，隔离混杂后再决定是否继续。
4. A3仍不能达到P99精度或预算用尽：停止P99扩样，转为P95/阶段边界结论，不制造稳态容量。
5. 只看到正常工作量成本，或原生阶段计时已充分解释混合变化：停止自动归因科研包装，保留工程成果。
6. 强baseline/未知干预或request级事件无法获得：不做准确率/因果声明，保留候选解释与反证。

## 6. 资源、时间与优先级

本轮分析/计划没有新GPU开销。首选现有RTX4060 Laptop 8GB+0.5B，TP1/FP16、最大1536+128上下文，沿用固定容量和cache配置。不要购买/租用GPU来补统计结论。

历史关键8请求episode时长中位数：queue4=4.887s、queue8=4.993s、cold=4.711s、warm=4.920s。按这些实测粗估，四条件A1活跃测量约13.0分钟，A2约52.0分钟，A3约208.1分钟；这些仅是线性外推，**不包含启动、预热、重置、trace、冷却和统计等待**，不是已完成实验或时间保证。实际预算至少留1.5–2倍余量；正式A3只选一对、分多个block，首轮45分钟到点停止并保存。

建议顺序：C0小规模原生request字段/开销核查→A1四关键条件→B两个2×2筛查→只对未被简单解释的成对条件A2/A3。避免全矩阵扩样耗费数小时却不能定位混淆。

若本机因设备共享/散热无法稳定，才讨论云GPU复验：暂定1×RTX4090标准24GB，0.5B/FP16/TP1/相同上下文能留足显存；仅扩大到7B/8B时再核显存。首租暂定4小时硬上限，费用=租前实时单价×时长+存储，当前价格/库存unknown，未经用户确认不租。不同硬件作为独立复验，不合并成4060的样本。

## 7. 下一动作与交付

唯一推荐下一执行动作：C0原生request metrics preflight，8请求×trace开/关×3pilot，校验末usage、ID映射及边界残差，预计30–120分钟，现有GPU，无诊断算法。它降低后续扩样测错指标的风险；本轮不执行。

未来每轮保存完整有效配置、trace schema/缺失率、warming/reset/episode状态、逐请求/服务器/GPU原始数据、失败、运行日志、hash和统计说明。保留全部Phase 1数据，不修改原报告以伪装新结果。

## 阶段复核

1. 本阶段实际完成了什么：36cell再分析、固定vLLM源码接口核查、A/B/C分级增强计划。
2. 原目标 vs 实际结果：计划交付完成；没有新实验或signature确认。
3. Correctness Review：已核实测来源/公式/保护hash；API返回和开销未实测；风险是单位和时间边界混淆。
4. Architecture Review：优势为先用原生request字段；弱点为未提供完整事件链；替代OTLP详细trace开销更高。
5. Performance Review：本轮仅历史证据和成本估算，没有新收益。
6. Bottleneck Analysis：TTFT混淆→client/server边界差异→原生计时核对→证据充分后扩大。
7. 10× Scale Test：只计划扩样；1024和更大模型未执行。
8. Alternative Design：扩样 alone成本高但无request关联；native字段成本较低、要核开销；详细trace成本高、可能阻塞。性能/内存/规模/容错均待验证。
9. Optimization Opportunities：P0边界/P1关键成对扩样/P2混合场景；不开发算法。
10. 与基础知识的联系：排队非平稳、独立重复/cluster、order statistics、时钟域与缓存状态。
11. 与其他开源项目的联系：vLLM原生metrics优先，OTLP备选，已有归因研究仍需排除重复。
12. 新产生的想法：Parking Lot，未知故障注入；本期不实现。
13. Resume Value Review：计划不能写作完成的trace系统/诊断准确率。
14. Interview Review：加N为何改变排队？server TTFT为何不含queue？如何防trace干扰？为何不能合并P99？冷组为何会热？
15. Failure / Mistake Review：纠正把加请求数直接当同工况扩样的风险；审批读取中断恢复后才标接口已读。
16. 独立能力检查：A用户背景；B助手本轮计划；C用户独立统计/trace未验收；D研究创新未验证。
17. 下一步最有价值实验：C0，s=有候选响应、请求边界未知，a=低成本原生字段核对，Q优于全矩阵扩样。
18. 是否允许进入下一阶段：PASS（计划交付），扩样/trace实测与算法门槛未通过。
