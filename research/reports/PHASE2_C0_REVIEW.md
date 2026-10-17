# Phase 2 C0 原生 trace 预检审查

日期：2026-10-12；主执行者：Codex；权威数据位于主体仓库 `research/experiments/results/phase2-20261012T145433Z/`。

## 1. 本阶段实际完成了什么
事实：真实GPU预检8请求×开/关×3重复=48测量请求；预热另存。4项CPU正确性检查通过。两次OOM失败完整保留于 `phase2-20261012T101158Z`、`phase2-20261012T101552Z`，不是有效测量。

## 2. 原目标 vs 实际结果
事实：请求关联和原生阶段公式通过；5%开销门未通过。TTFT paired ratios=1.055307/1.072827/1.051434，中位1.055307；TPOT中位1.018041，E2E中位1.026468。小pilot无法将全部偏差唯一归因于instrumentation，不能声称无扰动。

## 3. Correctness Review
已验证：request header、SSE ID映射、prompt/output usage、native mean ITL公式、3阶段均值与histogram对齐；有具体原始数据。未验证：GPU-only kernel时间、跨版本/模型的映射正确性。风险：client第一非空chunk与server第一token边界不同。

## 4. Architecture Review
优势：实验脚本复用已有配置/采集器，不改核心。弱点：原生阶段只有3段，没有完整调度/驱逐事件链。替代：OTLP detailed trace，当前不启用。

## 5. Performance Review
事实：只完成小规模开销对照；不合并trace-on/off与Phase1数据，不用估计开销校正。下一轮统一trace-on比较仅支持instrumented条件下的阶段响应。

## 6. Bottleneck Analysis
现象→假设→验证→成立后优化：两次KV分配OOM→环境资源/分配异常候选→原配置在设备占用下降后成功，但不能据此确定OOM根因→目前不优化。TTFT开销门失败→测量扰动/运行波动候选→隔离trace分析组→不开发算法。

## 7. 10× Scale Test
事实：尚未开展64/256/1024扩样；不得称尾部可靠。

## 8. Alternative Design
| 方案 | 复杂度/性能/内存 | 规模/维护/容错/成本 |
|---|---|---|
| 当前原生trace-on独立组 | 低；5%TTFT门失败；额外内存未测 | 小模型可用；原始数据/checkpoint；实验开销可控 |
| A仅client+Prom | 低；缺请求阶段关系；内存未测 | 易维护；无法回答本阶段关联问题 |
| B完整OTLP | 高；开销未测；内存未测 | 事件覆盖可能更强；依赖多，当前不采用 |

## 9. Optimization Opportunities
P0仅隔离trace组：防止混并与错误性能主张；验收为结果注明trace-on。P1扩样质量/区间；P2未来完整事件链；P3新模型均不在本次实施。

## 10. 与基础知识的联系
事实：排队发生于客户端和server不同位置；token与SSE chunk边界不同；bootstrap必须考虑episode依赖；逻辑阶段不是GPU kernel测量。

## 11. 与其他开源项目的联系
事实：vLLM已有per-request metrics，不把复用该API当作原创诊断方法。未建立SGLang同边界验证。

## 12. 新产生的想法
Parking Lot：跨engine原生指标边界审计；完整调度事件链。当前不实施。

## 13. Resume Value Review
可陈述：完成原生请求计时校验和测量扰动检查；不能写诊断准确率、性能提升或自动归因系统。

## 14. Interview Review
五问：为什么native TTFT不含queue？为什么histogram一致不等于GPU真值？为什么请求ID要检查header和SSE？为什么开销不能直接扣除？为何固定episode而非连续增加N？

## 15. Failure / Mistake Review
事实：原配置两次OOM后当前成功；全部失败保留。小样本开销5%门失败。不能将改变环境占用作为已确定的OOM原因。

## 16. 独立能力检查
A：用户已述开源背景；B：本轮脚本与检查由助手执行；C：用户独立trace解释尚未验收；D：学术创新尚未验证。

## 17. 下一步最有价值实验
s：真实计时通过、开销未通过；a：统一trace-on组下执行既定固定episode扩样与矩阵的首个45分钟block；收益：校验重复与混合可解释性；成本：现有单卡，无购买；Q最高理由：直接回答用户验证目标，数据原始可追溯，不转入算法设计。

## 18. 是否允许进入下一阶段
P0隔离已落实于元数据policy及后续报告边界。允许继续独立trace-on阶段分析；不允许无扰动性能结论、合并旧数据或自动归因开发。PASS（限定范围）。
