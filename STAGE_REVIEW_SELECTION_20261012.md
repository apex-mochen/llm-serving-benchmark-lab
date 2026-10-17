# 研究选题阶段复核（2026-10-12）

## 1. 本阶段实际完成了什么
事实：2026-10-12核当前HEAD/hash/GPU；27篇矩阵，8篇新Agent近邻方法/实验定向精读；三方向6假设与21天方案。没有新算法或GPU测量。

## 2. 原目标 vs 实际结果
按用户新要求优先Agent证伪、回归备用；工程不重构。先前16份暂存文档未落库，本轮不称其已提交。

## 3. Correctness Review
已验证原始链接/当前repo状态；未验证baseline/artifact执行、创新/收益。风险是拥挤方向和baseline不可得。

## 4. Architecture Review
保留CLI/raw与已确认薄管理面；弱点是Agent计时/pin观测未实现；替代为固定版本GuideLLM adapter。

## 5. Performance Review
暂无证据，不能判断新机制性能。

## 6. Bottleneck Analysis
暂停KV可能挤压保护tenant→强组合可能不充分→matched tool-shift对照→若成立再测试租约；都是假设。

## 7. 10× Scale Test
未测10倍scale；单卡与大模型/真实Agent质量不得互相外推。

## 8. Alternative Design
Current CLI低复杂度/内存随raw增长/失败日志；A薄adapter管理中成本/状态恢复/仍单worker；B新平台迁移高成本/生态能力强。性能均未知，选择A增量；不加微服务。

## 9. Optimization Opportunities
P0保护既有raw和交付；P1计时/native metrics与强基线；P2有信号才新机制。验收见决策报告。

## 10. 与基础知识的联系
cache/refcount/OS生命周期、queue反馈、GPU异步计时、配对统计与资源公平。

## 11. 与其他开源项目的联系
vLLM/SGLang/GuideLLM原生能力复用；真实bug才PR，不修改上游贡献队列。

## 12. 新产生的想法
立即验证：数据和baseline可达；未来研究：暂停lease/隔离组合；Parking：大规模近似跨agentKV，不同时开多主线。

## 13. Resume Value Review
现有有限batch工程可展示；新机制/论文/收益待验；AI完成不记用户独立能力。

## 14. Interview Review
五问：salt为何非性能隔离；fair+TTL何时已经足够；共享block如何计容量；为何job和token延迟分开；如何停止无信号研究。

## 15. Failure / Mistake Review
检索直接竞争后下调新颖性；Continuum占位PVLDB不认录用；Agentix/Autellix不重复算独立系统；未知硬件不编。

## 16. 独立能力检查
A助手调研/方案；B本轮只读仓库/硬件；C用户独立理解/运行待验；D真实贡献/实验未发生。

## 17. 下一步最有价值实验
s=工程raw可复用、Agent真值不足；a=方向讨论后60–120分钟CPU核trace字段与strongbaseline版本；收益排除不可实验路线，成本低，Q优于先写scheduler。

## 18. 是否允许进入下一阶段
本轮文档交付可审核；只允许一个下一步：与用户/导师确认21天证伪范围。未经确认不改核心。HOLD
