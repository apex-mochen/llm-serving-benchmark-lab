import json,subprocess,urllib.request,time,os,signal,pathlib,random
root=pathlib.Path('/home/dcl/projects/llm-serving-benchmark-lab')
model='/home/dcl/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775'
commit=subprocess.check_output(['git','-C','/home/dcl/projects/sglang-42070','rev-parse','HEAD'],text=True).strip()
print('Verified source commit:',commit,flush=True)
args=['/home/dcl/projects/llm-serving-benchmark-lab/sglang-python','-m','sglang.launch_server','--model-path',model,'--served-model-name','benchmark-model','--port','8019','--dtype','float16','--context-length','2048','--mem-fraction-static','0.45','--disable-radix-cache','--disable-cuda-graph','--attention-backend','triton','--sampling-backend','pytorch']
evidence=root/'smoke'; evidence.mkdir(exist_ok=True)
if (evidence/'sglang-server.log').exists() and not (evidence/'sglang-first-startup-failure.log').exists(): (evidence/'sglang-first-startup-failure.log').write_text((evidence/'sglang-server.log').read_text())
log=(evidence/'sglang-server.log').open('w')
p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'CUDA_VISIBLE_DEVICES':'0','PYTHONPATH':'/home/dcl/projects/llm-serving-benchmark-lab/.sglang-deps:/home/dcl/projects/sglang-42070/python'})
try:
 deadline=time.monotonic()+240
 while time.monotonic()<deadline:
  if p.poll() is not None: raise RuntimeError('Server exited: '+(evidence/'sglang-server.log').read_text()[-5000:])
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
 result=dict(status='passed',engine='sglang',source_repo='/home/dcl/projects/sglang-42070',engine_commit=commit,model_revision=pathlib.Path(model).name,command=args,environment_overrides={'PYTHONPATH':'/home/dcl/projects/llm-serving-benchmark-lab/.sglang-deps:/home/dcl/projects/sglang-42070/python','CUDA_VISIBLE_DEVICES':'0'},usage=usage,ttft_s=first-start,elapsed_s=time.monotonic()-start,limitation='single-request functional smoke, not an engine comparison or performance result')
 (evidence/'sglang-functional-smoke.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result),flush=True)
 client=['/home/dcl/projects/vllm-v2-gpu-venv/bin/python','-m','vllm.entrypoints.cli.main','bench','serve','--backend','vllm','--base-url','http://127.0.0.1:8019','--endpoint','/v1/completions','--model','benchmark-model','--tokenizer',model,'--dataset-name','random','--random-input-len','1024','--random-output-len','256','--random-range-ratio','0','--random-prefix-len','0','--num-prompts','4','--max-concurrency','1','--seed','20261002','--request-rate','inf','--ignore-eos','--temperature','0','--save-result','--save-detailed','--result-dir',str(evidence),'--result-filename','sglang-official-client-smoke.json']
 with (evidence/'sglang-official-client-smoke.log').open('w') as output:
  subprocess.run(client,stdout=output,stderr=subprocess.STDOUT,check=True,timeout=300)
 import sys
 sys.path.insert(0,str(root))
 from lab import validate
 actual=json.loads((evidence/'sglang-official-client-smoke.json').read_text())
 errors=validate(actual,4)
 print('Official-client smoke validation:',errors,'lengths:',actual.get('input_lens'),actual.get('output_lens'),flush=True)
 assert not errors,errors

finally:
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try: p.wait(timeout=15)
  except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL); p.wait()
 log.close()
