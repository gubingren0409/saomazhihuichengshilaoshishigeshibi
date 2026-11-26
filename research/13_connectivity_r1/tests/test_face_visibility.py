import math
import unittest

import networkx as nx
from shapely.geometry import Polygon,MultiPolygon,box,LineString,Point
from shapely.geometry import mapping
from shapely.ops import unary_union

from src.face_visibility import shortest_path,VisibilityRoadmap,reflex_vertices,build_overlay,_ground_arc,_add_arc,_certified_parent_contact,_contact_points


class VisibilityCorrectness(unittest.TestCase):
    def assert_route(self,domain,a,b,length):
        r=shortest_path(domain,a,b)
        self.assertTrue(r['reached'],r)
        self.assertAlmostEqual(r['length_m'],length,places=7)
        self.assertEqual(r['points'][0],a);self.assertEqual(r['points'][-1],b)
        self.assertLess(LineString(r['points']).difference(domain).length,1e-7)
        return r

    def test_rectangle_diagonal(self):
        self.assert_route(box(0,0,10,10),(0.,0.),(10.,10.),math.sqrt(200))

    def test_rectangle_hole_analytic(self):
        p=Polygon([(0,0),(10,0),(10,10),(0,10)],holes=[[(4,3),(6,3),(6,7),(4,7)]])
        r=self.assert_route(p,(1.,5.),(9.,5.),2*math.sqrt(13)+2)
        self.assertEqual(len(r['points']),4)

    def test_concave_outer_no_cut(self):
        p=Polygon([(0,0),(6,0),(6,2),(2,2),(2,6),(0,6)])
        self.assert_route(p,(1.,5.),(5.,1.),2*math.sqrt(10))

    def test_disjoint_multipart(self):
        p=MultiPolygon([box(0,0,1,1),box(2,0,3,1)])
        self.assertFalse(shortest_path(p,(.5,.5),(2.5,.5))['reached'])

    def test_point_contact_is_not_connection(self):
        p=MultiPolygon([box(0,0,1,1),box(1,1,2,2)])
        self.assertFalse(shortest_path(p,(.5,.5),(1.5,1.5))['reached'])

    def test_fence_true_opening(self):
        p=box(0,0,20,10).difference(unary_union([box(9.75,0,10.25,4.5),box(9.75,5.5,10.25,10)]))
        self.assert_route(p,(1.,5.),(19.,5.),18)

    def test_closed_fence(self):
        p=box(0,0,20,10).difference(box(9.75,0,10.25,10))
        self.assertFalse(shortest_path(p,(1.,5.),(19.,5))['reached'])

    def test_clearance_closes_narrow_corridor(self):
        obstacle=unary_union([box(4,0,6,1.8),box(4,2.2,6,4)])
        self.assert_route(box(0,0,10,4).difference(obstacle),(2.,2.),(8.,2.),6)
        self.assertFalse(shortest_path(box(0,0,10,4).difference(obstacle.buffer(.25,quad_segs=16)),(2.,2.),(8.,2.))['reached'])

    def test_original_boundary_endpoints(self):
        self.assert_route(box(0,0,5,5),(0.,2.),(5.,2.),5)

    def test_exact_collinear_only_redundancy(self):
        p=Polygon([(0,0),(2,0),(4,0),(4,4),(0,4)])
        self.assertEqual(reflex_vertices(p),[])

    def test_necessary_reflex_vertices_hole_winding(self):
        a=Polygon([(0,0),(10,0),(10,10),(0,10)],holes=[[(4,3),(6,3),(6,7),(4,7)]])
        b=Polygon(list(a.exterior.coords)[::-1],holes=[list(a.interiors[0].coords)[::-1]])
        self.assertEqual(reflex_vertices(a),reflex_vertices(b));self.assertEqual(len(reflex_vertices(a)),4)

    def test_multiple_portals_global_choice(self):
        model=VisibilityRoadmap(box(0,0,10,2));model.add_point('p1',(0,1));model.add_point('p2',(9,1));model.add_point('exit',(10,1));model.connect_all()
        g=model.graph.copy();g.add_edge('start','p1',cost=1);g.add_edge('start','p2',cost=5)
        p=nx.shortest_path(g,'start','exit',weight='cost')
        self.assertEqual(p,['start','p2','exit']);self.assertEqual(nx.path_weight(g,p,'cost'),6)

    def test_superset_nonincrease_and_finite_cost(self):
        old=nx.DiGraph();old.add_edge('s','t',length=20,assumed=False)
        graph=old.copy();graph.add_edge('s','a',length=4,assumed=True);graph.add_edge('a','t',length=4,assumed=False)
        before=[(u,v,dict(r))for u,v,r in graph.edges(data=True)]
        def cost(weight):return lambda u,v,r:r['length']*(weight if r['assumed']else 1)
        f0=nx.shortest_path_length(graph,'s','t',weight=cost(1));f1=nx.shortest_path_length(graph,'s','t',weight=cost(2))
        self.assertEqual(f0,8);self.assertEqual(f1,12);self.assertLessEqual(f0,20);self.assertLessEqual(f1,20)
        self.assertEqual(before,[(u,v,dict(r))for u,v,r in graph.edges(data=True)])
        self.assertEqual(nx.shortest_path_length(graph,'s','t',weight=cost(1)),f0)

    def test_extra_constraint_full_segment(self):
        fence=LineString([(5,0),(5,10)])
        r=shortest_path(box(0,0,10,10),(1.,5.),(9.,5.),edge_allowed=lambda line:not line.intersects(fence))
        self.assertFalse(r['reached'])

    def test_private_rule_is_not_waived(self):
        private=box(4,0,6,10)
        r=shortest_path(box(0,0,10,10),(1.,5.),(9.,5.),edge_allowed=lambda line:line.intersection(private).length==0)
        self.assertFalse(r['reached'])

    def test_stairs_or_explicit_layer_are_not_free_interfaces(self):
        g=nx.DiGraph();g.add_node('a',xy=(0,0),tags={});g.add_node('b',xy=(1,0),tags={})
        for tags in ({'highway':'steps'},{'highway':'footway','layer':'1'},{'foot':'private'}):
            self.assertFalse(_ground_arc(g,'a','b',{'segments':[{'tags':tags}]}))
        self.assertTrue(_ground_arc(g,'a','b',{'segments':[{'tags':{'highway':'footway'}}]}))

    def test_native_node_permission_does_not_become_free_interface(self):
        g=nx.DiGraph();g.add_node('a',xy=(0,0),tags={});g.add_node('b',xy=(1,0),tags={})
        row={'segments':[{'tags':{'highway':'footway'}}]}
        for tags in ({'access':'private'},{'foot':'no'},{'locked':'yes'},{'access:conditional':'yes @ (08:00-09:00)'}):
            g.nodes['b']['tags']=tags;self.assertFalse(_ground_arc(g,'a','b',row))

    def test_parallel_candidates_keep_F0_F1_cost_reversal(self):
        g=nx.DiGraph()
        def seg(layer,xy):
            length=LineString(xy).length
            return [{'xy':xy,'layer':layer,'source_id':'synthetic','length_m':length,'cost_m':length,'tags':{}}]
        assumed=seg('assumed',[(0,0),(8,0)]);derived=seg('derived',[(0,0),(4,3),(8,0)])
        stats=__import__('collections').defaultdict(int)
        _add_arc(g,'a','b',assumed,stats=stats);_add_arc(g,'a','b',derived,stats=stats)
        options=g['a']['b']['routing_alternatives'];self.assertEqual(len(options),2)
        cost=lambda ss,w:sum(s['cost_m']*(w if s['layer']=='assumed'else 1)for s in ss)
        self.assertEqual(min(options,key=lambda ss:cost(ss,1)),assumed)
        self.assertEqual(min(options,key=lambda ss:cost(ss,2)),derived)
        self.assertEqual(stats['unitcost_discard_would_lose_F1_candidate'],1)
        _add_arc(g,'a','b',derived);self.assertEqual(len(g['a']['b']['routing_alternatives']),2)

    def test_equal_length_derived_alternative_wins_F1(self):
        g=nx.DiGraph();base={'xy':[(0,0),(8,0)],'source_id':'synthetic','length_m':8.,'cost_m':8.,'tags':{}}
        old=[{**base,'layer':'assumed'}];new=[{**base,'layer':'derived'}]
        _add_arc(g,'a','b',old);_add_arc(g,'a','b',new)
        options=g['a']['b']['routing_alternatives'];self.assertEqual(len(options),2)
        self.assertEqual(min(sum(s['cost_m']*(2 if s['layer']=='assumed'else 1)for s in ss)for ss in options),8)
        source=nx.DiGraph();source.add_edge('a','b',cost=8,segments=old)
        overlay=nx.DiGraph();_add_arc(overlay,'a','b',new,source)
        self.assertEqual(len(overlay['a']['b']['routing_alternatives']),2)

    def test_alternative_audit_counts_all_APP_hypothesis_layers(self):
        from collections import defaultdict
        for layer in ('inferred','assumed','unknown'):
            g=nx.DiGraph();stats=defaultdict(int)
            base={'xy':[(0,0),(8,0)],'source_id':'synthetic','length_m':8.,'cost_m':8.,'tags':{}}
            _add_arc(g,'a','b',[{**base,'layer':layer}],stats=stats)
            _add_arc(g,'a','b',[{**base,'layer':'derived'}],stats=stats)
            self.assertEqual(stats['unitcost_discard_would_lose_F1_candidate'],1)

    def test_certified_large_coordinate_GEOS_contact_stays_on_parent(self):
        poly=Polygon([(354380.123,3456080.456),(354430.789,3456090.123),(354420.456,3456140.789),(354370.123,3456120.456)])
        xy=[(354394.4421610861,3456166.5431052404),(354384.54052966577,3456110.410148386)]
        line=LineString(xy);raw=_contact_points(line.intersection(poly.boundary))[0]
        self.assertFalse(poly.covers(Point(raw)))
        ss=[{'xy':xy,'layer':'native','source_id':'way/synthetic','length_m':line.length,'cost_m':line.length,'tags':{'highway':'footway'}}]
        pos=line.project(Point(raw));result=_certified_parent_contact(ss,line,poly,pos,raw,[0,pos,line.length])
        self.assertIsNotNone(result);self.assertTrue(poly.covers(Point(result['xy'])))
        self.assertLessEqual(result['coordinate_shift_m'],1e-8);self.assertLessEqual(abs(result['parameter_shift_m']),1e-8)
        self.assertEqual(xy,ss[0]['xy']);self.assertEqual(result['raw_intersection_xy'],list(raw))

    def test_point_touch_has_no_positive_parent_interval(self):
        poly=box(0,0,2,2);xy=[(-1,1),(1,-1)];line=LineString(xy);pos=line.project(Point(0,0))
        ss=[{'xy':xy,'layer':'native','source_id':'way/synthetic','length_m':line.length,'cost_m':line.length,'tags':{}}]
        self.assertIsNone(_certified_parent_contact(ss,line,poly,pos,(0,0),[0,pos,line.length]))

    def test_contact_roundoff_limit_is_not_a_snap(self):
        poly=box(0,0,2,2);xy=[(-1,1),(1,1)];line=LineString(xy)
        ss=[{'xy':xy,'layer':'native','source_id':'way/synthetic','length_m':2.,'cost_m':2.,'tags':{}}]
        self.assertIsNone(_certified_parent_contact(ss,line,poly,1,(-.001,1),[0,1,2]))

    def test_small_hole_is_not_waived_by_numerical_tolerance(self):
        p=box(0,0,2,2).difference(box(.99999999,.99999999,1.00000001,1.00000001))
        model=VisibilityRoadmap(p)
        self.assertFalse(model.visible((0.,1.),(2.,1.)))
        self.assertEqual(model.stats['numeric_tolerance_admissions'],0)

    def _touch_overlay(self,local_inward=False,native_sides=0):
        from src.common_constraints import build_contract
        a,b=box(0,0,2,2),box(2,2,4,4);domain=MultiPolygon([a,b]);coverage=box(-2,-2,6,6)
        obs={'crs':'EPSG:32651','domain':{'anchor_xy':[2,2]},'nodes':[],'edges':[],'context':{'hard':[],'background':[],'support':[]}}
        guards={'crs':'EPSG:32651','source_parse_status':'PARSED','coverage_geometry':mapping(coverage)}
        common=build_contract(obs,guards,{'domain_radius_m':30},domain=mapping(coverage))
        source=nx.DiGraph();local=nx.DiGraph()
        def link(g,u,v,layer):
            xy=[g.nodes[u]['xy'],g.nodes[v]['xy']];length=math.dist(*xy)
            ss={'xy':xy,'layer':layer,'source_id':'way/synthetic'if layer=='native'else'cell/synthetic','length_m':length,'cost_m':length,'tags':{'highway':'footway'}if layer=='native'else{}}
            g.add_edge(u,v,cost=length,segments=[ss]);g.add_edge(v,u,cost=length,segments=[{**ss,'xy':xy[::-1]}])
        for ident,xy in [('A',(1,1)),('An',(.5,1)),('B',(3,3)),('Bn',(3.5,3))]:source.add_node(ident,xy=xy,tags={})
        link(source,'A','An','native');link(source,'B','Bn','native')
        touch='native/touch'if native_sides else'cell/touch'
        local.add_node(touch,xy=(2,2),tags={})
        if native_sides:
            source.add_node(touch,xy=(2,2),tags={});link(source,touch,'A','native')
            if native_sides==2:link(source,touch,'B','native')
        if local_inward:
            for ident in ('A','B'):local.add_node(ident,**source.nodes[ident]);link(local,touch,ident,'inferred')
        else:
            local.add_node('outside',xy=(1,3),tags={});link(local,touch,'outside','inferred')
        face={'id':'touch-face','source_id':'touch-face','omega':domain,'tags':{'area':'yes','highway':'pedestrian'},
              'geometry_hash':'synthetic','clearance_m':.25,'components':[{'geometry':a},{'geometry':b}]}
        overlay,evidence=build_overlay([face],source,local,common)
        return nx.compose_all([source,local,overlay]),overlay,evidence

    def test_local_region_corner_does_not_bridge_components(self):
        graph,overlay,evidence=self._touch_overlay()
        self.assertFalse(nx.has_path(graph,'A','B'))
        self.assertTrue(all(p['id']!='cell/touch'for p in evidence['portals']))

    def test_inward_local_legs_keep_their_hypothesis_identity(self):
        graph,overlay,evidence=self._touch_overlay(local_inward=True)
        self.assertTrue(nx.has_path(graph,'A','B'))
        path=nx.shortest_path(graph,'A','B',weight='cost')
        self.assertGreater(sum(s['length_m']for u,v in zip(path,path[1:])for s in graph[u][v]['segments']if s['layer']=='inferred'),0)
        self.assertTrue(all(p['id']!='cell/touch'for p in evidence['portals']))

    def test_one_sided_native_touch_is_not_another_component_interface(self):
        graph,overlay,evidence=self._touch_overlay(native_sides=1)
        self.assertFalse(nx.has_path(graph,'A','B'))
        c=[p for p in evidence['portals']if p['id']=='native/touch']
        self.assertEqual({p['component']for p in c},{0})

    def test_existing_two_sided_native_topology_is_retained(self):
        graph,overlay,evidence=self._touch_overlay(native_sides=2)
        self.assertTrue(nx.has_path(graph,'A','B'))
        self.assertEqual({p['component']for p in evidence['portals']if p['id']=='native/touch'},{0,1})

    def test_no_face_falls_back_without_park_admission(self):
        source=nx.DiGraph();source.add_edge('a','b',cost=5)
        overlay,evidence=build_overlay([],source,nx.DiGraph(),None)
        self.assertEqual(len(overlay),0);self.assertEqual(source['a']['b']['cost'],5)
        self.assertEqual(evidence['fallback'],'NO_ELIGIBLE_MAPPED_FACE_KEEP_OLD_GRAPH')

    def test_tangent_reduction_equal_dense_visibility(self):
        domains=[Polygon([(0,0),(10,0),(10,10),(0,10)],holes=[[(4,3),(6,3),(6,7),(4,7)]]),
                 Polygon([(0,0),(6,0),(6,2),(2,2),(2,6),(0,6)]),
                 box(0,0,20,20).difference(Point(10,10).buffer(3,quad_segs=8))]
        endpoints=[((1.,1.),(2.,5.)),((1.,1.),(5.,1.)),((1.,1.),(1.,5.)),((1.,1.),(5.,5.))]
        for domain in domains:
            for a,b in endpoints:
                if not(domain.covers(Point(a))and domain.covers(Point(b))):continue
                results=[]
                for filtered in (False,True):
                    model=VisibilityRoadmap(domain,tangent_filter=filtered);model.add_point('a',a);model.add_point('b',b);model.connect_all();results.append(model.path('a','b'))
                self.assertEqual(results[0]is None,results[1]is None)
                if results[0]:self.assertAlmostEqual(results[0]['length_m'],results[1]['length_m'],places=9)

    def test_derived_only_door_connection_keeps_exact_split_direction(self):
        from src.common_constraints import build_contract
        domain=box(0,0,10,10);coverage=box(-3,-3,13,13)
        obs={'crs':'EPSG:32651','domain':{'anchor_xy':[5,5]},'nodes':[],'edges':[],'context':{'hard':[],'background':[],'support':[]}}
        guards={'crs':'EPSG:32651','source_parse_status':'PARSED','coverage_geometry':mapping(coverage)}
        common=build_contract(obs,guards,{'domain_radius_m':30},domain=mapping(coverage))
        graph=nx.DiGraph()
        for ident,xy in [('s',(9,5)),('sn',(8,5)),('b',(2,5)),('door',(-1,6))]:graph.add_node(ident,xy=xy,tags={})
        for u,v,layer in [('s','sn','native'),('b','door','derived')]:
            xy=[graph.nodes[u]['xy'],graph.nodes[v]['xy']];length=math.dist(*xy)
            graph.add_edge(u,v,cost=length,segments=[{'xy':xy,'layer':layer,'source_id':'way/synthetic','length_m':length,'cost_m':length,'tags':{'highway':'footway'}}])
        before=graph.copy()
        face={'id':'synthetic-face','source_id':'synthetic-face','omega':domain,'tags':{'area':'yes','highway':'pedestrian'},'geometry_hash':'synthetic','clearance_m':.25,'components':[{'geometry':domain}]}
        overlay,evidence=build_overlay([face],graph,nx.DiGraph(),common)
        combined=nx.compose(graph,overlay)
        self.assertTrue(nx.has_path(combined,'s','door'))
        self.assertFalse(any(u=='door'for u,v in overlay.edges))
        self.assertTrue(any(r['u']=='b'and r['v']=='door'and r['channel']=='SOURCE'for r in evidence['exact_directed_splits']))
        self.assertEqual(list(before.edges(data=True)),list(graph.edges(data=True)))


if __name__=='__main__':unittest.main()
