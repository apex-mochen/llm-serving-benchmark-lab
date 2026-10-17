"""Own one serving process group at a time; preserve all study evidence."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request
import urllib.error

from lab import collect, report


def wait_until_ready(proc, base_url, engine, server_log):
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'{engine}: server failed; inspect {server_log}')
        try:
            urllib.request.urlopen(base_url + '/health', timeout=2).close()
            return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
    raise TimeoutError(f'{engine}: readiness deadline exceeded')


def study(config, engines=None, existing_runs=None):
    root = Path(__file__).resolve().parent
    cfg = json.loads(Path(config).read_text())
    cfg['results_dir'] = str((root / cfg['results_dir']).resolve())
    lock = root / '.benchmark.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    runs = [Path(run).resolve() for run in (existing_runs or [])]
    try:
        for engine in (engines or ['vllm', 'sglang']):
            entry = cfg['engines'][engine]
            # Never replace a pre-existing service at the requested address.
            try:
                urllib.request.urlopen(entry['base_url'] + '/v1/models', timeout=2).close()
            except urllib.error.HTTPError:
                raise RuntimeError('An existing HTTP service occupies the configured endpoint')
            except urllib.error.URLError:
                pass
            else:
                raise RuntimeError('An existing model service occupies the configured endpoint')
            stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
            server_log = root / 'results' / (stamp + '-' + engine + '-server.log')
            server_log.parent.mkdir(exist_ok=True)
            before = set(Path(cfg['results_dir']).glob('*-' + engine))
            with server_log.open('w') as log:
                proc = subprocess.Popen(entry['server_command'], stdout=log, stderr=subprocess.STDOUT,
                                        start_new_session=True, env={**os.environ, **entry.get('server_environment', {})})
                print(f'{engine}: started owned server PID {proc.pid}; {server_log}', flush=True)
                try:
                    wait_until_ready(proc, entry['base_url'], engine, server_log)
                    print(f'{engine}: starting fixed concurrency study', flush=True)
                    collect(cfg, engine)
                    after = set(Path(cfg['results_dir']).glob('*-' + engine)) - before
                    if len(after) != 1:
                        raise RuntimeError('Cannot uniquely identify this study run')
                    run = after.pop()
                    (run / 'server-log-location.txt').write_text(str(server_log) + '\n')
                    runs.append(run)
                finally:
                    if proc.poll() is None:
                        try:
                            os.killpg(proc.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        try:
                            proc.wait(timeout=20)
                        except subprocess.TimeoutExpired:
                            os.killpg(proc.pid, signal.SIGKILL)
                            proc.wait(timeout=10)
                    print(f'{engine}: owned server stopped', flush=True)
        report(runs, root / 'reports/001-concurrency-study.md')
    finally:
        if lock.exists() and lock.read_text() == str(os.getpid()):
            lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config')
    parser.add_argument('--engine', choices=['vllm', 'sglang'])
    parser.add_argument('--existing-run', action='append', default=[])
    args = parser.parse_args()
    study(args.config, [args.engine] if args.engine else None, args.existing_run)
