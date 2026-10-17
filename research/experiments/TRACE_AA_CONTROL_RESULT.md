# A/A负控：协议已固定，内存预检HOLD

日期2026-10-15。用户要求两边完全相同设置验证运行本身波动。本轮已生成并实际调用A/A脚本，但在启动模型前被内存余量门拦下，**0性能请求、0完整配对，不能判断A/A是否稳定**。

## 后续实际运行与22:29复查（最新状态）

上面“0请求”是早先预检历史。后来`trace-aa-control-20261015T090240Z`确实启动了模型，完成A-r0/B-r0/B-r1三组及A-r1的5个episode，保存232测量请求、32预热。离线检查命令、payload、usage、ID与公式通过，所有native_metrics为空，两组实际启动命令相同。三轮没有完成，**不能验收A/A稳定性**；详见同目录`TRACE_AA_CONTROL_MEASURED_RESULT.md`。

09:06:49Z与09:06:51Z监测记录cmake/ninja，进程组3267不属于自有服务880/1447/2007/2653，属于实验外编译。最终错误文字为`Owned process release incomplete or foreign activity`，结合监测证据是外部活动触发，不能直接称已证明自有服务泄漏。原始记录和污染数据不删除、不跨运行拼接、不挑首对充当完整负控。

用户继续后再建`trace-aa-control-20261015T142925Z`（22:29本地），启动前主机空闲物理804408KiB，约0.77GiB，低于3GiB余量，0新请求。两次记录分开保留；未结束外部编译、关闭应用或改门。下一步需要约10分钟独占实验时段（时间估计），无其他编译/GPU活动且主机空闲>=3GiB，再原命令全新A/A。此前仅一对与三个完整组可描述，不构成可用三轮结论。

## 16:59 再次实际尝试

用户再次要求执行后运行原命令，新raw `trace-aa-control-20261015T085924Z`。仍在启动前被固定3GiB主机余量门拒绝；FreePhysicalMemory=2918204KiB，约2.78GiB，completed_variants=0，numeric_pass=null，核心hash未变。没有启动模型，不是A/A差异超阈值。此次原始记录单独保存，未覆盖此前预检。

同一主机快照进程工作集合计：QQ约769MiB、msedge约689MiB；工作集包含共享页，不能相加推算关闭后实际可释放量。建议用户保存工作后暂停不需要的应用，再验证空闲余量，不自动结束进程或重启WSL。不修改固定内存门，不从已有OFF数据伪造本次A/A结果。

## 固定协议

- 主体 `/home/dcl/projects/llm-serving-benchmark-lab`，执行前HEAD `1a50c5ee9b177dddbfdb81fe4ebf7dd72802c1d0`，工作树clean。
- `research/experiments/prepare_trace_aa_control.py`从原v3生成`run_trace_aa_control.py`，不修改v3或核心。生成变换逐项断言原片段恰出现一次；静态核查与语法检查通过。
- A与B都为trace OFF，实际server argv均`list(command)`，request采集参数均False，并要求所有native_metrics为None。两组模型/精度/缓存/环境/固定tokens/seed完全相同，只有记录标签不同。
- 仍为RTX4060 Laptop、Qwen2.5-0.5B、FP16/eager、cache OFF、chunked prefill、512输入128输出、cap8、4 requests/s、每组8×8请求、8预热单列，顺序A-B、B-A、A-B。共同engine stats开启，共同v3持续采样和清理逻辑，不做算法。
- 保留带符号B/A差异和绝对值。延迟signed=(B/A−1)×100，吞吐signed=(1−B/A)×100；负值不解释为优化。数值门为五项绝对配对差异中位数均<5%，阶段门还要求所有逐轮绝对差异<5%、无观测错误/检测污染、核心和资源释放检查通过。三轮只是筛查，不构成等价性证明。真实起跑前specification.json已写入这些门，不按结果改阈值。

## 实际调用与原始证据

`/home/dcl/projects/vllm-v2-gpu-venv/bin/python -u research/experiments/run_trace_aa_control.py --execute`

权威raw：`research/experiments/results/trace-aa-control-20261015T084921Z/`，包含runner.log、源码、固定payload、specification、host-preflight、5次preflight与outcome；不存在server.log或runtime.json，因为模型启动分支未进入。没有OOM事件可报告，不能称无OOM性能实验已通过。

| 预检项 | 结果 |
| --- | --- |
| 五次GPU利用率 | 2%、2%、3%、3%、2%，满足静默利用率要求 |
| 初始Windows空闲物理内存 | 2865100KiB，约2.73GiB，低于固定3GiB余量 |
| 后续独立资源复查 | 2734072KiB，约2.61GiB；另保存host-recheck.json |
| 运行结果 | HOLD，completed_variants=0，numeric_pass=null |
| A/B TTFT、TPOT、吞吐差异及CV | N/A；未测量 |
| 核心文件 | 原始outcome哈希检查未变 |

3GiB是前序为避免旧OOM设的保守操作余量，不是测得的模型最低需求。本次不能证明当前必然OOM，但不能见到资源不足后下调门槛。也不能用前次OFF/ON中OFF组的事后比较冒充这次新A/A结果。

## 下一步与停止边界

需要用户暂停不必要的内存任务、将空闲物理内存恢复到至少3GiB且GPU持续静默。当前复查距离门槛约0.39GiB，仅为本次快照差额，不保证释放某应用后能持续满足。未关闭程序、重启、购买资源或修改预算。

条件恢复后原命令重新执行，写全新run目录，不覆盖本次。通过A/A才讨论原trace差异归因；若A/A仍有超门波动，保留顺序与warmup/时钟等候选解释，先定位计量，不开展正式瓶颈对照或自动诊断。

## 阶段审查

1. 本阶段实际完成了什么：A/A脚本生成、语法静态检查、真实资源预检；无性能请求。
2. 原目标 vs 实际结果：计划三轮同设置；实际主机内存门停止，不支持或否定A/A稳定。
3. Correctness Review：已验证源码中两组命令/开关相同；未验证运行后实际配置等价及波动；风险是把计划当完成。
4. Architecture Review：复用v3，成本低；生成器依赖源码片段但逐项断言；替代独立重写容易漂移，暂不采用。
5. Performance Review：暂无新性能数据，不能判断波动。
6. Bottleneck Analysis：低空闲内存→候选资源压力→恢复余量后验证→不提前定位OOM根因。
7. 10× Scale Test：未运行，不扩样掩盖预检失败。
8. Alternative Design：当前生成复用复杂度/内存/成本低、维护靠断言、可重跑；A独立runner维护成本高；B隔离机器资源好但迁移成本高且改变硬件边界。性能均未新增比较。
9. Optimization Opportunities：P0恢复主机余量；P1执行冻结A/A；P2再决定trace组件；P3正式对照暂不做。
10. 与基础知识的联系：负控、运行顺序、绝对偏差与统计等价。
11. 与其他开源项目的联系：vLLM原接口不改，无上游动作。
12. 新产生的想法：立即可验证内存预检；其余Parking Lot。
13. Resume Value Review：只记可审计负控协议，不写稳定性或收益。
14. Interview Review：为何两组仍需独立启动？为何用绝对差异？为何负值不叫改善？资源门为何不改？历史OFF为何不是新A/A？
15. Failure / Mistake Review：预检拒绝真实保留，没有换配置补造结果。
16. 独立能力检查：A Codex准备执行；B用户理解未验收；C真实A/A测量未完成；D无创新声明。
17. 下一步最有价值实验：s=内存门HOLD；a=恢复余量后原配置A/A；启动窗口30–120分钟非完成保证；Q高于正式对照。
18. 是否允许进入下一阶段：仅允许恢复资源后的同配置A/A补救。HOLD。
