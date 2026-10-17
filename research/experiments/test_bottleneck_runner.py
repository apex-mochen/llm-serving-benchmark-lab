"""HTTP mock checks only: not serving performance measurements."""
import asyncio
import importlib.util
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import threading
import time
import unittest

spec=importlib.util.spec_from_file_location('runner',Path(__file__).with_name('run_bottleneck_signatures.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class RunnerTests(unittest.TestCase):
    def setUp(self):
        outer=self;self.payloads=[];self.inject_error=False
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.payloads.append(body)
                if outer.inject_error:self.send_response(500);self.end_headers();return
                time.sleep(.01)
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                for obj in [{'choices':[{'text':'mock'}]}, {'choices':[], 'usage':dict(prompt_tokens=len(body['prompt']),completion_tokens=body['max_tokens'])}]:
                    self.wfile.write(('data: '+json.dumps(obj)+'\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.worker=threading.Thread(target=self.server.serve_forever);self.worker.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):self.server.shutdown();self.server.server_close();self.worker.join()
    def test_variable_lengths_and_usage(self):
        tokens=r.prompts(7,512,n=2)
        rows,_=asyncio.run(r.run_requests(self.base,'mock',tokens,256,1))
        self.assertTrue(all(x['success'] and x['usage']['completion_tokens']==256 for x in rows))
        self.assertEqual([x['prompt'] for x in self.payloads],tokens)
        self.assertGreater(rows[1]['client_queue_s'],.005)
    def test_open_arrival_boundary(self):
        rows,_=asyncio.run(r.run_requests(self.base,'mock',r.prompts(7,128,n=3),32,4,20))
        for row in rows:self.assertGreaterEqual(row['sent_s'],row['planned_s'])
        self.assertEqual(sorted(x['planned_s'] for x in rows),[0,.05,.1])
    def test_failure_not_invented_as_success(self):
        self.inject_error=True
        rows,_=asyncio.run(r.run_requests(self.base,'mock',r.prompts(7,128,n=1),32,1))
        self.assertFalse(rows[0]['success']);self.assertNotIn('ttft_s',rows[0])
    def test_shared_prefix_and_percentile(self):
        values=r.prompts(7,1024,n=3,shared=256)
        self.assertEqual(values[0][:256],values[1][:256]);self.assertNotEqual(values[0][256:],values[1][256:])
        self.assertEqual(r.quantile([1,2,3,4],50),2.5)

if __name__=='__main__':unittest.main(verbosity=2)
