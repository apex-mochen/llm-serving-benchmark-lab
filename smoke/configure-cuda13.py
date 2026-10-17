from pathlib import Path
import subprocess
root=Path('/home/dcl/projects/llm-serving-benchmark-lab')
cuda=root/'.cuda13-verified/nvidia/cu13'
if not (cuda/'bin/nvcc').exists(): raise SystemExit('CUDA download not complete; no changes made')
if not (cuda/'lib64').exists(): (cuda/'lib64').symlink_to('lib',target_is_directory=True)
if not (cuda/'lib/libcudart.so').exists(): (cuda/'lib/libcudart.so').symlink_to('libcudart.so.13')
(cuda/'lib/stubs').mkdir(exist_ok=True)
driver=Path('/usr/lib/wsl/lib/libcuda.so')
if not (cuda/'lib/stubs/libcuda.so').exists() and driver.exists(): (cuda/'lib/stubs/libcuda.so').symlink_to(driver)
(root/'sglang-python').write_text('#!/bin/sh\nexec env CUDA_HOME='+str(cuda)+' PATH='+str(root/'.sglang-deps/bin')+':'+str(cuda/'bin')+':"$PATH" PYTHONPATH='+str(root/'.sglang-deps')+':/home/dcl/projects/sglang-42070/python /home/dcl/projects/vllm-v2-gpu-venv/bin/python "$@"\n')
print(subprocess.check_output([str(cuda/'bin/nvcc'),'--version'],text=True))
for p in (root/'.cuda13-verified').glob('*.dist-info'): print(p.name)
