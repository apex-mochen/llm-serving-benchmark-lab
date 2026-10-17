"""CPU correctness checks; no synthetic performance claims."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_diagnosis_phase2 import workload, validate_native, cell_schedule


class Correctness(unittest.TestCase):
    def test_paired_lengths(self):
        for seed in (20261012, 20271012):
            short = workload(seed, 512)
            long = workload(seed, 1536)
            self.assertEqual(short, [row[:512] for row in long])
            self.assertEqual(short, workload(seed, 512))

    def test_cache_prefix_and_unique_suffix(self):
        rows = workload(20261012, 1024, 256)
        self.assertTrue(all(row[:256] == rows[0][:256] for row in rows))
        self.assertEqual(len({tuple(row[256:]) for row in rows}), 8)

    def test_native_boundary_formula(self):
        m = dict(queue_time_ms=12., time_to_first_token_ms=4.,
                 generation_time_ms=127., mean_itl_ms=1.)
        validate_native(m, 128)
        for field in m:
            for invalid in (None, float('nan'), float('inf'), -1.):
                with self.assertRaises(ValueError):
                    validate_native({**m, field: invalid}, 128)
        with self.assertRaises(ValueError):
            validate_native({**m, 'mean_itl_ms': 2.}, 128)
        with self.assertRaises(ValueError):
            validate_native({}, 128)

    def test_fixed_expansion_and_matrices(self):
        expansion = cell_schedule('expand')
        self.assertEqual(len(expansion), 10)
        self.assertTrue(all(c[2] == 512 and c[4] == 'disabled' and c[6] == 128 for c in expansion))
        self.assertEqual({c[3] for c in expansion}, {4, 8})
        for mode in ('matrix-a', 'matrix-b'):
            cells = cell_schedule(mode)
            self.assertEqual(len(cells), 12)
            self.assertEqual(len({c[1] for c in cells}), 4)
            self.assertTrue(all(c[6] == 8 for c in cells))


if __name__ == '__main__':
    unittest.main(verbosity=2)
