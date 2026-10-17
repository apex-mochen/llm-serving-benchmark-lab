import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from benchmark_lab.catalog import Catalog, EvidenceError
from benchmark_lab.vllm_import import DETAILED, ImportRejected, import_file, inspect
from tail_report import percentile
from test_catalog import fixture


def bench_result(n=4, detailed=True):
    """Shape of `vllm bench serve --save-result [--save-detailed]` (vllm/benchmarks/serve.py)."""
    ttfts = [0.1 * (i + 1) for i in range(n)]
    result = dict(date='20261017-120000', backend='vllm', endpoint_type='vllm', model_id='fixture',
        num_prompts=n, request_rate='inf', burstiness=1.0, max_concurrency=2, duration=3.0,
        completed=n, failed=0, request_throughput=n / 3.0, output_throughput=50.0,
        mean_tpot_ms=12.0, mean_ttft_ms=sum(ttfts) / n * 1000,
        latencies=[1.0 + i for i in range(n)], queue_times=[0.0] * n,
        ttfts=ttfts, errors=[''] * n, start_times=[0.01 * i for i in range(n)],
        input_lens=[16] * n, output_lens=[8] * n)
    for p in (50, 95, 99):
        result[f'p{p}_ttft_ms'] = percentile(ttfts, p) * 1000
    if not detailed:
        for key in ('ttfts', 'errors', 'start_times', 'input_lens', 'output_lens'):
            del result[key]
    return result


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); fixture(self.root)
        self.catalog = Catalog(self.root, self.root/'index/cache.sqlite3')

    def write(self, name, value):
        path = self.root/'incoming'/name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(json.dumps(value).encode())
        return path

    def test_detailed_import_is_indexed_with_request_timing(self):
        source = self.write('run.json', bench_result())
        before = source.read_bytes()
        outcome = import_file(self.root, source, 'vllm', 'fixture run')
        self.assertEqual((outcome['status'], outcome['detail_level']), ('imported', 'detailed'))
        self.assertEqual(source.read_bytes(), before)
        copied = self.root/'imports'/outcome['id']/'result.json'
        self.assertEqual(copied.read_bytes(), before)
        self.assertEqual(self.catalog.rebuild(), 2)
        row = self.catalog.runs(kind='imported')[0]
        self.assertEqual((row['label'], row['concurrency'], row['repeat']), ('fixture run', 2, None))
        detail = self.catalog.detail(row['id'])
        self.assertEqual(len(detail['request_timing']), 4)
        self.assertEqual(detail['tails']['latencies']['50'], 2500)
        self.assertEqual(len(self.catalog.runs(kind='baseline')), 1)

    def test_summary_only_import_has_no_request_view(self):
        outcome = import_file(self.root, self.write('s.json', bench_result(detailed=False)), 'sglang')
        self.assertEqual(outcome['detail_level'], 'summary')
        self.catalog.rebuild()
        detail = self.catalog.detail(outcome['id'])
        self.assertIsNone(detail['request_timing'])
        self.assertIn('99', detail['tails']['latencies'])

    def test_reimport_is_idempotent(self):
        source = self.write('run.json', bench_result())
        first = import_file(self.root, source, 'vllm')
        self.assertEqual(import_file(self.root, source, 'vllm')['status'], 'already_imported')
        self.assertEqual(len(json.loads((self.root/'imports/manifest.json').read_text())), 2)
        self.assertTrue(first['id'].startswith('imp-'))

    def test_rejections(self):
        failed = bench_result(); failed['failed'] = 1
        partial = bench_result(); partial['completed'] = 3
        inconsistent = bench_result(); inconsistent['p99_ttft_ms'] += 5
        misaligned = bench_result(); misaligned['ttfts'] = misaligned['ttfts'][:-1]
        errored = bench_result(); errored['errors'][0] = 'timeout'
        for name, value in dict(failed=failed, partial=partial, inconsistent=inconsistent,
                                misaligned=misaligned, errored=errored).items():
            with self.subTest(name), self.assertRaises(ImportRejected):
                import_file(self.root, self.write(name + '.json', value), 'vllm')
        self.assertFalse((self.root/'imports').exists())
        with self.assertRaises(ImportRejected):
            import_file(self.root, self.write('x.json', bench_result()), 'other')

    def test_baseline_bytes_are_not_reimported(self):
        with self.assertRaises(ImportRejected):
            import_file(self.root, self.root/'results/fixture-vllm/c1-r0.json', 'vllm')

    def test_tampered_import_blocks_rebuild(self):
        outcome = import_file(self.root, self.write('run.json', bench_result()), 'vllm')
        self.catalog.rebuild()
        result = self.root/'imports'/outcome['id']/'result.json'
        result.write_text('{}')
        with self.assertRaises(EvidenceError):
            self.catalog.detail(outcome['id'])
        with self.assertRaises(EvidenceError):
            self.catalog.rebuild()

    def test_rehashed_but_invalid_import_still_rejected(self):
        outcome = import_file(self.root, self.write('run.json', bench_result()), 'vllm')
        folder = self.root/'imports'/outcome['id']
        bad = bench_result(); bad['failed'] = 2
        data = json.dumps(bad).encode(); (folder/'result.json').write_bytes(data)
        manifest = json.loads((self.root/'imports/manifest.json').read_text())
        manifest[f"imports/{outcome['id']}/result.json"] = hashlib.sha256(data).hexdigest()
        (self.root/'imports/manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(EvidenceError):
            self.catalog.rebuild()

    def test_summary_fields_match_upstream_drop_list(self):
        level, _ = inspect(bench_result(detailed=False))
        self.assertEqual(level, 'summary')
        self.assertTrue(set(DETAILED) - {'latencies', 'queue_times'})


if __name__ == '__main__': unittest.main()
