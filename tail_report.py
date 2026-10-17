"""Audit request tails from existing finite-batch evidence; never certify capacity."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def percentile(values, percent):
    """Linear interpolation of sorted observations, including endpoints."""
    if not values or not 0 <= percent <= 100:
        raise ValueError("Nonempty observations and percentile in [0,100] required")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(result, expected):
    if type(expected) is not int or expected <= 0:
        raise ValueError("Expected request count must be a positive integer")
    if result.get("completed") != expected or result.get("num_prompts") != expected:
        raise ValueError("Incomplete batch: do not hide failed requests in latency tails")
    errors = result.get("errors")
    if not isinstance(errors, list) or len(errors) != expected or any(errors):
        raise ValueError("Missing error evidence or failed requests")
    arrays = {}
    for key in ("ttfts", "latencies", "queue_times", "start_times"):
        values = result.get(key)
        if not isinstance(values, list) or len(values) != expected:
            raise ValueError("Missing or misaligned request array: " + key)
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("Non-finite or negative request timing: " + key)
        arrays[key] = values
    if any(t > latency for t, latency in zip(arrays["ttfts"], arrays["latencies"])):
        raise ValueError("TTFT exceeds end-to-end latency")
    arrays['arrival_to_first_token'] = [q + t for q, t in zip(arrays['queue_times'], arrays['ttfts'])]
    arrays['arrival_to_completion'] = [q + t for q, t in zip(arrays['queue_times'], arrays['latencies'])]
    return {
        "completed": expected,
        "client_start_span_s": max(arrays["start_times"]) - min(arrays["start_times"]),
        "observed_error_count": 0,
        "tails_ms": {
            key: {str(p): percentile(arrays[key], p) * 1000 for p in (50, 95, 99)}
            for key in ("ttfts", "latencies", "queue_times", "arrival_to_first_token", "arrival_to_completion")
        },
    }


def analyze(root):
    root = Path(root).resolve()
    metadata_path = root / "metadata.json"
    meta = json.loads(metadata_path.read_text())
    cfg = meta["config"]
    repeats = cfg["repeats"]
    expected = cfg["num_prompts"]
    if type(repeats) is not int or repeats < 3:
        raise ValueError("At least three repetitions required")
    files = [metadata_path]
    cells = []
    for concurrency in (1, 8, 32, 64):
        for repeat in range(repeats):
            stem = "c%d-r%d" % (concurrency, repeat)
            result_path = root / (stem + ".json")
            validation_path = root / (stem + "-validation.json")
            validation = json.loads(validation_path.read_text())
            if validation.get("valid") is not True or validation.get("errors") != []:
                raise ValueError("Original validation rejected " + stem)
            result = json.loads(result_path.read_text())
            if result.get("max_concurrency") != concurrency or result.get("request_rate") != "inf":
                raise ValueError("Unexpected workload: only original finite-batch study supported")
            cells.append({"concurrency": concurrency, "repeat": repeat, **summarize(result, expected)})
            files.extend((result_path, validation_path))
    return {
        "engine": meta["engine"],
        "engine_commit": meta["engine_commit"],
        "source_root": str(root),
        "evidence_class": "historical real-GPU laboratory; synthetic finite workload",
        "percentile_method": "linear interpolation; each repeat reported independently",
        "production_capacity_verified": False,
        "limitations": [
            "64 requests per repeat provide weak evidence for the far tail; no steady-state claim",
            "Client queue time is not server scheduler queue time",
            "No latency SLO, tenant fairness, model quality or recovery certification",
        ],
        "source_sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "cells": cells,
    }


def render(studies):
    text = [
        "# Request-tail audit of historical finite batches", "",
        "Real GPU laboratory evidence with synthetic prompts; not production capacity.",
        "Percentiles use linear interpolation within each repeat; no pooled percentile or median of percentiles.",
        "Client queue time must not be interpreted as engine scheduler wait.",
        "Only 64 requests per repeat: P99 is descriptive, not a reliable production tail estimate.", "",
        "Arrival includes benchmark client wait; infinite-rate batches are bursts, not realistic arrival traces.",
        "Queue-inclusive percentiles use per-request sums, never sums of percentiles.",
        "| Engine | C | Repeat | N | Dispatch TTFT P50/P95/P99 ms | Dispatch E2E P50/P95/P99 ms | Client queue P99 ms | Arrival-to-first P99 ms | Arrival-to-completion P99 ms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for study in studies:
        for cell in study["cells"]:
            tails = cell["tails_ms"]
            fmt = lambda key: "/".join("%.2f" % tails[key][str(p)] for p in (50, 95, 99))
            text.append("| %s | %d | %d | %d | %s | %s | %.2f | %.2f | %.2f |" % (
                study["engine"], cell["concurrency"], cell["repeat"], cell["completed"],
                fmt("ttfts"), fmt("latencies"), tails["queue_times"]["99"],
                tails['arrival_to_first_token']['99'], tails['arrival_to_completion']['99']))
    text += ["", "## Sources", ""]
    for study in studies:
        text += ["- " + study["source_root"] + " (engine commit " + study["engine_commit"] + ")"]
    return "\n".join(text) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+")
    parser.add_argument("--output", required=True, help="New evidence directory; existing paths are rejected")
    args = parser.parse_args()
    studies = [analyze(root) for root in args.roots]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "tails.json").write_text(json.dumps(studies, indent=2, allow_nan=False) + "\n")
    (output / "tails.md").write_text(render(studies))
    print(output / "tails.md")


if __name__ == "__main__":
    main()
