import unittest
from types import SimpleNamespace
from src.mechanism import boundary_binding_endpoint

class BoundaryContract(unittest.TestCase):
    def setUp(self):
        self.source=SimpleNamespace(outline=lambda sid:{1,2},projected={1:(10.,20.),2:(20.,30.)})
        self.endpoint={'id':'node/1','native_id':'node/1','xy':[10.,20.]}
    def test_original_membership_only(self):
        result=boundary_binding_endpoint(self.endpoint,'way/7',self.source,{'way/7'})
        self.assertEqual(result['source_area_id'],'way/7');self.assertEqual(result['xy'],self.endpoint['xy'])
        self.assertNotIn('source_area_id',self.endpoint)
    def test_no_inactive_or_nonmember_attachment(self):
        self.assertNotIn('source_area_id',boundary_binding_endpoint(self.endpoint,'way/7',self.source,set()))
        e={**self.endpoint,'native_id':'node/3'}
        self.assertNotIn('source_area_id',boundary_binding_endpoint(e,'way/7',self.source,{'way/7'}))
    def test_layer_alias_cannot_become_ground(self):
        e={**self.endpoint,'layer_aware_native_graph_id':'node/1@layer=1@level=0'}
        self.assertNotIn('source_area_id',boundary_binding_endpoint(e,'way/7',self.source,{'way/7'}))
    def test_no_coordinate_drift(self):
        with self.assertRaises(ValueError):boundary_binding_endpoint({**self.endpoint,'xy':[10.01,20.]},'way/7',self.source,{'way/7'})

if __name__=='__main__':unittest.main()
