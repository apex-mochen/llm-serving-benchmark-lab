# Direction Update 阶段复核

1. 本阶段实际完成了什么：按用户确认将A暂停、B设为重点，输出路线和受控退化设计。
2. 原目标 vs 实际结果：文档交付完成；没有实现/执行下一阶段实验。
3. Correctness Review：已核127个证据/核心文件hash不变及内部链接；B未验证；风险为标签误用。
4. Architecture Review：优势为只改research文档；弱点为真实服务端事件尚不足；替代为先CPU计时边界实验。
5. Performance Review：本轮无新性能证据；沿用真实Agent结果并保留其边界。
6. Bottleneck Analysis：指标路径不明→可能把代理等待误称prefill→记录各边界的已知干预→验证后才讨论定位。
7. 10× Scale Test：不执行；先小规模CPU，不外推。
8. Alternative Design：客户端等待最简单、内存/工程成本低但只验证客户端边界；代理等待增加转发状态，维护/容错成本中等；引擎源码插桩成本及兼容风险高，本期不选。性能和扩展需分别测量。
9. Optimization Opportunities：P0真值与观测分离，以注入恢复/计时正确验收；P1正常负载负样本；不开发算法。
10. 与基础知识的联系：测量边界、排队、负样本、混杂及实验留出。
11. 与其他开源项目的联系：保留vLLM/GuideLLM数据，StriaTrace等已有工作仍需排除重复。
12. 新产生的想法：Parking Lot，复合故障；本期不展开。
13. Resume Value Review：能展示证据驱动的路线调整，不能声称诊断准确率或新颖性。
14. Interview Review：为何暂停A？未检出是否等于不存在？代理等待与prefill如何区分？长度变化为何是负样本？真值如何防泄漏？
15. Failure / Mistake Review：旧快照A优先易造成误读，已更新research入口与假设状态，原实验不重写。
16. 独立能力检查：A用户背景；B Codex本轮文档；C用户独立实验设计未验收；D B假设未验证。
17. 下一步最有价值实验：仅提出30–120分钟CPU D0 healthy/sham/50/200ms/recovery计时核对；s=B已确认、边界未知，a=单路径可控验证，成本低，Q优先。用户本轮仅授权设计，当前不执行。
18. 是否允许进入下一阶段：PASS，限路线文档和实验设计交付；未批准实现/运行或诊断算法。
