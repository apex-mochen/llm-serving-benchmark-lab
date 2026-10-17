# Bottleneck Diagnosis Phase 2 Result

状态：**HOLD，Phase 2未完成。** trace计时正确性通过；5%开销门失败；扩样遇到环境混杂后停止。64/256/1024及两个矩阵未完成。只报告真实已保存数据。

运行目录：`phase2-20261012T145433Z`；正式扩样/矩阵请求数：40；预检请求单列。

## 配置与测量边界

RTX4060 Laptop / Qwen2.5-0.5B-Instruct 固定 snapshot / vLLM 0.30.0，FP16、TP1、max_model_len2048、max_num_seqs4、max_num_batched_tokens2048、eager、chunked prefill。原始 server-config、metadata、workload、requests、GPU/server 采样和日志均随运行保存。

预登记流程为固定8请求episode、根到达率4/s、output128，episode间排空、cold/warm每episode重置、warm独立preload。本轮只完成cold的5个episode，warm未执行。64/256/1024为同一运行累积前缀，不能作为三个独立实验。

queue=queued→scheduled；prefill=scheduled→first output token；decode=first→last output token。prefill是vLLM逻辑阶段，非纯GPU kernel时间。client TTFT=send→first非空内容；client TPOT=(last-first)/(output_tokens-1)，客户端chunk时间不是原生token ITL。GPU指标为设备级，包含桌面活动。吞吐分母为正式episode时长之和，排除启动/warmup/reset/preload和间隔。

## Trace 预检

```json
{
  "accuracy_pass": true,
  "overhead": {
    "mean_ttft_ms": {
      "paired_ratios": [
        1.055306960889356,
        1.0728267269229468,
        1.0514338216314476
      ],
      "median_ratio": 1.055306960889356,
      "within_5pct": false
    },
    "mean_tpot_ms": {
      "paired_ratios": [
        1.0180410282824572,
        1.0303672233737995,
        0.9767786895076003
      ],
      "median_ratio": 1.0180410282824572,
      "within_5pct": true
    },
    "mean_e2e_ms": {
      "paired_ratios": [
        1.0264683513476003,
        1.0389842051118567,
        0.9921004954573512
      ],
      "median_ratio": 1.0264683513476003,
      "within_5pct": true
    }
  },
  "overhead_5pct_pass": false,
  "policy": "Expansion trace group remains instrumented; never merge with trace-off or Phase1 uninstrumented performance samples."
}
```

## 执行状态

| 模式 | 状态 |
|---|---|
| metadata-cache-expand | hold_environment_confounding |
| metadata-preflight | completed |
| expand 64/256/1024 | not_executed |
| matrix-a | not_executed |
| matrix-b | not_executed |

## 数据

| 条件/重复 | 请求 | TTFT P50 ms | TPOT P50 ms | E2E P95/P99 ms | queue/prefill/decode 均值 ms | req/s | cache hit-token ratio |
|---|---:|---:|---:|---|---|---:|---|
| cache-expand-cold-r0 | 40 | 173.28 | 63.26 | 20967.23/21778.38 | 0.02/148.48/9180.03 | 0.402 | 0.21875 |

完整P50/P95/P99、planned E2E、GPU均值/峰值、KV gauge、preemptions及每cell条件性episode bootstrap区间见 `phase2-descriptive-analysis.json`。Bootstrap固定seed20261012、1000次整episode重采样；不把请求视为独立样本，不把条件性区间当作跨重复稳定性证据。

## 阶段判断

必须在扩样和两个矩阵完成后，结合重复间效应、尾部区间及混合条件再判断解释能力和可区分性。原生阶段分解本身是已有vLLM能力，不是研究创新；变量干预响应不是根因真值。当前不开发自动归因。

## 停止原因与失败证据

- 两次历史启动在2.49GiB KV Cache分配发生CUDA OOM，完整配置/日志保留于phase2-20261012T101158Z和phase2-20261012T101552Z；没有测量请求。当前尝试原配置成功，不把设备占用变化当作已确定OOM原因。
- 原生trace预检48请求完成，其中trace-on24请求。三轮TTFT on/off比1.055307、1.072827、1.051434，中位偏差+5.53%，超过预登记5%门。TPOT+1.80%、E2E+2.65%。小pilot不能将全部偏差唯一归因于trace；不能称“无测量扰动”。
- 缓存扩样只完成cold-r0的5个8请求episode，共40请求；未满64。episode duration依次8.408/27.237/29.275/20.238/14.242秒；同配置TPOT均值28.839/93.811/110.092/75.813/52.401ms。输入seed按预登记变化，尚无同payload重复证明，不能唯一解释波动原因。
- 环境snapshot同时记录其他任务的多进程rustc/cargo工作。并发host负载为混杂候选，非已证明原因。未终止其他任务；仅向本任务runner发送SIGINT，自有server正常shutdown，锁和8019监听清理。中断episode-005保留为不完整，不计入结果。
- 预检加完整扩样共88完成测量请求，预热/preload不计入；其中64有原生请求计时，但这些不能拼成“某cell已完成64请求”。
- 核心lab.py/study.py/tail_report.py/根README的hash与元数据记录一致。未开发归因算法、未改核心架构、未租用GPU、未发布成果。

## 回答本阶段四个问题

1. **阶段指标是否增加解释能力？** 有限支持测量层面的解释：已验证request级queue/prefill/decode与server histogram同边界，可区分client等待与server等待。尚无完整配对扩样证明其比TTFT/P99更准确诊断瓶颈；同源公式一致并非独立GPU真值。
2. **哪些瓶颈能区分？** 当前只能记录不同逻辑阶段耗时及等待位置，不能宣称已区分prefill compute、decode bandwidth、cache pressure等真实根因。cold数据非对照实验，不以变量名称充作瓶颈标签。
3. **哪些仍无法区分？** CPU调度/编译争用、GPU资源争用、kernel执行、缓存长度/命中变化及调度交互；阶段耗时不能唯一归因。没有warm对应条件、256/1024、Matrix A/B完整数据。P95/P99仅描述，不提供稳定尾部主张。
4. **是否进入自动归因？** 目前不值得直接进入，验收未通过。优先补齐受控环境及测量组边界后重跑最小配对；本阶段结论为证据不足，不是否定B研究问题。

## 下一次唯一最小补救

在无并行构建/压测的现有RTX4060时间窗，使用同一payload做trace off/on的64请求配对×3，固定缓存和episode配置，先记录host/GPU状态并重新评估开销与运行内/间波动。预计30–120分钟，实际耗时待测，无GPU购买。此前混杂数据保持隔离，不续接为同一统计重复；新运行目录保留旧失败及源hash。只有测量有效性通过，才继续既定64→256→1024和两个2×2，不设计算法。

## 阶段反思：18项验收

1. 实际完成：事实，4项CPU检查、48请求预检、40请求隔离pilot。
2. 原目标vs实际：扩样/矩阵未完成，不能交付稳定signature结论。
3. Correctness：已验证ID与公式；未验证完整矩阵/尾部；风险为native阶段与GPU纯执行边界混淆。
4. Architecture：优势复用；弱点没有host隔离；替代只使用client+Prom但丢失请求分解。
5. Performance：仅开销pilot和混杂描述，不声称收益/无扰动。
6. Bottleneck：现象为TPOT波动→host争用候选→同payload安静窗口配对验证→成立后仅调整实验资源安排，不提前优化引擎。
7. 10×：未执行，64/256/1024不能标完成。
8. Alternative：当前原生trace低复杂度、有开销；A无trace性能组低成本但缺分解；B完整OTLP高依赖/开销未测。内存/扩展性能未对比；当前checkpoint容错、维护成本较低，其他方案未实现。
9. Optimization：P0仅恢复实验可控性；P1扩样区间、P2完整事件链、P3新模型均暂不实施。
10. 基础联系：CPU/GPU共享资源、client/server排队、chunk/token边界、相关样本统计。
11. 开源联系：原生指标是vLLM已有能力，非本项目创新；未产生上游Bug/PR证据。
12. 新想法：host争用作为未来负样本进入Parking Lot，本期不加新方向。
13. 求职证据：可写测量校验与实验质量门，不能写诊断准确率/提升。
14. 五问：开销如何控制？为何整episode bootstrap？为何不能混并64 traced请求？逻辑阶段为何非GPU真值？为何并发编译只算混杂候选？
15. 失败：两次OOM、开销门失败、环境混杂、中断保留。
16. 能力A用户背景/B助手执行/C用户独立分析未验收/D创新未验证。
17. 下一实验：s=数据关联通过但测量有效性不足；a=安静窗口64请求trace配对×3；收益降低无效大实验风险；费用现有GPU；Q最高因先补最关键证据。
18. 下一阶段：HOLD。唯一补救为上面的受控trace配对；不进入自动归因研究。
