import datetime
import json
from pathlib import Path
import tempfile
import unittest
import collect
import publish

class ScanModes(unittest.TestCase):
    def rows(self,n=64):
        return [dict(country='US',protocol='http',host=f'8.8.8.{i}',port=80,source='proxio') for i in range(1,n+1)]

    def test_deep_stops_at_target_and_counts_old_successes(self):
        check=lambda r:dict(r,verified=True)
        old=[dict(country='US',verified=True) for _ in range(2)]
        results,attempted=collect.scan_candidates({'US':self.rows()},old,64,2,4,check)
        self.assertEqual(len(attempted),2)
        self.assertEqual(len(results),2)

    def test_deep_failures_exhaust_bounded_budget(self):
        results,attempted=collect.scan_candidates({'US':self.rows(80)},[],64,8,4,lambda r:dict(r,verified=False))
        self.assertEqual(len(attempted),64)
        self.assertFalse(any(r['verified'] for r in results))

    def test_daily_keeps_full_new_candidate_budget(self):
        results,attempted=collect.scan_candidates({'US':self.rows()},[],16,8,None,lambda r:dict(r,verified=True))
        self.assertEqual(len(attempted),16)

    def test_fresh_reverification_allows_long_scan_but_not_stale_nodes(self):
        now=datetime.datetime.now(datetime.timezone.utc)
        fresh=now.isoformat();old=(now-datetime.timedelta(hours=3)).isoformat()
        row=dict(self.rows(1)[0],verified=True,rechecked=True,checked_at=fresh,test_seconds=1,exit_ip='8.8.8.8')
        report=dict(checked_at=old,finished_at=fresh,results=[row],countries=['US'],source_errors=[],collected={'US':1})
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);collect.export(out,report)
            self.assertEqual(len(publish.validate(out/'pages')['nodes']),1)
            info=json.loads((out/'pages/nodes.json').read_text())
            info['nodes'][0]['checked_at']=old
            (out/'pages/nodes.json').write_text(json.dumps(info))
            with self.assertRaisesRegex(ValueError,'stale node'):
                publish.validate(out/'pages')

    def test_future_verification_rejected(self):
        now=datetime.datetime.now(datetime.timezone.utc)
        row=dict(self.rows(1)[0],verified=True,rechecked=True,checked_at=(now+datetime.timedelta(hours=1)).isoformat(),test_seconds=1,exit_ip='8.8.8.8')
        report=dict(checked_at=now.isoformat(),results=[row],countries=['US'],source_errors=[],collected={'US':1})
        with tempfile.TemporaryDirectory() as d:
            collect.export(Path(d),report)
            with self.assertRaisesRegex(ValueError,'stale'):
                publish.validate(Path(d)/'pages')

if __name__=='__main__': unittest.main()
