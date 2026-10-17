# Agent Workload Validation Result

2026-10-12；真实GPU实验室测量，合成冻结Agent trace；不是生产业务或自主Agent质量评测。

## 结论与假设判断

完成两阶段session/dependency/pause/resume与Traditional配对回放，Prefix Cache关闭/开启、每组3次，共12个有效cell、576个成功请求。输入Token及输出规模完全相同，Traditional目标发送时刻逐请求等于Agent实际发送偏移；实际偏差见配对校验。

**本轮不能证明“Agent workload使现有优化策略失效”。** 即使配对尾延迟存在差异，也不能由单卡0.5B、低缓存压力、原生Prefix Cache对照证明所有KV调度策略失效。尚未测试受保护租户或完整Continuum/FairInference强组合。

本轮原生Prefix Cache对平均TTFT的变化：Agent降低 16.51%，Traditional降低 17.32%；负值表示升高，不解释为优化收益已成立。三次配对P95比值 Agent/Traditional：cache关闭 [0.8298602424254009, 1.024703303716426, 0.9061003987308524]，开启 [1.0898960233177493, 0.9674435429220554, 1.2799564994425785]。这些都是实测描述，3次重复和固定执行顺序不足以证明因果或等价。

决策：**停止基于“Agent会导致缓存优化失效”的预设开展A方向算法开发或提前优化。** 没有证据时不列新的优化机制。全局A假设为证据不足，不能把未检出当不存在；重新启动需要明确缓存压力/多租户场景和可复现强基线，而不是包装本轮差异。下一步可向导师讨论转B或是否批准更窄的压力证伪实验。

## 实验设计

- Agent：24个session，两阶段，根任务4/s；父请求成功完成后暂停0.25或0.75秒，再恢复子请求。失败则取消子轮；逐请求事件保存。GuideLLM固定版本的idle_gap目标计算被复用，不设计调度算法。
- 每session首轮1024 Token；第二轮首轮冻结输入追加128 Token，合计1152；各轮输出64，temperature=0、ignore_eos。共享256 Token前缀。工具结果和中间上下文为合成固定内容，没有把实际生成输出写入下一轮，因此不代表端到端Agent推理质量。
- Traditional：同一trace里的token IDs与payload，在Agent实际发送偏移独立提交；保留ID用于配对，不等待父节点。它是严格匹配负载的扁平回放，不是另造长度相近但前缀不同的数据。
- 每cache状态先用不同seed的2个session/4请求预热；cache开启时每cell重置成功后测量，关闭时无需重置。3个seed为20261012/13/14；每repeat先Agent后Traditional；关闭cache的3组先于开启cache，顺序效应是限制。

## 配置与复现

模型 Qwen2.5-0.5B-Instruct，revision `7ae557604adf67be50417f59c2c2f167def9a775`；vLLM `0.30.0`，wheel build解析到 `ced6857afa0ea7b2e3f0846a62e1394e90f15607`。GPU `NVIDIA GeForce RTX 4060 Laptop GPU`，8188.0MiB，driver `616.64`。FP16、TP1、max_model_len2048、gpu_memory_utilization0.45、enforce_eager；实际命令/依赖/环境在metadata。实验服务仅localhost，启用DEV_MODE以访问cache reset，重置必须返回success=true；无核心代码修改。

```bash
PYTHONPATH=/home/dcl/.cache/lab-baselines/guidellm/src:/home/dcl/projects/vllm-v2-gpu-venv/lib/python3.12/site-packages \
  /home/dcl/.cache/lab-baselines/cpu-env/bin/python research/experiments/agent_workload_validation.py
```

脚本只启停自有服务、拒绝覆盖已有服务、创建新时间戳目录；不重写结果。

## 数据和结果

表为三次重复各cell统计值的中位数；原始逐次结果见aggregate.json，不是合并请求后的统计。P95/P99是每48请求的经验插值分位数，**P99样本不足，只描述，不作稳定尾部结论**；没有报告统计显著性或置信区间。

| Prefix Cache | workload | mean TTFT ms | mean TPOT ms | P95 E2E ms | P99 E2E ms | requests/s | output tokens/s | peak device memory MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| False | agent | 82.757 | 20.143 | 1476.509 | 1495.151 | 5.601 | 358.485 | 6252.000 |
| False | traditional | 86.466 | 21.214 | 1604.809 | 1615.497 | 5.506 | 352.396 | 6275.000 |
| True | agent | 69.094 | 19.179 | 1385.705 | 1409.092 | 5.585 | 357.427 | 5981.000 |
| True | traditional | 71.493 | 19.785 | 1424.197 | 1430.177 | 5.580 | 357.127 | 5985.000 |

实测配对发送偏移最大差值为 1.415ms；逐对见pairing-checks.json。若差异对该硬件时间尺度重要，不能声称完全相同实际到达。全部请求输入ID摘要和计数已逐一核对，输出usage均64。

测量边界：TTFT为httpx发起到首非空内容chunk；TPOT=(最后非空chunk−首非空chunk)/63，chunk合并/不可见末token可能改变边界，非GPU kernel时间；E2E为实际发送到流结束。吞吐为有限批次成功请求/从测量开始到所有完成的时间，包含开放到达与尾部drain，不是稳态容量。工具等待不计入请求E2E，但影响任务完成；本轮未比较任务JCT。设备显存每0.5秒采样，包含Windows桌面，非引擎独占分配。采集错误保留，不用0代替。

## KV Cache观测

Prometheus前后原文已保存，提取实际prefix/KV/preemption计数见kv-observations.json。不把客户端prefix机会冒充真实命中。计数刷新/采样周期导致前后差值边界近似；末端usage不是峰值压力，不据此归因。服务端启动日志报告的KV容量也保留，检查是否远大于本trace需求；未制造缓存压力或调整容量去追求异常。

| Cache | repeat | workload | observed query-token delta | observed hit-token delta | ratio |
| --- | --- | --- | --- | --- | --- |
| False | 0 | agent | 0.0 | 0.0 | unknown/无查询 |
| False | 0 | traditional | 0.0 | 0.0 | unknown/无查询 |
| False | 1 | agent | 0.0 | 0.0 | unknown/无查询 |
| False | 1 | traditional | 0.0 | 0.0 | unknown/无查询 |
| False | 2 | agent | 0.0 | 0.0 | unknown/无查询 |
| False | 2 | traditional | 0.0 | 0.0 | unknown/无查询 |
| True | 0 | agent | 52224.0 | 30464.0 | 0.5833 |
| True | 0 | traditional | 52224.0 | 30464.0 | 0.5833 |
| True | 1 | agent | 52224.0 | 30464.0 | 0.5833 |
| True | 1 | traditional | 52224.0 | 30464.0 | 0.5833 |
| True | 2 | agent | 52224.0 | 30464.0 | 0.5833 |
| True | 2 | traditional | 52224.0 | 30464.0 | 0.5833 |

表中ratio为服务端已公布token计数差值之比，不是请求命中概率，可能不覆盖最后一次统计刷新；无查询时unknown。session/dependency只在客户端维护，本轮没有向引擎注入session-aware缓存保留或暂停状态，不验证TTL/pin算法。

## 原始证据与失败运行

有效目录：[validation-runs/20261012T051151Z](validation-runs/20261012T051151Z/metadata.json)。其中包含config/version、完整启动日志、请求/events、trace、GPU采样、metrics原文、aggregate和配对校验。前两个目录为失败尝试：第一次等待校验失败，第二次reset API 404；没有正式cell统计，不混入结果。先修正实验脚本截止等待和版本接口，再通过2项本地HTTP mock测试重新测量；mock不计入GPU数据。

## 下一阶段边界

未验证：真实工具/多轮生成质量、多租户延迟隔离、KV高压/淘汰、其他调度策略、完整强基线、大模型/多卡/生产泛化。当前不设计新机制、不优化参数、不写论文。若导师选择重启A，应先批准具体压力/tenant假设与停止门；若选择B，复用已有请求/设备/metrics证据开展可核查干预，不假称根因已定位。

## 波动与异常值

| Cache | workload | mean TTFT range ms | P95 E2E range ms |
| --- | --- | --- | --- |
| False | agent | 78.240–85.899 | 1454.118–1538.279 |
| False | traditional | 78.354–86.869 | 1501.195–1779.226 |
| True | agent | 68.623–76.928 | 1330.367–1822.910 |
| True | traditional | 65.686–71.797 | 1220.636–1432.336 |

cache开启的Agent repeat2 P95为1822.910ms，而配对Traditional为1424.197ms；其它重复未呈现相同方向的明显退化。该异常保留原始数据，不能因中位数较好而隐藏；没有profiling/压力证据，不命名根因。固定顺序、GPU频率/温度与Windows桌面干扰均可能混杂。服务端KV容量202208 Token；服务端公布的preemption计数差值均0，未出现可核查的KV抢占退化。单个异常既不证明新瓶颈，也不允许宣布所有工况不存在问题。
