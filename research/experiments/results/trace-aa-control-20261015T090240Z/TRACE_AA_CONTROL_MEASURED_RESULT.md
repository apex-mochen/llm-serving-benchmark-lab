# A/A负控实际结果

日期2026-10-15；运行`trace-aa-control-20261015T090240Z`；阶段 **HOLD**。

## 设置与证据

RTX4060 Laptop / Qwen2.5-0.5B / vLLM，FP16/eager、cache OFF、chunked prefill、512/128 tokens、cap8、4 requests/s、每组8×8请求、8预热单列，三轮A-B/B-A/A-B。两组均trace OFF、stats ON，共用同采样器。已从实际command.json核查各组argv/cwd/环境覆盖一致，全部已保存请求native_metrics均为空；固定payload、usage、唯一ID和client公式已复算，核心hash未变。

实际保存232测量请求、32预热单列、完整组3/6，资源采样107条、检测污染采样2条。原始outcome错误：`AssertionError('Owned process release incomplete or foreign activity')`。审核错误：[]。记录污染：['compiler:3301:cmake', 'compiler:3301:cmake', 'compiler:3395:cmake', 'compiler:3396:ninja', 'compiler:3402:cmake']。

## 运行差异

以下表仅在6组完整时生成；不从残缺/受污染运行挑出一对冒充完成。带符号延迟差异=(B/A−1)×100，吞吐差异=(1−B/A)×100；负值不是优化收益。验收看绝对差异，各指标绝对配对差异中位数<5%，并要求逐轮绝对值<5%。该门是操作筛查，不是统计等价检验。

| 指标 | 三轮带符号差异 % | 绝对差异中位 % |
| --- | --- | --- |
| 未形成完整三轮 | N/A | N/A |

完整组均值的运行间CV（仅描述，受污染或不完整时不作为有效稳定性结论）：
- mean_ttft_ms: 8.988%
- mean_tpot_ms: 3.773%
- mean_e2e_ms: 4.750%
- requests_per_s: 3.040%
- output_tokens_per_s: 3.040%

吞吐分母为8个episode时长之和，不含启动/预热/组间采样；不能当连续饱和吞吐。请求不是独立重复，三对也不足证明等价。比较较早ON/OFF时存在时间与环境差异，A/A不能直接扣除为trace净开销。

## 解释与停止边界

若检测污染或组数不足，只能说明本次负控未完成；若完整且绝对差异超门，则说明在本协议下运行波动仍不可忽略，不证明具体host/GPU根因；若通过，也不替代trace开销门和正式诊断对照。semaphore日志警告：['A-r0: semaphore warning', 'A-r1: semaphore warning', 'B-r0: semaphore warning', 'B-r1: semaphore warning']，不宣称无host泄漏。完整继承环境与输出文本/SSE未存，准确环境重放仍有边界。没有训练或诊断算法，没有核心改动。

## 阶段审查

1. 本阶段实际完成了什么：本目录真实运行与离线审计，数量见上。
2. 原目标 vs 实际结果：检验同设置运行波动，不把未完成结果当通过。
3. Correctness Review：已核查命令/trace OFF/payload/计时；未验证GPU kernel精度；风险为背景变化。
4. Architecture Review：复用v3低成本；重启/采样仍可扰动；隔离环境为替代。
5. Performance Review：只报告A/A差异，不声称优化。
6. Bottleneck Analysis：波动/污染→候选运行环境→单一可控复核→成立才修正。
7. 10× Scale Test：未开展，不能用扩样替代控制。
8. Alternative Design：当前外部配对维护低/内存低/成本低/可重跑；A长进程内交错窗口减少重启但改变边界、维护中；B隔离机器资源控制较好但迁移成本高且硬件不同。新性能未测。
9. Optimization Opportunities：P0若HOLD先恢复可控环境；P1再检查计量；P2正式诊断暂不做；P3算法Parking Lot。
10. 与基础知识的联系：负控、绝对偏差、run重复与选择偏差。
11. 与其他开源项目的联系：原生vLLM接口，无上游修改。
12. 新产生的想法：可验证观测窗口/运行顺序；其余Parking Lot。
13. Resume Value Review：负控证据，不写收益或准确率。
14. Interview Review：为何相同命令仍波动？为何不用请求作重复？如何判外部编译？负值如何解释？为何不扣A/A得到净效应？
15. Failure / Mistake Review：旧预检与中断保留；不跨run拼接。
16. 独立能力检查：A Codex执行；B用户理解未验收；C独立实验能力未评；D无创新成立声明。
17. 下一步最有价值实验：若HOLD仅选择恢复静默或核查固定运行窗口的一项计量补救，先看本次具体结果再冻结协议；30–120分钟启动窗口非完成保证，不进入诊断。
18. 是否允许进入下一阶段：本轮仅负控结论，不自动开展正式对照；实际门见上。
