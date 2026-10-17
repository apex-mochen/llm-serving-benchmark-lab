import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient
from benchmark_lab.api import create_app

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_catalog import fixture


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);fixture(self.root)
        self.client=TestClient(create_app(self.root,self.root/'index.sqlite3'))
        self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)

    def test_read_only_list_detail_and_true_units(self):
        listing=self.client.get('/api/runs').json();self.assertEqual(listing['requests'],2)
        self.assertEqual(listing['mode'],'historical_replay');self.assertFalse(listing['launches_gpu'])
        detail=self.client.get('/api/runs/'+listing['runs'][0]['id']).json()
        self.assertEqual(detail['request_timing'][0]['ttft_ms'],100)
        self.assertEqual(detail['tails']['latencies']['99'],1990)
        # Fixture requests overlap while max_concurrency is 1: reported, never hidden.
        self.assertEqual((detail['timeline']['peak_in_flight'],detail['timeline']['within_client_limit']),(2,False))
        self.assertAlmostEqual(detail['request_timing'][1]['dispatch_ms'],100)

    def test_filters_and_csv_match(self):
        response=self.client.get('/api/export.csv?engine=vllm&concurrency=1')
        self.assertEqual(response.status_code,200)
        rows=list(csv.DictReader(io.StringIO(response.text)));self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['mean_ttft_ms'],'150')
        self.assertEqual(self.client.get('/api/runs?engine=sglang').json()['total'],0)
        self.assertEqual(self.client.get('/api/runs?engine=other').status_code,400)

    def test_artifacts_allowlist_and_hash_check(self):
        row=self.client.get('/api/runs').json()['runs'][0];base='/api/runs/'+row['id']+'/artifacts/'
        self.assertEqual(self.client.get(base+'result').content,(self.root/row['source']).read_bytes())
        self.assertEqual(self.client.get(base+'config.local.json').status_code,404)
        (self.root/row['source']).write_text('{}')
        self.assertEqual(self.client.get(base+'result').status_code,409)
        self.assertEqual(self.client.get('/api/runs/'+row['id']).status_code,409)

    def test_imported_runs_source_filter_and_provenance_artifact(self):
        from benchmark_lab.vllm_import import import_file
        from test_import import bench_result
        source=self.root/'incoming.json';source.write_bytes(__import__('json').dumps(bench_result()).encode())
        imported=import_file(self.root,source,'vllm','api fixture')['id']
        self.client.__exit__(None,None,None)
        self.client=TestClient(create_app(self.root,self.root/'index2.sqlite3'));self.client.__enter__()
        self.addCleanup(self.client.__exit__,None,None,None)
        listing=self.client.get('/api/runs?source=imported').json()
        self.assertEqual([r['id'] for r in listing['runs']],[imported])
        self.assertEqual(self.client.get('/api/runs?source=baseline').json()['total'],1)
        self.assertEqual(self.client.get('/api/runs?source=elsewhere').status_code,400)
        detail=self.client.get('/api/runs/'+imported).json()
        self.assertEqual(detail['provenance']['source_name'],'incoming.json')
        self.assertEqual(self.client.get(f'/api/runs/{imported}/artifacts/provenance').status_code,200)
        rows=list(csv.DictReader(io.StringIO(self.client.get('/api/export.csv?source=imported').text)))
        self.assertEqual((rows[0]['kind'],rows[0]['label']),('imported','api fixture'))

    def test_evidence_report_follows_filters(self):
        response=self.client.get('/api/report.md?engine=vllm')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.headers['content-type'].startswith('text/markdown'))
        self.assertIn('attachment',response.headers['content-disposition'])
        self.assertIn('# 证据报告',response.text);self.assertIn('数据范围：engine=vllm',response.text)
        self.assertEqual(self.client.get('/api/report.md?engine=other').status_code,400)

    def test_unknown_run_and_no_execution_endpoint(self):
        self.assertEqual(self.client.get('/api/runs/no-such-run').status_code,404)
        self.assertEqual(self.client.post('/api/runs',json={'command':'anything'}).status_code,405)
        self.assertEqual(self.client.post('/api/tasks',json={}).status_code,404)

    def test_local_assets_and_no_external_javascript(self):
        html=self.client.get('/').text
        self.assertIn('历史数据回放',html)
        self.assertIn('/static/app.js',html)
        for engine in ('vllm','sglang'):self.assertIn(f'<option value="{engine}">',html)
        self.assertEqual(self.client.get('/static/styles.css').status_code,200)
        self.assertNotIn('https://',self.client.get('/static/app.js').text)


if __name__=='__main__':unittest.main()
