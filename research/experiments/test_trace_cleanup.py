"""CPU failure-injection contracts. No CUDA, subprocess launch or real kill."""
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import trace_cleanup


class CleanupContracts(unittest.TestCase):
    def sample(self):
        return dict(processes='PID PPID PGID CPU RSS COMMAND\n99 1 99 0 1 idle', gpu_csv='gpu,uuid,100,8188,0')

    def call(self, proc=None, snapshot=None, writer=None, violations=None):
        return trace_cleanup.cleanup_owned(proc,self.sample(),Path('/unused'),
            snapshot or self.sample, writer or Mock(), violations or (lambda _: []), sleep=lambda _: None)

    def test_none_proc_does_not_access_pid(self):
        self.assertEqual(self.call(), [])

    def test_primary_exception_survives_cleanup_snapshot_failure(self):
        collected = []
        with self.assertRaisesRegex(ValueError, 'original request failure'):
            try:
                raise ValueError('original request failure')
            finally:
                collected.extend(self.call(snapshot=Mock(side_effect=RuntimeError('snapshot failed'))))
        self.assertEqual(collected[0]['phase'], 'snapshot_after')

    def test_secondary_external_activity_is_explicit(self):
        errors = self.call(violations=lambda _: ['compiler:123:cmake'])
        self.assertEqual(errors[0]['phase'], 'post_run_activity')

    def test_writer_failure_does_not_hide_other_checks(self):
        errors = self.call(writer=Mock(side_effect=OSError('disk failure')),
                           violations=lambda _: ['foreign'])
        self.assertEqual([e['phase'] for e in errors], ['write_after','post_run_activity'])

    def test_global_memory_is_not_labelled_owned_leak(self):
        proc = Mock(pid=10); proc.poll.return_value = 0
        after = self.sample(); after['gpu_csv'] = 'gpu,uuid,500,8188,0'
        errors = self.call(proc=proc, snapshot=lambda: after)
        self.assertEqual(errors[0]['phase'], 'global_gpu_memory_delta')

    @patch('trace_cleanup.os.killpg')
    def test_only_known_live_owned_group_is_signalled(self, kill):
        proc = Mock(pid=10); proc.poll.return_value = None
        self.assertEqual(self.call(proc=proc), [])
        kill.assert_called_once_with(10, trace_cleanup.signal.SIGTERM)
        proc.wait.assert_called_once_with(timeout=20)

    def test_termination_failure_is_recorded(self):
        proc = Mock(pid=10); proc.poll.side_effect = RuntimeError('poll failed')
        errors = self.call(proc=proc)
        self.assertEqual(errors[0]['phase'], 'terminate_owned_group')


if __name__ == '__main__': unittest.main()
