"""Generic binding regressions; IDs here are synthetic fixture names, not allowlists."""
from pathlib import Path
import sys, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import networkx as nx
from shapely.geometry import Point, box, mapping, GeometryCollection
from shapely.strtree import STRtree
from src.region import Surface,NATIVE,INFERRED,RESTRICTED,UNKNOWN
from src.region_routing import RegionGraph,bidirectional,segment
from src.free_routing import queries_on_graph

class EndpointRegressions(unittest.TestCase):
    def run_fixture(self,way_tags):
        domain=box(0,0,2,1);empty=GeometryCollection()
        surface=Surface(domain,[],{NATIVE:empty,INFERRED:domain,RESTRICTED:empty,UNKNOWN:empty},{'native':[]},'synthetic',{}, {},1)
        local=nx.DiGraph()
        local.add_node('cell/0',xy=(.5,.5));local.add_node('cell/1',xy=(1.5,.5))
        bidirectional(local,'cell/0','cell/1',[segment([[.5,.5],[1.5,.5]],'inferred','synthetic-cell')])
        pts=[('cell/0',Point(.5,.5),INFERRED),('cell/1',Point(1.5,.5),INFERRED)]
        region=RegionGraph(local,[],domain,pts,STRtree([x[1] for x in pts]),surface,{})
        base=nx.DiGraph();base.add_node('source',xy=(.2,.5),tags={});base.add_node('neighbor',xy=(.1,.5),tags={})
        bidirectional(base,'source','neighbor',[segment([[.2,.5],[.1,.5]],'native','source-way',tags=way_tags)])
        common={k:mapping(g) for k,g in {'domain':domain,'valid_geometry':domain,'blocked_geometry':empty,'physical_geometry':empty,'background_geometry':empty,'native_geometry':empty}.items()}
        common.update(road_centerlines=[],native_road_access_points=[],constraints=[])
        cfg={'interface_reach_m':1.6,'unknown_portal_budget_m':.65,'inference_cost_multiplier':1,'unknown_penalty_per_m':1,'unknown_fixed_penalty_m':0}
        query={'query_id':'changed-input','source':{'id':'source','xy':[.2,.5],'role':'NATIVE_NODE'},'target':{'id':'door','xy':[1.8,.5],'role':'REGISTERED_DOOR'}}
        before=(list(local.nodes),list(local.edges),list(base.nodes),list(base.edges))
        result,terminals=queries_on_graph(base,region,[query],cfg,common,'F0',1,visible_source=base)
        self.assertEqual(before,(list(local.nodes),list(local.edges),list(base.nodes),list(base.edges)))
        return result['changed-input'],terminals
    def test_existing_ground_node_gets_checked_stitch(self):
        result,terminals=self.run_fixture({'highway':'footway'})
        self.assertTrue(result['reached'])
        self.assertEqual(result['start_xy'],(.2,.5));self.assertEqual(result['end_xy'],(1.8,.5))
        self.assertTrue(any(t['id']=='source' for t in terminals))
    def test_steps_only_does_not_assert_ground_compatibility(self):
        result,terminals=self.run_fixture({'highway':'steps','foot':'yes'})
        self.assertFalse(result['reached'])
        self.assertFalse(any(t['id']=='source' for t in terminals))

if __name__=='__main__':unittest.main()
