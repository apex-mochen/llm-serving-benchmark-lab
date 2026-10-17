# 2026-10-16 A/A资源复查

实际调用原A/A脚本`--execute`，新运行`trace-aa-control-20261016T010421Z`，在启动服务器前因固定3GiB主机余量门停止。0性能请求，numeric_pass=null，核心hash未变；没有OOM事件可报告，不是测得A/A差异FAIL。

五次GPU利用率均3%，静默利用率条件满足；Windows快照FreePhysicalMemory=344472KiB（336.4MiB，约0.33GiB），FreeVirtualMemory=10468768KiB。没有达到固定物理内存余量，不修改门槛。

主机进程工作集合计Claude约1566MiB、Doubao约1094.3MiB（含共享页，不能保证退出后释放同等物理内存）；已建议用户保存任务后退出暂不用的应用。没有自动结束进程、关闭软件、重启WSL、租卡或更改配置。

权威raw：主体`research/experiments/results/trace-aa-control-20261016T010421Z/`，保存runner.log、specification、固定payload、host-preflight、5次preflight、outcome及源码快照。前次232请求仍在20261015T090240Z，不能与本次拼接。

下一步只有资源恢复后的全新原配置A/A：主机空闲>=3GiB、GPU静默且无其他编译，使用`/home/dcl/projects/vllm-v2-gpu-venv/bin/python -u research/experiments/run_trace_aa_control.py --execute`。保持HOLD，不进入正式对照。本次是既有HOLD资源复查，未开展新研究阶段。
