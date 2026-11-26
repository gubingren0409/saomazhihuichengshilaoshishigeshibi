"""Deterministic counterexamples, distinct from real-map recovery results."""
import unittest,sys,json,copy
from pathlib import Path
import networkx as nx
from shapely.geometry import box,LineString,Point,mapping,shape
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.region import build_surface,INFERRED,RESTRICTED,NATIVE,UNKNOWN
from src.common_constraints import build_contract,edge_conflicts
from src.free_surface import build_free_surface
from src.free_routing import build_graph,queries_on_graph,reweight,graph_record,checked_native
from src.region import digest

CFG=json.loads((Path(__file__).resolve().parents[1]/'config/frozen_region.json').read_text())
CFG.update(domain_radius_m=4,inference_cost_multiplier=1,unknown_penalty_per_m=1,unknown_fixed_penalty_m=0)
def fixture(hard=(),background=(),roads=(),coverage=True):
    obs=dict(task_id='SYNTHETIC_ONLY',crs='EPSG:32651',domain={'anchor_xy':[0,0]},registered_entrance=None,nodes=[],edges=[],context={'hard':list(hard),'background':list(background),'support':[]})
    guards=dict(crs='EPSG:32651',coverage_geometry=mapping(box(-8,-8,8,8)),source_parse_status='PARSED' if coverage else 'MISSING',road_centerlines=list(roads))
    common=build_contract(obs,guards,CFG)
    surface=build_free_surface(build_surface(obs,CFG),common,default=True)
    return obs,common,surface
def object_(g,kind='BUILDING',tags=None):return dict(id='fixture/'+kind,geometry=mapping(g),kind=kind,tags=tags or {})
def local_routes(surface,common,source,target):
    rg=build_graph(surface,nx.DiGraph(),CFG,common,'F0')
    q=[dict(query_id='Q',scope='LOCAL_REGION_ONLY',source=dict(id='s',xy=source,role='CONTROL_INTERIOR_POINT'),target=dict(id='t',xy=target,role='CONTROL_INTERIOR_POINT'))]
    return rg,q,queries_on_graph(nx.DiGraph(),rg,q,CFG,common,'F0',1)[0]['Q']

class FreeSpaceCounterexamples(unittest.TestCase):
    def test_01_unlabelled_frontage_really_routes(self):
        _,c,s=fixture();_,_,r=local_routes(s,c,[-2,0],[2,0]);self.assertTrue(r['reached']);self.assertGreater(r['layer_lengths']['inferred'],0)
    def test_02_no_positive_context_gate(self):
        _,c,s=fixture();self.assertAlmostEqual(s.masks[INFERRED].area,s.domain.area,6)
        self.assertTrue(all(x['reason_code']=='DEFAULT_FREE_POLICY_V1' for x in s.cells))
    def test_03_lawn_native_line_survives_no_area_opening(self):
        obs,c,s=fixture(background=[object_(box(-3,-3,3,3),'GRASS')]);obs['nodes']=[dict(id='a',xy=[-2,0],tags={}),dict(id='b',xy=[2,0],tags={})];obs['edges']=[dict(id='walk',u='a',v='b',kind='NATIVE_LINEAR',source_id='way/1',tags={'highway':'footway'})]
        graph,rejected=checked_native(obs,c);self.assertTrue(graph.has_edge('a','b'));self.assertFalse(rejected);self.assertAlmostEqual(s.masks[INFERRED].intersection(box(-3,-3,3,3)).area,0)
    def test_04_building_interior_and_exact_terminal(self):
        _,c,s=fixture(hard=[object_(box(0,-1,2,1))]);self.assertTrue(edge_conflicts(LineString([[-1,0],[1,0]]),c));self.assertFalse(edge_conflicts(LineString([[-1,0],[0,0]]),c))
    def test_05_wall_open_locked_gate(self):
        wall=object_(LineString([(0,-4),(0,4)]),'BARRIER',{'barrier':'fence'})
        obs,c,s=fixture(hard=[wall]);self.assertTrue(edge_conflicts(LineString([[-1,0],[1,0]]),c))
        wall['gates']=[{'xy':[0,0],'allowed':True}];_,c,s=fixture(hard=[wall]);self.assertFalse(edge_conflicts(LineString([[-1,0],[1,0]]),c))
        wall['gates']=[{'xy':[0,0],'allowed':False}];_,c,s=fixture(hard=[wall]);self.assertTrue(edge_conflicts(LineString([[-1,0],[1,0]]),c))
    def test_06_water_native_bridge_exact_exception(self):
        _,c,s=fixture(hard=[object_(box(-1,-4,1,4),'WATER')]);line=LineString([[-2,0],[2,0]])
        self.assertTrue(edge_conflicts(line,c));self.assertTrue(edge_conflicts(line,c,native=True));self.assertFalse(edge_conflicts(line,c,native=True,tags={'bridge':'yes'}))
    def test_07_explicit_level_vs_missing(self):
        _,c,s=fixture();line=LineString([[-1,0],[1,0]])
        self.assertFalse(edge_conflicts(line,c));self.assertTrue(edge_conflicts(line,c,tags={'level':'1'}))
    def test_08_no_new_road_crossing_existing_native_kept(self):
        road={'source_id':'way/9','geometry':mapping(LineString([(0,-5),(0,5)]))};_,c,s=fixture(roads=[road]);line=LineString([[-2,0],[2,0]])
        self.assertTrue(edge_conflicts(line,c));self.assertFalse(edge_conflicts(line,c,native=True,tags={'highway':'footway','footway':'crossing'}))
        _,_,r=local_routes(s,c,[-2,0],[2,0]);self.assertFalse(r['reached'])
    def test_09_enclosed_free_component_not_connected(self):
        wall=object_(LineString([(-1,-1),(1,-1),(1,1),(-1,1),(-1,-1)]),'BARRIER',{'barrier':'wall'});_,c,s=fixture(hard=[wall]);self.assertGreater(s.masks[INFERRED].intersection(box(-.5,-.5,.5,.5)).area,0)
        _,_,r=local_routes(s,c,[-2,0],[0,0]);self.assertFalse(r['reached'])
    def test_10_missing_data_is_not_default_free(self):
        _,_,s=fixture(coverage=False);self.assertEqual(s.masks[INFERRED].area,0);self.assertAlmostEqual(s.masks[UNKNOWN].area,s.domain.area,6);self.assertTrue(all(x['planning_state']=='NO_DATA' for x in s.cells))
    def test_11_thin_wall_and_corner_cut(self):
        wall=object_(LineString([(0,-5),(0,5)]),'BARRIER',{'barrier':'wall'});_,c,s=fixture(hard=[wall]);rg,q,r=local_routes(s,c,[-2,-2],[2,2]);self.assertFalse(r['reached'])
        for _,_,row in rg.internal.edges(data=True):
            for seg in row['segments']:self.assertFalse(edge_conflicts(LineString(seg['xy']),c))
        # Actual source-coordinate numerical regression: only one authoritative
        # intersection is permitted, never a domain-preclipped gridbox overlay.
        from src.free_surface import partition_roads
        cases=json.loads((Path(__file__).parent/'fixtures/near_coincident_masks.json').read_text())
        for case in cases:
            i,j=case['ij'];mask=shape(case['allowed']);tile=box(i,j,i+1,j+1)
            good=tile.intersection(mask)
            self.assertLess(good.area,1e-8)
            self.assertFalse([p for p in partition_roads(good,[]) if p.area>1e-8])
    def test_12_cost_only_graph_identity_and_finite_connectivity(self):
        _,c,s=fixture();rg,q,base=local_routes(s,c,[-2,0],[2,0]);ident=digest(graph_record(rg.internal))
        for weight in (1,1.5,2,3,5):
            reweight(rg.internal,weight);self.assertEqual(digest(graph_record(rg.internal)),ident)
            r,_=queries_on_graph(nx.DiGraph(),rg,q,CFG,c,'F0',weight);r=r['Q'];self.assertEqual(r['reached'],base['reached'])
            if weight==1:self.assertEqual(r,base)
        self.assertTrue(s.domain.covers(s.masks[INFERRED]))
        # Existing visible graph query nodes need not have a synthetic role or
        # be among the sixteen generic interfaces. Exact identity is required.
        visible=nx.DiGraph();visible.add_node('a',xy=(-2,0),tags={});visible.add_node('b',xy=(2,0),tags={})
        visible.add_edge('a','b',segments=[{'tags':{'highway':'footway'}}])
        qnative=[dict(query_id='nativeQ',scope='LOCAL_REGION_ONLY',source={'id':'a','xy':[-2,0]},target={'id':'b','xy':[2,0]})]
        rr,term=queries_on_graph(nx.DiGraph(),rg,qnative,CFG,c,'F0',1,visible_source=visible)
        self.assertTrue(rr['nativeQ']['reached']);self.assertTrue(all(t['binding_evidence']=='EXACT_VISIBLE_OBSERVED_GRAPH_ID_AND_COORDINATE' for t in term))
        qnative[0]['source']['xy']=[-2.01,0]
        rr,_=queries_on_graph(nx.DiGraph(),rg,qnative,CFG,c,'F0',1,visible_source=visible)
        self.assertFalse(rr['nativeQ']['reached'])

if __name__=='__main__':unittest.main(verbosity=2)
