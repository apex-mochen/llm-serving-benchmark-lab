# Existing Tool Gap Analysis

2026-10-12：工具能力来自官方文档/仓库；不意味着当前本机版本支持全部最新功能。迁移需核对实际 SHA、CLI 和采集字段。

| 工具 | 已解决/已提供 | 本项目不能重复包装为创新 | 尚待验证的研究切入点 |
| --- | --- | --- | --- |
| [vLLM](https://docs.vllm.ai/en/latest/cli/bench/serve/) | 官方 serving Benchmark、请求速率与并发控制、细粒度输出/指标；文档另列prefix cache、metrics、profiling和trace能力 | 官方指标封装、前缀缓存开关、常规压测、增加图表 | 当前窄Agent负载下机制残留问题；服务端事件与客户端边界匹配，不是说vLLM没有观测能力 |
| [SGLang](https://arxiv.org/abs/2312.07104) | RadixAttention及结构化程序/前缀复用；官方benchmark可用 | 发明已有radix缓存、多轮调用或简单LPM对照 | 特定暂停/集中返回负载的隔离行为；需在实际版本源码验证 |
| [GuideLLM](https://github.com/vllm-project/guidellm/tree/87a66f0e9d7af24ceb87b4c26e1b87ddfd9b0215) | 固定源码已有DAG、依赖回放、idle_gap/timestamp、worker失败取消传播；本轮组件验证9项 | 再写相同回放器、把依赖支持称首次 | token/prefix身份、事件接入与公平对照适配；HTTP端到端尚未完成 |
| [Mooncake](https://github.com/kvcache-ai/Mooncake) | KV中心架构、transfer engine、分布式KV store；项目官方说明 | KV转移、分布式缓存集成或connector数量 | 非本阶段首要范围；单卡不验证分布式传输瓶颈，必要时作为未来上游问题来源 |
| [Inference Perf](https://github.com/kubernetes-sigs/inference-perf) | inference性能benchmark工具，官方仓库可查 | 通用负载/结果输出工具再造 | 先按版本能力选择复用；尚未源码安装/执行，不声称缺少特定机制 |
| Continuum/FairInference/Justitia | 已有TTL、延迟隔离、Agent公平机制 | 简单TTL+quota组合、调参或session标签 | 只有正确强组合仍失败且可复现，才可能提出新机制 |
| XPerf/StriaTrace/Vidur | 执行图回放、追踪诊断、性能建模已有研究 | 回放/诊断/预测系统本身即创新 | 特定失败边界与更强验证方法；缺口需实验证据 |

官方网页本轮核查，SGLang指定文档URL读取失败，故其能力引用已核原论文而非臆造网页。未安装Mooncake或Inference Perf，未知细节标unknown。本项目工程价值是统一证据和实验交付；学术价值必须另行证伪验收。
