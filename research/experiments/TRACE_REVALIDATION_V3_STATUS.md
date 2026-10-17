# Trace复验v3：日志与持续观测完成，环境门HOLD

日期：2026-10-15；真实性：真实资源观测与CPU测试，**没有启动推理服务器，没有新增GPU性能测量**。

## 15:41 重新预检

用户要求继续后，实际执行`--preflight-only`，新目录`trace-revalidation-v3-20261015T074111Z`。首样本GPU23%、显存1472MiB，静默门拒绝；主机快照FreePhysicalMemory=2746264KiB（约2.62GiB），也未达到预登记保守3GiB余量，但执行实际停止原因为GPU检查，未走到内存断言。0性能请求、核心hash未变，numeric_pass为null。

另查询Windows GPU Engine计数器：三次各730行但active均为空，与稍早NVML利用率不形成可靠进程归属证据；采样不同步且计数口径可能不同，不据此宣布某个软件占用或GPU空闲。原始`windows-gpu-attribution.json`保留。此次没有结束进程、重启系统、修改阈值或启动模型。下一步仍需用户在任务管理器确认GPU活动并暂停不必要任务、释放内存后再预检，不能连续盲重试。

## 实际执行

在现有主体 `/home/dcl/projects/llm-serving-benchmark-lab` 的实验层新增 `research/experiments/run_trace_revalidation_v3.py` 和 `test_trace_v3_telemetry.py`。核心文件未修改。沿用v2模型、RTX4060 Laptop、FP16/eager、cache OFF、chunked prefill、512/128 token、cap8、4 requests/s、8×8 episode、三轮OFF/ON/ON/OFF/OFF/ON；stats在两组共同开启。配置计划未因环境失败缩小，实际完成variant数为0。

本轮调用（Python为`/home/dcl/projects/vllm-v2-gpu-venv/bin/python`）：

1. `python -u research/experiments/run_trace_revalidation_v3.py --execute` → `research/experiments/results/trace-revalidation-v3-20261015T072050Z/`；静默预检GPU22%，在启动模型前停止。
2. `python -u research/experiments/run_trace_revalidation_v3.py --observe-only` → `research/experiments/results/trace-revalidation-v3-20261015T072132Z/`；只观测30秒，不启动server/workload。
3. `python research/experiments/test_trace_v3_telemetry.py` → 4项合成CPU安全契约通过；日志在第二目录`cpu-contracts.log`。语法编译检查通过。

## 补充的证据能力

- 创建run目录后，将stdout/stderr在文件描述符层重定向到`runner.log`，不再依赖/tmp。server stdout/stderr另写`server.log`（本轮未启动，因此不存在该日志）。
- 每约2秒记录GPU显存、利用率、SM/显存时钟、温度、功耗、GPU UUID、Linux进程/进程组、内存、compute进程；每约15秒记录Windows内存和进程。调用耗时会拉长间隔，按实际monotonic时间解释，不称连续无间隙监控。
- 自有GPU进程按Linux进程组判断；未知PID保守拒绝，不假定归属。监测编译进程与重启，保留原始记录；不会终止无关程序。仅清理自有server和锁。
- 预检要求5次GPU利用率≤5%、无compute/编译；主机余量3GiB物理/6GiB虚拟。这是为旧OOM风险设的保守运行余量，不是测得的模型最低需求。
- 配对完成后分别记录旧数值门（五项中位开销<5%）与更严格阶段门（每轮<5%、证据完整、无检测污染、资源释放、核心hash一致），报告run-to-run CV。门和采样在两组一致；公共采样自身扰动尚未量化，不能宣称观测零开销。

## 实际观测与结论

| 项目 | 实际结果 |
| --- | --- |
| 持续采样 | 14次；首末间隔29.6435秒；2次Windows采样 |
| GPU利用率 | 最低20%、最高28%、均值22.714% |
| Windows空闲物理内存 | 975928、1110904 KiB，约0.93、1.06GiB |
| 采样错误 | outcome记录为空列表 |
| compute进程 | 未检出；不能据此排除桌面/图形GPU活动 |
| 新测量请求 / 完整OFF/ON配对 | 0 / 0 |
| TTFT/TPOT/吞吐/trace开销/CV | N/A，不能从资源记录计算 |
| 是否进入正式对照 | 否；HOLD |

这证明预检未满足，不证明已定位某个后台软件，也不证明trace本身开销过大。没有新OOM，因为没有启动模型。两个运行中的`numeric_pass:false`是旧初始schema在“无比较数据”时的默认值，**不是测得开销FAIL**；原始文件保留。当前脚本已改为无测量时写null，并添加observe_only标记；不重写历史。各run保存当时源码快照，所以源码版本差异可追溯。

## 证据位置与重做边界

两个结果目录保留specification、固定payload、源码副本、host-preflight、preflight/持续resources.jsonl、host-resources.jsonl、runner.log、outcome；观测汇总为`telemetry-summary.json`。并非每个目录都有全部类型文件：首次预检即停止，无持续采样；观察运行未执行性能组。无runtime.json，因为模型启动分支未进入；不补造运行环境。

精确下一步：在用户暂停不必要的GPU活动、主机内存有余量后，先执行`python -u research/experiments/run_trace_revalidation_v3.py --preflight-only`；该模式通过也只表示预检通过，实验状态仍HOLD。再执行相同脚本`--execute`，使用新的run目录；不得通过调高静默阈值、关闭监测或换配置绕过。租卡、关闭其他人任务、push或正式对外动作均未授权执行。

## 阶段审查

1. 本阶段实际完成了什么：日志/采样脚本、4项CPU契约、真实预检与30秒观测；没有性能请求。
2. 原目标 vs 实际结果：目标同配置复验；实际环境门拒绝，开销尚未验证。
3. Correctness Review：已验证日志落盘与采样；未验证server执行分支/同配置overhead；风险为Windows GPU归属不可全见。
4. Architecture Review：只增实验脚本，复用旧采集；弱点为采样本身扰动；替代隔离机器待需要时讨论。
5. Performance Review：暂无新性能证据，不能判断trace开销。
6. Bottleneck Analysis：背景GPU活跃→候选桌面/其他活动→静默预检→确认后才运行，不定位具体软件。
7. 10× Scale Test：未执行；正式矩阵不得越过计量门。
8. Alternative Design：Current本机采样复杂度低/内存低/成本低/扩展有限/易维护/可保留失败；A独立空闲机器隔离较好但迁移成本中且性能未测；B租GPU成本高需确认且硬件不同不可当4060复现。保持Current。
9. Optimization Opportunities：P0恢复静默资源；P1配对测量；P2信息增益正式对照；P3算法暂不做。
10. 与基础知识的联系：文件描述符重定向、异步采样、进程组与资源归属、统计门。
11. 与其他开源项目的联系：复用vLLM已有接口，无上游修改。
12. 新产生的想法：立即可验证静默预检；其他想法Parking Lot。
13. Resume Value Review：可记录实验保障工具，不能写性能收益/定位准确率。
14. Interview Review：无compute为何仍非静默？为何未知PID拒绝？采样如何带来扰动？为何未测量是null？如何保护其他服务？
15. Failure / Mistake Review：此前自动审批额度故障已恢复，不绕过；本次环境拒绝保留原件，无盲目重试。
16. 独立能力检查：A Codex实现；B用户理解未验收；C GPU实验能力本轮未验证；D无科研创新声明。
17. 下一步最有价值实验：s=环境HOLD；a=静默后预检再同配置配对；30–120分钟启动窗口非完成保证；收益为解除最早证据阻塞，成本小于扩样，Q最高。
18. 是否允许进入下一阶段：唯一补救是恢复静默资源并复验，不开展正式对照。HOLD。
