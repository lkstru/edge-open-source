import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import collect

class PreviousNodes(unittest.TestCase):
    def node(self,host='8.8.8.8',**extra):
        return dict(host=host,port=80,protocol='http',country='US',**extra)

    def test_published_pool_preferred_and_old_success_not_trusted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'dist').mkdir()
            (root/'dist/nodes.json').write_text(json.dumps({'nodes':[self.node('1.1.1.1')]}))
            (root/'.published-nodes.json').write_text(json.dumps({'nodes':[self.node(verified=True,rechecked=True)]}))
            with patch.object(collect,'ROOT',root): rows=collect.load_previous(root/'output',{'US'},set())
            self.assertEqual([r['host'] for r in rows],['8.8.8.8'])
            self.assertNotIn('verified',rows[0]); self.assertNotIn('rechecked',rows[0])
            with patch.object(collect,'download',side_effect=RuntimeError('TLS validation failed')):
                self.assertFalse(collect.verify(rows[0])['verified'])

    def test_bootstrap_dedup_and_security_filters(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'dist').mkdir()
            (root/'dist/nodes.json').write_text(json.dumps({'nodes':[
                self.node(),self.node(),self.node('1.1.1.1'),self.node('10.0.0.1')]}))
            with patch.object(collect,'ROOT',root):
                rows=collect.load_previous(root/'output',{'US'},{('1.1.1.1','80')})
            self.assertEqual(len(rows),1)

    def test_explicit_empty_published_pool_never_resurrects_old_local_nodes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'dist').mkdir()
            (root/'.published-nodes.json').write_text('{"nodes":[]}')
            (root/'dist/nodes.json').write_text(json.dumps({'nodes':[self.node()]}))
            with patch.object(collect,'ROOT',root):
                self.assertEqual(collect.load_previous(root/'output',{'US'},set()),[])

    def test_previous_does_not_consume_new_budget_or_get_retested_as_new(self):
        previous=[self.node()]
        fresh=[self.node('1.1.1.1',source='proxio'),self.node('9.9.9.9',source='proxio')]
        rows=[self.node(source='proxio')]+fresh
        selected=collect.new_candidates(rows,previous,2,{})
        self.assertEqual(len(selected),2)
        self.assertNotIn('8.8.8.8',[r['host'] for r in selected])

if __name__=='__main__': unittest.main()
