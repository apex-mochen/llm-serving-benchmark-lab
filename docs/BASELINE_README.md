# llm-serving-benchmark-lab

Status: the first complete fixed concurrency study is validated: 24 runs, 1,536 requests.
See [the report](reports/001-concurrency-study.md) for results, run ranges and interpretation limits.

V1 studies vLLM and SGLang on one machine/GPU/model snapshot: 1024 input tokens,
256 output tokens, concurrency 1/8/32/64. One pinned official vLLM benchmark
client drives both OpenAI-compatible completion endpoints. Three repeats per cell,
64 requests per repeat, fixed seed, alternating concurrency order, and a separate
16-request warmup. Synthetic random prompts are a controlled saturation workload.

Official client reference: https://docs.vllm.ai/en/latest/cli/bench/serve/
SGLang reference: https://docs.sglang.ai/developer_guide/bench_serving

## Run

Python 3.12+, NVIDIA driver/nvidia-smi, CUDA serving environments and the official
vLLM client are prerequisites. Copy `config.example.json` to `config.local.json`,
pin the actual model snapshot and fill exact source/runtime/launch metadata.
Example starting model: Qwen/Qwen2.5-0.5B-Instruct, subject to verifying complete
weights and tokenizer locally. It is a starting choice, not a completed measurement.

Launch only one engine at a time on the same GPU; disable prefix caching for both.
Use the same dtype, model context limit, memory fraction and tensor parallel size.
Preserve server logs and exact launch commands. Confirm the served model name and
snapshot; configuration entries are operator declarations, not runtime attestation.
The runner deliberately does not kill or replace any existing server.

```bash
python3 study.py config.local.json  # starts/stops only its own server process groups
# Or use manually launched services:
python3 lab.py run config.local.json --engine vllm
# Stop only the vLLM process you own; launch SGLang on the same GPU and endpoint.
python3 lab.py run config.local.json --engine sglang
python3 lab.py report results/UTC-vllm results/UTC-sglang
```

The report command generates `reports/001-concurrency-study.md`, CSV, JSON, SVG and PNG
only from complete validated studies. Request failures, invalid/non-finite metrics,
non-1024/256 lengths, incomplete telemetry or mismatched machine/GPU/model/client
conditions abort. Repeated means are aggregated by median; raw per-request data
and commands remain available for tail-latency analysis. No invented data fallback.
Matplotlib creates six metric panels; error bars are the three-run range, not confidence intervals.

Metadata records engine Git SHA, Python package versions, PyTorch/CUDA, GPU UUID,
driver, OS/machine, model revision, all parameters and command arguments. A dirty
source is rejected. For source installs the runtime must load from the recorded
repository. A vLLM wheel may expose its embedded build commit; that ID is resolved
through the upstream GitHub commit API using authenticated `gh` and saved as its
actual engine commit. Wheels without verifiable provenance are rejected: a nearby
checkout SHA cannot stand in for the installed wheel's actual build.

## Interpretation limits

GPU metrics are device-wide sampled at 0.5 seconds, aligned approximately to the
unbuffered client main-run marker plus its reported duration, excluding startup;
other workloads and desktop rendering can contaminate them. Reserve the GPU and
record Windows/WSL memory pressure, power/clocks and thermal conditions. These
samples alone cannot identify a particular kernel, prove GPU saturation or rule
out WDDM oversubscription. Prefix caches must be disabled for repeated prompts.
At concurrency 64 this workload is one full wave per repeat; it is a finite batch
study and does not establish steady-state capacity. Increase request count later
when studying sustained load or production tail latency.

TTFT/TPOT/ITL definitions and token counts come from the pinned client version.
Streaming chunks may coalesce tokens; ITL is not automatically a kernel decode
duration. Fix output length with ignore-EOS; this is not a model quality benchmark.
Compare server scheduling/KV/prefill/decode logs before explaining a speed change.

Before/After PR runs must use the same config and model; change only the tested
engine commit. Preserve original runs, don't overwrite baseline evidence.

## Verify tooling

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest test_readiness -v
```

Tests use explicit synthetic fixtures to verify rejection of bad studies. They
are never serving results. Actual vLLM/SGLang functional evidence is in `smoke/`.
The isolated CUDA 13.0 SDK is pinned in `cuda-toolchain-requirements.txt` to hashes
from the original PyPI releases. The report dependency versions are recorded in
`report-requirements.txt`; neither environment modifies the serving Python packages.
The first study and machine-state analysis are complete. Source code, fixed configuration, raw result hashes and report are preserved.

To retain a completed vLLM baseline after a SGLang startup failure:
```bash
python3 study.py config.local.json --engine sglang --existing-run results/UTC-vllm
```
The existing run is fully revalidated before reporting. Original results are not overwritten.
Before/After raw collection is supported through pinned configs; the current aggregate report requires one study per engine. A same-engine comparison report must be added when a concrete performance PR needs it.

## Business evidence increment

See docs/business-delivery.md for the simulated business requirements and limits.
The independent tail_report.py reads existing per-request data and writes a new directory;
it does not change the finite-batch benchmark or certify production capacity.
