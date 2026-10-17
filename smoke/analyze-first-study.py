from pathlib import Path
import json,statistics,re,hashlib,shutil,subprocess
root=Path('/home/dcl/projects/llm-serving-benchmark-lab')
runs=[root/'results/20261002T101126Z-vllm',root/'results/20261002T122324Z-sglang']
from sys import path
path.insert(0,str(root))
from lab import report,validate
for run in runs:
 meta=json.loads((run/'metadata.json').read_text())
 for c in [1,8,32,64]:
  for r in range(3):
   stem=f'c{c}-r{r}'
   assert json.loads((run/(stem+'-validation.json')).read_text())['valid']
   assert not validate(json.loads((run/(stem+'.json')).read_text()),64)
report(runs,root/'reports/001-concurrency-study.md')
data=json.loads((root/'reports/001-concurrency-study.json').read_text())
rows=data['rows']; metas=data['metadata']
summary=['','## Reproducible environment','', '| Item | Value |','|---|---|',
 '| GPU | RTX 4060 Laptop; 8188 MiB; driver '+str(metas[0]['gpu']['driver_version'])+' |',
 '| Model | Qwen/Qwen2.5-0.5B-Instruct; '+metas[0]['config']['model_revision']+' |',
 '| Runtime | PyTorch '+metas[0]['environment']['torch']+'; Torch CUDA '+metas[0]['environment']['cuda']+' |',
 '| Workload | 64 requests per run, 3 repeats; seed 20261002; temperature 0; ignore EOS |',
 '| Common server settings | float16; context 2048; memory fraction 0.45; TP=1; prefix cache off; CUDA graphs off |',
 '| Client | Same runtime vLLM '+metas[0]['environment']['engine']+'; installed distribution metadata '+str(metas[0]['client_version'])+' |']
for m in metas: summary.append('| '+m['engine']+' commit | '+m['engine_commit']+' |')
summary+=['','The model is identical, but implementations/backends differ: vLLM disables FlashInfer sampling; SGLang uses explicit Triton attention and PyTorch sampling. This is a comparison of these configurations, not their default or optimally tuned configurations. Full commands, package inventories and CUDA SDK version are in the JSON metadata and raw files.','','## Observations and bottleneck hypotheses','']
for engine in ['vllm','sglang']:
 rr=sorted((x for x in rows if x['engine']==engine),key=lambda x:x['concurrency']); first,last=rr[0],rr[-1]
 summary.append(f'- Observed {engine}: output throughput rises from {first["output_throughput"]:.2f} to {last["output_throughput"]:.2f} tok/s ({last["output_throughput"]/first["output_throughput"]:.2f}x for 64x the concurrency cap); TTFT rises from {first["mean_ttft_ms"]:.2f} to {last["mean_ttft_ms"]:.2f} ms. Batching improves aggregate throughput while request latency increases; these observations do not isolate a scheduler or kernel cause.')
 summary.append(f'- {engine} at C64: repeated throughput range {last["output_throughput_min"]:.2f}–{last["output_throughput_max"]:.2f} tok/s. Range bars show run variation, not statistical confidence intervals.')
summary+=['','### Machine-state audit','', '| Engine | Run | Mean temperature C | Mean SM MHz | Mean power W |','|---|---|---:|---:|---:|']
manifest={}
for run in runs:
 m=json.loads((run/'metadata.json').read_text())
 for f in sorted(run.glob('c*-gpu.json')):
  samples=json.loads(f.read_text())['samples']
  def avg(k):
   vals=[]
   for s in samples:
    try: vals.append(float(s[k]))
    except (ValueError,KeyError): pass
   return statistics.mean(vals) if vals else float('nan')
  summary.append('| '+m['engine']+' | '+f.name.removesuffix('-gpu.json')+' | '+ ' | '.join(f'{avg(k):.2f}' for k in ['temperature.gpu','clocks.sm','power.draw'])+' |')
 for f in sorted(run.iterdir()):
  if f.is_file(): manifest[str(f.relative_to(root))]=hashlib.sha256(f.read_bytes()).hexdigest()
summary+=['','Observed vLLM C64 run-to-run differences are substantial. Temperature and clocks also vary; however faster runs do not consistently have higher clocks, so this is insufficient to attribute variation specifically to thermal throttling. No isolated profiler trace or throttling-reason experiment was run.',
 'Hypothesis: increased batch size amortizes weight reads and launch overhead; the remaining latency/throughput trade-off may involve prefill scheduling and decode compute/memory limits. Verify with scheduler traces, prefill/decode timing and a targeted profile before changing scheduling, kernels or memory limits.',
 'SGLang server logs report zero cached prompt tokens, confirming cache-off behavior on observed prefill requests. The run contains successful prefill/decode activity; this alone does not prove a particular bottleneck.',
 'No KV exhaustion or OOM was observed in the successfully validated requests; absence of failures does not prove memory headroom for larger models/workloads.',
 '', '### Limits on interpretation','',
 '- Engines ran sequentially, with a restart and a time gap; engine order and desktop GPU load were not controlled with paired alternation. Treat engine differences as descriptive results, not causal proof.',
 '- C64 contains one finite wave of 64 requests. Higher throughput does not establish sustainable arrival rate, production p99 latency or an SLA.',
 '- Device-wide memory includes Windows/WSL and other processes; sampled peak memory is not engine-only allocated VRAM. Temperature/power/clocks are observations, not controlled variables.',
 '- Warmup was 16 separate requests; every measured request length was checked. Requests ignore EOS, so throughput is unrelated to model quality.',
 '- This serving study does not benchmark the HiCache lookup PR or the P2P timeout fix; their feature paths are not enabled here.',
 '', '## Evidence and interview draft','',
 'Engineering evidence: built one serving-benchmark pipeline using a shared official client; pinned model/runtime/engine commits; verified 1,536 measured requests (24 runs × 64), every prompt 1024 tokens and every output 256 tokens; recorded GPU telemetry and generated six-panel plots. This is assistant-implemented evidence, not a claim that the user independently implemented or explained it.',
 'Interview outline: explain why actual token lengths, cache settings and engine build provenance need checking; describe the initial CUDA/JIT and health-timeout failures; explain why repeated-run ranges and device/thermal limits prevent declaring a general engine winner.',
 'Maintainer feedback: no maintainer review of this benchmark lab yet; no upstream serving-performance PR or merged performance claim is implied.']
report_path=root/'reports/001-concurrency-study.md'
report_path.write_text(report_path.read_text()+'\n'.join(summary)+'\n')
(root/'reports/001-raw-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(report_path.read_text(),flush=True)
export=Path('/mnt/c/Users/ASUS/.codex/visualizations/2026/10/01/01a0f779-64fa-7300-81c9-aa6a1475ddb7/benchmark-results')
export.mkdir(exist_ok=True)
for f in (root/'reports').glob('001-*'): shutil.copy2(f,export/f.name)
subprocess.run(['git','status','--short'],cwd=root,check=True)
