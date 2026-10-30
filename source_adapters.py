"""Public JSON source adapters; no network activity at import time."""
import datetime
import math
import json
import urllib.parse


def quality_metadata(item):
    """Optional provider hints affect ordering only, never verification acceptance."""
    out={}
    value=item.get('last_checked')
    try:
        if isinstance(value,str):
            stamp=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
            value=stamp.timestamp() if stamp.tzinfo is not None else None
        if isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value) and 0<value<=datetime.datetime.now(datetime.timezone.utc).timestamp()+60:
            out['source_checked_at']=value
    except (ValueError,TypeError,OverflowError): pass
    for key,multiplier in (('latency_ms',1),('latency_s',1000)):
        value=item.get(key)
        if isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value) and value>=0:
            out['source_latency_ms']=value*multiplier
            break
    return out


def parse_payload(source, payload, stats=None):
    data=json.loads(payload)
    items=data.get('proxies') if isinstance(data,dict) else data
    if not isinstance(items,list): raise ValueError('Expected proxies array')
    if stats is not None: stats['raw_records']=stats.get('raw_records',0)+len(items)
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
                             country=country.upper(),source=source,**quality_metadata(item)))
    return rows,blocked


def fetch_source(source, download, stats=None):
    if source=='proxio':
        return parse_payload(source,download(
            'https://raw.githubusercontent.com/proxio-io/proxy-list/main/all.json',
            max_bytes=16000000),stats)
    rows=[];blocked=set()
    for offset in range(0,10000,1000):
        query=urllib.parse.urlencode(dict(request='display_proxies',format='json',
                    proxy_format='protocolipport',limit=1000,skip=offset))
        payload=download('https://api.proxyscrape.com/v4/free-proxy-list/get?'+query,
                         max_bytes=8000000)
        page=json.loads(payload)
        batch,bad=parse_payload(source,payload,stats)
        rows.extend(batch);blocked.update(bad)
        if not page.get('nextpage'): return rows,blocked
    raise ValueError('Source exceeds bounded 10000-record download; refusing partial pool')
