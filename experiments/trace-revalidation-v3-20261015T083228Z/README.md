# Trace v3配对复验原始证据索引

- 权威raw：`research/experiments/results/trace-revalidation-v3-20261015T083228Z/`。
- 权威报告：该目录`TRACE_REVALIDATION_V3_RESULT.md`；不在本索引复制实验正文。
- 预检：`research/experiments/results/trace-revalidation-v3-20261015T083202Z/`。
- 原命令：`/home/dcl/projects/vllm-v2-gpu-venv/bin/python -u research/experiments/run_trace_revalidation_v3.py --execute`。
- 重建：`/home/dcl/projects/vllm-v2-gpu-venv/bin/python research/experiments/finalize_trace_v3.py research/experiments/results/trace-revalidation-v3-20261015T083228Z`。
- 完整性：raw内`integrity-manifest.json`，只检测文件变化，不证明历史真实性或抗伪造。
- 6组384测量/48预热单列；中位门PASS，阶段HOLD，正式对照未开展。
- 限制：三轮不能证明等价；完整继承环境/输出文本未保存；semaphore警告保留；请求阶段不是GPU kernel时间。
