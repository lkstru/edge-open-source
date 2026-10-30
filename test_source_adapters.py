import json
import unittest
from unittest.mock import patch
import collect
from source_adapters import parse_payload, quality_metadata, fetch_source
from types import SimpleNamespace
from pathlib import Path
import tempfile
import contextlib
import io

class NewSources(unittest.TestCase):
    def test_proxio_connect_mapping_and_block_signal(self):
        rows,blocked=parse_payload('proxio',json.dumps({'proxies':[
            dict(ip='8.8.8.8',port=80,code='US',protocols=['HTTPS','SOCKS5','SOCKS4']),
            dict(ip='1.1.1.1',port=80,code='US',protocols=['HTTP'],tls_intercepted=True)]}))
        self.assertEqual([r['protocol'] for r in rows],['http','socks5'])
        self.assertIn(('1.1.1.1','80'),blocked)

    def test_proxyscrape_requires_alive_and_explicit_protocol(self):
        base=dict(ip='8.8.8.8',port=80,alive=True,protocol='http',ip_data={'countryCode':'US'})
        rows,_=parse_payload('proxyscrape',json.dumps({'proxies':[
            base,dict(base,alive=False),dict(base,protocol='https')]}))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['country'],'US')

    def test_balanced_total_budget_and_history_rotation(self):
        rows=[dict(source=s,protocol='http',host=f'8.8.{i}.{j}',port=80)
              for i,s in enumerate(['hproxy','proxio','proxyscrape'],1) for j in range(1,11)]
        first=collect.select_candidates(rows,16,{})
        self.assertEqual(len(first),16)
        self.assertEqual({r['source'] for r in first},{'hproxy','proxio','proxyscrape'})
        second=collect.select_candidates(rows,16,{collect.endpoint_key(r):1 for r in first})
        self.assertGreater(len({collect.endpoint_key(r) for r in first+second}),16)

    def test_global_interception_and_private_addresses_removed(self):
        extra=[dict(source='proxio',country='US',protocol='http',host=h,port=80)
               for h in ['1.1.1.1','10.0.0.1','8.8.8.8']]
        with patch.object(collect,'download',return_value='8.8.8.8:80'):
            rows,_=collect.collect('US','[]',extra,{('1.1.1.1','80')})
        self.assertEqual(len(rows),2) # one HTTP and one SOCKS5 entry from TXT fixtures
        self.assertTrue(all(r['host']=='8.8.8.8' for r in rows))

class ScanImprovements(unittest.TestCase):
    def test_source_timeout_retries_but_probe_and_404_do_not(self):
        timeout=SimpleNamespace(returncode=28,stderr=b'timed out',stdout=b'')
        success=SimpleNamespace(returncode=0,stderr=b'',stdout=b'fresh list')
        with patch.object(collect.subprocess,'run',side_effect=[timeout,success]) as run, patch.object(collect.time,'sleep'):
            self.assertEqual(collect.download_source('https://example.com/list'),'fresh list')
            self.assertEqual(run.call_count,2)
            self.assertIn('45',run.call_args.args[0])
        for source,result in [(False,timeout),(True,SimpleNamespace(returncode=22,stderr=b'HTTP error: 404',stdout=b''))]:
            with patch.object(collect.subprocess,'run',return_value=result) as run:
                with self.assertRaises(RuntimeError): collect.download('https://example.com/list',source=source)
                self.assertEqual(run.call_count,1)
        with patch.object(collect.subprocess,'run',return_value=timeout) as run, patch.object(collect.time,'sleep'):
            with self.assertRaises(RuntimeError): collect.download_source('https://example.com/list')
            self.assertEqual(run.call_count,3)

    def test_quality_hints_do_not_eliminate_exploration(self):
        rows=[dict(source='proxio',protocol='http',host=f'8.8.8.{i}',port=80,
                   source_checked_at=i,source_latency_ms=100-i) for i in range(1,9)]
        history={collect.endpoint_key(rows[7]):dict(attempted_at=10,successes=0,failures=20)}
        chosen=collect.select_candidates(rows,4,history)
        self.assertEqual(chosen[0]['host'],'8.8.8.7')
        self.assertEqual(chosen[3]['host'],'8.8.8.1')
        self.assertEqual(len({collect.endpoint_key(r) for r in collect.select_candidates(rows,8,history)}),8)
        self.assertEqual(quality_metadata(dict(last_checked='invalid',latency_ms=float('nan'))),{})
        self.assertEqual(quality_metadata(dict(latency_s=0.5))['source_latency_ms'],500)

    def test_statistics_distinguish_raw_records_and_unique_candidates(self):
        payload=json.dumps({'proxies':[
            dict(ip='8.8.8.8',port=80,code='US',protocols=['HTTP']),
            dict(ip='8.8.8.8',port=80,code='US',protocols=['HTTP']),
            dict(ip='10.0.0.1',port=80,code='US',protocols=['HTTP']),
            dict(ip='1.1.1.1',port=80,code='US',protocols=['SOCKS4'])]})
        stats={}
        rows,_=fetch_source('proxio',lambda *a,**kw:payload,stats)
        metrics={}
        with patch.object(collect,'download_source',return_value='8.8.8.8:80\n8.8.8.8:80'):
            merged,errors=collect.collect('US','[]',rows,(),metrics)
        self.assertFalse(errors)
        self.assertEqual(stats['raw_records'],4)
        self.assertEqual(len(metrics['eligible']['proxio']),1)
        self.assertEqual(metrics['raw_records'],4) # two protocol files, each two lines
        self.assertEqual(len(merged),2) # HTTP and SOCKS5, cross-source duplicates removed

    def test_main_reports_source_counts_and_migrates_numeric_history(self):
        def fake_download(url,**kwargs):
            if 'hproxy.com' in url:
                return json.dumps([dict(ip='8.8.8.8',port=80,country_code='US',status='alive',protocols=['http'])])
            if 'proxyscrape.com' in url:
                return json.dumps(dict(proxies=[dict(ip='9.9.9.9',port=80,alive=True,protocol='http',ip_data={'countryCode':'US'})]))
            if 'githubusercontent.com' in url:
                return json.dumps(dict(proxies=[dict(ip='1.1.1.1',port=80,code='US',protocols=['HTTP'])]))
            return ''
        def good(row):
            return dict(row,verified=True,checked_at='2026-10-30T00:00:00+00:00',test_seconds=1)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'.scan-history.json').write_text('{"http:8.8.8.8:80":1}')
            with patch.object(collect,'ROOT',root), patch.object(collect,'country_codes',return_value=['US']), patch.object(collect,'download_source',side_effect=fake_download), patch.object(collect,'verify',side_effect=good), patch.object(collect,'export',return_value=3) as export, patch('sys.argv',['collect.py','--output',str(root/'output')]), contextlib.redirect_stdout(io.StringIO()):
                collect.main()
            report=export.call_args.args[1]
            self.assertEqual(report['new_attempted'],3)
            self.assertEqual(report['source_summary']['proxio']['raw_records'],1)
            self.assertEqual(report['source_summary']['proxio']['eligible_unique'],1)
            self.assertEqual(report['source_summary']['proxio']['countries'],1)
            self.assertEqual(report['source_summary']['proxio']['final_verified_new'],1)
            history=json.loads((root/'.scan-history.json').read_text())
            self.assertEqual(history['http:8.8.8.8:80']['successes'],1)

if __name__=='__main__': unittest.main()
