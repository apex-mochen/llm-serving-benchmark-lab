import copy
import tempfile
import unittest
from pathlib import Path
from tail_report import percentile, summarize, main
from unittest.mock import patch


class TailEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.result = dict(completed=3, num_prompts=3, errors=["", "", ""],
                           ttfts=[0.1, 0.2, 0.3], latencies=[1, 2, 3],
                           queue_times=[0, 0.01, 0.02], start_times=[1, 1.1, 1.2])

    def test_linear_percentiles(self):
        self.assertAlmostEqual(percentile([1, 3, 2], 95), 2.9)
        self.assertEqual(percentile([4], 99), 4)

    def test_reject_hidden_request_failure(self):
        self.result["errors"][1] = "timeout"
        with self.assertRaisesRegex(ValueError, "failed requests"):
            summarize(self.result, 3)

    def test_reject_incomplete_batch(self):
        self.result["completed"] = 2
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            summarize(self.result, 3)

    def test_missing_misaligned_or_invalid_timings(self):
        for key in ("ttfts", "latencies", "queue_times", "start_times"):
            for value in (None, [1], [0, float("nan"), 1], [0, float("inf"), 1], [0, -1, 1], [0, True, 1]):
                data = copy.deepcopy(self.result)
                data[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    summarize(data, 3)

    def test_ttft_cannot_exceed_total_latency(self):
        self.result["ttfts"][0] = 2
        with self.assertRaisesRegex(ValueError, "exceeds"):
            summarize(self.result, 3)

    def test_seconds_converted_to_ms(self):
        summary = summarize(self.result, 3)
        self.assertAlmostEqual(summary["tails_ms"]["ttfts"]["50"], 200)
        self.assertAlmostEqual(summary["client_start_span_s"], 0.2)

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            marker = path / "keep"
            marker.write_text("old evidence")
            with patch("tail_report.analyze", return_value={}):
                with patch("sys.argv", ["tail_report", "fixture", "--output", directory]):
                    with self.assertRaises(FileExistsError):
                        main()
            self.assertEqual(marker.read_text(), "old evidence")

    def test_queue_inclusive_tail_uses_per_request_sum(self):
        self.result['queue_times'] = [3, 2, 1]
        self.result['latencies'] = [1, 2, 3]
        summary = summarize(self.result, 3)
        self.assertEqual(summary['tails_ms']['arrival_to_completion']['99'], 4000)
        self.assertNotEqual(summary['tails_ms']['arrival_to_completion']['99'],
                            summary['tails_ms']['queue_times']['99'] + summary['tails_ms']['latencies']['99'])


if __name__ == "__main__":
    unittest.main()
