"""Rebuildable SQLite index of hash-verified historical runs. No GPU or subprocesses."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from lab import validate
from tail_report import percentile, summarize

from . import vllm_import


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
            record = dict(id=run_id, kind='baseline', engine=metadata['engine'], concurrency=concurrency,
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
        records += self.imported_records(expected)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            # The index is disposable; recreate it so schema changes never need migration.
            con.execute('DROP TABLE IF EXISTS runs')
            con.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, engine TEXT NOT NULL, concurrency INTEGER, repeat INTEGER, payload TEXT NOT NULL)')
            con.executemany('INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)',
                [(r['id'], r['kind'], r['engine'], r['concurrency'], r['repeat'], json.dumps(r)) for r in records])
        return len(records)

    def imported_records(self, baseline):
        """Re-hash and re-inspect every imported result; provenance claims are not trusted."""
        manifest = vllm_import.load_manifest(self.root)
        if set(manifest) & set(baseline):
            raise EvidenceError('Import manifest overlaps the baseline manifest')
        self.expected = {**baseline, **manifest}
        records = []
        for relative in sorted(manifest):
            match = re.fullmatch(r'imports/(imp-[0-9a-f]{16})/result\.json', relative)
            if not match:
                continue
            provenance_path = relative.rsplit('/', 1)[0] + '/provenance.json'
            provenance = self.load(provenance_path)
            result = self.load(relative)
            if provenance.get('sha256') != manifest[relative] or provenance.get('id') != match[1]:
                raise EvidenceError('Provenance does not describe ' + relative)
            try:
                level, checks = vllm_import.inspect(result)
            except vllm_import.ImportRejected as exc:
                raise EvidenceError('Imported run no longer passes checks: ' + str(exc)) from exc
            latencies = result['latencies']
            records.append(dict(id=match[1], kind='imported', engine=provenance['declared']['engine'],
                concurrency=result.get('max_concurrency'), repeat=None, requests=result['completed'],
                status='imported_' + level, label=provenance['declared'].get('label'), detail_level=level,
                mean_ttft_ms=result['mean_ttft_ms'], mean_tpot_ms=result['mean_tpot_ms'],
                output_tokens_per_s=result['output_throughput'],
                **{f'p{p}_latency_ms': percentile(latencies, p) * 1000 for p in (50, 95, 99)},
                source=relative, source_sha256=manifest[relative],
                artifacts=dict(result=relative, provenance=provenance_path)))
        return records

    def runs(self, engine=None, concurrency=None, kind=None):
        if engine is not None and engine not in ('vllm', 'sglang'):
            raise EvidenceError('Unsupported engine filter')
        if concurrency is not None and (type(concurrency) is not int or concurrency <= 0):
            raise EvidenceError('Unsupported concurrency filter')
        if kind is not None and kind not in ('baseline', 'imported'):
            raise EvidenceError('Unsupported source filter')
        query = 'SELECT payload FROM runs WHERE 1=1'
        params = []
        if engine is not None:
            query += ' AND engine=?'; params.append(engine)
        if concurrency is not None:
            query += ' AND concurrency=?'; params.append(concurrency)
        if kind is not None:
            query += ' AND kind=?'; params.append(kind)
        query += ' ORDER BY kind, engine DESC, concurrency, repeat, id'
        with self.connect() as con:
            return [json.loads(row[0]) for row in con.execute(query, params)]

    def run(self, run_id):
        with self.connect() as con:
            row = con.execute('SELECT payload FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def imported_detail(self, row):
        result = self.load(row['source'])
        provenance = self.load(row['artifacts']['provenance'])
        count = result['completed']
        timing = None
        if row['detail_level'] == 'detailed':
            tails = summarize(result, count)['tails_ms']
            timing = [dict(index=i, ttft_ms=result['ttfts'][i]*1000, e2e_ms=result['latencies'][i]*1000,
                client_queue_ms=result['queue_times'][i]*1000) for i in range(count)]
        else:
            tails = dict(latencies={str(p): percentile(result['latencies'], p) * 1000 for p in (50, 95, 99)})
        limitations = list(provenance.get('limitations', []))
        limitations.append(f'{count} requests: P99 is descriptive, not production tail reliability.')
        row.update(tails=tails, request_timing=timing, provenance=dict(
            source_name=provenance['source_name'], imported_utc=provenance['imported_utc'],
            checks=provenance['checks'], reported=provenance['reported']), limitations=limitations)
        return row

    def detail(self, run_id):
        row = self.run(run_id)
        if row['kind'] == 'imported':
            return self.imported_detail(row)
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
