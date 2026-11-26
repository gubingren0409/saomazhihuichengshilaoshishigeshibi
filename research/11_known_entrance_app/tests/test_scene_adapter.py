"""Regression fixtures for source roles that previously lost constraints/edges."""
import unittest
import networkx as nx
from src.scene_data import _add_arc, area_role, restricted, door_catalog


class SceneAdapterRegression(unittest.TestCase):
    def test_closed_parking_permission_without_area_yes_is_not_just_a_line(self):
        private={'access':'private','amenity':'parking'}
        self.assertTrue(restricted(private))
        self.assertTrue(area_role(private))
        self.assertFalse(area_role({'access':'private','highway':'service'}))

    def test_foot_specific_permission_does_not_confuse_general_private_tag(self):
        self.assertFalse(restricted({'access':'private','foot':'yes','amenity':'parking'}))
        self.assertTrue(restricted({'access':'yes','foot':'private'}))
        self.assertTrue(restricted({'foot':'yes','locked':'yes'}))

    def test_parallel_evidence_is_not_discarded_before_constraint_checks(self):
        g=nx.DiGraph()
        a={'source_id':'way/native','edge_id':'native','length_m':1,'layer':'native','xy':[[0,0],[1,0]],'tags':{'foot':'yes'}}
        b={'source_id':'relation/area','edge_id':'face','length_m':1,'layer':'derived','xy':[[0,0],[1,0]],'tags':{}}
        _add_arc(g,'a','b',a);_add_arc(g,'a','b',b)
        candidates=g['a']['b']['segments']+g['a']['b']['alternative_segments']
        self.assertEqual({s['edge_id']for s in candidates},{'native','face'})
        self.assertEqual(len(candidates),2)

    def test_exit_identity_and_coordinates_never_become_inbound(self):
        scene={'building_native_id':'way/1','r4_entrances':[{'native_id':'node/1','tags':{'entrance':'exit'},'coordinate':[121.47,31.23]}]}
        d=door_catalog(scene)[0]
        self.assertEqual(d['wgs84'],[121.47,31.23])
        self.assertEqual(d['tags'],{'entrance':'exit'})
        self.assertEqual(d['eligible_purposes'],['APPROACH_OUTSIDE'])
        self.assertEqual(door_catalog({'building_native_id':'way/1'}),[])


if __name__=='__main__':unittest.main()
