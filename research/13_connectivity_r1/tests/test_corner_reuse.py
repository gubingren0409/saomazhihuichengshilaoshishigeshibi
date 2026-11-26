"""Isolated exact-geometry cache proofs, never real APP requests."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import networkx as nx
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from tests.test_connectivity import face, graph, common, compose
from src.face_visibility import VisibilityRoadmap, build_overlay


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


HERE = Path(__file__).resolve().parents[1]
FAST = load('candidate_connectivity', ROOT / 'src/connectivity.py')
SLOW = load('parent_connectivity', ROOT / 'audits/performance_parent/src/connectivity.py')


def geometry_options(*graphs):
    """Compare all directed geometric alternatives, independent of ID aliases."""
    return {repr([(tuple(tuple(p) for p in s['xy']), s['layer'], s.get('source_id'),
                   s.get('source_area_id'), s.get('geometry_kind'), s['length_m'], s['cost_m']) for s in option])
            for g in graphs for _, _, row in g.edges(data=True)
            for option in row.get('routing_alternatives', [row['segments']]) if option}


def fixture(cut):
    c = common(); q = box(0, 0, 10, 10).difference(box(4, 4, 6, 6))
    primary = face('q', q); primary['full_constraint_sha256'] = c['contract']['sha256']
    remote = box(18, 0, 20, 2)
    other = face('other', remote, original=unary_union([remote, cut]))
    other['full_constraint_sha256'] = c['contract']['sha256']
    source = graph([('a', 'aa', [(1, 1), (2, 1)], {}), ('b', 'bb', [(8, 9), (9, 9)], {})])
    return [primary, other], source, c


class ExactCornerReuse(unittest.TestCase):
    def compare(self, fs, source, c):
        base, evidence = build_overlay(fs, source, nx.DiGraph(), c)
        evidence.update(full_common_sha256=c['contract']['sha256'],
                        visibility_code_sha256=FAST._VISIBILITY_CODE_SHA256)
        slow, se = SLOW.build_connectivity_overlay(fs, source, nx.DiGraph(), c,
            base_overlay=base, base_evidence=evidence)
        fast, fe = FAST.build_connectivity_overlay(fs, source, nx.DiGraph(), c,
            base_overlay=base, base_evidence=evidence)
        self.assertEqual(geometry_options(base, slow), geometry_options(base, fast))
        a, b = compose(source, base, slow), compose(source, base, fast)
        for weight in (1, 2):
            cost = lambda u, v, r: min(sum(s['length_m'] * (weight if s['layer'] in
                ('inferred', 'unknown', 'assumed') else 1) for s in option)
                for option in r.get('routing_alternatives', [r['segments']]))
            self.assertAlmostEqual(nx.shortest_path_length(a, 'a', 'b', weight=cost),
                                   nx.shortest_path_length(b, 'a', 'b', weight=cost), places=10)
        return fast, fe

    def test_strict_subtractive_corner_cache_preserves_all_geometric_options(self):
        fs, source, c = fixture(box(0, 2, 1, 3))
        _, evidence = self.compare(fs, source, c)
        cert = next(r for r in evidence['corner_reuse_certificates'] if r['source_id'] == 'q')
        self.assertTrue(cert['strict_global_subset'])
        self.assertEqual(cert['reused_corner_count'], 4)
        self.assertGreater(cert['reused_positive_pairs'], 0)
        self.assertGreater(cert['reused_negative_pairs'], 0)

    def test_new_cut_rejects_identity_whose_old_incident_arc_is_not_legal(self):
        fs, source, c = fixture(box(4.8, 0, 5.2, 4.5))
        _, evidence = self.compare(fs, source, c)
        cert = next(r for r in evidence['corner_reuse_certificates'] if r['source_id'] == 'q')
        self.assertGreater(cert['rejected_alias_due_to_incident_arc_count'], 0)

    def test_constraint_hash_change_disables_negative_reuse(self):
        fs, source, c = fixture(box(0, 2, 1, 3))
        fs[0]['full_constraint_sha256'] = 'different-parent-constraint'
        _, evidence = self.compare(fs, source, c)
        self.assertFalse(any(r['source_id'] == 'q' for r in evidence['corner_reuse_certificates']))

    def test_split_old_component_never_shares_even_an_isolated_corner_identity(self):
        c = common(); q = Polygon([(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)])
        f = face('q', q); f['full_constraint_sha256'] = c['contract']['sha256']
        p = Polygon([(0, 0), (4, 0), (4, 1), (1, 1), (0, 2)])
        r = Polygon([(1, 1), (1, 4), (0, 4), (0, 3)])
        self.assertEqual(p.intersection(r).geom_type, 'Point')
        domains = [{'poly': poly, 'faces': [f], 'prefix': 'new/'+str(i), 'key': str(i)}
                   for i, poly in enumerate([p, r])]
        base = nx.DiGraph(); base.add_node('fullface/q/component/0/v/0', xy=(1., 1.), tags={})
        ev = {'faces': [{'source_id': 'q', 'geometry_hash': 'q'}],
              'full_common_sha256': c['contract']['sha256'], 'visibility_code_sha256': FAST._VISIBILITY_CODE_SHA256}
        for d in domains:
            model = VisibilityRoadmap(d['poly'], prefix=d['prefix'])
            result = FAST._reuse_original_corners(model, d, domains, c, [base], ev, __import__('collections').defaultdict(int))
            self.assertIsNone(result)

    def test_changed_common_constraints_cannot_reuse_old_negative_decisions(self):
        from shapely.geometry import mapping
        old = common(roads=[{'source_id': 'old-road', 'geometry': mapping(LineString([(5, 3), (5, 7)]))}])
        new = common()
        q = box(0, 0, 10, 10).difference(box(4, 4, 6, 6))
        f = face('q', q); f['full_constraint_sha256'] = new['contract']['sha256']
        d = {'poly': q, 'faces': [f], 'prefix': 'derived/numeric-prefix', 'key': 'q'}
        model = VisibilityRoadmap(q, prefix=d['prefix'])
        ev = {'faces': [{'source_id': 'q', 'geometry_hash': 'q'}],
              'full_common_sha256': old['contract']['sha256'], 'visibility_code_sha256': FAST._VISIBILITY_CODE_SHA256}
        result = FAST._reuse_original_corners(model, d, [d], new, [nx.DiGraph()], ev,
                                              __import__('collections').defaultdict(int))
        self.assertIsNone(result)

    def test_unchanged_single_face_keeps_exact_parent_graph(self):
        c = common(); fs = [face('q', box(0, 0, 10, 10))]
        source = graph([('a', 'aa', [(1, 1), (2, 1)], {}), ('b', 'bb', [(8, 9), (9, 9)], {})])
        delta, evidence = self.compare(fs, source, c)
        self.assertEqual(delta.number_of_edges(), 0)
        self.assertEqual(evidence['corner_reuse_certificates'], [])


def add_parent(g, u, v, xy, layer):
    g.add_node(u, xy=tuple(xy[0]), tags={}); g.add_node(v, xy=tuple(xy[-1]), tags={})
    length = LineString(xy).length
    g.add_edge(u, v, cost=length, segments=[{'xy': xy, 'length_m': length,
        'cost_m': length, 'layer': layer, 'source_id': 'synthetic/' + u + '/' + v,
        'tags': {'highway': 'footway'}}])


class PortalEligibility(unittest.TestCase):
    def test_dense_source_and_local_derived_interiors_stay_out_but_boundary_cut_routes(self):
        for channel in ('SOURCE', 'LOCAL_REGION'):
            c = common(); fs = [face('q', box(0, 0, 10, 10))]
            native = graph([('a', 'aa', [(5, 2), (6, 2)], {})])
            grid = nx.DiGraph()
            for x in range(1, 10):
                for y in range(1, 10):
                    for dx, dy in [(1, 0), (0, 1)]:
                        if x + dx <= 9 and y + dy <= 9:
                            add_parent(grid, f'grid/{x}/{y}', f'grid/{x+dx}/{y+dy}',
                                       [(x, y), (x+dx, y+dy)], 'derived')
            add_parent(grid, 'outside/u', 'outside/v', [(-2, 5), (12, 5)], 'derived')
            source = compose(native, grid) if channel == 'SOURCE' else native
            local = grid if channel == 'LOCAL_REGION' else nx.DiGraph()
            before = geometry_options(source, local)
            delta, ev = FAST.build_connectivity_overlay(fs, source, local, c,
                base_overlay=nx.DiGraph(), base_evidence={})
            self.assertFalse(any(p['id'].startswith('grid/') for p in ev['stitch_portals']))
            self.assertGreater(ev['stitch_statistics']['rejected_derived_interior_endpoint_promotion'], 0)
            combined = compose(source, local, delta)
            self.assertTrue(nx.has_path(combined, 'a', 'outside/v'))
            self.assertFalse(nx.has_path(combined, 'outside/v', 'a'))
            self.assertTrue(any(r['channel'] == channel for r in ev['stitch_directed_splits']))
            self.assertEqual(before, geometry_options(source, local))
            self.assertTrue(before.issubset(geometry_options(combined)))

    def test_point_touch_source_and_local_hypothesis_legs_do_not_become_free_bridge(self):
        for channel in ('SOURCE', 'LOCAL_REGION'):
            c = common(); fs = [face('left', box(0, 0, 3, 3)), face('right', box(3, 3, 6, 6))]
            native = graph([('gridA', 'a2', [(1, 1), (1.5, 1)], {}),
                            ('gridB', 'b2', [(5, 5), (5.5, 5)], {})])
            legs = nx.DiGraph()
            add_parent(legs, 'gridA', 'grid/shared', [(1, 1), (3, 3)], 'inferred')
            add_parent(legs, 'grid/shared', 'gridB', [(3, 3), (5, 5)], 'inferred')
            source = compose(native, legs) if channel == 'SOURCE' else native
            local = legs if channel == 'LOCAL_REGION' else nx.DiGraph()
            base, old = build_overlay(fs, source, local, c)
            delta, ev = FAST.build_connectivity_overlay(fs, source, local, c,
                base_overlay=base, base_evidence=old)
            combined = compose(source, local, base, delta)
            self.assertTrue(nx.has_path(combined, 'gridA', 'gridB'))
            self.assertFalse(any(p['id'] == 'grid/shared' for p in ev['stitch_portals']))
            free = nx.DiGraph(); free.add_nodes_from(combined.nodes(data=True))
            for u, v, row in combined.edges(data=True):
                for option in row.get('routing_alternatives', [row['segments']]):
                    if all(s['layer'] in ('native', 'derived') for s in option):
                        free.add_edge(u, v)
            self.assertFalse(nx.has_path(free, 'gridA', 'gridB'))
            self.assertTrue(geometry_options(legs).issubset(geometry_options(combined)))


if __name__ == '__main__':
    unittest.main()
