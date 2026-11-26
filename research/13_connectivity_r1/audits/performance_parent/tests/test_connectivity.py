"""Synthetic geometry tests; no real-map route answers or sample selection."""
import copy
import math
import unittest

import networkx as nx
from shapely.geometry import LineString, Point, Polygon, box, mapping
from shapely.ops import unary_union

from src.common_constraints import build_contract, parsed_contract
from src.connectivity import build_connectivity_overlay, validate_connectivity_segment
from src.face_visibility import _add_arc, build_overlay


def face(ident, geometry, tags=None, original=None, barriers=None):
    return {'id': ident, 'source_id': ident, 'omega': geometry,
        'source_geometry': original if original is not None else geometry,
        'components': [{'geometry': p} for p in
            ([geometry] if geometry.geom_type == 'Polygon' else geometry.geoms)],
        'status': 'ADMITTED', 'tags': tags or {'highway': 'pedestrian', 'area': 'yes'},
        'geometry_hash': ident, 'clearance_m': .25, 'barriers': barriers or []}


def graph(lines):
    result = nx.DiGraph()
    for u, v, coordinates, tags in lines:
        result.add_node(u, xy=tuple(coordinates[0]), tags={})
        result.add_node(v, xy=tuple(coordinates[-1]), tags={})
        length = LineString(coordinates).length
        result.add_edge(u, v, cost=length, segments=[{'xy': coordinates, 'length_m': length,
            'cost_m': length, 'layer': 'native', 'source_id': 'way/' + u + v,
            'tags': tags or {'highway': 'footway'}}])
    return result


def common(hard=None, background=None, roads=None, coverage=None, gates=None):
    coverage = coverage if coverage is not None else box(-30, -30, 50, 50)
    obs = {'crs': 'EPSG:32651', 'domain': {'anchor_xy': [5, 5]},
        'nodes': [], 'edges': [], 'context': {'hard': hard or [],
        'background': background or [], 'support': []}}
    guards = {'crs': 'EPSG:32651', 'source_parse_status': 'PARSED',
        'coverage_geometry': mapping(coverage), 'road_centerlines': roads or [],
        'barrier_gates': gates or {}}
    return parsed_contract(build_contract(obs, guards, {'domain_radius_m': 30}, domain=mapping(coverage)))


def compose(*graphs):
    result = nx.DiGraph()
    for g in graphs:
        result.add_nodes_from(g.nodes(data=True))
        for u, v, row in g.edges(data=True):
            for option in row.get('routing_alternatives', [row['segments']]):
                _add_arc(result, u, v, option)
    return result


def build(faces, source, contract=None, mode='EXACT_STITCH', maximum=2.):
    contract = contract or common()
    local = nx.DiGraph()
    frozen, old = build_overlay(faces, source, local, contract)
    delta, evidence = build_connectivity_overlay(faces, source, local, contract,
        {'seam_max_m': maximum}, mode, frozen, old)
    return compose(source, frozen, delta), evidence, delta


class ConnectivityCorrectness(unittest.TestCase):
    def assert_clean(self, delta, faces, contract, evidence):
        for _, _, row in delta.edges(data=True):
            for option in row.get('routing_alternatives', [row['segments']]):
                for segment in option:
                    self.assertEqual(validate_connectivity_segment(segment, faces, contract, evidence), [])

    def test_cross_face_without_shared_nodes_splits_curved_parent_and_keeps_direction(self):
        fs = [face('f', box(0, 0, 10, 10))]
        source = graph([('a', 'b', [(-2, 3), (4, 3), (4, 7), (12, 7)], {})])
        before = copy.deepcopy(source); p_before = fs[0]['source_geometry'].wkb
        combined, evidence, delta = build(fs, source)
        splits = evidence['stitch_directed_splits']; self.assertTrue(splits)
        self.assertTrue(nx.has_path(combined, 'a', 'b'))
        self.assertFalse(nx.has_path(combined, 'b', 'a'))
        for row in splits:
            self.assertAlmostEqual(row['parent_length_m'], row['split_length_m'], places=8)
            for u, v in row['graph_arcs']:
                self.assertTrue(combined.has_edge(u, v))
        self.assertEqual(list(source.edges(data=True)), list(before.edges(data=True)))
        self.assertEqual(fs[0]['source_geometry'].wkb, p_before)
        self.assert_clean(delta, fs, common(), evidence)

    def test_native_endpoint_on_boundary_is_an_interface(self):
        fs = [face('f', box(0, 0, 10, 10))]
        source = graph([('a', 'b', [(-2, 5), (0, 5)], {}), ('c', 'd', [(9, 5), (10, 5)], {})])
        combined, evidence, _ = build(fs, source)
        self.assertTrue(nx.has_path(combined, 'a', 'c'))
        self.assertTrue(any('b' in r['graph_node_ids'] for r in evidence['interfaces']))

    def test_independent_line_inside_face_retains_native_identity(self):
        fs = [face('f', box(0, 0, 10, 10))]
        source = graph([('a', 'b', [(2, 2), (3, 2)], {}), ('c', 'd', [(8, 8), (9, 8)], {})])
        combined, _, _ = build(fs, source)
        self.assertTrue(nx.has_path(combined, 'a', 'c'))
        self.assertEqual(source['a']['b']['segments'][0]['layer'], 'native')

    def test_positive_shared_edge_connects_faces_without_shared_ids(self):
        fs = [face('left', box(0, 0, 5, 10)), face('right', box(5, 0, 10, 10))]
        source = graph([('a', 'aa', [(1, 5), (2, 5)], {}), ('b', 'bb', [(8, 5), (9, 5)], {})])
        combined, evidence, delta = build(fs, source)
        self.assertTrue(nx.has_path(combined, 'a', 'b'))
        self.assertTrue(any(r['kind'] == 'SHARED_BOUNDARY' and r['entered_graph'] for r in evidence['face_relations']))
        self.assert_clean(delta, fs, common(), evidence)

    def test_area_overlap_union_route_and_per_piece_provenance(self):
        fs = [face('left', box(0, 0, 6, 10)), face('right', box(4, 0, 10, 10))]
        source = graph([('a', 'aa', [(1, 5), (2, 5)], {}), ('b', 'bb', [(8, 5), (9, 5)], {})])
        combined, evidence, delta = build(fs, source)
        self.assertTrue(nx.has_path(combined, 'a', 'b'))
        self.assertAlmostEqual(nx.shortest_path_length(combined, 'a', 'b', weight='cost'), 7.)
        self.assertTrue(any(r['kind'] == 'AREA_OVERLAP' for r in evidence['face_relations']))
        self.assert_clean(delta, fs, common(), evidence)

    def test_point_touch_does_not_create_alias_bridge(self):
        fs = [face('a', box(0, 0, 2, 2)), face('b', box(2, 2, 4, 4))]
        source = graph([('a', 'aa', [(1, 1), (1.5, 1)], {}), ('b', 'bb', [(3, 3), (3.5, 3)], {})])
        combined, evidence, _ = build(fs, source, mode='CONDITIONAL_SEAMS')
        self.assertFalse(nx.has_path(combined, 'a', 'b'))
        self.assertFalse(any(r['accepted'] for r in evidence['seams']))

    def test_point_touch_does_not_reassign_one_sided_native_portal_to_other_face(self):
        fs = [face('left', box(0, 0, 2, 2)), face('right', box(2, 2, 4, 4))]
        source = graph([('a', 'touch', [(1, 1), (2, 2)], {}),
                        ('b', 'bb', [(3, 3), (3.5, 3)], {})])
        combined, _, _ = build(fs, source, mode='CONDITIONAL_SEAMS')
        self.assertFalse(nx.has_path(combined, 'a', 'b'))
        source.add_edge('touch', 'b', cost=math.sqrt(2), segments=[{
            'xy': [(2, 2), (3, 3)], 'length_m': math.sqrt(2), 'cost_m': math.sqrt(2),
            'layer': 'native', 'source_id': 'way/existing-two-sided', 'tags': {'highway': 'footway'}}])
        combined, _, _ = build(fs, source, mode='CONDITIONAL_SEAMS')
        self.assertTrue(nx.has_path(combined, 'a', 'b'))

    def test_grade_separated_line_and_face_are_not_joined(self):
        fs = [face('f', box(0, 0, 10, 10))]
        source = graph([('a', 'b', [(-2, 5), (12, 5)], {'highway': 'footway', 'layer': '1'}),
                        ('c', 'd', [(5, 2), (6, 2)], {})])
        combined, _, _ = build(fs, source, mode='CONDITIONAL_SEAMS')
        self.assertFalse(nx.has_path(combined, 'a', 'c'))
        fs[0]['tags']['layer'] = '1'
        _, evidence, _ = build(fs, source)
        self.assertEqual(evidence['stitch_domains'], [])

    def test_fence_requires_exact_recorded_opening(self):
        wall = LineString([(5, 0), (5, 10)])
        source = graph([('a', 'aa', [(1, 5), (2, 5)], {}), ('b', 'bb', [(8, 5), (9, 5)], {})])
        for opened in (False, True):
            barrier = {'id': 'fence', 'geometry': wall, 'gates':
                [{'id': 'gate', 'xy': [5, 5], 'allowed': True}] if opened else []}
            f = face('f', box(0, 0, 10, 10), barriers=[barrier])
            f['required_points'] = [{'xy': [5, 5]}] if opened else []
            contract = common(hard=[{'id': 'fence', 'kind': 'BARRIER', 'geometry': mapping(wall), 'tags': {'barrier': 'fence'}}],
                              gates={'fence': barrier['gates']})
            combined, _, _ = build([f], source, contract)
            self.assertEqual(nx.has_path(combined, 'a', 'b'), opened)

    def test_small_gap_is_in_graph_with_inferred_F0_F1_costs(self):
        fs = [face('a', box(0, 0, 4, 10)), face('b', box(5, 0, 9, 10))]
        source = graph([('a', 'aa', [(1, 5), (2, 5)], {}), ('b', 'bb', [(7, 5), (8, 5)], {})])
        combined, evidence, delta = build(fs, source, mode='CONDITIONAL_SEAMS')
        self.assertTrue(nx.has_path(combined, 'a', 'b'))
        accepted = [r for r in evidence['seams'] if r['accepted']]
        self.assertTrue(accepted); self.assertTrue(all(r['entered_graph'] for r in accepted))
        for row in accepted:
            u, v = row['graph_node_ids']; s = delta[u][v]['segments'][0]
            self.assertEqual(s['layer'], 'inferred'); self.assertEqual(s['geometry_kind'], 'CONDITIONAL_GAP_LINK')
        self.assert_clean(delta, fs, common(), evidence)

    def test_small_gap_obstacle_and_0_25_clearance_block_whole_link(self):
        fs = [face('a', box(0, 0, 4, 10)), face('b', box(5, 0, 9, 10))]
        source = graph([('a', 'aa', [(1, 5), (2, 5)], {}), ('b', 'bb', [(7, 5), (8, 5)], {})])
        # The blocker intersects the interior of every possible nearest link;
        # no assumption is made about equal-distance boundary endpoint order.
        obstacle = box(4.4, -1, 4.6, 11)
        contract = common(hard=[{'id': 'obstacle', 'kind': 'BUILDING', 'tags': {}, 'geometry': mapping(obstacle)}])
        _, evidence, _ = build(fs, source, contract, mode='CONDITIONAL_SEAMS')
        face_pairs = [r for r in evidence['seams'] if not r['source_ids']]
        self.assertTrue(face_pairs); self.assertFalse(face_pairs[0]['accepted'])
        self.assertIn('AREAL_OBSTACLE_CLEARANCE_0_25', face_pairs[0]['reasons'])

    def test_0_25_clearance_rejects_gap_near_nonintersecting_building(self):
        fs = [face('a', box(0, 0, 4, 10)), face('b', box(5, 0, 9, 10))]
        contract = common(hard=[{'id': 'nearby', 'kind': 'BUILDING', 'tags': {},
            'geometry': mapping(box(4.4, 10.1, 4.6, 10.2))}])
        _, evidence, _ = build(fs, graph([]), contract, mode='CONDITIONAL_SEAMS')
        record = evidence['seams'][0]
        self.assertFalse(record['accepted'])
        self.assertIn('AREAL_OBSTACLE_CLEARANCE_0_25', record['reasons'])
        self.assertNotIn('MAPPED_HARD_INTERIOR_CONFLICT', record['reasons'])

    def test_no_fill_clearance_removed_from_original_P(self):
        original = box(0, 0, 10, 10)
        fs = [face('f', original.difference(box(4.8, 0, 5.2, 10)), original=original)]
        source = graph([('a', 'aa', [(1, 5), (2, 5)], {}), ('b', 'bb', [(7, 5), (8, 5)], {})])
        combined, evidence, _ = build(fs, source, mode='CONDITIONAL_SEAMS')
        self.assertFalse(nx.has_path(combined, 'a', 'b'))
        self.assertTrue(any('NO_FILL_P_TO_OMEGA_REMOVAL' in r['reasons'] for r in evidence['seams']))

    def test_road_centerline_prevents_new_crossing(self):
        fs = [face('a', box(0, 0, 4, 10)), face('b', box(5, 0, 9, 10))]
        source = graph([('a', 'aa', [(1, 5), (2, 5)], {}), ('b', 'bb', [(7, 5), (8, 5)], {})])
        contract = common(roads=[{'source_id': 'road', 'geometry': mapping(LineString([(4.5, -10), (4.5, 20)]))}])
        combined, evidence, _ = build(fs, source, contract, mode='CONDITIONAL_SEAMS')
        self.assertFalse(nx.has_path(combined, 'a', 'b'))
        self.assertTrue(any('NO_NEW_FREE_ROAD_CROSSING:road' in r['reasons'] for r in evidence['seams']))

    def test_original_grass_path_kept_without_filling_grass(self):
        lawn = box(3, 0, 7, 10)
        fs = [face('f', box(0, 0, 10, 10).difference(lawn))]
        source = graph([('a', 'b', [(1, 5), (9, 5)], {'highway': 'footway'})])
        contract = common(background=[{'id': 'grass', 'kind': 'GRASS', 'tags': {}, 'geometry': mapping(lawn)}])
        combined, evidence, _ = build(fs, source, contract, mode='CONDITIONAL_SEAMS')
        self.assertTrue(nx.has_path(combined, 'a', 'b'))
        self.assertEqual(combined['a']['b']['segments'][0]['layer'], 'native')
        self.assertFalse(any(r['accepted'] for r in evidence['seams']))

    def test_private_adjacent_face_does_not_become_public(self):
        fs = [face('a', box(0, 0, 4, 10)), face('b', box(5, 0, 9, 10),
              tags={'highway': 'pedestrian', 'area': 'yes', 'foot': 'private'})]
        source = graph([('a', 'aa', [(1, 5), (2, 5)], {}), ('b', 'bb', [(7, 5), (8, 5)], {'foot': 'private'})])
        _, evidence, _ = build(fs, source, mode='CONDITIONAL_SEAMS')
        self.assertFalse(any('b' in r['source_area_ids'] for r in evidence['seams']))

    def test_line_projection_gap_splits_parent_in_original_direction(self):
        fs = [face('f', box(0, 0, 5, 5))]
        source = graph([('a', 'b', [(6, -2), (6, 7)], {})])
        combined, evidence, delta = build(fs, source, mode='CONDITIONAL_SEAMS')
        accepted = [r for r in evidence['seams'] if r['accepted'] and r['source_ids']]
        self.assertTrue(accepted)
        self.assertTrue(evidence['stitch_directed_splits'])
        for row in accepted:
            a, b = row['graph_node_ids']; self.assertTrue(delta.has_edge(a, b))
        self.assertFalse(nx.has_path(combined, 'b', 'a'))

    def test_parallel_source_option_and_F0_F1_choice_survive(self):
        fs = [face('f', box(0, 0, 10, 10))]
        source = graph([('a', 'b', [(-2, 5), (12, 5)], {})])
        native = source['a']['b']['segments'][0]
        detour = {**native, 'xy': [(-2, 5), (-2, 6), (12, 6), (12, 5)], 'length_m': 16., 'cost_m': 16.}
        source['a']['b']['routing_alternatives'] = [[{**native, 'layer': 'inferred'}], [detour]]
        source['a']['b']['segments'] = [{**native, 'layer': 'inferred'}]
        _, evidence, _ = build(fs, source)
        signatures = {r['option_sha256'] for r in evidence['stitch_directed_splits'] if r['u'] == 'a'}
        self.assertEqual(len(signatures), 2)

    def test_coverage_and_frozen_threshold_sensitivity(self):
        fs = [face('a', box(0, 0, 4, 10)), face('b', box(5, 0, 9, 10))]
        source = graph([])
        for maximum, expected in [(.5, False), (2., True), (5., True)]:
            _, evidence, _ = build(fs, source, mode='CONDITIONAL_SEAMS', maximum=maximum)
            self.assertEqual(any(r['accepted'] for r in evidence['seams']), expected)
        coverage = unary_union([box(-1, -1, 4.4, 11), box(4.6, -1, 11, 11)])
        _, evidence, _ = build(fs, source, common(coverage=coverage), mode='CONDITIONAL_SEAMS')
        self.assertFalse(any(r['accepted'] for r in evidence['seams']))
        with self.assertRaisesRegex(ValueError, 'FROZEN'):
            build(fs, source, mode='CONDITIONAL_SEAMS', maximum=6.)

    def test_delta_reuses_complete_frozen_single_face_interfaces(self):
        fs = [face('f', box(0, 0, 10, 10))]
        source = graph([('a', 'b', [(-2, 5), (12, 5)], {})])
        _, evidence, delta = build(fs, source)
        self.assertTrue(evidence['delta_only'])
        self.assertEqual(delta.number_of_edges(), 0)
        self.assertEqual(len(delta), 0)

    def test_B3_reuses_B2_union_graph_and_actual_F0_F1_route_choice_differs(self):
        from src.planner import _weighted_route, graph_sha
        fs = [face('left', box(0, 0, 4, 10)), face('right', box(5, 0, 9, 10))]
        source = graph([('a', 'b', [(1, 10), (1, 10.25), (8, 10.25), (8, 10)], {})])
        c = common(); local = nx.DiGraph()
        frozen, old = build_overlay(fs, source, local, c)
        exact, e2 = build_connectivity_overlay(fs, source, local, c, base_overlay=frozen, base_evidence=old)
        gap, e3 = build_connectivity_overlay(fs, source, local, c, mode='CONDITIONAL_SEAMS',
            base_overlay=[frozen, exact], base_evidence=e2)
        combined = compose(source, frozen, exact, gap); before = graph_sha(combined)
        f0, _, _ = _weighted_route(combined, 'a', 'b', 1)
        f1, _, _ = _weighted_route(combined, 'a', 'b', 2)
        self.assertTrue(any(s.get('geometry_kind') == 'CONDITIONAL_GAP_LINK' for s in f0['segments']))
        self.assertFalse(any(s.get('geometry_kind') == 'CONDITIONAL_GAP_LINK' for s in f1['segments']))
        self.assertAlmostEqual(sum(s['cost_m'] for s in f0['segments']), 7.)
        self.assertAlmostEqual(sum(s['cost_m'] for s in f1['segments']), 7.5)
        self.assertEqual(before, graph_sha(combined))
        self.assert_clean(gap, fs, c, e3)

    def test_gap_endpoint_preserves_native_exit_identity_and_all_node_metadata(self):
        fs = [face('f', box(0, 0, 5, 5))]
        source = graph([('exit', 'outside', [(6, 2), (8, 2)], {})])
        source.nodes['exit'].update(tags={'entrance': 'exit', 'name': 'Original exit'},
            osm_id='node/123', source_marker={'version': 4}, kind='NATIVE_SOURCE_NODE')
        before = copy.deepcopy(source.nodes['exit'])
        combined, evidence, delta = build(fs, source, mode='CONDITIONAL_SEAMS')
        self.assertTrue(any(r['accepted'] and 'exit' in r['graph_node_ids'] for r in evidence['seams']))
        self.assertEqual(delta.nodes['exit'], before)
        self.assertEqual(combined.nodes['exit'], before)
        self.assertEqual(source.nodes['exit'], before)

    def test_same_face_road_partition_is_reported_as_blocked_and_stays_disconnected(self):
        original = box(0, 0, 10, 10); f = face('f', original)
        f['components'] = [{'geometry': box(0, 0, 5, 10)}, {'geometry': box(5, 0, 10, 10)}]
        source = graph([('a', 'aa', [(1, 5), (2, 5)], {}), ('b', 'bb', [(8, 5), (9, 5)], {})])
        c = common(roads=[{'source_id': 'road', 'geometry': mapping(LineString([(5, -10), (5, 20)]))}])
        combined, evidence, _ = build([f], source, c, mode='CONDITIONAL_SEAMS')
        self.assertFalse(nx.has_path(combined, 'a', 'b'))
        row = evidence['face_relations'][0]
        self.assertFalse(row['accepted']); self.assertFalse(row['entered_graph'])
        self.assertEqual(row['reason'], 'ROAD_PARTITION_NO_NEW_FREE_CROSSING')

    def test_gap_internal_fence_uses_complete_original_line_and_exact_gate(self):
        fs = [face('left', box(0, 0, 4, 10)), face('right', box(5, 0, 9, 10))]
        source = graph([('a', 'aa', [(1, 10), (2, 10)], {}),
                        ('b', 'bb', [(7, 10), (8, 10)], {})])
        barrier = {'id': 'gap-fence', 'kind': 'BARRIER', 'tags': {'barrier': 'fence'},
                   'geometry': mapping(LineString([(4.5, -1), (4.5, 12)]))}
        observations = {}
        for gate_y, expected in [(10., True), (10.15, False), (None, False)]:
            gates = [] if gate_y is None else [{'id': 'registered-gate', 'xy': [4.5, gate_y], 'allowed': True}]
            c = common(hard=[barrier], gates={'gap-fence': gates})
            combined, evidence, delta = build(fs, source, c, mode='CONDITIONAL_SEAMS')
            pair = next(r for r in evidence['seams'] if not r['source_ids'])
            self.assertEqual(pair['accepted'], expected)
            self.assertEqual(nx.has_path(combined, 'a', 'b'), expected)
            self.assertTrue(all(not f['barriers'] for f in fs))
            if expected:
                self.assert_clean(delta, fs, c, evidence)
                u, v = pair['graph_node_ids']
                observations['valid'] = (delta[u][v]['segments'][0], evidence)
            else:
                self.assertIn('FULL_SOURCE_BARRIER_WITHOUT_EXACT_ALLOWED_GATE:gap-fence', pair['reasons'])
            observations[gate_y] = c
        segment, evidence = observations['valid']
        self.assertIn('FULL_SOURCE_BARRIER_WITHOUT_EXACT_ALLOWED_GATE:gap-fence',
            validate_connectivity_segment(segment, fs, observations[10.15], evidence))
        missing = observations[10.]
        del missing['contract']['constraints'][0]['source_geometry']
        _, e_missing, _ = build(fs, source, missing, mode='CONDITIONAL_SEAMS')
        self.assertFalse(any(r['accepted'] for r in e_missing['seams']))
        self.assertTrue(all('INCOMPLETE_SOURCE_BARRIER_GEOMETRY:gap-fence' in r['reasons'] for r in e_missing['seams']))
        self.assertIn('INCOMPLETE_SOURCE_BARRIER_GEOMETRY:gap-fence',
            validate_connectivity_segment(segment, fs, missing, evidence))

    def test_gap_may_go_around_fence_endpoint_only_outside_existing_clearance(self):
        fs = [face('left', box(0, 0, 4, 10)), face('right', box(5, 0, 9, 10))]
        for fence_end, expected in [(9.7, True), (9.9, False)]:
            barrier = {'id': 'short-fence', 'kind': 'BARRIER', 'tags': {'barrier': 'fence'},
                       'geometry': mapping(LineString([(4.5, -1), (4.5, fence_end)]))}
            c = common(hard=[barrier])
            _, evidence, delta = build(fs, graph([]), c, mode='CONDITIONAL_SEAMS')
            pair = evidence['seams'][0]
            self.assertEqual(pair['accepted'], expected)
            if expected:
                self.assert_clean(delta, fs, c, evidence)
            else:
                self.assertIn('MAPPED_HARD_INTERIOR_CONFLICT', pair['reasons'])


if __name__ == '__main__':
    unittest.main()
