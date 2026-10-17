# Agent GPU Validation 阶段复核

1. 本阶段实际完成了什么：事实，最小两阶段Agent与匹配Traditional回放，12cell/576请求真实GPU测量；TTFT/TPOT/分位数/吞吐/显存及prefix计数保存。
2. 原目标 vs 实际结果：回放和对照完成；未支持策略失效声明，未验证多租户/高KV压力或强调度基线。
3. Correctness Review：已验证payload hash/长度/输出量/发送偏移/依赖、2项mock回归、核心hash；未验证真实Agent质量、生产泛化；风险是小样本P99与低压力。
4. Architecture Review：优势是独立research脚本复用lab/study和GuideLLM，不改核心；弱点是依赖环境需正式锁定；替代为完整GuideLLM backend集成，工作量更大。
5. Performance Review：有真实本机数据，但无稳定因果优化结论；缓存开关TTFT描述性下降，固定顺序与桌面干扰需控制。
6. Bottleneck Analysis：一个cached Agent尾异常→可能GPU/排队变化→需重复及profile→成立后才定位；当前不优化、不命名memory-bound。
7. 10× Scale Test：未执行，202208 Token容量不构成高压力；不能外推7B/多卡。
8. Alternative Design：本轮冻结trace工作量低且公平payload；自主Agent更真实但输出/工具引入混杂，工程成本高；高压力多租户可检隔离但需资源和强基线。性能、内存、扩展及故障恢复只能在各自条件下实测。
9. Optimization Opportunities：P0停止无证据A优化；P1若转B则固定健康参考和已知干预；成功标准是误报/检出证据而非新功能；本阶段不实施。
10. 与基础知识的联系：DAG、开放根到达/闭环依赖、流式测量、缓存块、统计重复与混杂。
11. 与其他开源项目的联系：实际vLLM0.30与GuideLLM；SGLang/Mooncake/完整论文强基线未测。
12. 新产生的想法：Parking Lot，缓存高压/租户场景；不设计算法。
13. Resume Value Review：可陈述本机可复现配对实验与校验；不能写Agent性能优化收益或新机制。
14. Interview Review：为何匹配实际到达？冻结上下文限制什么？P99为何不可靠？cache比例分母是什么？如何区分波动和失效？
15. Failure / Mistake Review：首次异步截止校验失败；第二次reset接口404；已保留失败证据，修正独立脚本并通过mock测试后重跑，未混入结果。
16. 独立能力检查：A用户既有贡献；B Codex完成本轮测量与报告；C用户独立操作未新增验收；D研究假设未通过。
17. 下一步最有价值实验：在导师接受转B后，以保存的健康请求数据做30–120分钟CPU持续退化已知注入，比较固定参考/简单阈值；s=有真实健康样本且A不支持，a=小规模证伪，成本低于扩大GPU，Q优先。当前不自动切换方向。
18. 是否允许进入下一阶段：PASS，仅对实验交付；A算法/优化停止。重大研究方向调整由用户/导师确认，不继续GPU或新算法。
