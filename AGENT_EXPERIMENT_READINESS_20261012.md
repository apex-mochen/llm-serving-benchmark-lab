# Agent 最小实验就绪审查（2026-10-12）

本轮只核查基线可获得性、现有接口及 CPU 测试；没有新 GPU 性能数据，没有改动核心代码。

## 基线忠实度

| 基线 | 核查结果 | 下一步与限制 |
| --- | --- | --- |
| Continuum | 作者公开仓库存在；README 明确省略论文估计器；HEAD 为 `316a58794a6ff86b216e579b74fd56ed0c5a911f` | 公开预览不能标为完整论文复现。源码下载连接失败，未完成调度器、pin/TTL 及取消路径核查；需要取得固定版本源码并确定估计器方案。 |
| FairInference | 论文可读；本轮未确认作者正式代码链接 | 未确认不等于代码不存在；取得代码或明确标注并验证忠实重实现之前，强基线门禁不通过。 |
| GuideLLM | 仓库存在；HEAD 为 `87a66f0e9d7af24ceb87b4c26e1b87ddfd9b0215` | 未安装、未执行；源码下载连接失败，尚未核验依赖回放、时间戳和会话语义，不声明可直接替代 Agent 回放。 |

来源：[Continuum 作者仓库](https://github.com/Hanchenli/vllm-continuum)、[FairInference 原文](https://arxiv.org/html/2609.18112)、[GuideLLM 官方仓库](https://github.com/vllm-project/guidellm)。远程 HEAD 仅表示本轮查询版本，不保证论文使用相同版本。

## 现有模块与最小改动

`lab.py:71` 拒绝启用 Prefix Cache；`lab.py:119` 起构造 vLLM bench serve 的随机固定长度请求（输入 1024、输出 256、无限到达率、前缀长度 0）。`lab.py:256` 的跨引擎对照也要求缓存关闭。这些约束服务于已有对照，保留。

复用配置、环境记录、原始文件保存、GPU 采集、结果校验和已有报告；后续另加可配置的 Agent workload 入口，不放宽原有基线校验。新增接口还未实现。

| 必需信息 | 最小接口要求 | 现有证据边界 |
| --- | --- | --- |
| 身份 | tenant/session/program/request ID；取消和重试保留关联 | 本轮静态入口未提供这些语义 |
| 依赖 | 父请求、工具开始/结束、状态及错误 | 固定随机请求不代表 Agent DAG |
| 到达 | 根任务计划到达、依赖满足、实际发送、完成；明确同一单调时钟 | 客户端 queue_times 不能冒充引擎排队 |
| 前缀 | 固定 tokenizer revision、实际 token 序列或可校验摘要、cache salt | 长度相同不证明缓存共享；生成输出改变后续前缀 |
| 服务端缓存 | 块分配、共享引用、pin、淘汰、抢占事件与来源 | 本轮没有验证此类事件；客户端不能推断真实命中率 |

最小 CPU 验证需覆盖：DAG 无环；子任务实际发送不早于父任务完成加工具等待；取消/失败子任务规则；请求 ID 唯一；跨租户共享策略明确；相同 token 前缀与不同长度的反例。它们属于回放正确性验证，不是性能实验。本轮仅完成现有测试回归，未声称 Agent validator 已实现。

## 验证与下一步门禁

本轮 `python3 -m unittest discover -s tests -v`：15 项通过；存在第三方 Matplotlib/Pyparsing 弃用告警。执行日志和历史单文件字段审查见 `research/evidence/agent-readiness-20261012/`。历史样本仅用于字段核对，不重新包装为 Agent 实验。

结论 **HOLD：尚不进入缓存调度算法实现或付费 GPU 实验**。先恢复固定版本源码读取，补齐强基线忠实度；随后实现独立 Agent trace 校验与极小依赖回放样例。不要用原有随机请求报告证明 H2-H1。

本步骤不需要 GPU 租用。后续基础功能试验可优先本机 RTX 4060 Laptop 8GB + 已有 Qwen2.5-0.5B；只有完成正确性门禁后，再确定 GPU 对照范围。此配置不复现 FairInference 的 A100 80GB 平台，也不能支持跨硬件收益推断。
