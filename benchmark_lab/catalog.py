"""Rebuildable SQLite index of hash-verified historical runs. No GPU or subprocesses."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from lab import validate
from tail_report import summarize


class EvidenceError(ValueError):
    pass


class Catalog:
    def __init__(self, root, database):
        self.root = Path(root).resolve()
        self.database = Path(database)
        self.expected = {}

    def read(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise EvidenceError('Evidence path escapes project root')
        expected = self.expected.get(relative)
        if not expected:
            raise EvidenceError('File is not listed in the baseline manifest')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise EvidenceError('Source hash mismatch: ' + relative)
        return data

    def load(self, relative):
        return json.loads(self.read(relative))

    @contextmanager
    def connect(self):
        # sqlite3's own context manager only commits/rolls back; close explicitly so
        # Windows does not keep the index file locked.
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def rebuild(self):
        manifest = self.root / 'reports/001-raw-sha256.json'
        expected = json.loads(manifest.read_text(encoding='utf-8'))
        if not isinstance(expected, dict) or not expected:
            raise EvidenceError('Missing baseline evidence manifest')
        self.expected = expected
        # Verify the whole original baseline before making any indexed values available.
        for relative in expected:
            self.read(relative)
        records = []
        for relative in sorted(expected):
            match = re.fullmatch(r'results/([^/]+)/c(1|8|32|64)-r(\d+)\.json', relative)
            if not match:
                continue
            # Manifest keys are POSIX paths; Path() would use backslashes on Windows.
            directory = relative.rsplit('/', 1)[0]
            metadata = self.load(directory + '/metadata.json')
            result = self.load(relative)
            validation_path = relative[:-5] + '-validation.json'
            validation = self.load(validation_path)
            count = metadata['config']['num_prompts']
            concurrency, repeat = int(match[2]), int(match[3])
            if metadata['engine'] not in ('vllm', 'sglang'):
                raise EvidenceError('Unknown baseline engine')
            if (validation.get('valid') is not True or validation.get('errors') != []
                    or validate(result, count)
                    or result.get('max_concurrency') != concurrency
                    or result.get('request_rate') != 'inf'):
                raise EvidenceError('Invalid original run: ' + relative)
            tail = summarize(result, count)
            run_id = hashlib.sha256(relative.encode()).hexdigest()[:20]
            record = dict(id=run_id, engine=metadata['engine'], concurrency=concurrency,
                repeat=repeat, requests=count, status='validated_history',
                mean_ttft_ms=result['mean_ttft_ms'], mean_tpot_ms=result['mean_tpot_ms'],
                output_tokens_per_s=result['output_throughput'],
                p50_latency_ms=tail['tails_ms']['latencies']['50'],
                p95_latency_ms=tail['tails_ms']['latencies']['95'],
                p99_latency_ms=tail['tails_ms']['latencies']['99'],
                source=relative, source_sha256=expected[relative],
                artifacts=dict(result=relative, validation=validation_path, metadata=directory+'/metadata.json'))
            records.append(record)
        if not records:
            raise EvidenceError('No validated runs found')
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, engine TEXT NOT NULL, concurrency INTEGER NOT NULL, repeat INTEGER NOT NULL, payload TEXT NOT NULL)')
            con.execute('DELETE FROM runs')
            con.executemany('INSERT INTO runs VALUES (?, ?, ?, ?, ?)',
                [(r['id'], r['engine'], r['concurrency'], r['repeat'], json.dumps(r)) for r in records])
        return len(records)

    def runs(self, engine=None, concurrency=None):
        if engine is not None and engine not in ('vllm', 'sglang'):
            raise EvidenceError('Unsupported engine filter')
        if concurrency is not None and concurrency not in (1, 8, 32, 64):
            raise EvidenceError('Unsupported concurrency filter')
        query = 'SELECT payload FROM runs WHERE 1=1'
        params = []
        if engine is not None:
            query += ' AND engine=?'; params.append(engine)
        if concurrency is not None:
            query += ' AND concurrency=?'; params.append(concurrency)
        query += ' ORDER BY engine DESC, concurrency, repeat'
        with self.connect() as con:
            return [json.loads(row[0]) for row in con.execute(query, params)]

    def run(self, run_id):
        with self.connect() as con:
            row = con.execute('SELECT payload FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def detail(self, run_id):
        row = self.run(run_id)
        result = self.load(row['source'])
        metadata = self.load(row['artifacts']['metadata'])
        count = metadata['config']['num_prompts']
        tail = summarize(result, count)
        config = metadata['config']
        row.update(tails=tail['tails_ms'], environment=dict(
            engine_commit=metadata['engine_commit'],
            engine_version=metadata['environment'].get('engine'),
            gpu=metadata['gpu']['name'], gpu_memory_mib=metadata['gpu']['memory.total'],
            model_snapshot=config['model_snapshot'], model_revision=config['model_revision'],
            seed=config['seed'], input_tokens=1024, output_tokens=256,
            arrival='infinite-rate finite batch', prefix_cache=False),
            request_timing=[dict(index=i,ttft_ms=result['ttfts'][i]*1000,
                e2e_ms=result['latencies'][i]*1000,client_queue_ms=result['queue_times'][i]*1000)
                for i in range(count)],
            limitations=tail.get('limitations', [
                '64 requests per run: P99 is descriptive, not production tail reliability.',
                'Client queue time is not engine scheduler waiting time.',
                'Historical finite batches do not establish steady-state capacity.']))
        return row
