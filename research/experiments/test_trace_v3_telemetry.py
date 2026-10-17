"""Synthetic CPU contracts for safety gating; not real-GPU validation."""
import unittest
from run_trace_revalidation_v3 import violations


class OwnershipContracts(unittest.TestCase):
    def sample(self, compute='11, EngineCore'):
        return dict(processes='PID PPID PGID CPU RSS COMMAND\n10 1 10 0 1 vllm\n11 10 10 0 1 EngineCore', compute_csv=compute)

    def test_owned_child_is_not_foreign(self):
        self.assertEqual(violations(self.sample(), 10), [])

    def test_initial_compute_is_protected(self):
        self.assertTrue(violations(self.sample(), None))

    def test_unresolved_pid_is_not_assumed_owned(self):
        self.assertTrue(violations(self.sample('999, unknown'), 10))

    def test_compiler_blocks_even_without_compute(self):
        snapshot = self.sample('')
        snapshot['processes'] += '\n12 1 12 0 1 rustc'
        self.assertTrue(violations(snapshot, 10))


if __name__ == '__main__':
    unittest.main()
