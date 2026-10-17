import unittest

from benchmark_lab.catalog import request_timeline


def result(starts, queues, ttfts, latencies, limit):
    return dict(start_times=starts, queue_times=queues, ttfts=ttfts, latencies=latencies, max_concurrency=limit)


class TimelineTests(unittest.TestCase):
    def test_offsets_follow_vllm_dispatch_clock(self):
        # Request 1 arrives with request 0 but waits 2 s for the single client slot.
        timing, summary = request_timeline(result([100.0, 102.0], [0.0, 2.0], [0.5, 0.25], [2.0, 1.0], 1), 2)
        second = timing[1]
        self.assertEqual((second['arrival_ms'], second['dispatch_ms']), (0.0, 2000.0))
        self.assertEqual((second['first_token_ms'], second['end_ms']), (2250.0, 3000.0))
        self.assertEqual(summary, dict(peak_in_flight=1, max_concurrency=1, span_ms=3000.0, within_client_limit=True))

    def test_completion_frees_slot_before_next_dispatch_at_same_instant(self):
        _, summary = request_timeline(result([0.0, 1.0], [0.0, 1.0], [0.1, 0.1], [1.0, 1.0], 1), 2)
        self.assertEqual(summary['peak_in_flight'], 1)

    def test_overlap_beyond_limit_is_reported_not_hidden(self):
        _, summary = request_timeline(result([0.0, 0.5], [0.0, 0.0], [0.1, 0.1], [1.0, 1.0], 1), 2)
        self.assertEqual((summary['peak_in_flight'], summary['within_client_limit']), (2, False))

    def test_rate_limited_run_without_concurrency_cap(self):
        _, summary = request_timeline(result([0.0, 0.5], [0.0, 0.0], [0.1, 0.1], [1.0, 1.0], None), 2)
        self.assertIsNone(summary['within_client_limit'])


if __name__ == '__main__': unittest.main()
