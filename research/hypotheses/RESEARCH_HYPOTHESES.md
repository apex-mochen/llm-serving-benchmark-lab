# Research Hypotheses

六个假设均为待验证；CPU 回放正确性不支持任何性能假设。最新状态：A“当前实验条件下未验证出问题，暂停作为主研究方向”；B为当前重点，C观察。六个假设正文保留为探索记录；GPU最小实验尚未覆盖强A1，B也未验证。见[路线更新](../reports/RESEARCH_DIRECTION_UPDATE.md)，下一阶段只设计受控退化，不开发算法。

## Hypothesis A1：Agent 返回模式与隔离损失

### Research Question

在相同请求 token、模型、根到达和正确调优的缓存/公平组合下，集中返回是否仍增大受保护租户的 SLO 违反率？

### Motivation

Continuum 已有 TTL，FairInference 已有隔离；二者组合效果未知，不能预设传统策略失效。

### Expected Observation

假设存在：配对 trace 上违反率升高，或 P95 增幅超过预登记 10% 实际意义阈值，置信区间不跨无差异。10% 是探索门槛不是结果。

### How to Validate

实验1；保留 token 身份和相同根任务，工具间隔分布分成固定与集中返回，测量排除工具等待的请求延迟及包含等待的任务完成时间；用最优组合而非默认参数作强对照。

### Possible Failure

长度、生成输出或实际到达率不同解释全部差异；现有组合消除差异；小模型不产生足够缓存压力。

### Stop Condition

第14天无可重复差异或普通组合已解决，停止新策略创新声明；第7天仍无法复现强基线则缩小问题并报告。

## Hypothesis A2：暂停会话缓存保留的边界

### Research Question

在有限 KV 容量下，延长暂停会话 TTL 是否同时提高复用并损害活跃租户尾延迟，且该权衡在公平组合下仍存在？

### Motivation

已有 pin/TTL 与公平策略，不以扫描 TTL 为创新，只验证矛盾是否残留。

### Expected Observation

复用增加但 protected tenant P95/SLO 恶化；若命中不可观测，只能报告可核对 prefix 机会，不能报告命中率。

### How to Validate

实验1的缓存开关/TTL与暂停比例子实验；限制范围，控制物理容量、请求长度、采样和顺序；对照调优固定 TTL、原生缓存及适用公平策略。

### Possible Failure

复用收益覆盖开销；请求强制长输出或人工暂停导致不代表真实场景；公平策略已消除冲突。

### Stop Condition

最强普通组合消除权衡或只有极端 OOM 场景时，停止该研究声明；TTL扫参只作工程素材。

## Hypothesis B1：持续退化与匹配参考

### Research Question

按模型/硬件/负载状态匹配的固定健康参考，是否比简单阈值及自适应参考更稳定检出持续退化？

### Motivation

StriaTrace 已有追踪诊断；候选只研究参考更新与持久退化，不重复仪表盘。

### Expected Observation

独立健康 trace 与已知注入上，给定相同误报预算，持续退化检出率或检测延迟改善。

### How to Validate

实验2；阈值、CUSUM/变点、冻结匹配参考、自适应参考；按整条 trace 留出，先登记1%窗口误报预算，调参集与测试集分开。

### Possible Failure

普通CUSUM已足够；负载相位误报；测试故障均在训练出现。

### Stop Condition

强统计基线达到相同性能或数据无法区分正常变化与退化，停止新方法声明，仅保留工程检测。

## Hypothesis B2：多源诊断证据增益

### Research Question

加入请求时间边界与可观测引擎事件，是否比客户端聚合指标更准确缩小已知干预的候选原因？

### Motivation

TTFT可受不同路径影响；相关峰值不能当真根因。

### Expected Observation

盲测干预上的 top-1/top-3准确率提高，同时未知原因能拒绝判断；目标标签是干预位置，不是假装全面根因。

### How to Validate

实验2消融：客户端→GPU→服务端事件；强规则及专家标签对照，多类和复合干预留出。

### Possible Failure

仅识别负载变化而不是瓶颈；注入特征泄漏；只有一种根因；服务端事件缺失。

### Stop Condition

无可核查标签/事件，降级为候选原因证据报告；无独立增益则停止自动归因创新声明。

## Hypothesis C1：缓存状态预测增益

### Research Question

在固定硬件/模型上，加入可观测缓存状态是否减少留出工作负载的延迟预测误差？

### Motivation

Vidur已建模/模拟；简单回归加字段不认定创新。

### Expected Observation

相同训练预算下，缓存相关负载的 MAE与高分位误差降低，且非缓存负载不明显恶化。

### How to Validate

沿用实验1原始数据；长度/并发模型、同预算回归及可校准Vidur作baseline；整条trace划分，冷/热状态分开。

### Possible Failure

缓存状态是未来信息；聚合cache hit包含预测时尚未知数据；无跨trace收益。

### Stop Condition

增益由泄漏/强基线调优不足解释，或无实时缓存观测，停止声明。

## Hypothesis C2：相位变化预测可靠性

### Research Question

在未见的突发相位，状态感知预测能否比稳态模型更早发现延迟预测不可信？

### Motivation

点预测平均误差掩盖过载；预测区间价值需独立验证。

### Expected Observation

在相同区间覆盖率下，突发测试上的区间宽度/拒绝率更优，预测不确定性不漏报。

### How to Validate

长度/并发预测、状态模型及固定/校准区间对照；完整负载族留出，报告覆盖率、宽度、预测成本。

### Possible Failure

区间总是极宽；训练见过全部相位；更新延迟抵消价值。

### Stop Condition

不能超越普通校准区间、数据不足或资源成本超过本阶段，停在备用观察方向。
