import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from benchmark_lab.catalog import Catalog, EvidenceError


def fixture(root):
    directory = root/'results/fixture-vllm'
    directory.mkdir(parents=True)
    (root/'reports').mkdir()
    result = dict(completed=2,num_prompts=2,input_lens=[1024,1024],output_lens=[256,256],
        mean_ttft_ms=150,mean_tpot_ms=3,mean_itl_ms=3,output_throughput=100,
        ttfts=[.1,.2],latencies=[1,2],queue_times=[0,.1],start_times=[1,1.1],errors=['',''],
        request_rate='inf',max_concurrency=1)
    metadata = dict(engine='vllm',engine_commit='a'*40,environment=dict(engine='fixture-version'),
        gpu=dict(name='CPU fixture, not measured GPU',**{'memory.total':8192}),
        config=dict(num_prompts=2,model_snapshot='/fixture/model',model_revision='b'*40,seed=42))
    values={'metadata.json':metadata,'c1-r0.json':result,'c1-r0-validation.json':dict(valid=True,errors=[])}
    for name,value in values.items(): (directory/name).write_text(json.dumps(value))
    seal(root)


def seal(root):
    manifest={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'results').rglob('*.json')}
    (root/'reports/001-raw-sha256.json').write_text(json.dumps(manifest))


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);fixture(self.root)
        self.catalog=Catalog(self.root,self.root/'index/cache.sqlite3')

    def test_single_engine_fixture_and_unit_conversion(self):
        self.assertEqual(self.catalog.rebuild(),1)
        run=self.catalog.runs(engine='vllm',concurrency=1)[0]
        detail=self.catalog.detail(run['id'])
        self.assertEqual(detail['request_timing'][1]['ttft_ms'],200)
        self.assertEqual(detail['tails']['latencies']['95'],1950)
        self.assertEqual(detail['mean_ttft_ms'],150)

    def test_bad_hash_prevents_index(self):
        (self.root/'results/fixture-vllm/c1-r0.json').write_text('{}')
        with self.assertRaises(EvidenceError):self.catalog.rebuild()
        self.assertFalse(self.catalog.database.exists())

    def test_failed_original_validation_rejected_even_with_matching_hash(self):
        (self.root/'results/fixture-vllm/c1-r0-validation.json').write_text('{"valid":false,"errors":["fixture failure"]}')
        seal(self.root)
        with self.assertRaises(EvidenceError):self.catalog.rebuild()

    def test_invalid_request_timing_rejected(self):
        path=self.root/'results/fixture-vllm/c1-r0.json';data=json.loads(path.read_text());data['ttfts'][0]=10
        path.write_text(json.dumps(data));seal(self.root)
        with self.assertRaises(ValueError):self.catalog.rebuild()

    def test_failed_rebuild_preserves_existing_transaction(self):
        self.catalog.rebuild();before=self.catalog.runs()
        (self.root/'results/fixture-vllm/c1-r0.json').write_text('{}')
        with self.assertRaises(EvidenceError):self.catalog.rebuild()
        self.assertEqual(self.catalog.runs(),before)

    def test_path_escape_rejected(self):
        self.catalog.expected={'../not-project.json':'x'}
        with self.assertRaises(EvidenceError):self.catalog.read('../not-project.json')

    def test_detail_detects_post_import_mutation(self):
        self.catalog.rebuild();run=self.catalog.runs()[0]
        (self.root/run['source']).write_text('{}')
        with self.assertRaises(EvidenceError):self.catalog.detail(run['id'])

    def test_unknown_and_injected_filters_do_not_query_arbitrary_data(self):
        self.catalog.rebuild()
        with self.assertRaises(EvidenceError):self.catalog.runs(engine="vllm' OR 1=1--")
        self.assertEqual(self.catalog.runs(engine='sglang'),[])
        with self.assertRaises(KeyError):self.catalog.run("' OR 1=1--")

    def test_raw_evidence_unchanged_and_stable_ids(self):
        before={str(p):p.read_bytes() for p in (self.root/'results').rglob('*.json')}
        self.catalog.rebuild();old=self.catalog.runs()[0]['id'];self.catalog.rebuild()
        self.assertEqual(old,self.catalog.runs()[0]['id'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in (self.root/'results').rglob('*.json')})


if __name__=='__main__':unittest.main()
