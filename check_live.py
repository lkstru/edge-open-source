#!/usr/bin/env python3
"""Compare a deployed HTTPS Pages site with the local dist/ snapshot."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
FILES = [
    ('/', 'index.html'),
    ('/nodes.json', 'nodes.json'),
    ('/subscribe.conf', 'subscribe.conf'),
    ('/app.js', 'app.js'),
    ('/style.css', 'style.css'),
]


def fetch(base, route):
    with tempfile.TemporaryDirectory() as directory:
        body_path = Path(directory) / 'body'
        headers_path = Path(directory) / 'headers'
        result = subprocess.run([
            'curl', '-q', '--proxy', '', '--noproxy', '*', '--silent', '--show-error',
            '--max-time', '25', '--proto', '=https', '--dump-header', str(headers_path),
            '--output', str(body_path), '--write-out', '%{http_code}', base + route,
        ], capture_output=True, check=True)
        return int(result.stdout), headers_path.read_text(), body_path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', help='HTTPS Pages deployment URL to verify')
    args = parser.parse_args()
    if not args.url.startswith('https://'):
        parser.error('url must use HTTPS')
    for route, relative in FILES:
        status, headers, body = fetch(args.url.rstrip('/'), route)
        if status != 200:
            raise SystemExit(f'{route}: expected HTTP 200, received {status}')
        if body != (ROOT / 'dist' / relative).read_bytes():
            raise SystemExit(f'{route}: deployed bytes differ from dist/{relative}')
        lowered = headers.lower()
        if 'x-content-type-options: nosniff' not in lowered:
            raise SystemExit(f'{route}: missing X-Content-Type-Options: nosniff')
        if "default-src 'self'" not in lowered:
            raise SystemExit(f'{route}: missing expected Content-Security-Policy')
        print(f'OK {route}: HTTP 200, byte-for-byte match, security headers present')


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as error:
        print(f'Verification failed: {error}', file=sys.stderr)
        raise SystemExit(1)
