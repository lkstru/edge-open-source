#!/usr/bin/env python3
"""Bounded, local-only public proxy collection and HTTPS verification."""
import argparse
import concurrent.futures
import csv
import fcntl
import datetime
import ipaddress
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.parse

ROOT = Path(__file__).resolve().parent


def public_endpoint(host, port):
    try:
        ip = ipaddress.ip_address(host)
        return (ip.version == 4 and ip.is_global and not ip.is_multicast
                and not ip.is_reserved and 1 <= int(port) <= 65535)
    except (ValueError, TypeError):
        return False


def download(url, proxy=None, max_bytes=500000):
    # -q ignores ~/.curlrc, explicit proxy ignores ambient proxy configuration.
    cmd = ['curl', '-q', '--silent', '--show-error', '--fail', '--proto', '=https',
           '--connect-timeout', '5', '--max-time', '12', '--max-filesize', str(max_bytes),
           '--proxy', proxy or '', '--noproxy', '', url]
    result = subprocess.run(cmd, capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError('curl ' + str(result.returncode) + ': ' +
                           result.stderr.decode(errors='replace').strip()[:160])
    if len(result.stdout) > max_bytes:
        raise ValueError('Response too large')
    return result.stdout.decode('utf-8')


def parse_source(text, source, country, protocol):
    rows, blocked = [], set()
    if source == 'hproxy':
        items = json.loads(text)
        if not isinstance(items, list):
            raise ValueError('Expected HProxy JSON array')
        for row in items:
            if not isinstance(row, dict):
                continue
            if row.get('tls_intercepted') is True:
                blocked.add((str(row.get('ip')), str(row.get('port'))))
            if (row.get('country_code') != country or row.get('status') != 'alive'
                    or protocol not in (row.get('protocols') or [])
                    or row.get('tls_intercepted') is True):
                continue
            host, port = row.get('ip'), row.get('port')
            if public_endpoint(host, port):
                rows.append(dict(host=host, port=int(port), protocol=protocol,
                                 country=country, source=source))
    else:
        for line in text.splitlines():
            match = re.fullmatch(r'(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})', line.strip())
            if match and public_endpoint(*match.groups()):
                rows.append(dict(host=match[1], port=int(match[2]), protocol=protocol,
                                 country=country, source=source))
    return rows, blocked


def collect(country, hproxy_rows=None):
    groups, blocked, errors = [], set(), []
    for source in ('hproxy', 'proxyspace'):
        for protocol in ('http', 'socks5'):
            if source == 'proxyspace':
                url = f'https://proxyspace.pro/country/{country.lower()}/{protocol}.txt'
            else:
                query = urllib.parse.urlencode(dict(format='json', country=country,
                    protocol=protocol, limit=200, sort='uptime', min_uptime_pct=70))
                url = 'https://hproxy.com/api/proxy-list?' + query
            try:
                text = (hproxy_rows if source == 'hproxy' and hproxy_rows is not None
                        else download(url))
                rows, bad = parse_source(text, source, country, protocol)
                groups.append(rows)
                blocked.update(bad)
            except Exception as exc:
                errors.append(dict(country=country, source=source,
                                   protocol=protocol, error=str(exc),
                                   kind='not_published' if source == 'proxyspace' and
                                   'returned error: 404' in str(exc) else 'error'))
    seen, rows = set(), []
    for batch in itertools.zip_longest(*groups):
        for row in batch:
            if not row:
                continue
            key = (row['protocol'], row['host'], row['port'])
            if (row['host'], str(row['port'])) in blocked or key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows, errors


def verify(row):
    started = time.monotonic()
    scheme = 'socks5h' if row['protocol'] == 'socks5' else 'http'
    proxy = f"{scheme}://{row['host']}:{row['port']}"
    try:
        trace = dict(line.split('=', 1) for line in download(
            'https://www.cloudflare.com/cdn-cgi/trace', proxy).splitlines() if '=' in line)
        geo = json.loads(download('https://geo.proxyspace.pro/ip', proxy))
        # Provider contract: inspect only documented country/IP fields.
        country = geo.get('country_code') or geo.get('country')
        geo_ip = geo.get('ip')
        if trace.get('loc') != row['country'] or country != row['country']:
            raise ValueError('Country mismatch: ' + str(trace.get('loc')) + '/' + str(country))
        if not trace.get('ip') or not ipaddress.ip_address(trace['ip']).is_global:
            raise ValueError('Missing public exit IP')
        if not geo_ip or ipaddress.ip_address(geo_ip) != ipaddress.ip_address(trace['ip']):
            raise ValueError('Exit IP mismatch between verification services')
        robots = download('https://www.youtube.com/robots.txt', proxy)
        if 'User-agent:' not in robots:
            raise ValueError('Unexpected YouTube robots response')
        return dict(row, verified=True, exit_ip=trace['ip'],
                    checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    test_seconds=round(time.monotonic()-started, 2))
    except Exception as exc:
        return dict(row, verified=False, error=str(exc))


def atomic_write(path, content):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     delete=False) as f:
        f.write(content)
        temporary = f.name
    os.replace(temporary, path)


def country_codes():
    return json.loads((ROOT/'countries.json').read_text())


def config_text(verified, generated):
    groups = {}
    lines = ['# LKSTRU Edge: client connects directly to public proxies.',
        '# Checked on Mac: ' + generated, '# No guarantee of continuing availability.',
        '[General]', 'ipv6 = false', 'udp-policy-not-supported-behaviour = REJECT',
        '', '[Proxy]']
    for row in verified:
        name = f"{row['country']}-{row['protocol']}-{row['host'].replace('.', '-')}-{row['port']}"
        groups.setdefault(row['country'], []).append(name)
        lines.append(f"{name} = {row['protocol']}, {row['host']}, {row['port']}, , , udp-relay=false")
    lines += ['', '[Proxy Group]']
    for country, names in sorted(groups.items()):
        lines.append(f"{country}-EXIT = select, " + ', '.join(names))
    lines.append('GLOBAL-EXIT = select, ' + ', '.join(
        [country+'-EXIT' for country in sorted(groups)] or ['REJECT']))
    lines += ['', '[Rule]', 'FINAL,GLOBAL-EXIT', '']
    return '\n'.join(lines)


def export(output, report):
    output.mkdir(parents=True, exist_ok=True)
    verified = sorted([r for r in report['results'] if r['verified']],
                      key=lambda r:(r['country'], r['test_seconds']))
    text = config_text(verified, report['checked_at'])
    atomic_write(output/'shadowrocket.conf', text)
    atomic_write(output/'report.json', json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    atomic_write(output/'verified.json', json.dumps(verified, indent=2)+'\n')
    page = output/'pages'
    page.mkdir(parents=True, exist_ok=True)
    per_country = page/'countries'
    per_country.mkdir(exist_ok=True)
    # Remove country exports from the previous run, including newly failed countries.
    for old in per_country.glob('*.conf'):
        old.unlink()
    counts = {}
    for row in verified:
        counts[row['country']] = counts.get(row['country'], 0) + 1
    states = {}
    for code in country_codes():
        count = counts.get(code, 0)
        tested = sum(r['country']==code for r in report['results'])
        state = ('verified' if count else 'not_checked' if code not in report['countries']
                 else 'failed' if tested else 'source_error' if any(
                     e['country']==code for e in report['source_errors']) else 'no_candidates')
        states[code] = dict(state=state, verified=count, tested=tested,
                           candidates=report['collected'].get(code, 0))
        if count:
            atomic_write(per_country/(code+'.conf'), config_text(
                [r for r in verified if r['country']==code], report['checked_at']))
    for asset in (ROOT/'web').iterdir():
        if asset.is_file():
            atomic_write(page/asset.name, asset.read_text())
    atomic_write(page/'subscribe.conf', text)
    atomic_write(page/'nodes.json', json.dumps(dict(
        generated_at=report['checked_at'], finished_at=report.get('finished_at'),
        stale_after_minutes=30, countries=states,
        nodes=[{key: row[key] for key in ('country','protocol','host','port','checked_at','test_seconds')}
               for row in verified]), ensure_ascii=False, indent=2)+'\n')
    with (output/'nodes.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['country','protocol','host','port','exit_ip','test_seconds'])
        writer.writeheader()
        writer.writerows({key: row[key] for key in writer.fieldnames} for row in verified)
    return len(verified)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--countries', default='ALL', help='Comma-separated ISO codes, or ALL')
    parser.add_argument('--limit', type=int, default=8, help='Candidates per country (1-100)')
    parser.add_argument('--workers', type=int, default=8, help='Concurrent checks (1-8)')
    parser.add_argument('--output', type=Path, default=ROOT/'output')
    args = parser.parse_args()
    codes = set(country_codes())
    countries = sorted(codes) if args.countries.upper() == 'ALL' else list(dict.fromkeys(
        c.strip().upper() for c in args.countries.split(',')))
    if not countries or any(c not in codes for c in countries):
        parser.error('Unknown country code')
    if not 1 <= args.limit <= 100 or not 1 <= args.workers <= 8:
        parser.error('limit must be 1-100; workers must be 1-8')
    report = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  scope='Local Mac HTTPS checks; no iPhone, UDP, DNS leak or playback acceptance',
                  countries=countries, source_errors=[], results=[], collected={})
    # One bounded HProxy global response avoids hundreds of repeated API requests.
    try:
        query = urllib.parse.urlencode(dict(format='json', protocol='http,socks5',
                                           sort='uptime', min_uptime_pct=70))
        hproxy_rows = download('https://hproxy.com/api/proxy-list?'+query, max_bytes=8000000)
        if not isinstance(json.loads(hproxy_rows), list):
            raise ValueError('Expected HProxy JSON array')
    except Exception as exc:
        hproxy_rows = '[]'
        report['source_errors'].extend(dict(country=c, source='hproxy', error=str(exc))
                                       for c in countries)
    print(f'Collecting {len(countries)} countries; source concurrency 4', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(lambda c: collect(c, hproxy_rows), countries))
    jobs = []
    for country, (rows, errors) in zip(countries, batches):
        report['source_errors'].extend(errors)
        report['collected'][country] = len(rows)
        jobs.extend(rows[:args.limit])
    print(f'Checking {len(jobs)} candidates, concurrency {args.workers}', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(verify, row) for row in jobs]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            report['results'].append(future.result())
            if index % 25 == 0 or index == len(jobs):
                print(f"Checked {index}/{len(jobs)}; verified " +
                      str(sum(r['verified'] for r in report['results'])), flush=True)
    report['unpublished_lists'] = [e for e in report['source_errors']
                                   if e.get('kind') == 'not_published']
    report['source_errors'] = [e for e in report['source_errors']
                               if e.get('kind') != 'not_published']
    report['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    count = export(args.output, report)
    print(f'Exported {count} nodes to {args.output}; static Pages bundle: {args.output}/pages', flush=True)


if __name__ == '__main__':
    with (ROOT/'.collect.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another collection is running.')
        main()
