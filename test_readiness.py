import unittest
from unittest.mock import Mock, patch

from study import wait_until_ready


class ReadinessTests(unittest.TestCase):
    def test_slow_first_health_request_is_retried(self):
        proc = Mock()
        proc.poll.return_value = None
        response = Mock()
        with patch('study.urllib.request.urlopen', side_effect=[TimeoutError(), response]) as request:
            with patch('study.time.sleep') as sleep:
                wait_until_ready(proc, 'http://localhost:8019', 'sglang', 'server.log')
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1)
        response.close.assert_called_once()

    def test_dead_server_is_not_retried(self):
        proc = Mock()
        proc.poll.return_value = 1
        with patch('study.urllib.request.urlopen') as request:
            with self.assertRaisesRegex(RuntimeError, 'server failed'):
                wait_until_ready(proc, 'http://localhost:8019', 'sglang', 'server.log')
        request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
