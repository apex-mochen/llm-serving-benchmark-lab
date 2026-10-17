# Agent trace CPU 组件验收

2026-10-12；9 项通过。源码固定为 GuideLLM `87a66f0e9d7af24ceb87b4c26e1b87ddfd9b0215`。测试直接导入真实类，没有 AST 提取；后端、IPC 与时钟被 mock，未运行 HTTP、多进程完整调度、模型或 GPU。

## 复现

从主体仓库执行，当前本机环境示例：

```bash
PYTHONPATH=/home/dcl/.cache/lab-baselines/guidellm/src:/home/dcl/projects/vllm-v2-gpu-venv/lib/python3.12/site-packages \
  /home/dcl/.cache/lab-baselines/cpu-env/bin/python research/tools/agent_trace_integration.py
```

GuideLLM 源码从官方仓库稀疏检出；隔离 Python 3.12 环境安装 culsans，已有推理环境仅通过 PYTHONPATH 只读复用其依赖，没有修改。完整有效包集合、源码 SHA 和测试日志保存在 `research/evidence/agent-trace-integration-20261012/`。culsans 实际为 0.11.0，未宣称满足 GuideLLM 全部声明的版本范围或完成完整上游安装；后续正式集成需独立锁定兼容依赖。

适配器是受限的单会话 CPU 样例：校验 duration/timestamp、重复 ID、图循环及父节点引用，映射到 GuideLLM graph。不是完整生产 trace schema；没有真实 token/prefix 身份、工具结果或质量评测，也没有验证多租户隔离。

## 阶段复核

1. 本阶段实际完成了什么：真实类组件测试 9 项通过，导师讨论稿完成三轮修订。
2. 原目标 vs 实际结果：等待、缺 duration、失败/取消均验证；未执行真实网络与 GPU 回放。
3. Correctness Review：已验证依赖等待与拒绝非法输入；未验证多进程、HTTP、缓存身份；风险为合成输入代表性不足。
4. Architecture Review：优势为复用 GuideLLM；弱点为依赖包尚未正式锁定；替代为自写回放，维护成本更高。
5. Performance Review：暂无证据，不能判断性能。
6. Bottleneck Analysis：完整回放未知→接口集成可能改变历史和 timing→用本地 mock HTTP 执行两轮→发现差异后修正适配。
7. 10× Scale Test：未执行，不能外推会话规模与资源消耗。
8. Alternative Design：随机 CLI 简单但无依赖；GuideLLM 组件复用增加依赖，维护较易；自写回放需自行承担并发/故障状态，成本高。性能、内存、规模和容错须实测比较。
9. Optimization Opportunities：P0 独立锁定兼容环境并验证实际 HTTP 请求；验收为成功、失败、取消的请求数/顺序可核对；P1 接入原始数据保存。
10. 与基础知识的联系：DAG、取消传播、开放根到达与闭环依赖、时钟边界。
11. 与其他开源项目的联系：复用 GuideLLM；与 vLLM/SGLang 接入尚未真实测量。
12. 新产生的想法：Parking Lot，多租户和缓存事件，先不扩张。
13. Resume Value Review：可陈述组件语义测试，不陈述性能收益或生产部署。
14. Interview Review：duration 为什么必需？取消如何阻断子节点？模拟时钟证明什么？为何尚非端到端？跨进程会话如何路由？
15. Failure / Mistake Review：上轮临时目录清理使环境失效；恢复到持久 cache，保留有效版本。审批中断不算测试通过。
16. 独立能力检查：A 用户已有经验；B Codex 编写并运行本轮测试；C 用户独立实现尚未展示；D 性能研究尚未验证。
17. 下一步最有价值实验：30–120 分钟，在锁定隔离环境下通过本地 mock OpenAI API 执行两轮请求与失败路径；当前 s 是组件语义通过，a 是网络闭环；收益是排除接入错误，成本 CPU，优于提前 GPU 实验。
18. 是否允许进入下一阶段：PASS，仅通过组件语义与导师讨论材料交付；不代表研究假设、完整回放或论文创新通过。
