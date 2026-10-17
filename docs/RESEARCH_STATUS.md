# 当前研究状态（2026-10-17整理）

## 主线

LLM Serving Performance Degradation Detection and Bottleneck Attribution。先建立可重复的测量，再检验额外阶段/资源信息是否减少相似症状的混淆。尚无自动归因准确率、性能优化收益或论文创新成立的结论。

## 最近两项证据

- [真实GPU单进程负控](../research/experiments/results/within-process-aa-20261016T143646Z/MEASURED_PILOT_RESULT.md)：完成64条请求，其中24条是测量段、40条是预热/burn-in。准备下一episode时触发>50ms启动延迟门；未完成完整窗口或ABBA，HOLD。没有事后放宽门槛。公开包省略部分主机观测件，见公开范围说明。
- [CPU定时探针结果](../research/experiments/results/cpu-timing-probe-20261016T144402Z/outcome.json)：32次定时观测，16次sleep、16次真实客户端初始化配合内存合成响应。没有模型请求。最大sleep后检查延迟0.686ms，最大episode起点延迟16.390ms；只支持本次CPU条件下预算可执行，不解释或否定GPU运行中断。

CPU探针的32条时钟与汇总已独立复算，见[审计结果](../research/experiments/results/cpu-timing-probe-20261016T144402Z/offline-audit.json)。没有据此将GPU计量状态改为PASS。

## 边界

前后半请求的TTFT差异具有可复算的序号分层，但不能据此直接认定全部延迟由KV、调度或host争用造成。阶段经过时间不是纯GPU执行时间，相关性不是因果证明。当前没有足够证据生成自动根因结论。

下一步保留原预算和完整时钟记录，在安静资源条件下验证GPU运行可重复性；不把重复试跑中较好的结果挑作结论。
