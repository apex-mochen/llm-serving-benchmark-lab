# Trace v3 同配置复验结果

运行：`trace-revalidation-v3-20261015T083228Z`；日期2026-10-15。阶段门 **HOLD**，数值中位门 **True**，逐轮<5% **False**。

## 实际执行与核验

RTX4060 Laptop / Qwen2.5-0.5B / vLLM，512输入128输出、cap8、4 requests/s、8×8请求每组，三轮交替顺序。固定配置和payload与v2逐项相同，公共资源采样协议新增并对两组一致。配置、runtime、命令、源码和原始请求在本目录。

已保存384测量请求、192请求原生阶段字段、48预热单列，完整variant 6/6。资源采样175条，Windows采样22条。usage、client公式、native公式、请求ID和比较值离线复算；错误[]，核心hash未变True。

| 指标 | 三轮开销/吞吐损失 % | 中位 % |
| --- | --- | --- |
| mean_ttft_ms | 11.698 / -11.879 / -1.967 | -1.967 |
| mean_tpot_ms | 4.536 / -3.125 / -1.926 | -1.926 |
| mean_e2e_ms | 5.840 / -4.907 / -1.933 | -1.933 |
| requests_per_s | 3.547 / -2.158 / -1.742 | -1.742 |
| output_tokens_per_s | 3.547 / -2.158 / -1.742 | -1.742 |

延迟开销=(ON/OFF−1)×100，吞吐损失=(1−ON/OFF)×100；吞吐为64请求除8个episode时长之和，不含启动/预热/组间采样，不能当连续饱和吞吐。run-to-run CV保存在outcome.json，3轮仍不足以证明统计等价或一般硬件结论。

## 证据与局限

数值中位门与逐轮门分开报告，任何异常轮不剔除。server日志中semaphore警告：['off-r0: leaked semaphore warning', 'off-r1: leaked semaphore warning', 'off-r2: leaked semaphore warning', 'on-r0: leaked semaphore warning', 'on-r1: leaked semaphore warning', 'on-r2: leaked semaphore warning']，保留原文；进程组/GPU释放检查不能证明全部host semaphore已无泄漏。未检测干扰不等于证明零干扰，公共采样自身开销未单独量化。没有独立GPU kernel请求计时，native阶段仍是经过时间。

本报告只回答观测开销门，不回答瓶颈误判率。未运行正式混淆对照、扩样矩阵或诊断算法。若HOLD，仅分析本次波动/观测开销与环境，不能进入正式对照；若PASS，也仅在本配置下通过预登记门，需先阶段审查并冻结正式对照协议。

本轮TTFT OFF运行间CV=11.549%，ON为2.451%。负开销不是性能提升，未定位具体trace组件责任，也不将波动直接归因于host/GPU温度。runtime只记录部分环境，完整继承环境与全部输出文本/SSE未存，精确环境重放仍有缺口，暂不对外发布一般定量主张。

## 阶段审查

1. 本阶段实际完成了什么：6组同配置真实运行、384测量、48预热单列及离线核验。
2. 原目标 vs 实际结果：完成复验，但逐轮5%门未全通过，正式对照未执行。
3. Correctness Review：已验证usage/ID/payload/计时公式；未验证GPU kernel精度及完整环境重放；风险为测量波动。
4. Architecture Review：保持核心、复用原采集；持续采样扰动待单独量化；替代隔离环境暂不实施。
5. Performance Review：只报告上表；不从负值推断优化，不外推硬件。
6. Bottleneck Analysis：配对变号→候选运行顺序/测量波动或trace效应→A/A负控检验→成立后再设计最小修正。
7. 10× Scale Test：未运行，不能扩样掩盖计量问题。
8. Alternative Design：当前外部进程配对复杂度低/内存低/维护低/可重跑但重启波动；A同flag A/A成本中且提供空效应参照；B完整profiler成本高且可能新扰动。三者新增性能收益未测。
9. Optimization Opportunities：P0同flag A/A验证运行间波动；P1确认稳定后才拆trace组件；P2正式对照；P3算法Parking Lot。
10. 与基础知识的联系：配对顺序、warmup、独立重复与异步计时边界。
11. 与其他开源项目的联系：vLLM原生metrics，无上游变更。
12. 新产生的想法：立即可验证A/A负控；其余新机制Parking Lot。
13. Resume Value Review：可审计实验能力；不写性能改善或准确率。
14. Interview Review：中位门为何不足？负开销为何不代表优化？CV如何解释？semaphore警告为何保留？为何不用增加请求数解决一切？
15. Failure / Mistake Review：未隐藏离群或删除负值，旧失败数据保留。
16. 独立能力检查：A Codex执行；B用户理解未验收；C独立运行能力本轮未测；D科研贡献未成立。
17. 下一步最有价值实验：s=三轮结果变号且OFF波动较大；a=冻结同flag/同配置A/A负控，区分空效应波动与trace差异；30–120分钟启动窗口非完成保证；Q高于马上做诊断对照。不自动追加运行。
18. 是否允许进入下一阶段：当前仅允许上述A/A计量补救，不进入正式对照。HOLD。
