# Business delivery increment: requirements and acceptance draft

This is a simulated internal-assistant scenario, not a customer deployment.
Existing evidence: pinned local GPU, fixed model and synthetic 1024/256 prompts.
Unknowns remain unknown; historical throughput is not a promised business SLA.

## User outcome and constraints

Interactive users need a timely first response; document-summary users need eventual completion.
Both compete for limited GPU memory and budget. Scope starts with one owned local engine process.
Business arrival rates, prompt/output distributions, priority, privacy requirements, model quality,
agreed latency/error targets, recovery objective and actual prices are not supplied.
They must be declared before a production pass/fail claim; do not infer them from a benchmark.

## Incremental acceptance

1. Historical tail audit: align per-request timing/error arrays, refuse incomplete/invalid evidence,
   preserve originals, show P50/P95/P99 per repeat, record hashes and limitations.
2. Sustained-load experiment: separate arrival rate from concurrency, record planned/actual arrivals,
   client backlog, response latency, failures, server metrics and KV pressure; use warmup and a
   declared measured interval, at least three repeats and sufficient requests for the stated tail.
   At least 1,000 completed observations per declared class is a proposed experimental minimum,
   not statistical confidence or an agreed production requirement. Burst and long/short mixtures
   need independent fixtures. Demonstrate the generator was not the bottleneck.
3. Recovery experiment: only an owned test service may be stopped; record outage/error observations,
   restart/readiness and recovery time; never summarize only successful requests to hide downtime.
4. Delivery: one pinned configuration, setup/run/readiness/evidence commands, ownership-safe stop,
   rollback to the last local commit, and a cold-start repeat by the user before claiming usability.
5. Quality, tenant fairness, production privacy and cost are separate acceptance dimensions.
   No P99/SLO, model quality, production availability or deployment success is claimed yet.

## First executable step

python3 tail_report.py results/20261002T101126Z-vllm results/20261002T122324Z-sglang --output reports/business-tails-UNIQUE

No GPU launch is needed; this reads existing evidence. Choose a new output directory on each run.
Tests: python3 -m unittest discover -s tests -v
Readiness tests: python3 -m unittest test_readiness -v

## Deployment and rollback boundaries

Reuse study.py for local engine ownership, lock, readiness and process-group cleanup.
Its config includes exact Python environments, engine provenance and server launch commands.
Review configuration locally; do not copy credentials into evidence. Do not run while another
GPU workload owns the device. No automatic reboot, port eviction, killall or GPU reset.

The first increment is offline analysis only. To roll it back, check out the previous known local
revision in a clean worktree and rerun its tests; retain all results/report directories. Do not
reset dirty checkouts or force-push. A real start/stop/failure/recovery drill remains unexecuted.
