import unittest
from exercises.workflow.reference import build
from sandbox.broker import Broker

class Workflow(unittest.TestCase):
    def test_checkpoint_resume(self):
        b=Broker(); b.register('a','s','inventory-v1'); token=b.issue('a','s','inventory-v1')
        self.addCleanup(b.db.close)
        effects=[]
        def call(sku):
            effects.append(sku)
            return b.call(('a','s','inventory-v1'),token,'inventory.lookup',{'sku':sku},'lookup-1')
        g=build(call); config={'configurable':{'thread_id':'a:s:inventory-v1'}}
        first=g.invoke({'sku':'apple','quantity':5},config)
        self.assertNotIn('accepted',first)
        self.assertEqual(g.get_state(config).next,('explain',))
        result=g.invoke(None,config)
        self.assertTrue(result['accepted']); self.assertEqual(effects,['apple'])
        self.assertIn('available 7',result['explanation'])
    def test_rejection_and_invalid(self):
        calls=[]
        g=build(lambda sku: calls.append(sku) or {'available':3})
        config={'configurable':{'thread_id':'a:s:2'}}
        g.invoke({'sku':'pear','quantity':4},config)
        self.assertFalse(g.invoke(None,config)['accepted'])
        with self.assertRaises(ValueError): g.invoke({'sku':'pear','quantity':-1},{'configurable':{'thread_id':'a:s:3'}})
        self.assertEqual(calls,['pear'])
