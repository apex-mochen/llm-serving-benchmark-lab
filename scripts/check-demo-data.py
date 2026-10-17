"""Integration check against the existing real baseline. No server or GPU inference."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from benchmark_lab.api import create_app

manifest=json.loads((ROOT/'reports/001-raw-sha256.json').read_text())
before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in manifest}
assert before==manifest
with TestClient(create_app(ROOT,ROOT/'.benchmark/integration-index.sqlite3')) as client:
    listing=client.get('/api/runs').json()
    assert listing['total']==24 and listing['requests']==1536
    assert client.get('/api/runs?engine=vllm').json()['total']==12
    assert client.get('/api/runs?engine=sglang&concurrency=32').json()['total']==3
    for row in listing['runs']:
        detail=client.get('/api/runs/'+row['id']).json()
        assert len(detail['request_timing'])==64
        original=json.loads((ROOT/row['source']).read_text())
        assert detail['mean_ttft_ms']==original['mean_ttft_ms']
        assert detail['mean_tpot_ms']==original['mean_tpot_ms']
        assert detail['output_tokens_per_s']==original['output_throughput']
        assert client.get('/api/runs/'+row['id']+'/artifacts/result').content==(ROOT/row['source']).read_bytes()
after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in manifest}
assert before==after
answer=dict(status='PASS',historical_runs=24,historical_requests=1536,original_files_verified=len(manifest),
    before_after_hashes_unchanged=True,metric_values_equal_original=True,new_inference_requests=0)
output=ROOT/'docs/validation/demo-browser/real-data-integration.json'
output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(answer,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps(answer,indent=2))
