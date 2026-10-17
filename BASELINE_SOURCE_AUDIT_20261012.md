# 固定版本基线源码审查

2026-10-12；主执行者 Codex。源码通过 Git 稀疏检出到临时目录，未安装或运行推理引擎。上一轮 raw.githubusercontent.com 连接失败已通过 Git 获取源码解决。本报告不代表完整基线复现。

## 可复用能力及限制

| 基线 | 固定版本与源码位置 | 实际结论 |
| --- | --- | --- |
| Continuum | `316a58794a6ff86b216e579b74fd56ed0c5a911f`；`vllm/v1/core/estimate_with_func.py:10,137,150` | 阈值为 2 秒；工具耗时历史更新使用平均值；`set_up_pin` 对无工具调用返回 0，对未知或估计不超过阈值的工具返回固定 2 秒，对超阈值返回 0。不是完整论文估计器，也不是完全没有估计代码。 |
| Continuum 生命周期 | 同版本 `vllm/v1/core/sched/scheduler.py:237,248,1285,1350` | pin 截止用 `time.time()`；周期清理与相同 job 的释放路径遍历 pinned list 并调用会删除元素的 unpin；取消也进入完成释放路径。是否跳过清理或重新 pin 已取消请求需独立复现，暂不能标为真实引擎 Bug。 |
| GuideLLM | `87a66f0e9d7af24ceb87b4c26e1b87ddfd9b0215`；`src/guidellm/scheduler/strategies.py:775` 起 | 已有依赖节点和会话范围的完成记录。idle_gap 使用 `父实际完成 + time_scale × max(子记录时间−父记录时间−父记录duration,0)`；timestamp 使用基准开始加记录偏移。值得复用，不另写重复调度器。 |
| GuideLLM 输入 | 同版本 `src/guidellm/schemas/data/deserializers/trace_common.py`；对应 replay/session timing 测试文件存在 | 缺 duration 会改变 idle gap 语义；max_wait、session packing 和缩放会改变原始负载。研究基线默认禁用裁剪与 packing、缩放设 1；所有变换需记录。真实 token/prefix、失败传播及服务端事件仍待集成验证。 |
| FairInference | arXiv 2609.18112v1 §9 | 原文表述后续将开源 SGLang fork；本轮检索尚未确认正式仓库。仅可说未确认，不能断言现在不存在。获取不到忠实基线时，不进入以其为对照的新算法收益结论。 |

来源：[Continuum 固定版本](https://github.com/Hanchenli/vllm-continuum/tree/316a58794a6ff86b216e579b74fd56ed0c5a911f)、[GuideLLM 固定版本](https://github.com/vllm-project/guidellm/tree/87a66f0e9d7af24ceb87b4c26e1b87ddfd9b0215)、[FairInference 原文](https://arxiv.org/html/2609.18112#S9)。

## CPU 方法探针

从固定源码 AST 提取相关原方法，去除类型注解后用最小 stub 对象执行；不加载第三方依赖。4 个 Continuum 分支及 2 个 GuideLLM 时间规则断言通过，结果及源码 SHA256 见 `research/evidence/baseline-source-20261012/probe.json`。

GuideLLM 合成反例：父记录开始 0、duration 1，子记录开始 3；父实际完成 1010，基准开始 1000。idle_gap 得到 1012；timestamp 得到 1003。这里只验证目标时间计算差异，不能据此推断整个 scheduler 会在父完成之前实际发送子请求。所有数字为 CPU 合成输入，非延迟或 GPU 数据。没有运行完整上游测试、网络回放、缓存命中或取消生命周期实验。

## 阶段复核

1. 本阶段实际完成了什么：事实，恢复两份固定源码读取、检查关键方法、6 个分支断言并保存摘要。
2. 原目标 vs 实际结果：源码门禁部分解除；完整强基线与 trace 集成仍未完成。
3. Correctness Review：已验证上述方法分支；未验证完整服务、失败传播、缓存身份；风险为把 stub 通过误写成系统通过。
4. Architecture Review：优势是复用 GuideLLM；弱点是仍需语义适配；替代是自写回放器，工程与维护成本更高。
5. Performance Review：暂无证据，不能判断性能。
6. Bottleneck Analysis：源码缺失已解除；强基线未确认 → 忠实实现可能不可得 → 核对作者正式资源 → 成立后缩小对照范围并重新评估创新声明。
7. 10× Scale Test：未执行；不能外推大规模会话行为。
8. Alternative Design：现有随机请求流程简单、内存成本低但不表达 Agent 依赖；GuideLLM 适配增加依赖但复用成熟能力、维护成本较低；自写回放器需承担图调度、状态与失败容错，成本较高。三者性能、扩展性和故障恢复尚无实测。
9. Optimization Opportunities：P0 补齐依赖时间与失败语义验收；P1 将 workload 输入映射现有采集保存链路；成功标准是可复现反例通过，不是功能数量。
10. 与基础知识的联系：DAG 依赖、开放到达与闭环会话、时钟边界、缓存引用生命周期。
11. 与其他开源项目的联系：GuideLLM 为工程复用候选，Continuum 为部分基线；FairInference 尚未完成复现。
12. 新产生的想法：Parking Lot，Continuum 清理与取消路径检查；不扩张本轮到上游修复。
13. Resume Value Review：可描述固定版本源码审查和 CPU 语义探针；不能描述缓存优化收益或完整 Agent 系统。
14. Interview Review：为何缺 duration 改变回放？何时使用 idle_gap？如何保存 token 前缀身份？为何 stub 不是集成测试？取消后缓存谁负责释放？
15. Failure / Mistake Review：上一轮“省略估计器”须区分论文估计器缺失与源码中存在简单估计；本轮已纠正。
16. 独立能力检查：A 用户原有贡献经历；B 本轮助手执行审查；C 用户尚未展示独立回放实现；D GPU 基线和研究假设未验证。
17. 下一步最有价值实验：30–120 分钟构造两轮 Agent 合成 trace，以已有 GuideLLM 回放语义验证“父完成+工具等待”、缺 duration 拒绝、失败/取消不触发成功依赖；先 CPU，仅适配输入和验收，不实现新调度算法。当前 s 为已有固定源码与方法证据，a 为集成语义探针，收益是排除错误负载，成本低于 GPU，Q(s,a) 优先。
18. 是否允许进入下一阶段：HOLD；唯一整改为完成最小 Agent trace 集成语义验收。此 HOLD 阻止算法收益实验，不阻止整改本身；FairInference 忠实基线仍是未来算法实验前置条件。
