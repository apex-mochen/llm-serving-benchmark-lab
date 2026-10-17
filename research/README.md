# LLM Serving Research Workspace

阶段：Trace测量补救复验，2026-10-13；当前BLOCKED/HOLD。

当前主研究方向：**LLM Serving Performance Degradation Detection and Bottleneck Attribution**。A：**当前实验条件下未验证出问题，暂停作为主研究方向**；C观察。当前先恢复测量有效性，不设计诊断算法。

- [Trace开销补救复验](experiments/results/TRACE_OVERHEAD_REVALIDATION.md)：2026-10-13，BLOCKED/HOLD；固定payload两轮256请求，第三轮baseline两次KV分配OOM；不能宣布<5%，不进入Phase 2。

- [Phase 2真实执行结果](experiments/results/BOTTLECKNECK_DIAGNOSIS_PHASE2_RESULT.md)：HOLD；48预检+40隔离pilot，计时关联通过、trace开销门失败、host并行负载混杂；分级扩样与矩阵未完成，不开发自动归因。

- [最新路线更新与B实验设计](reports/RESEARCH_DIRECTION_UPDATE.md)
- [B四类真实GPU筛查结果](experiments/results/BOTTLENECK_SIGNATURE_RESULT.md)：36cell/288请求；候选响应同向，正式稳定性和自动归因未通过。

最新验证：[真实GPU配对结果](experiments/AGENT_WORKLOAD_VALIDATION_RESULT.md)。本轮未支持策略失效，停止基于该预设的A优化开发；探索报告保留为此前讨论快照。主执行者 Codex。目标是证明问题、排除已有解法；不修改核心 Benchmark，不预设创新成立。

- [导师阶段报告 v1.0](reports/RESEARCH_EXPLORATION_REPORT.md)
- [Related Work 矩阵](literature/RELATED_WORK_MATRIX.md)
- [六个可证伪假设](hypotheses/RESEARCH_HYPOTHESES.md)
- [已有工具覆盖](reports/EXISTING_TOOL_GAP_ANALYSIS.md)
- [两组最小实验](experiments/MINIMAL_VALIDATION_PLAN.md)
- [实验配置模板](experiments/minimal-validation.template.json)
- [已通过 CPU 组件验证](../docs/research/AGENT_TRACE_CPU_VALIDATION.md)
- [导师方向讨论稿](../docs/research/RESEARCH_DIRECTION_PROPOSAL.md)

事实类别：文献/作者报告、源码静态证据、本地 CPU mock 证据、真实 GPU 测量、待验证假设分别标注。旧根目录 RELATED_WORK_20261012.md 保留为当日阅读快照，不声称新目录矩阵意味着再次精读或复现。当前唯一进度仍由知识库 research/progress.md 维护。

不把测试中的虚拟时钟、模拟后端返回值混入实验结果。已完成本机Agent真实GPU验证，结果见最新验证报告；历史固定并发数据不回答Agent假设。旧探索材料不代表最新优先级。

- [Phase 2增强计划](reports/BOTTLENECK_DIAGNOSIS_PHASE2_PLAN.md)：先核原生请求计时，再按固定episode扩样与混合对照；无算法开发。
