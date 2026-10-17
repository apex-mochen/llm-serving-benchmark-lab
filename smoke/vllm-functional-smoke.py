import json,subprocess,urllib.request,time,os,signal,pathlib,random
root=pathlib.Path('/home/dcl/projects/llm-serving-benchmark-lab')
model='/home/dcl/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775'
commit=json.loads(subprocess.check_output(['gh','api','repos/vllm-project/vllm/commits/ced6857af'],text=True))['sha']
print('Verified wheel commit:',commit,flush=True)
args=['/home/dcl/projects/vllm-v2-gpu-venv/bin/python','-m','vllm.entrypoints.openai.api_server','--model',model,'--served-model-name','benchmark-model','--port','8019','--dtype','float16','--max-model-len','2048','--gpu-memory-utilization','0.45','--no-enable-prefix-caching','--enforce-eager']
evidence=root/'smoke'; evidence.mkdir(exist_ok=True)
if (evidence/'vllm-server.log').exists(): (evidence/'vllm-first-startup-failure.log').write_text((evidence/'vllm-server.log').read_text())
log=(evidence/'vllm-server.log').open('w')
p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'CUDA_VISIBLE_DEVICES':'0','VLLM_USE_FLASHINFER_SAMPLER':'0'})
try:
 deadline=time.monotonic()+240
 while time.monotonic()<deadline:
  if p.poll() is not None: raise RuntimeError('Server exited: '+(evidence/'vllm-server.log').read_text()[-5000:])
  try:
   urllib.request.urlopen('http://127.0.0.1:8019/health',timeout=2).close(); break
  except Exception: time.sleep(1)
 else: raise TimeoutError('Server readiness timeout')
 # Valid non-special vocabulary IDs; API receives exactly 1024 IDs without chat templating.
 prompt=random.Random(20261002).choices(range(1000,20000),k=1024)
 payload=dict(model='benchmark-model',prompt=prompt,max_tokens=256,temperature=0,ignore_eos=True,stream=True,stream_options={'include_usage':True})
 request=urllib.request.Request('http://127.0.0.1:8019/v1/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 start=time.monotonic(); first=None; usage=None
 with urllib.request.urlopen(request,timeout=120) as response:
  for line in response:
   if not line.startswith(b'data: '): continue
   content=line[6:].strip()
   if content==b'[DONE]': break
   item=json.loads(content)
   if any(c.get('text') for c in item.get('choices',[])) and first is None: first=time.monotonic()
   if item.get('usage'): usage=item['usage']
 assert first is not None and usage and usage['prompt_tokens']==1024 and usage['completion_tokens']==256,usage
 result=dict(status='passed',engine='vllm',wheel_version='0.30.0',engine_commit=commit,model_revision=pathlib.Path(model).name,command=args,environment_overrides={'VLLM_USE_FLASHINFER_SAMPLER':'0','CUDA_VISIBLE_DEVICES':'0'},usage=usage,ttft_s=first-start,elapsed_s=time.monotonic()-start,limitation='single-request functional smoke, not an engine comparison or performance result')
 (evidence/'vllm-functional-smoke.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result),flush=True)
finally:
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try: p.wait(timeout=15)
  except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL); p.wait()
 log.close()
