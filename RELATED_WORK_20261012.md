# Related Work矩阵：2024–2026选题复核

检索截止2026-10-12。27篇正式论文/预印本；工具另列。D=本轮方法、实验及相关限制定向阅读全文章节（非逐页通读/独立复现），共8篇。其它阅读范围逐条声明，未知实验条件不补猜测。
实际覆盖MLSys、OSDI、NSDI、ASPLOS、EuroSys、ICML、NeurIPS、SIGMOD；SOSP核作者原始资源；VLDB相关Continuum新版出现占位引用，**未确认正式出版**。不为了覆盖每会议伪造录用，未宣称穷尽2024–2026会议目录。
每行“限制/待验证”包含本项目比较推断；只有注明原文章节者才当作者自述。所有实验条件为作者报告，非本人资源。

| ID | 论文与真实原文 | 年份/渠道 | 已解决的问题与贡献 | 实验条件与Baseline | 未充分回答/比较边界 | 资源/阅读 |
|---|---|---|---|---|---|---|
| M01 | [Continuum / HTML标题Continnum: Efficient and Robust Multi-Turn LLM Agent Scheduling with KV Cache Time-to-Live](https://arxiv.org/abs/2511.02230) | 2025–2026预印本；ICLR2026 Workshop版本；v7 PVLDB有占位DOI，不认定正式VLDB录用 | reload+queue utility、TTL pin、program FCFS | SWE/BFCL/OpenHands；8B/12B/70B；A100/H100/B200；vLLM、InferCept、Autellix+ | 已有工具期间缓存保留；多tenant隔离需直接评估组合，不能断言失效 | Hanchenli/vllm-continuum preview，版本/可运行性未核；D |
| M02 | [Token Latency Fairness: Performance Isolation for Multi-Tenant LLM Serving](https://arxiv.org/abs/2609.18112) | 2026预印本 | FairInference token deadline+cache reservation | Llama3-8B、单A10080GB、WildChat；VTC/DLPM/static partition | §5.5隔离参考模型有假设；§9tool composition评估后续；已覆盖cache公平 | 完整artifact未确认；D |
| M03 | [Justitia: Fair and Efficient Scheduling of Task-parallel LLM Agents with Selective Pampering](https://arxiv.org/abs/2510.17015) | 2025预印本；v2为2026；ICML关键词不是录用证明 | memory space-time成本、预测、虚拟公平完成顺序 | 300agents/9类；7B单A10040GB、13B四V100、32B单H80080GB；VTC/SRJF等 | memory-time公平已有；task-parallel与tool-suspended交互需核原假设 | 原文/附录可读，完整code未核；D |
| M04 | [TOPAS: Workflow-Aware Prefix-State Scheduling for Multi-Agent LLM Serving](https://arxiv.org/abs/2608.25523) | 2026预印本 | workflow-critical path、prefix驻留与batch联合决策 | SGLang0.5.3/Qwen2.5-32B、单A10080GB；3合成DAG+MetaGPT；FCFS/LPM/Autellix LAS等 | 已经联合cache/scheduler；本文不能只把workflow-aware作为创新 | 完整artifact未确认；D |
| M05 | [Learning Agent Execution for KV-Cache Management in Agentic Serving](https://arxiv.org/abs/2608.14624) | 2026预印本 | CacheScout在线Markov图、survival eviction、warmup prefetch | 六agent AutoGen/4类任务；8卡PRO6000 Blackwell96GB testbed；8B主模型；235B四H200；vLLM/Continuum | baseline Continuum取0.3s固定TTL；评估时应使用/调优完整策略，不照抄弱实现 | 完整code未确认；D |
| M06 | [Capture the lifecycle: KV Cache management in ReAct Agents with KVTether](https://arxiv.org/abs/2609.39819) | 2026预印本 | message到KV scope、生命周期状态、多tier驻留策略 | 3node/12GB200、GLM4.7 358B、PD TP4；SGLang/LMCache/MoonCake；production trajectories | 生命周期/取消shared reference不是无人解决；不能单卡复现集群收益 | 完整code/生产trace可得性未核；D |
| M07 | [Ask the Tool, Don't Guess: Agent Tool Calls Hold Their Progress, and the Serving System Should Read It](https://arxiv.org/abs/2609.18849) | 2026预印本 | 实时tool progress、remaining time、cache hints、untrusted校验 | 4公开agent corpora；Continuum/CacheWise/InferCept等预测器；真实engine，GPU型号本轮未定位 | 进度信号/可靠性已有；只有细化隔离交互可能再验证 | artifact未确认；D |
| M08 | [ThunderAgent: A Fast, Simple, and Program-Aware Agentic Inference System](https://proceedings.mlr.press/v306/kang26j.html) | 2026 ICML正式PMLR | program抽象、acting/reasoning状态、cache压力与tool资源协调 | 355B/235B FP8、8H100 nodes；Qwen3-8B单5090；coding/routing/science/RL | 已处理暂停acting与KV thrashing；不能声称首次暂停cache协调 | ThunderAgent-org/ThunderAgent；D原文方法与实验定向读 |
| M09 | [Agentix: An Efficient Serving Engine for LLM Agents as General Programs](https://www.usenix.org/conference/nsdi26/presentation/luo) | 2026 NSDI正式；Autellix是早期名称 | general program-level scheduling | 原始Autellix全文可读；最终NSDI模型/GPU本轮未逐项提取 | 不能当两个独立baseline或误标OSDI2025；最终版本需复验 | 预印本2502.13965及conference PDF；S+早期全文筛读 |
| M10 | [RelayCaching: Accelerating LLM Collaboration via Decoding KV Cache Reuse](https://proceedings.mlr.press/v306/geng26a.html) | 2026 ICML正式PMLR | decode-KV到后续prefill、选择性recompute | 数学/知识/代码任务；GPU/model本轮未从PDF提取 | 非同prefix精确reuse，需quality验证；不选首期实现 | 论文PDF公开，artifact未核；S |
| M11 | [Towards End-to-End Optimization of LLM-based Applications with Ayo](https://doi.org/10.1145/3676641.3716278) | 2025 ASPLOS，DOI10.1145/3676641.3716278 | workflow重写/并行/pipeline | 作者repo有RAG demo；论文完整实验GPU未本轮核对 | workflow整体优化已有，demo不是所有论文实验 | NetX-lab/Ayo；S |
| M12 | [QoServe: Breaking the Silos of LLM Inference Serving](https://www.microsoft.com/en-us/research/wp-content/uploads/2025/10/QoServe_CC_final_v2.pdf) | 2026 ASPLOS作者终稿 | 多QoS/slack-aware动态chunk、调度与overload | Llama3-8B A10080GB TP1、Qwen7B TP2、70B H100 TP4；ShareGPT/Azure；含16A100实验 | dynamic chunk/SLO、负载变化已有；不只与静态FCFS比 | 作者PDF方法/§4选择读，完整artifact待核 |
| M13 | [Pie: A Programmable Serving System for Emerging LLM Applications](https://arxiv.org/abs/2510.24051) | 2025 SOSP，作者lab/项目核验 | 可编程inference/program抽象 | 题录核验；PDF抓取失败，硬件/实验未精提 | API/program可编程已有，不从源码接口推断实现所有策略 | pie-project/pie；S |
| M14 | [CacheBlend: Fast Large Language Model Serving for RAG with Cached Knowledge Fusion](https://arxiv.org/abs/2405.16444) | 2025 EuroSys；2024预印本 | cached chunk融合+局部recompute保质量 | RAG多chunk；GPU/model本轮未精提 | 跨chunk缓存涉及quality；不直接复用为exact Agent prefix | 作者稿可读；S |
| M15 | [HyGen: Efficient LLM Serving via Elastic Online-Offline Request Co-location](https://proceedings.neurips.cc/paper_files/paper/2025/hash/15e92839359df6d22e80042e572538d4-Abstract-Conference.html) | 2025 NeurIPS正式 | interference-aware线上/离线co-location | production workloads；模型/GPU未全文提取 | 吞吐与保护online SLO已有；不同于证明所有Agent暂停隔离 | 原文PDF可取；S |
| M16 | [Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve](https://www.usenix.org/conference/osdi24/presentation/agrawal) | 2024 OSDI | chunked prefill/stall-free batching | 7–180B；A100/A40；ShareGPT/arXiv；vLLM/Orca | 已测tail/SLO/消融，不把chunk扫参当新算法 | microsoft/sarathi-serve；此前全文精读，本轮题录复核 |
| M17 | [Fairness in Serving Large Language Models](https://www.usenix.org/conference/osdi24/presentation/sheng) | 2024 OSDI | VTC，服务量公平 | 原文有baseline与artifact；硬件本轮不重复提取 | long-run service公平不自动等于token latency隔离 | Ying1123/VTC-artifact；此前题录核验 |
| M18 | [Locality-aware Fair Scheduling in LLM Serving](https://arxiv.org/abs/2501.14312) | 2025预印本；正式渠道未核 | DLPM/D²LPM公平+prefix locality | 3B/8B A10G/A100；Gamma/ChatbotArena；VTC/Preble | 已联合公平与缓存；论文保证需按假设 | 基于SGLang；此前方法/实验精读，本轮题录复核 |
| M19 | [Apt-Serve: Adaptive Request Scheduling on Hybrid Cache for Scalable LLM Inference Serving](https://doi.org/10.1145/3725394) | 2025 PACMMOD/SIGMOD，DOI10.1145/3725394 | hidden cache+自适应batch/近似算法 | OPT13/30/66B；1/2/4A10040GB；3任务；component ablation | hidden不是prefix；cache×scheduler消融已有 | eddiegaoo/Apt-Serve；此前精读，本轮题录复核 |
| M20 | [Vidur: A Large-Scale Simulation Framework For LLM Inference](https://arxiv.org/abs/2405.05465) | 2024 MLSys | profile/预测+离散事件/配置搜索 | 7–72B、A100/H100；Chat/arXiv/BWB；扩展vLLM验证 | 容量附近误差放大，新的单卡/cache状态要校准 | microsoft/vidur；此前精读，本轮题录复核 |
| M21 | [SGLang: Efficient Execution of Structured Language Model Programs](https://arxiv.org/abs/2312.07104) | 2024 NeurIPS正式版本；2023预印本 | RadixAttention/cache-aware execution | Agent/RAG/JSON/多轮；本轮硬件不重提 | 结构化多调用/prefix reuse已有；上游功能不计本人贡献 | sgl-project/sglang；此前核验，本轮official工具检查 |
| M22 | [ServeGen: Workload Characterization and Generation of Large Language Model Serving in Production](https://www.usenix.org/conference/nsdi26/presentation/xiang-servegen) | 2026 NSDI正式 | 按client组合生成现实相关时变负载 | cloud多模型/语言多模态reasoning；参数化脱敏数据 | 相似arrival/length不是token-prefix等价；不能称首个dynamic generator | alibaba/ServeGen；此前§6.2读，本轮conference复核 |
| M23 | [StriaTrace: Efficient Tracing and Diagnosis for Online LLM Inference (Operational Systems)](https://www.usenix.org/conference/osdi26/presentation/wu-haonan) | 2026 OSDI正式 | 低开销trace/动态roofline/分层相关诊断 | Qwen3-Coder30B-FP8/H20-3e144GiB节点；NSys/TProf/Scalene；注入/生产 | §6.4持续退化可能被参考吸收；不是自动root oracle | 完整code未确认；此前全文精读，本轮venue复核 |
| M24 | [Benchmarking LLM Serving Systems for Agentic AI Workloads with XPerf](https://arxiv.org/abs/2608.20370) | 2026预印本 | 执行图/token重放与全栈profile/debug | 8应用，120B/35B-A3B，H100-NVL | same seed不保证same trace；host/tool不在scope；对本研究replay强基线 | 原文写将开源；此前精读，本轮题录复核 |
| M25 | [PrefixBench-H100: Characterizing Prefix Reuse and Time-to-First-Token in H100 LLM Serving](https://arxiv.org/abs/2609.19657) | 2026预印本 | reuse/arrival/压力对照 | 单H100-NVL94GB，Qwen2-7B/32B，vLLM/TRT | 固定间隔非Poisson；跨runtime根因仍hypothesis | Zenodo21725505；此前精读，本轮题录复核 |
| M26 | [AgentPerfBench: A Benchmarking and Evaluation Suite for Inference Performance of Agentic LLMs](https://arxiv.org/abs/2609.34683) | 2026预印本 | 真实Agent trace/合成/推理性能suite | SWE/Terminal等；硬件本轮未精提 | Agent Benchmark本身已有，不能作为本项目论文唯一贡献 | artifact本轮未运行；S |
| M27 | [Online Scheduling for LLM Inference with KV Cache Constraints](https://arxiv.org/abs/2502.07115) | 2025预印本，2026新版 | MC-SF/整数规划，KV增长约束 | LMSYS1万对话，Vidur模拟Llama2-70B/两A100 | 是真实trace驱动模拟，不是对应GPU服务实测；word/token近似 | 此前v5全文读，本轮最新题录复核，版本变更需核 |

## 直接竞争论文的阅读结论
- Continuum：§4 utility/TTL、§5工具handler/pin、§6.1及baseline、§9 artifact已核。HTML拼写Continnum与abstract题名Continuum不一致；PVLDB卷/DOI仍占位，不能写已正式VLDB发表。公开仓库为preview，未安装或复现。
- FairInference：§4–5 token deadlines/cache reservations、§5.5理论假设、§6/8/9实验与future work。它已处理cache隔离，不能用“缺少cache公平”做动机；tool composition评估缺口需新实验证实。
- Justitia：§4 memory-centric prediction/queue，§5.1模型GPU/agent mix/基线，§5.2完成公平与延迟。已经按space-time建模，简单memory-debt不是本项目新颖点。§5.1文字对finish ratio方向需复核，本文不照抄可疑定义为自身指标。
- TOPAS：联合prefix state/batch/workflow调度，§V固定arrival trace/基线。静态DAG不是全部Agent负载，但对照不能忽略其联合机制。
- CacheScout：§3在线Markov/survival、§5.1真实testbed/任务/TTL对照。作者设置Continuum固定0.3s，此选择不等于其完整算法。本文不以此作为故意弱baseline。
- KVTether：§5 message→token/KV范围与shared context ownership、§7 backend、§8集群与消融。单卡不能照抄其生产集群收益，pin/replace/one-off已有接口先例。
- Ask the Tool：§3progress stream/partial/invalid报告、§4预测器与decision checkpoints、§6related work。预测漂移、显式信号和untrusted处理已有，本文不声称首次。其引用含未来年份项，正式使用须逐项核出版版本。
- ThunderAgent：§4程序状态/space-time cost/压力协调、§5硬件任务、附录HiCache。暂停acting programs/内存pressure也已存在；新租约方案若等价它的控制方式应停止创新声明。

## 工具能力核查（不是论文）
| 工具/原始链接 | 已覆盖能力 | 本项目如何复用/不能声称 |
|---|---|---|
| [vLLM APC](https://docs.vllm.ai/en/latest/design/prefix_caching/) | hashed block reuse/refcount/allocation/eviction；cache_salt trust group隔离 | 复用KV事件/profiling及bench；salt是安全共享范围，不是租户性能隔离；本地固定版本是否有新接口需核 |
| [SGLang HiCache](https://docs.sglang.io/docs/advanced_features/hicache) | 分层KV缓存等native能力；原论文RadixAttention缓存aware调度 | native字段/version mapping，不能把所有cache能力计本人实现；调度/pin具体源码需本地核 |
| [GuideLLM](https://vllm-project.github.io/guidellm/stable/getting-started/benchmark/) | OpenAI/vLLM backend、concurrency/knee/Poisson/sweep/replay、synthetic/data、report；multi-turn/tool文档 | 直接固定version/schema做runner；不自造同类sweep/replay。idle_gap和timestamp两种turn时钟语义不同，精确replay须核token/DAG |
| [Inference Perf](https://github.com/kubernetes-sigs/inference-perf) | load/client/metrics、trace、多backend/Prometheus；作者稿非已核正式论文 | source adapters；client可观测性已有，不称新增测lag即创新 |
| [llm-grill](https://github.com/fisheatfish/llm-grill) | 多轮/ramp、部分cache/server指标、JSONL/report | 不重复工具功能，也不以其结果替本机验证 |

## 引用网络与剩余排除
Continuum→InferCept/Agentix/Parrot/Pie；FairInference→VTC/DLPM/Kairos/FairBatching；TOPAS→Ayo/Parrot/AugServe；ThunderAgent→HiCache；CacheScout→动态workflow预测；StriaTrace→一般profile诊断。
待深入/源码级排除：FairBatching、Kairos、AugServe、Astraea、SAGA、Pythia与近期cache论文；只命中引用不计已精读。已有同机制则撤回新颖性，不忽略预印本。
ACM/IEEE直连失败/旧GitHub文档404时采用作者正式资源和稳定官方文档，保留访问范围；不使用二手AI摘要填实验条件，不用占位DOI。
