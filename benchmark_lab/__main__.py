import argparse
import socket
import sys
import uvicorn
from .api import create_app

DEFAULT_PORT = 8765


def bindable(port):
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', port))
            return sock.getsockname()[1]
        except OSError:
            return None


parser = argparse.ArgumentParser(description='Browse verified historical results; no GPU required')
parser.add_argument('--port', type=int, default=None,
    help=f'default {DEFAULT_PORT}; if it is reserved or busy, a free local port is chosen')
args = parser.parse_args()
port = bindable(args.port if args.port is not None else DEFAULT_PORT)
if port is None and args.port is not None:
    sys.exit(f'Port {args.port} is busy or reserved (Windows/Hyper-V may exclude port ranges). '
             'Choose another --port or omit it for automatic selection.')
if port is None:
    # e.g. Windows reserves dynamic ranges such as 8752-8851 for Hyper-V/WSL.
    port = bindable(0)
print(f'Open http://127.0.0.1:{port} - historical results, no GPU required. Ctrl+C stops the server.', flush=True)
uvicorn.run(create_app(), host='127.0.0.1', port=port)
