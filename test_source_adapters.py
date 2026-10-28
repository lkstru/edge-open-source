import json
import unittest
from unittest.mock import patch
import collect
from source_adapters import parse_payload

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

if __name__=='__main__': unittest.main()
