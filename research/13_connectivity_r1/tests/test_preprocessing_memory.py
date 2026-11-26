import unittest
from src import planner

class CacheOwnership(unittest.TestCase):
    def tearDown(self):
        planner._activate_preprocessing_group('TEST_CLEAR_FINAL',None)
        planner.SOURCE_CACHE.clear()
    def test_same_namespace_keeps_shared_graph(self):
        planner._activate_preprocessing_group('A','door')
        graph={'unweighted':'same-object'};planner.CONNECTIVITY_CACHE['entry']=graph
        planner._activate_preprocessing_group('A','door')
        self.assertIs(planner.CONNECTIVITY_CACHE['entry'],graph)
    def test_evict_does_not_mutate_inflight_reference_or_source(self):
        planner._activate_preprocessing_group('A','door')
        prepared={'graph':{'nodes':[1,2]}};planner.CACHE['key']=prepared
        source={'source_graph':'checked'};planner.SOURCE_CACHE['source']=source
        planner._activate_preprocessing_group('A','other-door')
        self.assertFalse(planner.CACHE);self.assertEqual(prepared['graph']['nodes'],[1,2])
        self.assertIs(planner.SOURCE_CACHE['source'],source)

if __name__=='__main__':unittest.main()
