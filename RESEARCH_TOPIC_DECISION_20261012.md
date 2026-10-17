# 研究选题决策报告：Agent缓存与隔离优先，回归定位备用

日期：2026-10-12。供用户与导师讨论，非论文初稿；本轮未实现新算法、未开展新GPU实验、未证明创新。用户提供的软件工程本科/2028毕业、求职/升学目标与导师意见是规划输入，不是实验事实。

## 1. 决策与项目边界
**保留现有Benchmark作为毕设底座；方向2仅批准“优先证伪”的研究顺序，方向3作为有独立验收门的备用，方向1暂不单开主线。**
推荐具体问题：在工具调用等待时间变化、多个Agent与交互请求共享单GPU时，已有cache保留策略与公平/隔离调度组合后，是否仍存在可重复的“保留收益与其他租户延迟目标冲突”？如果存在，是否需要超出“调好的TTL+既有公平份额”的新协调机制？
不能预设冲突存在，更不能把组合策略失败就自动认定新算法。方向2与方向3不同时开展两篇论文。

候选论文题目：
中文：**《面向多租户Agent推理的暂停态KV缓存保留与延迟隔离协同机制》**。
英文：**Coordinating Suspended KV-Cache Retention and Latency Isolation for Multi-Tenant Agent Serving**。
题目是工作题目，不含“最优/首次/因果/保证”；若前期只得到问题表征，改为Study，不保留机制创新声明。
毕设题目按用户最新提供：《面向动态工作负载的大语言模型推理服务自适应性能评测与瓶颈分析系统》。自适应压测属于工程能力，不自动属于论文创新。

## 2. 当前工程与资产核对
本轮实际读取仓库状态并核对核心源码hash：/home/dcl/projects/llm-serving-benchmark-lab，HEAD c269c26f6bbe575336a16534e565c11d5569e6cb，branch codex/benchmark-control-plane，工作区初始干净，无此次核心修改。lab.py/study.py/tail_report.py与上次读取一致；本轮不是新的完整代码审计。此前已完整读核心代码、17项CPU工具测试通过，属于2026-10-10验证，不冒充今天重跑。
当前nvidia-smi：RTX4060 Laptop8188MiB，driver616.64。旧GPU数据仅0.5B模型、固定1024/256、无限rate批次；cache-off；不能作为Agent/SLO研究证据。
现有：统一官方client、vLLM/SGLang endpoint、model/runtime来源、raw/log/设备遥测、static report、request-tail离线分析；缺：可独立配置单engine、通用持续/Agent workload、任务DB/UI、server事件与KV生命周期观测。用户已确认FastAPI/SQLite/单GPU worker最小架构，但Windows管理端草稿未安装/验收。
上轮16份研究材料仍在Windows暂存区，本次只新增新的决策/矩阵/复核，不运行旧安装脚本、不把旧“回归主选”静默改成历史结论。R1现在作为方向3备用；本次用户明确提出方向2优先，研究优先级据此更新，工程架构保持。

## 3. 文献结论：什么已经被解决
2024–2026原始论文/会议/作者稿的范围、年份、实验条件与阅读层级见 [文献矩阵](RELATED_WORK_20261012.md)。不是穷尽系统综述，未核实的渠道/硬件/代码标未知，不按arXiv编号推测提交日期。

关键排除：
- Continuum已经按工具时间分布与reload/queue成本选择TTL并pin缓存。不能把“工具等待保留KV”当新问题。[原文](https://arxiv.org/html/2511.02230)
- TOPAS已经在SGLang联合workflow依赖、prefix驻留与batch状态；单A100/Qwen32B验证，不是只处理静态简单请求。[原文](https://arxiv.org/html/2608.25523)
- CacheScout已有执行图/生存概率驱动的eviction/prefetch；KVTether已有message生命周期→KV状态与多层cache策略；“预测复用/加生命周期事件”已经拥挤。[CacheScout](https://arxiv.org/html/2608.14624)、[KVTether](https://arxiv.org/html/2609.39819)
- FairInference明确联合调度deadline与每client cache reservation；Justitia已有memory-space-time成本与虚拟公平完成顺序。不能把“加入tenant配额/计byte-time”当新算法。[FairInference](https://arxiv.org/html/2609.18112)、[Justitia](https://arxiv.org/html/2510.17015)
- Ask the Tool已有实时progress→cache hints，并处理untrusted signal。不能把“工具进度更准/需要校验”本身称创新。[原文](https://arxiv.org/html/2609.18849)
- StriaTrace已提供在线trace/roofline/相关诊断，XPerf已有Agent保真replay/debugging。方向3也不是空白地带。[StriaTrace](https://www.usenix.org/conference/osdi26/presentation/wu-haonan)、[XPerf](https://arxiv.org/html/2608.20370)

有证据支持的待验证边界：FairInference§9把tool-calling隔离组合评估列后续，§5.5还明确isolated latency模型的限制；Continuum目标主要是JCT/throughput而非证明多租户token隔离；这支持测试二者组合，**不证明它们组合一定失败，也不证明尚无其他论文解决**。
未命中“fair”关键词不能作为论文没有公平机制的证据。需读算法/代码并与新稿持续比对。
发现Justitia和FairInference后，原先“内存时间公平+TTL”的新颖性评估下调为高风险；若简单组合够用，立即停止机制创新。

## 4. 三方向比较
评分1–5，5更有利；GPU项指资源可控性。是判断，不是投稿概率。
| 维度 | 1动态KV调度/tail | 2Agent缓存/隔离 | 3回归检测/定位 |
|---|---|---|---|
| 创新空间 | 2：Sarathi/Apt/QoServe等密集 | 3：具体组合边界可证伪，仍很拥挤 | 3：持续退化/匹配协议有局限证据 |
| 技术与开源价值 | 5：engine调度深，但风险高 | 5：cache lifecycle/scheduler/正确性 | 4：计量、profile与真实regression |
| 现有工程复用 | 3：需要engine改动 | 4：runner/raw+单engine实验，需agent计划 | 5：tail/provenance/历史数据直接复用 |
| 单卡初验 | 4：小模型可做 | 4：短多轮/受控tool delays可做 | 5：A/A与受控退化可做 |
| 强baseline成本 | 2：重现多scheduler/预测 | 2：TTL、deadline、workflow、组合需适配 | 3：完整Stria实现不确定，检测部分可对照 |
| 数据可得 | 4：长度/arrival trace | 3：token/DAG/tool timing不足时只能模拟 | 4：受控因素易得，自然bug真值难 |
| 21天可判定 | 3：怕停留参数sweep | 3：必须Day7/14硬止损 | 4：能较快测误报/漏检，但并非保证 |
| 毕设独立性 | 4 | 4 | 5 |
| 等权合计，仅辅助 | 27/40 | 28/40 | 33/40 |

纯工程可行性方向3更稳；方向2优先是用户目标与可获得的新机制机会的**有期限探索选择**，不是按评分硬说它最安全。已有2028毕业时间允许积累深度，但不因此无限延长无信号研究。

## 5. 每方向两个可证伪假设
| 假设 | 具体支持/推翻标准 | 实现/资源/数据 | 方法与创新风险 |
|---|---|---|---|
| 1-H1 调度/cache交互 | 固定trace/cache初态后，chunk预算×prefix reuse对protected P95-TTFT有非加性交互；CI兼容0/无决策影响则不支持 | 中；单4060+0.5B，后续4090+7B；arrival/token/prefix轨迹 | 随机2×2配对、server queue/prefill/KV观测；交互本身已知且非创新 |
| 1-H2 压力感知自适应有增量 | 同观测信息的自适应策略在held-out burst超过最佳静态+强SLO基线，且无starvation/开销恶化 | 高；单24GB初验，正式多模型；策略源码/长度先验 | 同预算阈值调优与washout，QoServe/SLOs-Serve强对照；简单调chunk不算新算法 |
| 2-H1 组合非充分性（优先） | TTL保留+原有fair cache/scheduler，在tool等待突变/return bursts下仍存在保护租户违反预注册SLO、或明显低效的tradeoff；最佳调优组合消除则不支持 | 高；单4060短上下文可检计量，单4090+7B/8B更合适；tenant/session/token/依赖/tool时间 | 原生+TTL+fair+严格组合，对照共享KV容量/信息；不能“关掉fair”制造问题 |
| 2-H2 协同机制超出组合 | 显式可撤销暂停缓存租约与外部等待状态协调，在held-out实现更优JCT/隔离Pareto点，相比既有可撤销reservation+TTL仍有增量；无增量则否证 | 高；单24GB机制pilot，48/80GB后续；need engine缓存所有权/安全撤销 | H1先过门，机制候选非已成立；FairInference/KVTether/Justitia直接竞争 |
| 3-H1 自适应基线吸收退化 | 固定trace的持续退化被adaptive reference漏检，固定条件参考在同false-positive预算可检出；否则否证 | 中；CPU方案+单4060；step/请求metrics、已知注入/版本 | Stria检测部分+fixed conditional+CUSUM+matched pairing；普通fixed baseline够好则不认新机制 |
| 3-H2 少量复验提高定位可靠性 | 相同GPU分钟、数据预算下，有针对性复验降低独立case误归因且coverage不降；固定复验达到同等则否证 | 中高；单卡，需scheduler/KV/client观测与受控因素 | blind held-out fault family、precision/recall/unknown+cost；不能把事件相关当因果 |

所有“改善/显著”仅是待检验条件；尚无实测提升。假设1-H1可作教学/工程验证，不能因此选成论文贡献。

## 6. 方向2的最小方法：先问题，再算法
RQ：**在单GPU共享KV容量下，暂停于工具调用的Agent缓存保留与交互租户延迟隔离，能否通过超出既有TTL与公平reservation组合的状态协调获得可复现的Pareto改进？**
先界定：tenant是身份/资源主体，session是会话，program是Agent任务，request是单LLM调用；一个tenant不能通过多session逃逸配额。安全salt隔离≠性能隔离。

拟建优化对象：
最小化Agent平均JCT或相对公平参考的slowdown，约束保护租户TTFT/ITL SLO违反率<=预注册ε、有效KV占用<=容量；请求失败与超时计入，不仅统计成功样本。这是问题表述，不能称算法创新。
状态包括active/suspended/resumed/cancelled，block ownership/refcount、剩余/可撤销pin、已知工具返回信息、queue slack。共享block按物理容量唯一计数，tenant公平成本另给明确分摊规则，不能重复计容量。

候选机制（仅H1成立后）：
- hard reservation保留，剩余KV允许暂停session借用，但**以可撤销租约**记录，而非无条件pin；
- 在active admission/工具完成/取消/timeout事件更新，按保护租户压力回收idle borrowed KV；live active引用不能撤销；
- 保留价值已有TTL/预测器提供，不发明新预测器；优先审查现有fork有没有相同租约机制；
- 若初始静态lease够用，它就是工程组合baseline。只有证明需要新状态估计/决策规则、明确错误上界或收益机制、消融及强baseline差异后，才设计自适应机制。现在不宣称数学保证。

可验证invariant：无悬空引用/重复free；physical KV守恒；取消/timeout后pin可释放；租约回收只在cache-safe point、有限回收延迟实测；模型输出/token等价（限定deterministic配置仍需容差/并发验证）。
这些首先是正确性，不自动成为性能/论文贡献。

## 7. Baseline与消融
B0：固定版本vLLM/SGLang原生cache和调度，同模型/同容量。
B1：Continuum实际TTL/utility实现，不能用唯一0.3s固定TTL代替其全部算法。preview代码必须核论文版本；无对应版本标实现差异。
B2：FairInference策略或明确标“论文级重实现”，加VTC/DLPM；延迟隔离目标不同，不能只选throughput-fair VTC。
B3：**强组合**B1+B2，优先级/pin可撤销语义正确，给予相同tool信息与充分调参；静态份额/静态租约构成另一强组合。
B4：可获得时加入TOPAS/ThunderAgent/Justitia的适用部分；不同Agent/DAG范围明确，不强造不可运行对照。
B5：oracle工具剩余时间/最优离线容量只作上界，不能作为低成本可部署baseline。

消融：去暂停态协调、固定预算替自适应、移除返回信息、关闭借用、固定TTL、禁prefix、取消/timeout分支、共享block计量；每项对应一个机制，不全扫参数。调参只在开发trace；每baseline调参时间与信息预算相同。
若baseline不可实现/条件公平不可保障，结论是“评估不足”，不是默认新方法赢。

## 8. 实验、数据与统计
最小场景：两租户，一类短交互请求，一类4–8轮串行Agent；同tenant多个session是辅助。prefix沿历史增长，tool gap三种：短稳定、重尾、mid-run等待分布突变。再加return burst/取消/timeout，只在基础场景稳定后扩展。
独立到达计划是open-loop，依赖的下一turn在实际完成+tool gap之后发送；不能为了相同timestamp破坏Agent依赖。记录planned root arrival、ready time、actual send及dispatch lag；closed-loop单独作为部署模型，不一概称不真实。
先合成确定性token与可控tool delay：标“模拟Agent流程+真实GPU推理”。真实SWE/BFCL轨迹须核许可/是否带token、tool时间和依赖；只有长度无法重建prefix。不调用收费模型生成轨迹。
0.5B只能测机制/计量，不声称真实编程Agent质量；performance replay与真实agent completion/success分开。跨Agent decode→prefill近似KV复用涉及质量，首期不做RelayCaching式近似。

主终点：保护tenant SLO违反率和P95-TTFT/真正ITL，Agent JCT；次终点缓存节省prefill、bytes×time、preemption/recompute、拒绝/timeout、output吞吐与运行开销。返回后TTFT与从最初task到完成JCT都报，防把工具暂停从账上消失。
对每trace seed/run配对、策略顺序随机、每run清cache/同暖机；至少5独立seed作为探索起点，根据方差追加，不保证统计功效。bootstrap以run或session cluster为单位，token不是独立样本。95%CI报告效应与失败/unknown覆盖。
P99只有尾样本和CI够时作为主张；1000样本只有约10个1%尾部观察，不足自动认证生产P99。
用预注册主要终点，次要多比较校正；test按trace/环境/工具类型划分，不能同run按请求随机split。置信区间宽则inconclusive，不以“不显著”宣称无效。
CPU/mock、profile校准仿真、真实GPU分别目录/字段/evidence_id；deviceutil不能证明memory-bound，client queue不是schedulerqueue。

## 9. 资源与租卡建议
**第一步不租卡**：本地4060/8GB、现有Qwen2.5-0.5B，CPU trace/invariant检查和短上下文机制pilot；不能复现大模型论文硬件收益。
若Day7数据/接口门通过、需要7B/8B真实验证：**暂定租1张RTX4090 24GB**，FP16/BF16、TP1、context2–4K、初始2–4活跃session；建议首轮4–6小时，不先租多卡。理由是权重+有限KV可放单卡，降低阶段性成本；实际engine预留/激活/模型GQA配置必须先显存预检。
需要8K上下文、更多active+retained sessions或复验FairInference A100平台：**1张A100 80GB**；只是机制扩展时也可选**1张A40 48GB**，实际供给/价格待确认。不使用改装显存卡结果冒充标准4090或A100证据。

估算FP16/BF16 KV单token bytes=2×layers×KVheads×head_dim×bytes_per_element，乘唯一驻留token数；另加weights/激活/runtime/碎片/预留。不能只靠model weight大小租卡；share/pin/recompute需用实际allocator block计量。
[AutoDL GPU文档](https://api.autodl.com/docs/gpu/)列4090/A40/A100规格；[计费规则](https://www.autodl.com/docs/price/)按开机至关机时长×单价，准备环境也可能计费。检索到官方首页4090示例价1.88元/时，**不是账号实时报价**；若该价适用，4–6小时计算费约7.52–11.28元，另有存储等费用须租前核对。不擅自购买/充值/租用。
首次基线套件6策略×2场景×5seed×180秒=3GPU小时纯测量，加setup/warmup预计4–6小时；完整扩展不是同预算，需再估。无信号/版本不兼容/只能通过OOM制造退化则关停实验并记录，不反复烧预算。
选型依据是功能与小模型验证；指定A100/H100原文性能复现必须用对应硬件/模型/版本，不能用4090替代。

## 10. 21天验证路线与停止条件
以方向审核与资源可用后D1起算；若2026-10-13启动，D21为11-02。计划不是后台自动任务，也不是21天出论文承诺。
| 天 | 动作 | 必须交付/门 |
|---|---|---|
| D1–3 | 核对Continuum/FairInference/Justitia/TOPAS/ThunderAgent源码及版本；画invariant/强组合定义 | 近邻差异表；若已有等价机制，取消创新声明 |
| D4–7 | 复用GuideLLM/现client接口做CPU Agent trace与计量、cancel/refcount fixtures；本机短GPU baseline opt-in | 依赖/token/cache计量可达；无接口/不可复现强基线，止损转3 |
| D8–10 | 同单卡运行native、TTL、fair、正确组合；开发trace调参，正常/pressure负例 | 判断H1；最佳组合够用则保留工程case并转3 |
| D11–14 | H1支持才isolated hook试验可撤销暂停lease；不重写engine | safety+rollback+profile开销；仅加配额已等价先例则不认算法 |
| D15–18 | held-out tool shift/return burst与独立seeds；必要消融/敏感性 | paired effect/CI/失败；无Pareto增量停止H2 |
| D19–21 | 冷启动复现、artifact/checklist、导师审查继续/缩题/转向 | 研究gate记录；只有可信差异才计划更大实验 |

进入继续研究的建议门：至少两种独立held-out trace/工具变化下，最强组合仍暴露可重复冲突；候选机制改善预注册主终点且另一目标不越过声明容差，正确性全部通过；不是仅扩大资源或调弱baseline。门阈值先与导师确定，不伪造收益。
任何安全错误先停GPU；超过2天只能修依赖无机制可达信号则缩scope；Day14未获得可解释现象则切备用，不以2028毕业为由无限延期。
预期失败：working set都能放进HBM无冲突；memory分区+TTL已足够；工具gap长无复用；queue/CPU热主导；hint失真；共享prefixownership难正确；pin回收让Agent更慢；小模型模拟无法代表真实Agent。均记录负结果与适用边界。

## 11. 备用方向3及双轨保障
备用题目：《面向状态变化的LLM推理性能回归判定与受控瓶颈验证》。
主问题：固定健康参考、合法实验状态匹配与有限受控复验，相比普通matched pairing/conditional CUSUM及Stria式adaptive检测，是否改善持续退化判断/误归因？StriaTrace§6.4已说明持续退化吸收入基线的边界；fixed baseline若够用仍只算工程，不自动创新。
停方向2不意味着方向3自动创新；重新执行3-H1/3-H2与强baseline门。注入退化不是自然上游bug，需真实revision case。

本科验收：单engine/task状态/index/UI/配置/trace/指标/报告/自动测试/真实demo/学校材料，沿现有最小架构增量做；研究失败也完成。用户2028毕业，优先积累一个可复跑、可独立解释的系统。
论文验收：新的可证伪问题或机制、完整近邻排除、强baseline公平对照、消融/统计/失败/泛化与artifact。没有这些不写完整论文或承诺投稿等级。
上游成果：若发现真实pin生命周期、计量、取消、scheduler缺陷，先最小复现/全状态Issue-PR排重/Red→Green→Regression/真实性能配对，再准备中文/英文reviewer package。不把参数取舍当bug，不保证有PR；公开Issue/评论/Push/投稿均由用户确认。
求职与升学：可展示实验设计、metric边界、源码根因与可验证修复；AI辅助与用户独立完成程度分别记，尚无独立操作记录不声称已掌握。

## 12. 给导师的待讨论决策
推荐**同意方向2的21天证伪探索**，明确强组合Baseline与Day7/14/21停止门；保留方向3备用、方向1作对照机制。此报告完成文献初审，不代表“已找到可发表创新点”。
需要导师讨论的是研究问题和证据门，而非承诺某会议录用；不将CCF分类与期刊分区混用。
