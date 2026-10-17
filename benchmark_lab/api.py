"""Local read-only FastAPI result browser; never launches an inference engine."""
from contextlib import asynccontextmanager
import csv
import io
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .catalog import Catalog, EvidenceError


def create_app(root=None, database=None):
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    catalog = Catalog(root, database or root/'.benchmark/catalog.sqlite3')

    @asynccontextmanager
    async def lifespan(app):
        catalog.rebuild()
        app.state.catalog = catalog
        yield

    app = FastAPI(title='LLM Serving Benchmark Lab', lifespan=lifespan)

    @app.exception_handler(EvidenceError)
    async def invalid_evidence(request, exc):
        return JSONResponse(status_code=409, content=dict(detail=str(exc)))

    @app.exception_handler(KeyError)
    async def not_found(request, exc):
        return JSONResponse(status_code=404, content=dict(detail='Run not found'))

    @app.get('/api/runs')
    def runs(engine: str | None = None, concurrency: int | None = None):
        rows = filtered(engine, concurrency)
        return dict(runs=rows, total=len(rows), requests=sum(r['requests'] for r in rows),
            mode='historical_replay', launches_gpu=False,
            aggregation='Each table row is one original run, not an aggregate across repetitions.')

    @app.get('/api/runs/{run_id}')
    def detail(run_id: str):
        return catalog.detail(run_id)

    @app.get('/api/runs/{run_id}/artifacts/{kind}')
    def artifact(run_id: str, kind: str):
        row = catalog.run(run_id)
        relative = row['artifacts'].get(kind)
        if relative is None:
            raise HTTPException(404, 'Artifact not found')
        data = catalog.read(relative)
        return Response(data, media_type='application/json', headers={
            'Content-Disposition': f'attachment; filename="{Path(relative).name}"'})

    @app.get('/api/export.csv')
    def export(engine: str | None = None, concurrency: int | None = None):
        rows = filtered(engine, concurrency)
        fields = ('id','engine','concurrency','repeat','requests','mean_ttft_ms','mean_tpot_ms',
            'output_tokens_per_s','p50_latency_ms','p95_latency_ms','p99_latency_ms','source_sha256')
        data = io.StringIO(newline='')
        writer = csv.DictWriter(data, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)
        return Response(data.getvalue(), media_type='text/csv', headers={
            'Content-Disposition': 'attachment; filename="benchmark-runs.csv"'})

    def filtered(engine, concurrency):
        try:
            return catalog.runs(engine, concurrency)
        except EvidenceError as exc:
            raise HTTPException(400, str(exc)) from exc

    web = Path(__file__).resolve().parents[1]/'web'
    app.mount('/static', StaticFiles(directory=web), name='static')

    @app.get('/')
    def homepage():
        return FileResponse(web/'index.html')

    return app
