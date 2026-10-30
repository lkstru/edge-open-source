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
from source_adapters import fetch_source, quality_metadata

ROOT = Path(__file__).resolve().parent


def public_endpoint(host, port):
    try:
        ip = ipaddress.ip_address(host)
        return (ip.version == 4 and ip.is_global and not ip.is_multicast
                and not ip.is_reserved and 1 <= int(port) <= 65535)
    except (ValueError, TypeError):
        return False


def download(url, proxy=None, max_bytes=500000, source=False):
    # Source lists get more time; proxy probes keep their existing strict limits.
    connect, total = (10, 45) if source else (5, 12)
    cmd = ['curl', '-q', '--silent', '--show-error', '--fail', '--proto', '=https',
           '--connect-timeout', str(connect), '--max-time', str(total),
           '--max-filesize', str(max_bytes), '--proxy', proxy or '', '--noproxy', '', url]
    for attempt in range(3 if source else 1):
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=total+3)
        except subprocess.TimeoutExpired:
            if source and attempt < 2:
                time.sleep(attempt+1)
                continue
            raise RuntimeError('Source download process timed out' if source else 'Proxy probe timed out')
        if not result.returncode:
            if len(result.stdout) > max_bytes: raise ValueError('Response too large')
            return result.stdout.decode('utf-8')
        stderr = result.stderr.decode(errors='replace').strip()
        transient = result.returncode in (5, 6, 7, 18, 28, 35, 52, 55, 56, 92)
        transient |= result.returncode == 22 and bool(re.search(r'\b(408|429|5\d\d)\b', stderr))
        if source and transient and attempt < 2:
            time.sleep(attempt+1)
            continue
        raise RuntimeError('curl ' + str(result.returncode) + ': ' + stderr[:160])


def download_source(url, max_bytes=500000):
    return download(url, max_bytes=max_bytes, source=True)


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
                                 country=country, source=source, **quality_metadata(row)))
    else:
        for line in text.splitlines():
            match = re.fullmatch(r'(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})', line.strip())
            if match and public_endpoint(*match.groups()):
                rows.append(dict(host=match[1], port=int(match[2]), protocol=protocol,
                                 country=country, source=source))
    return rows, blocked


def collect(country, hproxy_rows=None, extra_rows=(), global_blocked=(), metrics=None):
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
                        else download_source(url))
                rows, bad = parse_source(text, source, country, protocol)
                if metrics is not None and source == 'proxyspace':
                    metrics['raw_records'] = metrics.get('raw_records',0) + len([x for x in text.splitlines() if x.strip()])
                groups.append(rows)
                blocked.update(bad)
            except Exception as exc:
                errors.append(dict(country=country, source=source,
                                   protocol=protocol, error=str(exc),
                                   kind='not_published' if source == 'proxyspace' and
                                   'returned error: 404' in str(exc) else 'error'))
    blocked.update(global_blocked)
    for source in ('proxyscrape', 'proxio'):
        for protocol in ('http', 'socks5'):
            groups.append([r for r in extra_rows if r['country']==country
                           and r['source']==source and r['protocol']==protocol
                           and public_endpoint(r['host'],r['port'])])
    if metrics is not None:
        metrics['eligible'] = {}
        for group in groups:
            for row in group:
                if not public_endpoint(row['host'],row['port']) or (row['host'],str(row['port'])) in blocked: continue
                metrics['eligible'].setdefault(row['source'],set()).add(endpoint_key(row))
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


def endpoint_key(row):
    return f"{row['protocol']}:{row['host']}:{row['port']}"


def history_entry(value):
    return value if isinstance(value,dict) else dict(attempted_at=value if isinstance(value,(int,float)) else 0)


def select_candidates(rows, limit, history):
    groups={}
    for row in rows:
        groups.setdefault((row['source'],row['protocol']),[]).append(row)
    def quality(row):
        h=history_entry(history.get(endpoint_key(row),0))
        successes=h.get('successes',0); failures=h.get('failures',0)
        reliability=(successes+1)/(successes+failures+2)
        return (-reliability, -row.get('source_checked_at',0),
                row.get('source_latency_ms',float('inf')), h.get('attempted_at',0))
    for key,group in groups.items():
        ranked=sorted(group,key=quality)
        explore=sorted(group,key=lambda r:history_entry(history.get(endpoint_key(r),0)).get('attempted_at',0))
        ordered=[];seen=set();qi=ei=0
        while len(ordered)<len(group):
            queue=explore if len(ordered)%4==3 else ranked
            index=ei if queue is explore else qi
            while index<len(queue) and endpoint_key(queue[index]) in seen: index+=1
            if index==len(queue): break
            row=queue[index];ordered.append(row);seen.add(endpoint_key(row))
            if queue is explore: ei=index+1
            else: qi=index+1
        groups[key]=ordered
    selected=[]
    for batch in itertools.zip_longest(*groups.values()):
        selected.extend(r for r in batch if r is not None)
        if len(selected)>=limit: break
    return selected[:limit]


def load_previous(output, countries, blocked):
    # Prefer the last successful publish, not a failed/empty local scan.
    paths=[ROOT/'.published-nodes.json', ROOT/'dist/nodes.json', output/'verified.json']
    for path in paths:
        if not path.exists(): continue
        try:
            data=json.loads(path.read_text())
            items=data.get('nodes',[]) if isinstance(data,dict) else data
            if not isinstance(items,list): raise ValueError('Invalid previous snapshot')
        except (OSError,ValueError):
            continue
        rows=[];seen=set()
        for item in items:
            if not isinstance(item,dict): continue
            if (item.get('country') not in countries or item.get('protocol') not in ('http','socks5')
                    or not public_endpoint(item.get('host'),item.get('port'))): continue
            row={key:item[key] for key in ('country','protocol','host','port')}
            if (row['host'],str(row['port'])) in blocked: continue
            row['source']=item.get('source') if item.get('source') in (
                'hproxy','proxyspace','proxyscrape','proxio') else 'previous'
            row['previous']=True
            key=endpoint_key(row)
            if key not in seen: rows.append(row);seen.add(key)
        return rows
    return []


def new_candidates(rows, previous, limit, history):
    attempted={endpoint_key(row) for row in previous}
    return select_candidates([row for row in rows if endpoint_key(row) not in attempted],limit,history)


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
        if trace.get('loc') != row['country'] or country != row['country']:
            raise ValueError('Country mismatch: ' + str(trace.get('loc')) + '/' + str(country))
        if not trace.get('ip') or not ipaddress.ip_address(trace['ip']).is_global:
            raise ValueError('Missing public exit IP')
        robots = download('https://www.youtube.com/robots.txt', proxy)
        if 'User-agent:' not in robots:
            raise ValueError('Unexpected YouTube robots response')
        return dict(row, verified=True, exit_ip=trace['ip'],
                    checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    test_seconds=round(time.monotonic()-started, 2))
    except Exception as exc:
        return dict(row, verified=False, error=str(exc))


def scan_candidates(pools, previous_results, limit, workers, target=None, check=None):
    """Bounded country rounds; stop deep sampling after enough initial successes."""
    check=check or verify
    queues={country:list(rows[:limit]) for country,rows in pools.items()}
    counts={country:sum(r['country']==country and r['verified'] for r in previous_results)
            for country in queues}
    results=[];attempted=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        while True:
            batch=[]
            for country in sorted(queues,key=lambda c:(counts[c]>0,c)):
                if target is not None and counts[country]>=target: continue
                take=len(queues[country]) if target is None else min(4,target-counts[country])
                batch.extend(queues[country][:take]);del queues[country][:take]
            if not batch: break
            attempted.extend(batch)
            futures=[pool.submit(check,row) for row in batch]
            for future in concurrent.futures.as_completed(futures):
                result=future.result();results.append(result)
                counts[result['country']]+=bool(result['verified'])
                if len(results)%25==0:
                    print(f"Checked {len(results)} new candidates; verified "
                          f"{sum(r['verified'] for r in results)}",flush=True)
    return results,attempted


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
        '# Includes filtered/verified Proxio data: https://proxio.io/ (CC BY 4.0)',
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
    validated_at=min((r['checked_at'] for r in verified),
                     default=report.get('finished_at',report['checked_at']))
    text = config_text(verified, validated_at)
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
                [r for r in verified if r['country']==code], validated_at))
    for asset in (ROOT/'web').iterdir():
        if asset.is_file():
            atomic_write(page/asset.name, asset.read_text())
    atomic_write(page/'subscribe.conf', text)
    atomic_write(page/'nodes.json', json.dumps(dict(
        generated_at=report['checked_at'], finished_at=report.get('finished_at'),
        validated_at=validated_at,
        stale_after_minutes=30, countries=states,
        nodes=[dict({key: row[key] for key in ('country','protocol','host','port','checked_at','test_seconds')},
                    rechecked=row.get('rechecked',False)) for row in verified]), ensure_ascii=False, indent=2)+'\n')
    with (output/'nodes.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['country','protocol','host','port','exit_ip','test_seconds'])
        writer.writeheader()
        writer.writerows({key: row[key] for key in writer.fieldnames} for row in verified)
    return len(verified)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--countries', default='ALL', help='Comma-separated ISO codes, or ALL')
    parser.add_argument('--mode',choices=['daily','deep'],default='daily')
    parser.add_argument('--target',type=int,default=4,help='Deep-mode initial successes per country')
    parser.add_argument('--limit', type=int, default=None, help='Candidates per country (1-100)')
    parser.add_argument('--workers', type=int, default=8, help='Concurrent checks (1-8)')
    parser.add_argument('--output', type=Path, default=ROOT/'output')
    args = parser.parse_args()
    args.limit=args.limit if args.limit is not None else (64 if args.mode=='deep' else 16)
    if not 1<=args.target<=16: parser.error('target must be 1-16')
    codes = set(country_codes())
    countries = sorted(codes) if args.countries.upper() == 'ALL' else list(dict.fromkeys(
        c.strip().upper() for c in args.countries.split(',')))
    if not countries or any(c not in codes for c in countries):
        parser.error('Unknown country code')
    if not 1 <= args.limit <= 100 or not 1 <= args.workers <= 8:
        parser.error('limit must be 1-100; workers must be 1-8')
    report = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  scope='Local Mac HTTPS checks; no iPhone, UDP, DNS leak or playback acceptance',
                  countries=countries, mode=args.mode, target=args.target if args.mode=='deep' else None,
                  source_errors=[], results=[], collected={})
    hproxy_complete=False
    # One bounded HProxy global response avoids hundreds of repeated API requests.
    try:
        query = urllib.parse.urlencode(dict(format='json', protocol='http,socks5',
                                           sort='uptime', min_uptime_pct=70))
        hproxy_rows = download_source('https://hproxy.com/api/proxy-list?'+query, max_bytes=8000000)
        if not isinstance(json.loads(hproxy_rows), list):
            raise ValueError('Expected HProxy JSON array')
        hproxy_complete=True
    except Exception as exc:
        hproxy_rows = '[]'
        report['source_errors'].extend(dict(country=c, source='hproxy', error=str(exc))
                                       for c in countries)
    fetch_metrics={'hproxy':dict(raw_records=len(json.loads(hproxy_rows)),fetch_complete=hproxy_complete),
                   'proxyspace':dict(raw_records=0), 'proxyscrape':{}, 'proxio':{}}
    extra_rows=[]; global_blocked=set()
    for row in json.loads(hproxy_rows):
        if row.get('tls_intercepted') is True:
            global_blocked.add((str(row.get('ip')),str(row.get('port'))))
    for source in ('proxyscrape','proxio'):
        try:
            fetch_metrics[source]['fetch_complete']=False
            rows,bad=fetch_source(source,download_source,fetch_metrics[source])
            fetch_metrics[source]['fetch_complete']=True
            extra_rows.extend(rows);global_blocked.update(bad)
            print(f'{source}: loaded {len(rows)} protocol candidates',flush=True)
        except Exception as error:
            report['source_errors'].extend(dict(country=c,source=source,error=str(error))
                                          for c in countries)
            print(f'{source}: source unavailable: {error}',flush=True)
    history_path=ROOT/'.scan-history.json'
    try:
        history=json.loads(history_path.read_text())
        if not isinstance(history,dict): raise ValueError('Invalid history')
        history={k:v for k,v in history.items() if isinstance(v,(int,float,dict))}
    except (OSError,ValueError): history={}
    print(f'Collecting {len(countries)} countries; source concurrency 4', flush=True)
    collection_metrics={c:{} for c in countries}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(lambda c: collect(c, hproxy_rows, extra_rows, global_blocked,
                                                  collection_metrics[c]), countries))
    previous=load_previous(args.output,set(countries),global_blocked)
    print(f'Checking {len(previous)} previously published nodes (outside new-candidate budget)',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        report['results'].extend(pool.map(verify,previous))
    pools={}
    for country,(rows,errors) in zip(countries,batches):
        report['source_errors'].extend(errors)
        report['collected'][country]=len(rows)
        pools[country]=new_candidates(rows,previous,args.limit,history)
    print(f'Mode {args.mode}: up to {sum(map(len,pools.values()))} new candidates; '
          f'concurrency {args.workers}',flush=True)
    results,jobs=scan_candidates(pools,report['results'],args.limit,args.workers,
                                args.target if args.mode=='deep' else None)
    report['results'].extend(results)
    # A second full HTTPS/country/YouTube check immediately before exporting.
    passing=[(i,r) for i,r in enumerate(report['results']) if r['verified']]
    print(f'Rechecking {len(passing)} initially verified nodes before publication',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        rechecks=list(pool.map(verify,[r for _,r in passing]))
    for (index,initial),result in zip(passing,rechecks):
        result['initial_checked_at']=initial['checked_at']
        result['rechecked']=True
        report['results'][index]=result
    now=time.time()
    for row in report['results']:
        key=endpoint_key(row); old=history_entry(history.get(key,0))
        history[key]=dict(attempted_at=now, successes=old.get('successes',0)+int(row['verified']),
                          failures=old.get('failures',0)+int(not row['verified']))
    history={k:v for k,v in history.items() if now-history_entry(v).get('attempted_at',0)<30*86400}
    atomic_write(history_path,json.dumps(history)+'\n')
    report['source_summary']={source:dict(
        attempted=sum(r['source']==source for r in report['results']),
        verified=sum(r['source']==source and r['verified'] for r in report['results']))
        for source in ('hproxy','proxyspace','proxyscrape','proxio','previous')}
    for source in ('hproxy','proxyspace','proxyscrape','proxio'):
        eligible=set(); unique=set(); covered=set()
        for country,(rows,_) in zip(countries,batches):
            keys=collection_metrics[country].get('eligible',{}).get(source,set())
            eligible.update(keys)
            if keys: covered.add(country)
            unique.update(endpoint_key(r) for r in rows if r['source']==source)
        if source=='proxyspace':
            fetch_metrics[source]['raw_records']=sum(m.get('raw_records',0) for m in collection_metrics.values())
        summary=report['source_summary'][source]
        summary.update(fetch_metrics[source], source_error_count=sum(e['source']==source and e.get('kind')!='not_published' for e in report['source_errors']), eligible_unique=len(eligible),
                       assigned_after_cross_source_dedup=len(unique), countries=len(covered),
                       new_attempted=sum(r['source']==source and not r.get('previous') for r in results),
                       final_verified_new=sum(r['source']==source and not r.get('previous') and r['verified'] for r in report['results']))
        print(f"{source}: raw records {summary.get('raw_records',0)}, eligible unique {len(eligible)}, "
              f"after cross-source dedup {len(unique)}, countries {len(covered)}, "
              f"new tested {summary['new_attempted']}, new passed {summary['final_verified_new']}",flush=True)
    report['source_statistics_scope']='Raw JSON records include all downloaded countries/protocols; ProxySpace raw lines and eligible/dedup counts cover requested countries and HTTP/SOCKS5. Dedup assignment credits the first source only, not exclusive ownership.'
    report['previous_summary']=dict(attempted=len(previous),
        verified=sum(r.get('previous',False) and r['verified'] for r in report['results']))
    report['new_attempted']=len(jobs)
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
