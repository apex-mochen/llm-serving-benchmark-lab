import argparse
import json
from pathlib import Path
import socket
import sys

DEFAULT_PORT = 8765
ROOT = Path(__file__).resolve().parents[1]


def bindable(port):
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', port))
            return sock.getsockname()[1]
        except OSError:
            return None


def import_command(argv):
    from .vllm_import import ImportRejected, import_file
    parser = argparse.ArgumentParser(prog='python -m benchmark_lab import-vllm',
        description='Import `vllm bench serve --save-result` JSON (use --save-detailed for per-request checks). '
                    'The source file is copied unchanged and never edited.')
    parser.add_argument('result', type=Path)
    parser.add_argument('--engine', required=True, choices=('vllm', 'sglang'),
        help='server that was benchmarked; recorded as declared, not detected')
    parser.add_argument('--label', help='short note shown in the browser')
    args = parser.parse_args(argv)
    try:
        outcome = import_file(ROOT, args.result, args.engine, args.label)
    except ImportRejected as exc:
        sys.exit('Rejected: ' + str(exc))
    print(json.dumps(outcome, indent=2, ensure_ascii=False))


def serve(argv):
    import uvicorn
    from .api import create_app
    parser = argparse.ArgumentParser(description='Browse verified historical results; no GPU required. '
                                                 'Subcommand: import-vllm FILE --engine vllm')
    parser.add_argument('--port', type=int, default=None,
        help=f'default {DEFAULT_PORT}; if it is reserved or busy, a free local port is chosen')
    args = parser.parse_args(argv)
    port = bindable(args.port if args.port is not None else DEFAULT_PORT)
    if port is None and args.port is not None:
        sys.exit(f'Port {args.port} is busy or reserved (Windows/Hyper-V may exclude port ranges). '
                 'Choose another --port or omit it for automatic selection.')
    if port is None:
        # e.g. Windows reserves dynamic ranges such as 8752-8851 for Hyper-V/WSL.
        port = bindable(0)
    print(f'Open http://127.0.0.1:{port} - historical results, no GPU required. Ctrl+C stops the server.', flush=True)
    uvicorn.run(create_app(), host='127.0.0.1', port=port)


if sys.argv[1:2] == ['import-vllm']:
    import_command(sys.argv[2:])
else:
    serve(sys.argv[1:])
