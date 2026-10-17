import hashlib
from pathlib import Path
import tempfile
import unittest

from benchmark_lab.report import compare_groups, render
from test_catalog import fixture


def run(engine, concurrency, value, kind='baseline', repeat=0):
    return dict(kind=kind, engine=engine, concurrency=concurrency, repeat=repeat, requests=64, label=None,
        mean_ttft_ms=value, mean_tpot_ms=value, output_tokens_per_s=value, p99_latency_ms=value,
        source=f'results/x/c{concurrency}-r{repeat}.json', source_sha256='a' * 64)


class CompareTests(unittest.TestCase):
    def test_overlap_and_separation_match_browser_rule(self):
        runs = [run('vllm', 8, v) for v in (10, 12, 30)] + [run('sglang', 8, v) for v in (11, 13, 14)]
        runs += [run('vllm', 32, v) for v in (50, 55, 60)] + [run('sglang', 32, v) for v in (20, 21, 22)]
        rows = compare_groups(runs, 'mean_ttft_ms')
        self.assertEqual([(r['concurrency'], r['separated']) for r in rows], [(8, False), (32, True)])
        self.assertAlmostEqual(rows[1]['ratio'], 55 / 21)
        self.assertEqual(rows[1]['vllm'], dict(median=55, min=50, max=60, n=3))

    def test_imported_runs_and_single_engine_groups_are_excluded(self):
        runs = [run('vllm', 8, 10), run('sglang', 8, 99, kind='imported'), run('vllm', 64, 5)]
        self.assertEqual(compare_groups(runs, 'mean_ttft_ms'), [])

    def test_render_states_scope_hashes_and_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); fixture(root)
            rows = [run('vllm', 1, 150)]
            text = render(root, rows, dict(engine='vllm', concurrency=None, source=None), '2026-10-17T00:00:00+00:00')
            manifest_sha = hashlib.sha256((root/'reports/001-raw-sha256.json').read_bytes()).hexdigest()
        self.assertIn(manifest_sha, text)
        self.assertIn('数据范围：engine=vllm', text)
        self.assertIn('不是显著性检验', text)
        self.assertIn('当前数据范围内没有同一并发下同时包含 vLLM 和 SGLang 的历史基线', text)
        self.assertIn('`' + 'a' * 64 + '`', text)


if __name__ == '__main__': unittest.main()
