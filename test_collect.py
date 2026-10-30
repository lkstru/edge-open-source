import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import collect


class CollectorTests(unittest.TestCase):
    def test_reject_private_and_invalid_endpoints(self):
        for host, port in [('127.0.0.1',80),('10.0.0.1',80),('169.254.169.254',80),
                           ('224.0.0.1',80),('8.8.8.8',0),('8.8.8.8',65536)]:
            self.assertFalse(collect.public_endpoint(host, port))

    def test_hproxy_filters_and_cross_source_interception(self):
        base = dict(ip='8.8.8.8',port=80,country_code='US',status='alive',protocols=['http'])
        payload = json.dumps([base,dict(base,ip='1.1.1.1',tls_intercepted=True),
                              dict(base,country_code='DE'),dict(base,status='offline')])
        rows, blocked = collect.parse_source(payload,'hproxy','US','http')
        self.assertEqual(len(rows),1)
        self.assertIn(('1.1.1.1','80'), blocked)
        def source(url, **kwargs):
            return payload if 'hproxy.com' in url else '1.1.1.1:80\n8.8.8.8:80'
        with patch.object(collect,'download',source):
            merged, errors = collect.collect('US')
        self.assertFalse(errors)
        self.assertTrue(all(r['host']!='1.1.1.1' for r in merged))
        self.assertEqual(len({(r['protocol'],r['host'],r['port']) for r in merged}),len(merged))

    def test_country_mismatch_not_exported(self):
        row=dict(host='8.8.8.8',port=80,protocol='http',country='US')
        with patch.object(collect,'download',side_effect=['loc=US\nip=8.8.8.8',
                                                         '{"country_code":"DE"}']):
            result=collect.verify(row)
        self.assertFalse(result['verified'])

    def test_empty_refresh_replaces_stale_exports_without_direct_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            (output/'shadowrocket.conf').write_text('old node')
            collect.export(output,dict(checked_at='test',results=[],countries=['US'],
                                       source_errors=[],collected={'US':0}))
            text=(output/'shadowrocket.conf').read_text()
            self.assertNotIn('old node',text)
            self.assertNotIn('DIRECT',text)
            self.assertIn('GLOBAL-EXIT = select, REJECT',text)
            self.assertEqual(json.loads((output/'verified.json').read_text()),[])

    def test_global_visibility_and_failed_refresh_removes_country_download(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            row=dict(host='8.8.8.8',port=80,protocol='http',country='US',
                     verified=True,checked_at='test',test_seconds=1,exit_ip='8.8.8.8')
            report=dict(checked_at='test',results=[row],countries=['US'],
                        source_errors=[],collected={'US':1})
            collect.export(output,report)
            data=json.loads((output/'pages/nodes.json').read_text())
            self.assertEqual(len(data['countries']),249)
            self.assertEqual(data['countries']['US']['state'],'verified')
            self.assertEqual(data['countries']['JP']['state'],'not_checked')
            self.assertTrue((output/'pages/countries/US.conf').exists())
            self.assertIn('udp-relay=false',(output/'pages/subscribe.conf').read_text())
            failed=dict(row,verified=False,error='TLS certificate failed')
            collect.export(output,dict(report,results=[failed]))
            self.assertFalse((output/'pages/countries/US.conf').exists())
            self.assertNotIn('8.8.8.8',(output/'pages/subscribe.conf').read_text())
            self.assertEqual(json.loads((output/'pages/nodes.json').read_text())
                             ['countries']['US']['state'],'failed')

    def test_tls_failure_never_falls_back_to_direct(self):
        row=dict(host='8.8.8.8',port=80,protocol='socks5',country='US')
        with patch.object(collect,'download',side_effect=RuntimeError('TLS failure')) as fetch:
            result=collect.verify(row)
        self.assertFalse(result['verified'])
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(fetch.call_args.args[1],'socks5h://8.8.8.8:80')


if __name__ == '__main__':
    unittest.main()
