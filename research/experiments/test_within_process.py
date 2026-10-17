import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import within_process_control as w


class Response:
    headers={}
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    def raise_for_status(self): pass
    async def aiter_lines(self):
        yield 'data: '+json.dumps(dict(id='test',choices=[dict(text='a')]))
        yield 'data: '+json.dumps(dict(id='test',choices=[dict(text='b')]))
        yield 'data: '+json.dumps(dict(usage=dict(prompt_tokens=1,completion_tokens=2)))


class Client:
    def __init__(self,*args,**kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    def stream(self,*args,**kwargs): return Response()


class Tests(unittest.TestCase):
    def test_missing_metrics_not_zero(self):
        with self.assertRaises(RuntimeError): w.check_boundary({})
    def test_nonzero_not_drained(self):
        with self.assertRaises(RuntimeError): w.check_boundary({'vllm:num_requests_running':1,'vllm:num_requests_waiting':0})
    def test_valid_boundary(self):
        w.check_boundary({'vllm:num_requests_running':0,'vllm:num_requests_waiting':0})
    def test_labels(self):
        self.assertEqual(''.join(w.label(i) for i in range(0,64,4)),'ABBA'*4)
    def test_summary_by_index_not_completion_order(self):
        rows=[dict(index=i,success=True,ttft_ms=i,tpot_ms=2,e2e_ms=4) for i in reversed(range(8))]
        self.assertEqual(w.summarize(rows)['front_ttft_ms'],1.5)
        self.assertEqual(w.summarize(rows)['back_ttft_ms'],5.5)
    def test_host_memory_gate(self):
        self.assertIn('host_physical_below_3GiB',w.host_problems(dict(memory=dict(FreePhysicalMemory=1,FreeVirtualMemory=7*1024*1024),processes=[])))
    def test_absolute_clock_and_partial_raw(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(w.x.httpx,'AsyncClient',Client):
            timing={}; path=Path(folder)/'partial.jsonl'
            before=w.anchor()['monotonic_s']
            rows,elapsed=asyncio.run(w.x.episode_http('http://fixture','fixture',[[1]],2,1,'fixture',False,rate=0,timing=timing,partial_path=path))
            self.assertTrue(rows[0]['success'])
            self.assertLessEqual(before,timing['start_monotonic_s'])
            self.assertGreaterEqual(timing['end_monotonic_s'],timing['start_monotonic_s']+rows[0]['end_s'])
            self.assertAlmostEqual(elapsed,timing['end_monotonic_s']-timing['start_monotonic_s'])
            self.assertEqual(len(path.read_text().splitlines()),1)
    def test_monitor_failure_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder); (p/'monitor-hazard.json').write_text('{}')
            with self.assertRaises(RuntimeError): w.healthy(p,None)
    def test_legacy_signature_still_works(self):
        with patch.object(w.x.httpx,'AsyncClient',Client):
            rows,elapsed=asyncio.run(w.x.episode_http('http://fixture','fixture',[[1]],2,1,'legacy',False,rate=0))
            self.assertTrue(rows[0]['success'])
            self.assertGreaterEqual(elapsed,0)


if __name__=='__main__': unittest.main(verbosity=2)
