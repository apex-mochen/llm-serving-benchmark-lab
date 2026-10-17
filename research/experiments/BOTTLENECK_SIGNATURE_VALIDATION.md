# Bottleneck Signature Validation

2026-10-12；**四类controlled experiment的设计与验证门槛**。本轮没有运行新的四类GPU实验；只读分析既有Agent实验阶段计时。设计表中的指标模式是待验证假设，不是结果。主线B已确认；A维持“当前实验条件下未验证出问题，暂停作为主研究方向”。不修改核心架构，不设计诊断算法。

## 1. 问题定义

目标是判断：受控工作负载变化是否产生可重复的客户端/服务端指标响应，哪些信号能排除其它解释。

必须区分三种概念：工作量变大导致耗时增加；同工作负载下系统退化；某阶段成为限制吞吐或SLO的瓶颈。本轮用户指定input/output/concurrency/cache为干预，首先测试指标响应，不以干预名称充当瓶颈真值。没有服务端阶段数据或profile时，使用“input-length response”等表述。

## 2. 固定配置与共同流程（待执行）

- 第一轮候选：Qwen2.5-0.5B-Instruct，model/tokenizer revision `7ae557604adf67be50417f59c2c2f167def9a775`，vLLM0.30.0，wheel SHA `ced6857afa0ea7b2e3f0846a62e1394e90f15607`；RTX4060 Laptop 8188MiB、FP16/TP1、上下文2048、gpu_memory_utilization0.45、enforce_eager。实际运行必须重新核验可用环境，旧驱动/包列表不自动代表新实验。
- 普通单变量基准：input512、output128、并发1、prefix cache关闭、temperature0、ignore_eos、seed20261012。同一比较只改指定变量；完整启动参数（含chunked prefill、max_num_seqs、max_num_batched_tokens）按有效版本固定记录，不接受未记录默认值。
- input变化用同一token池的嵌套长度，记录实际token ID摘要；同一长度重复不得无意形成跨cell暖cache。output变化保持完全相同输入；cache比较保持同一请求序列及发送计划。
- 每cell16个独立prefix预热，冷cache测量在预热后明确重置并核验成功。hot cache先按指定trace预加载，准备流量不混入测量；保存准备命中/统计基线。
- pilot：每cell64请求×3个独立重复，仅验证计时/数据完整性与趋势。正式稳定性验证至少5重复×1000测量请求/每cell，随机或交替cell顺序，健康基准穿插；预算不足则保持pilot结论，不声称稳定P99。根到达/发送/入队定义分开记录。
- 保存所有失败、超时、取消；不能只筛成功请求得出改善。真实GPU、CPU mock、历史分析分目录。每次一个引擎及自有服务，固定设备状态，保留温度/频率/功耗、桌面干扰与资源采集错误。

## 3. 四类controlled experiments

### E1：Prefill bottleneck候选——input length

变量input={128,512,1024,1536}，output128、并发1、cache关闭，其它不变；最长总上下文1664，低于2048。先顺序执行隔离单请求服务成本，再决定是否值得做负载压力验证，不并行改到达率。

待验证模式：TTFT和服务端prefill time随输入增大；TPOT可能较稳，也可能因更长KV attention上下文而变慢。GPU计算利用率可能升高，单独不足以证明compute-bound。P95/P99必须按各长度单独比较，长输入正常耗时不标回归。

必要证据：服务端prefill/queue/decode计时、实际未命中prefill Token、无KV抢占。只有prefill成为主要延迟/吞吐约束，并有stage/profile证据时才称瓶颈。GPU利用率/P99单独不够。

### E2：Decode bottleneck候选——output length

变量output={32,128,256,512}，input512、并发1、cache关闭；输出长度用ignore_eos并逐请求usage核对，不能只按max_tokens推算。总上下文最高1024。

待验证模式：总decode time与E2E随输出量增大；**TPOT不必上升**。长输出的吞吐变化可能来自prefill成本摊薄、KV增长、服务时间与样本分母，不直接标decode瓶颈。保留每轮输入不变的输出Token数和流式时间轴；比较归一化每token成本及服务端阶段占比。

必要证据：服务端decode/inference time、TPOT与ITL边界、KV使用/抢占；memory-bandwidth-bound需相关profile/counter，普通nvidia-smi无法证明。若只有总耗时随输出数增加，本实验仅验证工作量响应，不能认定失效或瓶颈。

### E3：Queue bottleneck候选——concurrency

变量client concurrency={1,4,8,16}，input512/output128/cache关闭；服务端max_num_seqs暂定4且各cell完全一致，用固定可观测服务容量产生WAITING候选。这个固定配置用于实验控制，不是调度优化，也不修改核心或引擎代码。

primary使用同一计划到达序列、同一payload与请求数，client cap改变时保存计划到达→实际发送的客户端等待。固定计划4请求/s作pilot起点；若没有形成服务端WAITING，记录“未形成queue候选”，不先标瓶颈。不得在同一对照里同时提高rate和concurrency；需改变rate则另立分层实验。

另一个可选闭环concurrency扫描只作吞吐/饱和曲线，明确没有相同到达率；不能混入primary并声称只改变并发。客户端信号量等待与引擎WAITING时间严格分开。

待验证模式：服务端queue time或waiting gauge增长，TTFT/E2E尾部随之增加；TPOT也可能因batch/资源争用增加。仅TTFT升高不够，必须确认等待发生在服务端。若max_num_seqs限制形成queue，则标签为该固定配置下的容量排队，不称vLLM调度Bug。

### E4：Cache state change——prefix cache

变量state={disabled,enabled-cold,enabled-warm}；input1024/output128，固定同一输入ID和256-token共享prefix，固定计划4请求/s和client cap4。冷组重置成功后按自然请求序列运行，组内可逐步变热，按请求序号报告；不把整个cold cell当每请求零命中。warm组预加载匹配prefix，确认服务端计数后开始测量。

待验证模式：cache hit-token/query-token、computed-prefill Tokens与prefill/TTFT变化相关；TPOT不保证下降。容量压力下淘汰/抢占可改变结果，但本轮设计不自动加高压力变量。状态变化是干预，不是故障。若有效命中差异没有形成，先核trace/cache salt/重置，不解释为优化无效。

## 4. 每个实验必须保存的记录

| 类别 | 字段/数据 | 边界 |
| --- | --- | --- |
| configuration | 模型/tokenizer SHA、引擎实际build、依赖、GPU UUID/驱动、精度/上下文、所有有效参数、seed、命令、cell顺序 | 声明配置与实测环境分开 |
| workload | token ID/hash、长度、输出usage、request/session、到达计划、actual send、并发上限、cache准备与重置 | 不用长度相同证明前缀相同 |
| TTFT | client发送→首有效内容chunk；服务端TTFT另列 | 不包含计划到达前等待；内容chunk可合并Token |
| TPOT/ITL | (最后内容−首内容)/(实际output Tokens−1)，output≤1时null；原始chunk间隔保留 | 不是kernel decode时间，不伪造逐token时间 |
| latency distribution | 客户端E2E、dispatch delay分开；原始请求列表、P50/P95/P99、失败率 | P99样本不足标描述性 |
| throughput | requests/s、output Tokens/s；测量开始/结束、arrival窗口和drain说明 | finite batch不自动等于稳态容量 |
| GPU metrics | 每0.5秒设备memory used、compute utilization、temperature、power、SM/memory clocks，采样时间和错误 | device-wide，非请求级显存/带宽瓶颈证据 |
| cache metrics | prefix查询/命中Token计数差、KV usage时序、preemptions、computed prefill Token | 无事件/计数时unknown；末端usage不是峰值 |
| server stage | request_queue/prefill/decode/inference time直方图count/sum/buckets，running/waiting gauge；可用时request trace | histogram均值/分位数是边际统计，不能相加成客户端P99 |

数据来源候选已由本机vLLM0.30保存的Prometheus HELP核查：`vllm:request_queue_time_seconds`表示WAITING、`request_prefill_time_seconds`表示PREFILL、`request_decode_time_seconds`表示DECODE；未来版本必须再次核定义。用前后sum/count差计算区间均值需覆盖相同请求集合；缺统计刷新/计数不匹配则不报告该cell的有效阶段均值。

## 5. 已有实测：历史阶段边际分析

以下来自此前Agent配对GPU实验，不是新E1/E2/E3/E4运行。12个cell的queue/prefill/decode count差均48，sum差非负；每个cell阶段均值按delta_sum/delta_count计算，再对3个重复取中位数。

| Prefix cache | workload | server WAITING mean ms | server PREFILL mean ms | server DECODE mean ms |
| --- | --- | --- | --- | --- |
| False | agent | 0.0081 | 66.7995 | 1269.6402 |
| False | traditional | 0.0080 | 66.9522 | 1336.8869 |
| True | agent | 0.0079 | 52.1462 | 1208.6752 |
| True | traditional | 0.0080 | 54.4215 | 1246.8517 |

逐cell计算见[历史边际统计](HISTORICAL_PHASE_MARGINALS.json)，原始histogram见[有效运行](validation-runs/20261012T051151Z/metadata.json)。这些数据表明可采集阶段信息，但固定输入/输出、并发/到达没有形成四类干预，不能从此建立可泛化瓶颈签名。缓存开组公布的token计数比例58.33%，异常波动仍保留；没有说明原生策略普遍失效。

## 6. 稳定性与可解释性验收（预登记设计）

- 稳定性：5个独立正式重复中至少4个主要指标方向一致；预设实际意义门槛10%（探索标准），按重复/block bootstrap给95%CI，不能把一个cell的请求当多个独立重复。若样本或预算不足，结论“尚未验证稳定”。
- 基准漂移：同配置sham/healthy穿插；先确认设备、输入和cache状态匹配。若健康组同样漂移，不能把干预组变化归因指定因素。
- 可解释性：客户端变化与服务端相应阶段/状态证据吻合，其它阶段/等待也要检查。Prefill、decode、queue、cache可共同变化；四类不是互斥标签。
- 尾部：如需解释特定P99请求，须有request级事件关联；阶段histogram平均值只能支持群体响应，不能给单请求根因。
- 每类至少有无变化/sham或负样本；计时误差校准、重复顺序、缺失值与停止规则在运行前冻结，不按结果挑成功指标。

## 7. 回答四个问题

1. **是否存在稳定指标模式？** 四类新对照尚未执行，当前不能确认。历史缓存与阶段统计提供候选现象，但不足以验证稳定、可区分的四类模式。
2. **哪些指标可以区分？** 候选为queue time + dispatch delay区分等待位置；prefill time + computed/hit Tokens区分输入计算与缓存复用；decode time + output count + TPOT区分总工作量与每token速度。GPU利用率/显存仅辅助。是否有独立判别力须受控实验确认。
3. **哪些情况无法区分？** 只有TTFT/P99时，排队、长prefill、冷cache、网络延迟可混淆；TPOT升高可来自长上下文、batch变化、共享GPU或抢占；设备显存高不证明KV压力；无request事件无法解释具体尾请求；多个因素共同变化时单变量签名不足。即使阶段数据完整，也可能只是正常成本增长。
4. **下一步是否值得研究自动归因？** 值得先验证观测边界与受控模式，尚不值得直接开发自动归因算法。门槛是稳定响应、强负样本、独立干预真值、已有关联方法/规则仍不足，以及可复现的未知案例。若现成阶段计时/简单分析已经充分解释，则作为毕设工程能力，不宣称研究创新。

## 8. 执行边界、资源与下一动作

本轮仅设计，不运行GPU矩阵、不实现注入或诊断器。下一动作推荐30–120分钟CPU计时边界/sham核对，然后只执行E1的最小pilot再复核，避免一次跑完整大矩阵。本机4060/0.5B可用于功能初验，不保证形成decode带宽或KV压力瓶颈。无需租GPU；若以后扩大到7B/8B，暂定1×RTX4090 24GB，经精度/上下文/并发显存核验及预算确认再使用。

## 阶段复核

1. 本阶段实际完成了什么：四类单变量设计、记录定义、历史阶段边际只读分析。
2. 原目标 vs 实际结果：设计完成；四类稳定模式未实证。
3. Correctness Review：已核历史count/sum与保护hash；未核新干预；风险是把变量标签当瓶颈真值。
4. Architecture Review：优势为复用既有采集；弱点为request trace不足；替代为先proxy/CPU边界验证。
5. Performance Review：仅历史数据，无新增B对照性能结论。
6. Bottleneck Analysis：TTFT相同变化→多个路径→阶段计时与受控因素核对→证据充分后再研究。
7. 10× Scale Test：未执行；单卡pilot不泛化到多机。
8. Alternative Design：指标读取成本低、无request关联；事件trace维护/开销中等可关联；kernel profile成本高需专门范围。性能/内存/规模/容错代价都须实测。
9. Optimization Opportunities：P0计时/真值，P1负样本；此期不优化或开发算法。
10. 与基础知识的联系：排队、工作量归一化、边际分布、cache状态与混杂。
11. 与其他开源项目的联系：vLLM阶段计时已存在，GuideLLM输入复用；StriaTrace等需继续排除重复。
12. 新产生的想法：Parking Lot，复合因素，不展开。
13. Resume Value Review：能展示受控实验设计，不声称诊断准确率。
14. Interview Review：长输出为何不代表TPOT退化？并发为何不等于queue？阶段P99能否相加？冷cache是否整组零命中？为何需sham？
15. Failure / Mistake Review：纠正将prefill/decode/queue作为预先确定标签的风险。
16. 独立能力检查：A用户经验；B助手本轮设计/计算；C用户独立操作未验收；D新模式未验证。
17. 下一步最有价值实验：CPU计时边界和0ms sham，s=可采集阶段数据、边界待校准，a=小型核验，成本低且避免无效GPU。
18. 是否允许进入下一阶段：PASS，仅设计交付；自动归因算法门槛未通过。
