import datetime
import json
from pathlib import Path
import tempfile
import unittest
import collect
import publish

class PublishTests(unittest.TestCase):
    def snapshot(self,folder):
        collect.export(Path(folder),dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       results=[],countries=['US'],source_errors=[],collected={'US':0}))
        return Path(folder)/'pages'

    def test_only_static_snapshot_can_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            page=self.snapshot(folder)
            self.assertEqual(len(publish.validate(page)['countries']),249)
            (page/'_worker.js').write_text('unexpected worker')
            with self.assertRaisesRegex(ValueError,'Unexpected files'):
                publish.validate(page)

    def test_nonempty_snapshot_requires_second_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            row=dict(host='8.8.8.8',port=80,protocol='http',country='US',
                     verified=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),test_seconds=1,exit_ip='8.8.8.8')
            report=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        results=[row],countries=['US'],source_errors=[],collected={'US':1})
            collect.export(Path(folder),report)
            with self.assertRaisesRegex(ValueError,'second verification'):
                publish.validate(Path(folder)/'pages')
            row['rechecked']=True
            collect.export(Path(folder),report)
            self.assertEqual(len(publish.validate(Path(folder)/'pages')['nodes']),1)

    def test_stale_snapshot_cannot_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            page=self.snapshot(folder)
            info=json.loads((page/'nodes.json').read_text())
            info['generated_at']='2020-01-01T00:00:00+00:00'
            info['validated_at']=info['generated_at']
            (page/'nodes.json').write_text(json.dumps(info))
            with self.assertRaisesRegex(ValueError,'stale'):
                publish.validate(page)

    def test_unverified_subscription_changes_cannot_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            page=self.snapshot(folder)
            with (page/'subscribe.conf').open('a') as f:f.write('FINAL,DIRECT')
            with self.assertRaisesRegex(ValueError,'does not match'):
                publish.validate(page)

if __name__=='__main__':unittest.main()
