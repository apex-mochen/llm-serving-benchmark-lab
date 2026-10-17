import unittest
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

from lab import validate, report, write_json, CONCURRENCIES


class ResultValidation(unittest.TestCase):
    def setUp(self):
        self.result = dict(completed=2, input_lens=[1024, 1024], output_lens=[256, 256],
                           mean_ttft_ms=10, mean_tpot_ms=2, mean_itl_ms=2, output_throughput=100)

    def test_completed_counter_cannot_hide_wrong_output_length(self):
        self.result['output_lens'][1] = 255
        self.assertTrue(validate(self.result, 2))

    def test_all_success_required(self):
        self.result['completed'] = 1
        self.assertTrue(validate(self.result, 2))

    def test_detailed_lengths_required(self):
        self.result.pop('input_lens')
        self.assertTrue(validate(self.result, 2))

    def test_nan_metric_rejected(self):
        self.result['mean_ttft_ms'] = float('nan')
        self.assertTrue(validate(self.result, 2))

    def test_verified_fixture_accepted(self):
        self.assertEqual(validate(self.result, 2), [])


class ReportIntegration(unittest.TestCase):
    def fixture(self, root, engine, uuid='fixture-gpu'):
        root.mkdir()
        params = {'prefix_cache': False}
        cfg = dict(repeats=3, num_prompts=256, model_revision='f'*40,
                   model_snapshot='/fixture/model', seed=1, served_model_name='fixture-model',
                   engines={e: {'server_parameters': params} for e in ['vllm', 'sglang']})
        write_json(root / 'metadata.json', dict(engine=engine, config=cfg, machine='fixture-machine',
                   client_version='fixture-version', gpu=dict(uuid=uuid, driver_version='fixture',
                   **{'memory.total': 8192})))
        for c in CONCURRENCIES:
            for r in range(3):
                stem = f'c{c}-r{r}'
                write_json(root / (stem+'.json'), dict(completed=256, input_lens=[1024]*256,
                           output_lens=[256]*256, mean_ttft_ms=10, mean_tpot_ms=2,
                           mean_itl_ms=2, output_throughput=100*c))
                write_json(root / (stem+'-validation.json'), dict(valid=True, errors=[]))
                write_json(root / (stem+'-gpu.json'), dict(errors=[], samples=[
                           dict(uuid=uuid, **{'memory.used': 1000, 'utilization.gpu': 50})]*2))

    def test_complete_fixture_generates_report_and_parseable_plot(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            roots = [base/'vllm', base/'sglang']
            for root, engine in zip(roots, ['vllm','sglang']):
                self.fixture(root, engine)
            output = base/'reports'/'001-concurrency-study.md'
            report(roots, output)
            self.assertIn('| sglang | 64 |', output.read_text())
            ET.parse(output.with_suffix('.svg'))
            self.assertEqual(len(output.with_suffix('.csv').read_text().splitlines()), 9)

    def test_cross_gpu_comparison_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.fixture(base/'vllm', 'vllm', 'gpu-a')
            self.fixture(base/'sglang', 'sglang', 'gpu-b')
            with self.assertRaisesRegex(ValueError, 'GPU UUID'):
                report([base/'vllm', base/'sglang'], base/'report.md')


if __name__ == '__main__':
    unittest.main()
