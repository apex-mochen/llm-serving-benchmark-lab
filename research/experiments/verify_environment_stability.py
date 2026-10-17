"""Offline verification only. No server, GPU workload or profiler is launched."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT=Path('/home/dcl/projects/llm-serving-benchmark-lab')
RUN=ROOT/'research/experiments/results/environment-stability-20261013T002857Z'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
spec=read(RUN/'specification.json'); payload=read(RUN/'fixed-payload.json')
runner=ROOT/'research/experiments/run_environment_stability.py'
source=runner.read_text()
assert hashlib.sha256(json.dumps(payload).encode()).hexdigest()==spec['payload_sha256']
assert len(payload)==8 and all(len(p)==512 for p in payload)
prompt_hash=[hashlib.sha256(json.dumps(p).encode()).hexdigest() for p in payload]
forbidden=('--enable-per-request-metrics','--enable-request-id-headers','--enable-prompt-tokens-details','--collect-detailed-traces','--otlp-traces-endpoint','--enable-layerwise-nvtx-tracing')
assert not any(f in spec['command'] for f in forbidden)
checks=[]; cycles=[]; snapshots=[]; ids=set()
def gate(name,value,evidence):
    checks.append(dict(name=name,status='PASS' if value else 'FAIL',evidence=evidence))
gate('01 specification / source / payload',sha(runner)==spec['script_sha256'] and spec['cycles']==3 and spec['input_tokens']==512 and spec['output_tokens']==128,'specification + saved runner + payload')
gate('02 fixed protocol / trace-free',spec['arrival_rate']==4 and spec['cap']==8 and spec['episode_requests']==8 and not any(f in spec['command'] for f in forbidden),'command and workload parameters')
for c in range(3):
    d=RUN/f'cycle-{c}'; b=read(d/'before.json'); a=read(d/'after.json'); own=read(d/'ownership.json'); result=read(d/'result.json')
    during=[json.loads(line) for line in (d/'during.jsonl').read_text().splitlines()]
    releases=read(d/'release-observations.json'); group=read(d/'process-group-after.json'); log=(d/'server.log').read_text()
    snapshots.extend([b,*during,*releases,a]); rows=[]; warm=read(d/'warmup.json')['requests']
    for e in range(8):
        episode=read(d/f'episode-{e}.json'); assert len(episode['requests'])==8
        rows.extend(episode['requests'])
    allrows=[*warm,*rows]
    request_ok=len(rows)==64 and len(warm)==8
    for r in allrows:
        request_ok &= r['success'] is True and r['input_tokens']==512 and r['output_tokens']==128 and r['usage']==dict(prompt_tokens=512,total_tokens=640,completion_tokens=128) and r['native_metrics'] is None and r['prompt_sha256']==prompt_hash[r['index']]
        request_ok &= r['request_id'] not in ids and len(r['sse_response_ids'])==1
        ids.add(r['request_id'])
        assert 0<=r['sent_s']<=r['first_content_s']<=r['last_content_s']<=r['end_s']
        assert abs(r['ttft_ms']-(r['first_content_s']-r['sent_s'])*1000)<1e-5
        assert abs(r['tpot_ms']-(r['last_content_s']-r['first_content_s'])/127*1000)<1e-5
    delta=a['gpu']['memory.used']-b['gpu']['memory.used']; loss=(b['host']['memory']['FreeVirtualMemory']-a['host']['memory']['FreeVirtualMemory'])/1024
    release_ok=[r['gpu']['memory.used']-b['gpu']['memory.used']<=256 and (b['host']['memory']['FreeVirtualMemory']-r['host']['memory']['FreeVirtualMemory'])/1024<=512 for r in releases]
    oom=bool(re.search(r'OutOfMemoryError|CUDA out of memory|memory allocation failed with OOM|Cannot allocate memory',log))
    flags=all(s in log for s in ("'max_num_seqs': 4","'max_num_batched_tokens': 2048","'enable_prefix_caching': False","'enable_chunked_prefill': True","'gpu_memory_utilization': 0.45","version 0.30.0"))
    nums=3+c*5
    gate(f'{nums:02} cycle {c} requests and warmup',request_ok,f'8 episode JSON + warmup JSON, {len(allrows)} rows')
    gate(f'{nums+1:02} cycle {c} launch / allocation / no OOM / no DEBUG',flags and not oom and 'DEBUG' not in log and 'Available KV cache memory: 2.49 GiB' in log and f'APIServer pid={own["server_pid"]}' in log,'server.log and ownership.json')
    gate(f'{nums+2:02} cycle {c} GPU release budget',delta<=256 and abs(delta-result['gpu_memory_delta_mib'])<1e-6,'after-before <=256 MiB')
    gate(f'{nums+3:02} cycle {c} host release budget',loss<=512 and abs(loss-result['host_free_virtual_loss_mib'])<1e-6,'FreeVirtualMemory before-after <=512 MiB')
    gate(f'{nums+4:02} cycle {c} consecutive release / process group',len(releases)>=3 and all(release_ok[-3:]) and group==[] and result['release_stable_samples']>=3 and result['owned_resources_released'] is True and own['server_group']==own['server_pid'],'3 raw resource samples + empty final group; historical port release only recorded composite verdict')
    cycles.append(dict(cycle=c,measurement_requests=len(rows),warmup_requests=len(warm),before_utc=b['utc'],after_utc=a['utc'],before_tick=b['monotonic_s'],after_tick=a['monotonic_s'],during_first_utc=during[0]['utc'],during_last_utc=during[-1]['utc'],during_tick_range=[during[0]['monotonic_s'],during[-1]['monotonic_s']],during_samples=len(during),before_gpu_mib=b['gpu']['memory.used'],peak_gpu_mib=max(r['gpu']['memory.used'] for r in during),after_gpu_mib=a['gpu']['memory.used'],before_host_freevirtual_mib=b['host']['memory']['FreeVirtualMemory']/1024,after_host_freevirtual_mib=a['host']['memory']['FreeVirtualMemory']/1024,gpu_delta_mib=delta,host_freevirtual_loss_mib=loss,oom=oom,release_samples=len(releases),release_tick_span_s=releases[-1]['monotonic_s']-releases[0]['monotonic_s'],owned_server_pid=own['server_pid'],allocation_log_lines=[line for line in log.splitlines() if any(word in line.lower() for word in ('kv cache memory','gpu kv cache','model loading took'))],shutdown_warnings=[line for line in log.splitlines() if 'force killing' in line or 'leaked semaphore' in line]))
outcome=read(RUN/'outcome.json')
core_matches={name:sha(ROOT/name)==expected for name,expected in spec['core_sha256'].items()}
gate('18 same boot / UUID / core / trace remains off',len({r['boot_id'] for r in snapshots})==1 and len({r['gpu']['uuid'] for r in snapshots})==1 and all(core_matches.values()) and outcome['trace_overhead_resumed'] is False,'all parsed snapshots + core hashes + outcome')
assert len(checks)==18
limits=['Port connect_ex return values were not independently persisted; resource release composite verdict records historical successful check. Cannot reconstruct each port check from snapshots.','Exact server command saved; stdout/stderr merged into server.log; runner invocation and runner stderr not separately saved in this run.','Start/end UTC below are observation bounds, not invented process creation timestamps; log clock has no explicit timezone.','Historical Python/Torch/CUDA/Triton package versions and embedded source build commit not saved in this run; log establishes vLLM 0.30.0 only. Current environment is not historical attestation.','force-kill and leaked-semaphore warnings retained; observed release budgets do not establish zero leaks or graceful-only shutdown.','Three same-boot cycles with synthetic token prompts demonstrate bounded completion/release only; not long-term stability, production reliability, quality, phase mechanism or earlier OOM root-cause fix.','No trace-overhead experiment resumed; earlier two completed pairs and third-round OOM remain separate BLOCKED evidence.']
limits += ['Response text and full SSE stream were not persisted: rows contain timing/usage/IDs only. Sufficient for stated completion/resource gates, not independent output-correctness verification.','Inherited runtime environment and run_diagnosis_phase2 helper historical source hash were not separately snapshotted; its current source clarifies intended sampling seed only, not independently frozen historical attestation.','This baseline explicitly used --disable-log-stats, uvicorn-log-level warning, DEV_MODE=0 and INFO, with extra observer flags disabled. Observability differs from prior trace tests. Future off/on revalidation must align flags and check that metrics are actually returned; this PASS does not establish restored trace conditions.']
verification=dict(verified_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),status='PASS' if all(g['status']=='PASS' for g in checks) else 'FAIL',scope='18 bounded recorded stage gates only; not publication blanket approval',measurement_requests=192,warmup_requests=24,cycles=cycles,gates=checks,core_matches=core_matches,actual_observation_start_utc=min(r['utc'] for r in snapshots),actual_observation_end_utc=max(r['utc'] for r in snapshots),limitations=limits)
(RUN/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
files=[p for p in RUN.rglob('*') if p.is_file() and p.name!='integrity-manifest.json']
manifest={str(p.relative_to(ROOT)):sha(p) for p in files}; manifest[str(Path(__file__).resolve().relative_to(ROOT))]=sha(Path(__file__))
(RUN/'integrity-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
report=['# Environment Stability Validation','',f'Run `{RUN.name}`. Offline raw validation: **{verification["status"]}** for 18 bounded gates, 3 cycles ×64=192 measurement requests, 3×8=24 warmup requests separately. No new experiment was run.','',f'UTC observation bounds: {verification["actual_observation_start_utc"]} → {verification["actual_observation_end_utc"]}.','', 'Evidence layer: **End-to-End real GPU serving with synthetic random token prompts**, not production, not model quality or compression mechanism.','', '## Configuration and raw command','', 'RTX4060 Laptop 8188 MiB / driver616.64; Qwen2.5-0.5B snapshot7ae557604adf67be50417f59c2c2f167def9a775; log vLLM0.30.0; FP16, TP1, eager, context2048, cache off, memory fraction0.45, seq4, batchtokens2048, chunked prefill; payloadseed20261013, request samplingseed20261012 from saved collector source, temperature0, ignoreEOS, input512/output128, rate4/s, cap8.','', '```json',json.dumps(spec['command'],indent=2),'```','', '## Before / during / after','', '|cycle|UTC before → after|monotonic before → after|GPU before / peak / after MiB|Host free virtual before / after MiB|GPU delta / host loss MiB|during samples|','|---|---|---|---|---|---|---|']
for c in cycles:
    report.append(f'|{c["cycle"]}|{c["before_utc"]} → {c["after_utc"]}|{c["before_tick"]:.6f} → {c["after_tick"]:.6f}|{c["before_gpu_mib"]}/{c["peak_gpu_mib"]}/{c["after_gpu_mib"]}|{c["before_host_freevirtual_mib"]:.2f}/{c["after_host_freevirtual_mib"]:.2f}|{c["gpu_delta_mib"]:.2f}/{c["host_freevirtual_loss_mib"]:.2f}|{c["during_samples"]}|')
report+=['','## Allocation / shutdown raw excerpts','']
for c in cycles:
    report += [f'Cycle {c["cycle"]}; server PID/group {c["owned_server_pid"]}; during UTC {c["during_first_utc"]} → {c["during_last_utc"]}, tick {c["during_tick_range"]}; release {c["release_samples"]} samples across {c["release_tick_span_s"]:.3f}s; OOM={c["oom"]}.','```text',*c['allocation_log_lines'],*c['shutdown_warnings'],'```']
report+=['','## 18 recorded stage gates','', '|gate|status|evidence|','|---|---|---|']+[f'|{g["name"]}|{g["status"]}|{g["evidence"]}|' for g in checks]
report+=['','## Limits and evidence reviews','']+['- '+s for s in limits]+['','Authenticity: PASS for mutually consistent saved serving logs/request/resource records within stated scope; not forensic proof. Reproducibility: UNKNOWN for fully exact historical software environment due absent package/build provenance; recorded protocol is reconstructable. Claim boundary: PASS only for these three bounded cycles. Consequently no blanket public-claim release; missing provenance and existing send authorization must be resolved.','', 'Earlier OOM failure remains preserved; this successful later run does not prove its cause or remediation. Trace overhead remains BLOCKED / Phase2 HOLD. No automatic experiment continuation.','', '## Reconstruct (offline only)','', '`python3 research/experiments/verify_environment_stability.py`', '',f'Unique raw: `{RUN}`; derived verification.json and integrity-manifest.json in that directory. Evidence index: `experiments/{RUN.name}/README.md`.']
path=ROOT/'research/experiments/results/ENVIRONMENT_STABILITY_VALIDATION.md';path.write_text('\n'.join(report)+'\n')
index=ROOT/'experiments'/RUN.name/'README.md'; index.parent.mkdir(parents=True,exist_ok=True)
index.write_text(f'# {RUN.name}\n\nEnd-to-End real GPU serving; synthetic random token prompts.\n\nUnique raw retained at [original run](../../research/experiments/results/{RUN.name}/). No migration or duplication.\n\n[Specification](../../research/experiments/results/{RUN.name}/specification.json), [verification](../../research/experiments/results/{RUN.name}/verification.json), [manifest](../../research/experiments/results/{RUN.name}/integrity-manifest.json), [report](../../research/experiments/results/ENVIRONMENT_STABILITY_VALIDATION.md), [offline verifier](../../research/experiments/verify_environment_stability.py).\n\n18 bounded recorded gates PASS; full historical environment reproducibility UNKNOWN. 192 measured +24 warmup requests. Earlier OOM cause not established; trace-overhead not resumed. See report for missing runner stderr/build-version/port-check details.\n')
export=Path('/mnt/c/Users/ASUS/.codex/visualizations/2026/10/09/01a12005-1f89-7b31-8f8e-dadb3e0b1b7e')
(export/'ENVIRONMENT_STABILITY_VALIDATION.md').write_bytes(path.read_bytes())
with zipfile.ZipFile(export/'Environment-Stability-Evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in RUN.rglob('*'):
        if p.is_file(): z.write(p,str(p.relative_to(ROOT)))
    for p in (path,index,Path(__file__)):z.write(p,str(p.relative_to(ROOT)))
print(json.dumps(verification,indent=2))
