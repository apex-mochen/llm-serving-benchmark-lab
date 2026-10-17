# Bottleneck Diagnosis Phase 2 Result

状态：仅报告已保存的真实数据；未完成项目明确标记，不将 CPU 测试或旧 Phase 1 数据充作新结果。

运行目录：`phase2-20261012T145433Z`；正式扩样/矩阵请求数：40；预检请求单列。

## 配置与测量边界

RTX4060 Laptop / Qwen2.5-0.5B-Instruct 固定 snapshot / vLLM 0.30.0，FP16、TP1、max_model_len2048、max_num_seqs4、max_num_batched_tokens2048、eager、chunked prefill。原始 server-config、metadata、workload、requests、GPU/server 采样和日志均随运行保存。

固定8请求episode，根到达率4/s，output128；episode间排空，cold/warm每episode重置，warm独立preload。64/256/1024为同一运行累积前缀，不能作为三个独立实验。

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
| status-expand | not_executed |
| status-matrix-a | not_executed |
| status-matrix-b | not_executed |

## 数据

| 条件/重复 | 请求 | TTFT P50 ms | TPOT P50 ms | E2E P95/P99 ms | queue/prefill/decode 均值 ms | req/s | cache hit-token ratio |
|---|---:|---:|---:|---|---|---:|---|
| cache-expand-cold-r0 | 40 | 173.28 | 63.26 | 20967.23/21778.38 | 0.02/148.48/9180.03 | 0.402 | 0.21875 |

完整P50/P95/P99、planned E2E、GPU均值/峰值、KV gauge、preemptions及每cell条件性episode bootstrap区间见 `phase2-descriptive-analysis.json`。Bootstrap固定seed20261012、1000次整episode重采样；不把请求视为独立样本，不把条件性区间当作跨重复稳定性证据。

## 阶段判断

必须在扩样和两个矩阵完成后，结合重复间效应、尾部区间及混合条件再判断解释能力和可区分性。原生阶段分解本身是已有vLLM能力，不是研究创新；变量干预响应不是根因真值。当前不开发自动归因。
