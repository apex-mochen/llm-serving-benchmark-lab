# 单进程负控执行状态

## 1. 这是什么

2026-10-16按用户指令补齐实验层记录与独立采集后，实际执行负控的状态报告。**HOLD：模型启动前主机物理内存门未通过，0个新推理请求。**不是GPU性能失败，也不是完成了负控。

## 2. 解决什么问题

已补episode与资源时间对齐、采集器与客户端进程隔离、CPU契约检查；保持既有核心架构和历史数据。原方案见同目录`单进程负控先导协议-2026-10-16.md`。

## 3. 核心原理

- `research/experiments/run_diagnosis_phase2.py`仅增加可选`timing`与`partial_path`参数：记录episode内部monotonic原点/结束、UTC锚点、boot ID、client PID，逐请求完成后追加JSONL。默认调用与原返回值兼容，不改变负载/网络请求/指标公式。中止时已完成请求保留，未完成请求不伪造结果。
- 新`within_process_control.py`通过独立OS进程采集Linux/GPU和Windows资源，不与客户端共享GIL；保存每次调用的起止区间、错误、PID、/proc/stat、CPU pressure与可得CPU频率。Windows时间只用Linux调用包围区间关联。主机采集仍可能延迟同一采集进程的Linux轮询，实际频率不保证严格2秒。
- 新执行器固定历史argv/config/payload、trace OFF、max-num-seqs4、client cap8、4请求/秒、512输入/128输出、payload seed20261013、sampling seed20261012。版本/GPU身份/容量检查在通过资源门后执行；本次因提前停止尚未走到这些检查，不称当前环境完整匹配已验证。
- 1预热+4burn-in+64测量、ABBA窗口标签、边界排空、2秒间隔与50毫秒启动延迟预算已落实；描述性输出，无等价PASS或自动诊断。

## 4. 代码 / 例子

实际执行命令（主体WSL Ubuntu-24.04）：

```text
/home/dcl/projects/vllm-v2-gpu-venv/bin/python -u research/experiments/within_process_control.py --execute
```

权威raw：`/home/dcl/projects/llm-serving-benchmark-lab/research/experiments/results/within-process-aa-20261016T071756Z/`。包含specification、固定payload、源码快照、host-preflight、runner.log和outcome。

| 项目 | 实测/状态 |
| --- | --- |
| FreePhysicalMemory | 1,395,976 KiB，约1.33 GiB |
| 固定物理余量门 | 3 GiB，未通过 |
| FreeVirtualMemory | 12,410,508 KiB，约11.84 GiB |
| 已完成episode/推理请求 | 0 / 0 |
| 模型/server | 未启动，无服务器启动进程 |
| 核心文件hash | 未改变 |
| GPU静默/框架版本检查 | 本次尚未执行到，不写PASS |

CPU检查：`test_within_process.py`9项通过，覆盖绝对时钟与partial记录、旧接口兼容、序号分层、标签、排空指标缺失/非零、内存门及采样hazard；`test_trace_cleanup.py`7项通过。使用模拟HTTP流，非模型推理。语法检查通过。

另在`collector-functional-probe/`实际启动独立采集进程，PID916，成功保存Linux/GPU和Windows事件，随后按内存门停止。一次Linux采集区间0.166秒，Windows调用区间0.946秒；它们是单次采集耗时，**不是推理测量开销百分比**。CPU pressure可用，CPU频率字段为0项，表示本WSL路径不可用，不表示CPU频率为0。采集器对推理的扰动尚未量化，GPU执行分支仍未验证。

最后增加了GPU身份核对和采集进程清理错误保留；本次raw保留执行时源码，未替换为最终源码，不事后补造已经走过的检查。

## 5. 常见坑

不降低内存门，不关闭用户程序，不重复运行碰运气。此次没有OOM证据；门是保守操作余量，不是测得的模型最低内存。CPU测试通过不等于GPU测试通过。进程隔离不等于零CPU/IO竞争，采样器单次耗时也不等于客户端扰动。

## 6. 可以用在哪个项目里

本科毕设保留可复现性工程成果；B方向测量仍HOLD，尚无新性能或诊断收益。下一步只在用户保存并关闭暂不用程序、恢复主机空闲物理至少3GiB/虚拟至少6GiB且无其他编译/GPU任务后，用上述命令创建全新run。不拼接本次raw，不扩样或开发诊断算法。

### 阶段审查

1. 本阶段实际完成了什么：时间记录、独立采集、9+7项CPU检查、实际负控预检与采集功能探针。
2. 原目标 vs 实际结果：工程补齐；负控因资源未完成，0请求。
3. Correctness Review：已验证CPU记录/门禁与真实探针；未验证GPU路径、观测开销、版本/GPU一致性；风险为采样盲区与资源竞争。
4. Architecture Review：实验层进程隔离可复用；仍争用主机资源；替代为独立机器采集，当前成本高不采用。
5. Performance Review：暂无新推理证据，不能判断性能。
6. Bottleneck Analysis：主机余量低→可能环境竞争→先恢复资源→成立后只讨论测量可信度。
7. 10× Scale Test：未扩样，不能以单次采集耗时外推。
8. Alternative Design：旧线程复杂度/维护成本低但共享GIL；当前独立进程复杂度中/内存小增/故障可见性较好；独立主机隔离更强但部署与成本高。性能/扩展收益未实测，不为此重构。
9. Optimization Opportunities：P0恢复资源门；P1采样扰动验证；P2重启方差；P3其他模型/硬件。成功标准是可信完成先导，不是低CV。
10. 与基础知识的联系：monotonic时钟、进程隔离、异常保真、采样与排队。
11. 与其他开源项目的联系：固定vLLM服务配置，无上游改动或公开操作。
12. 新产生的想法：立即可验证资源恢复；未来研究测量扰动；其他算法Parking Lot。
13. Resume Value Review：可记录测试/故障保护，不写性能改善。
14. Interview Review：为何UTC不能直接相减？为何缺指标不能当0？独立进程有何残余竞争？CPU fixture验证什么？预检失败为何不是OOM？
15. Failure / Mistake Review：不把预检等同实验完成；历史清理缺陷已回归；最终源码与执行快照差异保留。
16. 独立能力检查：A Codex实现/测试，Claude前轮审查；B用户理解未验收；C GPU未执行；D创新未成立。
17. 下一步最有价值实验：s=物理空闲1.33GiB；a=恢复资源后全新run，准备30–120分钟非保证；收益为可对齐的进程内噪声，成本低于扩样或租卡。
18. 是否允许进入下一阶段：唯一补救为恢复安静资源后运行此负控，不进入Phase2正式对照。HOLD。
