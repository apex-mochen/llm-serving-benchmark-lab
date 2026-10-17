import unittest
import cpu_timing_probe as p

class Tests(unittest.TestCase):
    def test_fixed_order(self):
        self.assertEqual(len(p.ORDER),32);self.assertEqual(p.ORDER.count('sleep'),16);self.assertEqual(p.ORDER.count('client'),16)
    def test_distinct_delay_boundaries(self):
        r=p.derived('client',0,.01,dict(start_monotonic_s=.03),[dict(sent_s=.005)])
        self.assertAlmostEqual(r['wakeup_check_lateness_ms'],10);self.assertAlmostEqual(r['episode_start_lateness_ms'],30)
        self.assertAlmostEqual(r['first_request_send_lateness_ms'],35);self.assertAlmostEqual(r['client_initialization_after_check_ms'],20)
    def test_sleep_has_no_fictional_episode(self):
        self.assertIsNone(p.derived('sleep',0,.01,{},[])['episode_start_lateness_ms'])
    def test_budget_preserved(self):
        self.assertTrue(p.derived('sleep',0,.051,{},[])['wakeup_over_50ms'])

if __name__=='__main__':unittest.main(verbosity=2)
