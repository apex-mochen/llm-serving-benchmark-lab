# 单进程负控实际测量结果

## 1. 这是什么

用户表示资源准备好后，2026-10-16按已确认v2协议重新执行。**本次确实启动模型并完成64条真实GPU推理请求，但负控不完整，状态HOLD。**不是前几次0请求预检，也不是完整ABBA或稳定性验证。

## 2. 解决什么问题

检查修复后的版本来源、分阶段内存门、独立采集和时间记录能否支持单进程负控。沿用RTX4060 Laptop/Qwen2.5-0.5B/vLLM与固定payload，不改变50ms启动预算、核心架构或诊断研究范围。

## 3. 核心原理

启动前物理空闲4701472KiB约4.48GiB，虚拟23989312KiB约22.88GiB；五次静默、实际import版本及GPU身份检查通过并启动server。执行代码提交为`f78ce0f123cb05673fe3c4b7ba6bdeef8fff75d9`。

完成1个预热、4个burn-in、3个测量episode，共64请求，其中正式测量段24请求。准备episode8（第四个测量episode）时，sleep后的检查触发`Episode start lateness >50ms`，停止且未发送下一episode。0个完整四episode窗口，0个ABBA组；不比较A/B、不算等价检验、不补跑。

该分支原代码未保存触发时具体monotonic值，不能报告超时究竟多少毫秒，也不能认定CPU/Windows/采集器为原因。停止点早于新episode的AsyncClient初始化，不是另一条“实际episode内部起点延误”的分支。

## 4. 代码 / 例子

权威raw：WSL `/home/dcl/projects/llm-serving-benchmark-lab/research/experiments/results/within-process-aa-20261016T143646Z/`。

离线审计程序：`research/reviews/executor-remediation-20261016/audit_measured_pilot.py`。所有64条请求成功、输入512/输出128、native trace为空，TTFT公式复算、relative/absolute时序、逐请求partial记录均通过。client PID525、独立monitor PID696；37条Linux/GPU采样、5条Windows采样，已有记录issues为空，不等于零干扰。

下表仅为3个测量episode的均值描述，不含40条预热/burn-in请求，不能作为稳定性或历史提升结论：

| 指标 | 均值ms |
| --- | ---: |
| TPOT | 12.055 |
| 序号0–3 TTFT | 48.150 |
| 序号4–7 TTFT | 623.359 |
| 全体TTFT | 335.755 |
| E2E | 1866.949 |

核心文件hash未变、cleanup_errors为空、锁已清理；server正常关闭日志保留。OOM关键词未命中；出现1条semaphore资源追踪警告，不能称“所有资源无泄漏”。进程/GPU清理检查不能证明Python host对象全部释放。

发现日志缺口后，新增`experiment_schedule.py`：仅失败分支保存目标时间、检查时间、差值与episode编号；正常分支不新增写盘，仍使用>50ms同一门。3项CPU测试通过（正常不写盘、80ms fixture记录、写盘失败不盖门异常），语法检查通过。**此修复未在GPU上重验**，本次raw源码保持运行时版本，没有回填缺失的超时值。

## 5. 常见坑

“实际有数据”和“负控通过”是两件事；3个测量episode不构成一个完整窗口。没有记录污染不能排除采样盲区，GPU低利用率不能归因host。50ms是工程预算而非效应判定，不因本次失败事后放宽。未完成请求不补造，不跨run拼接。

## 6. 可以用在哪个项目里

本科工程新增真实端到端运行与可对齐证据；科研测量仍HOLD，没有诊断收益或创新结论。下一步唯一补救：用CPU定时探针记录计划时刻、sleep后检查与真实开始时刻，检查固定2秒间隔/50ms预算在当前Windows+WSL环境的可执行性；先冻结探针次数与口径，不立即重跑GPU或放宽阈值。

### 阶段审查

1. 本阶段实际完成了什么：一次真实GPU负控尝试、64请求离线审计、失败日志最小修补与3项CPU测试。
2. 原目标 vs 实际结果：3/64测量episode，不完整HOLD，不声称完成窗口。
3. Correctness Review：已验证请求、公式、时序、分层；未验证具体延迟值、根因、稳定性；采样/退出警告风险保留。
4. Architecture Review：独立监控与绝对时钟可关联；严格定时在宿主系统可能受调度影响；替代为相对间隔协议需另行预登记，暂不采用。
5. Performance Review：仅3episode描述，无性能改善证据。
6. Bottleneck Analysis：唤醒检查超时→OS/负载/采样等候选→CPU时钟探针→成立后再判断测量方案，不优化引擎。
7. 10× Scale Test：本次即被定时门停止，扩样不能弥补缺证据。
8. Alternative Design：当前50ms门复杂度低/故障可见但可用性未证；A先CPU探针成本低/无额外GPU内存/维护低；B改负载间隔改变可比性，需新协议。先A，不声称任何性能优势。
9. Optimization Opportunities：P0失败时间保真已补；P1CPU定时可行性；P2采样扰动；P3跨模型。成功看完整证据而非追求PASS。
10. 与基础知识的联系：sleep非实时保证、monotonic、系统调度、排队与测量误差。
11. 与其他开源项目的联系：vLLM版本/配置通过，无公开PR动作。
12. 新产生的想法：立即可验证定时探针；未来独立重复；诊断算法Parking Lot。
13. Resume Value Review：可记录真实端到端与失败保护，不写稳定性/性能提升。
14. Interview Review：sleep为何可能晚？两个起点检查区别？为何3episode不足？资源警告意味着什么？零issues为何非零干扰？
15. Failure / Mistake Review：承认停止分支未记具体时钟，已修但不回填旧raw。
16. 独立能力检查：A Codex执行/审计、Claude前轮审查；B用户掌握未验收；C负控不完整；D创新未成立。
17. 下一步最有价值实验：s=模型已可运行但定时违约缺细节；a=预登记CPU定时探针，30–120分钟可启动；收益为协议可执行证据，成本低于重复GPU。
18. 是否允许进入下一阶段：保持计量HOLD；唯一补救为CPU定时探针，不进入正式瓶颈对照。HOLD。
