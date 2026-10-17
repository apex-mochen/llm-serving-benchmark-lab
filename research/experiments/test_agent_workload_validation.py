"""Local HTTP mock tests, never GPU performance evidence."""
import asyncio
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

path=Path(__file__).with_name('agent_workload_validation.py')
spec=importlib.util.spec_from_file_location('validation',path)
v=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.payloads=[]
        outer=self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.payloads.append(body)
                if getattr(outer,'inject_failure',False):
                    self.send_response(500);self.end_headers();return
                self.send_response(200)
                self.send_header('Content-Type','text/event-stream');self.end_headers()
                messages=[{'choices':[{'text':'mock'}]}, {'choices':[], 'usage':{'prompt_tokens':len(body['prompt']),'completion_tokens':64}}]
                for message in messages:
                    self.wfile.write(('data: '+json.dumps(message)+'\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')
            def log_message(self,*args): pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def test_paired_payloads_and_dependency(self):
        rows=v.trace(7,sessions=2)
        with tempfile.TemporaryDirectory() as directory:
            records,_=asyncio.run(v.requests_run(rows,self.base,'mock',Path(directory)/'agent'))
            targets={r['request_id']:r['sent_s'] for r in records}
            baseline,_=asyncio.run(v.requests_run(rows,self.base,'mock',Path(directory)/'traditional',targets))
        a={r['request_id']:r for r in records};b={r['request_id']:r for r in baseline}
        self.assertEqual({k:r['prompt_sha256'] for k,r in a.items()},{k:r['prompt_sha256'] for k,r in b.items()})
        self.assertEqual({k:r['input_tokens'] for k,r in a.items()},{k:r['input_tokens'] for k,r in b.items()})
        for row in rows:
            if row['parent']:
                self.assertGreaterEqual(a[row['request_id']]['sent_s']+1e-5,a[row['parent']]['end_s']+row['pause_s'])
            self.assertEqual(b[row['request_id']]['target_s'],a[row['request_id']]['sent_s'])

    def test_parent_failure_cancels_unsent_child(self):
        self.inject_failure=True
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                asyncio.run(v.requests_run(v.trace(7,sessions=1),self.base,'mock',Path(directory)))
            events=json.loads((Path(directory)/'events.json').read_text())
        self.assertEqual(len(self.payloads),1)
        self.assertTrue(any(e['event']=='cancelled_dependency' for e in events))

if __name__=='__main__': unittest.main(verbosity=2)
