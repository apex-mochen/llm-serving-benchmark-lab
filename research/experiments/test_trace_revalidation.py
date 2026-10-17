import unittest
from run_trace_revalidation import compare, summarize


class Arithmetic(unittest.TestCase):
    def rows(self, ratio):
        result=[]
        for i in range(3):
            for variant,m in (('off',1.),('full',ratio)):
                result.append(dict(variant=variant,repeat=i,summary={
                    'mean_ttft_ms':100*m,'mean_tpot_ms':10*m,'mean_e2e_ms':1000*m,
                    'requests_per_s':8/m,'output_tokens_per_s':1024/m}))
        return result

    def test_identity(self):
        self.assertTrue(all(abs(v['median_overhead_percent'])<1e-9 for v in compare(self.rows(1),'off','full').values()))

    def test_latency_and_throughput_sign(self):
        values=compare(self.rows(1.1),'off','full')
        self.assertAlmostEqual(values['mean_ttft_ms']['median_overhead_percent'],10)
        self.assertAlmostEqual(values['requests_per_s']['median_overhead_percent'],100*(1-1/1.1))

    def test_equal_five_is_not_pass(self):
        values=compare(self.rows(1.05),'off','full')
        self.assertFalse(all(v['median_overhead_percent']<5 for v in values.values()))

    def test_measurement_denominator(self):
        values=summarize([dict(duration_s=4.,mean_ttft_ms=10.,mean_tpot_ms=2.,mean_e2e_ms=100.) for _ in range(8)])
        self.assertEqual(values['requests_per_s'],2.)
        self.assertEqual(values['output_tokens_per_s'],256.)


if __name__=='__main__':unittest.main(verbosity=2)
