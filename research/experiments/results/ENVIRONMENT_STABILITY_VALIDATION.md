# Environment Stability Validation

Run `environment-stability-20261013T002857Z`. Offline raw validation: **PASS** for 18 bounded gates, 3 cycles ×64=192 measurement requests, 3×8=24 warmup requests separately. No new experiment was run.

UTC observation bounds: 2026-10-13T00:28:58.601035+00:00 → 2026-10-13T00:33:39.555066+00:00.

Evidence layer: **End-to-End real GPU serving with synthetic random token prompts**, not production, not model quality or compression mechanism.

## Configuration and raw command

RTX4060 Laptop 8188 MiB / driver616.64; Qwen2.5-0.5B snapshot7ae557604adf67be50417f59c2c2f167def9a775; log vLLM0.30.0; FP16, TP1, eager, context2048, cache off, memory fraction0.45, seq4, batchtokens2048, chunked prefill; payloadseed20261013, request samplingseed20261012 from saved collector source, temperature0, ignoreEOS, input512/output128, rate4/s, cap8.

```json
[
  "/home/dcl/projects/vllm-v2-gpu-venv/bin/python",
  "-m",
  "vllm.entrypoints.openai.api_server",
  "--model",
  "/home/dcl/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775",
  "--served-model-name",
  "benchmark-model",
  "--port",
  "8019",
  "--dtype",
  "float16",
  "--max-model-len",
  "2048",
  "--gpu-memory-utilization",
  "0.45",
  "--no-enable-prefix-caching",
  "--enforce-eager",
  "--host",
  "127.0.0.1",
  "--max-num-seqs",
  "4",
  "--max-num-batched-tokens",
  "2048",
  "--enable-chunked-prefill",
  "--disable-log-stats",
  "--uvicorn-log-level",
  "warning"
]
```

## Before / during / after

|cycle|UTC before → after|monotonic before → after|GPU before / peak / after MiB|Host free virtual before / after MiB|GPU delta / host loss MiB|during samples|
|---|---|---|---|---|---|---|
|0|2026-10-13T00:28:58.601035+00:00 → 2026-10-13T00:30:35.427687+00:00|916.196173 → 1011.867604|1457.0/5233.0/1511.0|9142.03/8973.07|54.00/168.96|33|
|1|2026-10-13T00:30:36.457325+00:00 → 2026-10-13T00:32:06.973779+00:00|1012.897240 → 1101.923514|1513.0/5246.0/1513.0|8942.89/9385.50|0.00/-442.60|28|
|2|2026-10-13T00:32:07.997776+00:00 → 2026-10-13T00:33:39.555066+00:00|1102.947503 → 1191.857865|1513.0/5250.0/1518.0|9356.51/9334.00|5.00/22.51|29|

## Allocation / shutdown raw excerpts

Cycle 0; server PID/group 704; during UTC 2026-10-13T00:28:59.786917+00:00 → 2026-10-13T00:30:17.669207+00:00, tick [917.382054358, 994.109131646]; release 6 samples across 16.549s; OOM=False.
```text
(EngineCore pid=843) INFO 10-13 08:29:25 [model_runner.py:428] Model loading took 0.93 GiB memory and 4.180214 seconds
(EngineCore pid=843) INFO 10-13 08:29:29 [gpu_worker.py:640] Available KV cache memory: 2.49 GiB
(EngineCore pid=843) INFO 10-13 08:29:29 [kv_cache_utils.py:2395] GPU KV cache size: 217,616 tokens, Maximum concurrency for 2,048 tokens per request: 106.26x
(EngineCore pid=843) INFO 10-13 08:29:30 [gpu_worker.py:888] Free memory on device (6.93/8.0 GiB) on startup. Desired GPU memory utilization is (0.45, 3.6 GiB). Actual usage is 1.04 GiB for consumed memory (weights + non-torch), 0.07 GiB for peak activation, and 0.0 GiB for CUDAGraph memory. Replace gpu_memory_utilization config with `--kv-cache-memory=2516973568` (2.34 GiB) to fit into requested memory, or `--kv-cache-memory=6094321664` (5.68 GiB) to fully utilize gpu memory. Current kv cache memory in use is 2.49 GiB.
(APIServer pid=704) WARNING 10-13 08:30:17 [utils.py:652] [shutdown] Process manager: force killing remaining processes count=1
(APIServer pid=704) WARNING 10-13 08:30:17 [utils.py:657] [shutdown] Process manager: force killing remaining process EngineCore pid 843
/usr/lib/python3.12/multiprocessing/resource_tracker.py:254: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
```
Cycle 1; server PID/group 1391; during UTC 2026-10-13T00:30:37.475472+00:00 → 2026-10-13T00:31:41.002048+00:00, tick [1013.915383116, 1076.680152424]; release 9 samples across 24.628s; OOM=False.
```text
(EngineCore pid=1519) INFO 10-13 08:30:57 [model_runner.py:428] Model loading took 0.93 GiB memory and 1.968863 seconds
(EngineCore pid=1519) INFO 10-13 08:30:58 [gpu_worker.py:640] Available KV cache memory: 2.49 GiB
(EngineCore pid=1519) INFO 10-13 08:30:58 [kv_cache_utils.py:2395] GPU KV cache size: 217,616 tokens, Maximum concurrency for 2,048 tokens per request: 106.26x
(EngineCore pid=1519) INFO 10-13 08:30:59 [gpu_worker.py:888] Free memory on device (6.93/8.0 GiB) on startup. Desired GPU memory utilization is (0.45, 3.6 GiB). Actual usage is 1.04 GiB for consumed memory (weights + non-torch), 0.07 GiB for peak activation, and 0.0 GiB for CUDAGraph memory. Replace gpu_memory_utilization config with `--kv-cache-memory=2516973568` (2.34 GiB) to fit into requested memory, or `--kv-cache-memory=6094321664` (5.68 GiB) to fully utilize gpu memory. Current kv cache memory in use is 2.49 GiB.
(APIServer pid=1391) WARNING 10-13 08:31:41 [utils.py:652] [shutdown] Process manager: force killing remaining processes count=1
(APIServer pid=1391) WARNING 10-13 08:31:41 [utils.py:657] [shutdown] Process manager: force killing remaining process EngineCore pid 1519
/usr/lib/python3.12/multiprocessing/resource_tracker.py:254: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
```
Cycle 2; server PID/group 2058; during UTC 2026-10-13T00:32:09.040692+00:00 → 2026-10-13T00:33:16.038429+00:00, tick [1103.99041954, 1169.239851839]; release 8 samples across 22.084s; OOM=False.
```text
(EngineCore pid=2187) INFO 10-13 08:32:29 [model_runner.py:428] Model loading took 0.93 GiB memory and 2.727949 seconds
(EngineCore pid=2187) INFO 10-13 08:32:31 [gpu_worker.py:640] Available KV cache memory: 2.49 GiB
(EngineCore pid=2187) INFO 10-13 08:32:31 [kv_cache_utils.py:2395] GPU KV cache size: 217,616 tokens, Maximum concurrency for 2,048 tokens per request: 106.26x
(EngineCore pid=2187) INFO 10-13 08:32:32 [gpu_worker.py:888] Free memory on device (6.93/8.0 GiB) on startup. Desired GPU memory utilization is (0.45, 3.6 GiB). Actual usage is 1.04 GiB for consumed memory (weights + non-torch), 0.07 GiB for peak activation, and 0.0 GiB for CUDAGraph memory. Replace gpu_memory_utilization config with `--kv-cache-memory=2516973568` (2.34 GiB) to fit into requested memory, or `--kv-cache-memory=6094321664` (5.68 GiB) to fully utilize gpu memory. Current kv cache memory in use is 2.49 GiB.
(APIServer pid=2058) WARNING 10-13 08:33:15 [utils.py:652] [shutdown] Process manager: force killing remaining processes count=1
(APIServer pid=2058) WARNING 10-13 08:33:15 [utils.py:657] [shutdown] Process manager: force killing remaining process EngineCore pid 2187
/usr/lib/python3.12/multiprocessing/resource_tracker.py:254: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
```

## 18 recorded stage gates

|gate|status|evidence|
|---|---|---|
|01 specification / source / payload|PASS|specification + saved runner + payload|
|02 fixed protocol / trace-free|PASS|command and workload parameters|
|03 cycle 0 requests and warmup|PASS|8 episode JSON + warmup JSON, 72 rows|
|04 cycle 0 launch / allocation / no OOM / no DEBUG|PASS|server.log and ownership.json|
|05 cycle 0 GPU release budget|PASS|after-before <=256 MiB|
|06 cycle 0 host release budget|PASS|FreeVirtualMemory before-after <=512 MiB|
|07 cycle 0 consecutive release / process group|PASS|3 raw resource samples + empty final group; historical port release only recorded composite verdict|
|08 cycle 1 requests and warmup|PASS|8 episode JSON + warmup JSON, 72 rows|
|09 cycle 1 launch / allocation / no OOM / no DEBUG|PASS|server.log and ownership.json|
|10 cycle 1 GPU release budget|PASS|after-before <=256 MiB|
|11 cycle 1 host release budget|PASS|FreeVirtualMemory before-after <=512 MiB|
|12 cycle 1 consecutive release / process group|PASS|3 raw resource samples + empty final group; historical port release only recorded composite verdict|
|13 cycle 2 requests and warmup|PASS|8 episode JSON + warmup JSON, 72 rows|
|14 cycle 2 launch / allocation / no OOM / no DEBUG|PASS|server.log and ownership.json|
|15 cycle 2 GPU release budget|PASS|after-before <=256 MiB|
|16 cycle 2 host release budget|PASS|FreeVirtualMemory before-after <=512 MiB|
|17 cycle 2 consecutive release / process group|PASS|3 raw resource samples + empty final group; historical port release only recorded composite verdict|
|18 same boot / UUID / core / trace remains off|PASS|all parsed snapshots + core hashes + outcome|

## Limits and evidence reviews

- Port connect_ex return values were not independently persisted; resource release composite verdict records historical successful check. Cannot reconstruct each port check from snapshots.
- Exact server command saved; stdout/stderr merged into server.log; runner invocation and runner stderr not separately saved in this run.
- Start/end UTC below are observation bounds, not invented process creation timestamps; log clock has no explicit timezone.
- Historical Python/Torch/CUDA/Triton package versions and embedded source build commit not saved in this run; log establishes vLLM 0.30.0 only. Current environment is not historical attestation.
- force-kill and leaked-semaphore warnings retained; observed release budgets do not establish zero leaks or graceful-only shutdown.
- Three same-boot cycles with synthetic token prompts demonstrate bounded completion/release only; not long-term stability, production reliability, quality, phase mechanism or earlier OOM root-cause fix.
- No trace-overhead experiment resumed; earlier two completed pairs and third-round OOM remain separate BLOCKED evidence.
- Response text and full SSE stream were not persisted: rows contain timing/usage/IDs only. Sufficient for stated completion/resource gates, not independent output-correctness verification.
- Inherited runtime environment and run_diagnosis_phase2 helper historical source hash were not separately snapshotted; its current source clarifies intended sampling seed only, not independently frozen historical attestation.
- This baseline explicitly used --disable-log-stats, uvicorn-log-level warning, DEV_MODE=0 and INFO, with extra observer flags disabled. Observability differs from prior trace tests. Future off/on revalidation must align flags and check that metrics are actually returned; this PASS does not establish restored trace conditions.

Authenticity: PASS for mutually consistent saved serving logs/request/resource records within stated scope; not forensic proof. Reproducibility: UNKNOWN for fully exact historical software environment due absent package/build provenance; recorded protocol is reconstructable. Claim boundary: PASS only for these three bounded cycles. Consequently no blanket public-claim release; missing provenance and existing send authorization must be resolved.

Earlier OOM failure remains preserved; this successful later run does not prove its cause or remediation. Trace overhead remains BLOCKED / Phase2 HOLD. No automatic experiment continuation.

## Reconstruct (offline only)

`python3 research/experiments/verify_environment_stability.py`

Unique raw: `/home/dcl/projects/llm-serving-benchmark-lab/research/experiments/results/environment-stability-20261013T002857Z`; derived verification.json and integrity-manifest.json in that directory. Evidence index: `experiments/environment-stability-20261013T002857Z/README.md`.
