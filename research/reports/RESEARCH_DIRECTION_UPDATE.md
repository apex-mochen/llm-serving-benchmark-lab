# Research Direction Update

2026-10-12；用户已明确确认本次方向调整。本文更新研究路线，不是论文，不认定创新成立。本阶段仅文档与实验设计，没有运行新实验或修改核心系统。

## 当前方向状态

| 方向 | 最新状态 | 行动边界 |
| --- | --- | --- |
| A：Agent Cache/Scheduling/Isolation | **当前实验条件下未验证出问题，暂停作为主研究方向** | 保留所有配置、原始数据、结果与失败分析；不继续A算法/优化开发，不把未检出解释成全局不存在 |
| B：LLM Serving Performance Degradation Detection and Bottleneck Attribution | **当前研究重点，问题与实验待验证** | 下一阶段只设计和审查可控退化实验；不设计诊断算法 |
| C：Performance Prediction | 暂缓/观察 | 不训练预测模型、不扩充GPU矩阵 |

## 1. 原始假设

A方向希望验证：多阶段Agent调用、工具等待、session暂停与恢复，是否会使现有缓存复用/调度机制出现不可忽略的尾延迟退化或隔离损失。强版本A1还要求调优缓存/公平策略组合、受保护租户及可重复SLO恶化。

实际最小实验仅评估原生vLLM Prefix Cache和冻结两阶段trace，没有覆盖完整Continuum/FairInference、多租户隔离或高KV压力。因此对强A1证据不足，不能称已证明其错误。

## 2. 验证方法

- vLLM0.30.0，Qwen2.5-0.5B-Instruct固定revision `7ae557604adf67be50417f59c2c2f167def9a775`；RTX4060 Laptop 8GB，FP16、TP1、上下文2048。
- Agent：24 session×2阶段；输入1024/1152、输出64 Token；根4/s，暂停0.25/0.75秒，父成功才恢复子请求。工具/上下文是合成冻结内容。
- Traditional：完全相同token IDs、输出规模及模型，逐请求目标发送偏移匹配Agent实际发送；实测最大偏差1.415ms。
- cache关闭/开启各3次配对，共12个有效cell、576正式请求。先预热，开启cache时每cell验证重置成功。Agent先于Traditional、cache关闭先于开启，顺序效应未消除。

## 3. 实验结果与证据

以下为每cell统计值在3次重复中的中位数；详细边界及波动见[原始验证报告](../experiments/AGENT_WORKLOAD_VALIDATION_RESULT.md)。

| workload | cache关闭mean TTFT ms | cache开启mean TTFT ms | cache关闭P95 E2E ms | cache开启P95 E2E ms |
| --- | --- | --- | --- | --- |
| Agent | 82.757 | 69.094 | 1476.509 | 1385.705 |
| Traditional | 86.466 | 71.493 | 1604.809 | 1424.197 |

缓存开启后公布的hit-token/query-token差值比例均58.33%；不是请求命中率。三次配对P95变化没有一致方向：其中cached Agent repeat2为1822.910ms、Traditional为1424.197ms，异常未删，不擅自命名根因。服务端KV容量202208 Token，preemption计数差值均0；本次未形成可核查高压抢占场景。

每cell48请求，P99仅描述；没有显著性/等价检验结论。GPU采样包含桌面、温度/频率及固定顺序混杂。前两次失败为截止等待校验失败与reset接口404，保存日志后修正实验脚本重跑，不混入有效数据。

保留位置：[有效运行与完整配置](../experiments/validation-runs/20261012T051151Z/metadata.json)、[配对校验](../experiments/validation-runs/20261012T051151Z/pairing-checks.json)、[原始数据hash](../experiments/validation-runs/20261012T051151Z/raw-sha256.json)、[第一次失败](../experiments/validation-runs/20261012T050708Z/metadata.json)、[第二次失败](../experiments/validation-runs/20261012T050937Z/metadata.json)。不删除、不重写、不迁移这些证据。

## 4. 为什么暂停A方向

当前工况未得到策略失效的稳定证据；缓存复用仍工作，孤立异常不足以支持新机制。小模型、低KV压力与缺乏强组合对照限制结论。继续以失效为既定事实开发算法会先有方案后找证据，且影响本科工程交付。

本次是依据已有证据调整资源优先级，不宣称Agent问题普遍不存在。A可作为历史研究记录保留；若未来有真实高压力/多租户现象、可复现强基线及导师批准，再另立明确证伪实验，不自动重启。

## 5. B方向研究问题

主研究问题：**在模型、硬件、输入输出与到达条件可核查的情况下，可控持续退化与正常负载变化是否能由请求级时间边界及可观测运行证据区分，并缩小退化因素的候选范围？**

先分开两个子问题：

1. Detection：是否确有退化、从何时开始、幅度与持续多久？正常输入/到达变化应作为负样本，不默认都是故障。
2. Attribution：哪些证据支持哪条候选路径？标签只能是可验证的干预位置；客户端等待、代理响应延迟、引擎排队、prefill/decode不可混为一谈。

与已有[StriaTrace](https://www.usenix.org/conference/osdi26/presentation/wu-haonan)、[Vidur](https://arxiv.org/abs/2405.05465)及原生指标的差异尚未证明。检测与归因是目标，不是已完成算法。当前不得以增加图表/指标/规则组合宣称学术创新。

## 6. 下一阶段：只设计可控退化实验

### 实验集合与标签边界

| 编号 | 设计的干预/对照 | 真值记录 | 预期核对的观测（假设） | 不能推断什么 |
| --- | --- | --- | --- | --- |
| D0 | 客户端计划发送至实际发送增加0/50/200ms等待；同一请求payload | 计划、等待开始/结束、实际发送 | dispatch delay改变；从实际发送计的TTFT不应被强行加等待 | 不称服务端排队或prefill退化 |
| D1 | localhost代理在首内容chunk转发前增加0/50/200ms已知等待 | 代理收到首chunk、缓冲开始/结束、客户端收到 | 客户端TTFT变化与注入边界核对；代理上游时间单独保存 | 不称GPU或引擎prefill根因 |
| D2 | 无故障改变concurrency1/4或input512/1024；每次一因子 | 完整工作负载和版本配置 | 作为正常负载变化负样本；不能因TTFT变大就判回归 | 并发/长度变化不是已知故障标签 |
| D3 | 同payload/时序的cache关闭、冷cache开启、warm cache开启 | 重置成功、实际token前缀及服务端计数 | 确认缓存状态变化可否解释观察差异 | 禁用缓存不是引擎Bug；本机不能默认已制造KV压力 |

D0/D1先用CPU mock后端核查计时和失败行为；模拟结果与真实GPU分目录。若后续批准小规模真实验证，再在独立代理/实验脚本中注入，不改vLLM/SGLang或核心Benchmark。此轮不实现或运行上述注入。

### 控制、记录与验收设计

- 初验候选配置：现有Qwen2.5-0.5B固定revision、vLLM同一可核查wheel SHA、RTX4060 Laptop 8GB、FP16/TP1、上下文2048、温度0、输出128、seed20261012；具体运行前填有效配置。CPU mock无模型/GPU性能值。
- healthy→intervention→recovery构成一个完整block，注入0ms作sham；至少3个block核正确性。正式误报/检出研究需更长独立健康trace，不能用几次请求声称稳定准确率或P99。
- 已知延迟必须记录实际等待时长，不只记录期望时长；实验前登记计时误差预算（暂定5ms，按CPU测量分辨率校验后冻结），不按测试结果修改阈值。
- 保存planned/send/first-content/end、代理上下游时间、请求token ID摘要/usage、失败/取消、注入配置与真值时间轴、GPU设备采样及可得服务端指标。每列标来源与单位，不可观测留unknown。
- 调参/分析trace与后续盲测trace按整段分离。真值文件独立保存，不作为待诊断输入；负载干预和根因位置不能偷换标签。
- 本阶段验收是“计时边界正确、干预可开关/恢复、负样本完整、原始证据可追溯”；不验收诊断算法准确率、性能收益或论文创新。

### 资源与停止条件

设计与CPU预检不需要租GPU。后续若批准真实小模型验证，先复用本机；没有新增GPU需求或预算。更大模型选卡与费用另行核验、确认。当前不启动实验、不购买服务。

无法区分计时边界、干预影响多条路径却无证据、版本/负载不匹配、无法恢复healthy状态时停止该实验设计并修订。若后续简单阈值/强现成方法已充分解决窄问题，则B只作为工程分析，不硬包装科研贡献。

## 7. 路线与毕设保障

当前主线B，A暂停，C观察。工程底座继续保留既定FastAPI/SQLite/单GPU worker规划；本次没有改其实现。即使B没有新颖性，配置复现、请求证据、受控实验与分析报告仍可支撑本科毕设。历史探索v1.0及导师提案为当时讨论快照，当前优先级以本报告和research入口为准。

本轮交付仅路线更新及实验设计；下一次执行需以用户授权的明确最小实验为范围，不自动进入诊断算法、GPU大矩阵、优化或论文。
