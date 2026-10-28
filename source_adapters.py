"""Public JSON source adapters; no network activity at import time."""
import json
import urllib.parse


def parse_payload(source, payload):
    data=json.loads(payload)
    items=data.get('proxies') if isinstance(data,dict) else data
    if not isinstance(items,list): raise ValueError('Expected proxies array')
    rows=[]; blocked=set()
    for item in items:
        if not isinstance(item,dict): continue
        host=item.get('ip'); port=item.get('port')
        try: port=int(port)
        except (ValueError,TypeError): continue
        if item.get('tls_intercepted') is True:
            blocked.add((str(host),str(port))); continue
        if source=='proxyscrape':
            if item.get('alive') is not True: continue
            country=(item.get('ip_data') or {}).get('countryCode')
            protocols=[item.get('protocol')]
        elif source=='proxio':
            country=item.get('code')
            protocols=item.get('protocols') or []
        else: raise ValueError('Unknown source')
        if not isinstance(country,str): continue
        for protocol in protocols:
            if not isinstance(protocol,str): continue
            protocol=protocol.lower()
            # Proxio explicitly defines HTTPS as HTTP CONNECT, not TLS-to-proxy.
            if source=='proxio' and protocol=='https': protocol='http'
            if protocol not in ('http','socks5'): continue
            rows.append(dict(host=host,port=port,protocol=protocol,
                             country=country.upper(),source=source))
    return rows,blocked


def fetch_source(source, download):
    if source=='proxio':
        return parse_payload(source,download(
            'https://raw.githubusercontent.com/proxio-io/proxy-list/main/all.json',
            max_bytes=16000000))
    rows=[];blocked=set()
    for offset in range(0,10000,1000):
        query=urllib.parse.urlencode(dict(request='display_proxies',format='json',
                    proxy_format='protocolipport',limit=1000,skip=offset))
        payload=download('https://api.proxyscrape.com/v4/free-proxy-list/get?'+query,
                         max_bytes=8000000)
        page=json.loads(payload)
        batch,bad=parse_payload(source,payload)
        rows.extend(batch);blocked.update(bad)
        if not page.get('nextpage'): return rows,blocked
    raise ValueError('Source exceeds bounded 10000-record download; refusing partial pool')
