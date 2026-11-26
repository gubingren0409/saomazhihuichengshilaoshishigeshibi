"""Source-supported interfaces and separately labelled conditional gap links.

The frozen FULL_FACE builder is reused unchanged. This module only adds arcs;
it never edits source graphs, source coordinates, original polygons or queries.
Compatible positive-width face unions use the same VisibilityRoadmap, not a new
area-routing algorithm. Gap links are logical centre lines of unknown width.
"""
from __future__ import annotations

from collections import defaultdict
from time import perf_counter
import math

import networkx as nx
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import nearest_points, unary_union
from shapely.strtree import STRtree

from src.common_constraints import edge_conflicts, parsed_contract
from src.face_visibility import (CONTACT_ROUNDOFF_LIMIT_M, EPS, VisibilityRoadmap,
    _add_arc, _certified_parent_contact, _contact_points, _identity,
    _split_point, _split_record_segments, build_overlay, polygon_parts)
from src.region import access_conflict, non_ground


def _options(row):
    """Include parallel source alternatives retained by the frozen parser."""
    options = [row['segments'], *row.get('routing_alternatives', [])]
    options.extend([s] for s in row.get('alternative_segments', []))
    return list({_identity(s): s for s in options}.values())


def _ground(graph, u, v, segments):
    return (all(not non_ground(graph.nodes[n].get('tags', {})) and
                not access_conflict(graph.nodes[n].get('tags', {})) for n in (u, v)) and
            all(not non_ground(s.get('tags', {})) and
                not access_conflict(s.get('tags', {})) for s in segments))


def _line(segments):
    return LineString([q for s in segments for q in s['xy']])


def _face_ok(face):
    return (face.get('status', 'ADMITTED') == 'ADMITTED' and
            not access_conflict(face.get('tags', {})) and
            not non_ground(face.get('tags', {})) and not face['omega'].is_empty)


def _raw(face):
    return face.get('source_geometry', face['omega'])


def _barrier_conflicts(line, faces):
    reasons = []
    for face in faces:
        for barrier in face.get('barriers', []):
            geometry = barrier['geometry']
            hit = line.intersection(geometry)
            if hit.is_empty:
                continue
            contacts = ([hit] if hit.geom_type == 'Point' else
                        list(hit.geoms) if hit.geom_type == 'MultiPoint' else None)
            if contacts is None or any(not any(
                    gate.get('allowed') and Point(gate['xy']).distance(p) <= .001 and
                    geometry.distance(Point(gate['xy'])) <= .001
                    for gate in barrier.get('gates', [])) for p in contacts):
                reasons.append('SOURCE_BARRIER_WITHOUT_EXACT_ALLOWED_GATE:' + barrier['id'])
    return reasons


def _domains(faces, common=None):
    """Union only positive-area/positive-edge contacts; never point contacts."""
    components = [(f, p) for f in faces if _face_ok(f) for p in
                  ([r['geometry'] for r in f['components']] if f.get('components')
                   else list(polygon_parts(f['omega'])))]
    graph = nx.Graph(); graph.add_nodes_from(range(len(components)))
    roads = unary_union([g for _, g in common['roads']]) if common else LineString()
    relations = []; point_contacts = []
    for i, (a, p) in enumerate(components):
        for j in range(i + 1, len(components)):
            b, q = components[j]
            if p.distance(q) > 10:
                continue
            hit = p.intersection(q)
            kind = ('AREA_OVERLAP' if hit.area > 0 else 'SHARED_BOUNDARY'
                    if hit.length > EPS else 'POINT_TOUCH' if not hit.is_empty else 'POSITIVE_GAP')
            road_partition = kind == 'SHARED_BOUNDARY' and hit.difference(roads).length <= EPS
            row = {'kind': kind, 'source_ids': [a['source_id'], b['source_id']],
                   'p_distance_m': _raw(a).distance(_raw(b)), 'omega_distance_m': p.distance(q),
                   'overlap_area_m2': hit.area, 'overlap_length_m': hit.length,
                   'accepted': kind in ('AREA_OVERLAP', 'SHARED_BOUNDARY') and not road_partition,
                   'reason': 'ROAD_PARTITION_NO_NEW_FREE_CROSSING' if road_partition else
                   'POSITIVE_WIDTH_COMPATIBLE_SOURCE_DOMAIN' if kind in
                   ('AREA_OVERLAP', 'SHARED_BOUNDARY') else 'POINT_ONLY_NO_NEW_ALIAS_BRIDGE'
                   if kind == 'POINT_TOUCH' else 'CONDITIONAL_BRANCH_ONLY',
                   'geometry': mapping(hit) if not hit.is_empty else None}
            relations.append(row)
            if row['accepted']:
                graph.add_edge(i, j)
            elif kind == 'POINT_TOUCH':
                point_contacts.extend(_contact_points(hit))
    domains = []
    # An excluded part of one P must not be silently restored by another face.
    removed = unary_union([_raw(f).difference(f['omega']) for f in faces if _face_ok(f)])
    for members in sorted(nx.connected_components(graph), key=lambda s: min(s)):
        selected = [components[i] for i in sorted(members)]
        fs = list({f['source_id']: f for f, _ in selected}.values())
        merged = unary_union([p for _, p in selected]).difference(removed)
        for poly in polygon_parts(merged):
            key = _identity([sorted(f['source_id'] for f in fs), poly.wkb_hex])[:24]
            prefix = 'stitch/domain/' + key
            if len(fs) == 1:
                original = ([r['geometry'] for r in fs[0]['components']] if fs[0].get('components')
                            else list(polygon_parts(fs[0]['omega'])))
                for ci, part in enumerate(original):
                    if poly.equals(part):
                        prefix = f"fullface/{fs[0]['source_id']}/component/{ci}"
                        break
            domains.append({'key': key, 'prefix': prefix, 'poly': poly, 'faces': fs, 'portals': {}})
    return domains, relations, point_contacts, removed


def _domain_conflicts(line, domain, common):
    reasons = [] if domain['poly'].covers(line) else ['OUTSIDE_STITCH_DOMAIN']
    reasons.extend(edge_conflicts(line, common))
    reasons.extend(_barrier_conflicts(line, domain['faces']))
    return sorted(set(reasons))


def _derived_segments(line, domain):
    """Split at face boundaries so every derived interval keeps its source."""
    cuts = {0., line.length}
    for face in domain['faces']:
        cuts.update(line.project(Point(p)) for p in _contact_points(line.intersection(face['omega'].boundary)))
    parent = [{'xy': list(line.coords), 'length_m': line.length, 'cost_m': line.length}]
    result = []
    positions = sorted(cuts)
    for lo, hi in zip(positions, positions[1:]):
        if hi <= lo:
            continue
        pieces = _split_record_segments(parent, lo, hi)
        piece = _line(pieces)
        owners = [f for f in domain['faces'] if f['omega'].covers(piece)]
        if not owners:
            # A GEOS contact can round differently from the parent substring.
            # Do not invent provenance or increase a geometric tolerance.
            return None
        owners.sort(key=lambda f: f['source_id']); face = owners[0]
        result.append({'xy': [list(q) for q in piece.coords], 'length_m': piece.length,
            'cost_m': piece.length, 'layer': 'derived', 'source_id': face['source_id'],
            'source_area_id': face['source_id'], 'source_area_ids': [f['source_id'] for f in owners],
            'tags': face.get('tags', {}), 'geometry_kind': 'SOURCE_SUPPORTED_INTERFACE',
            'interface_id': 'source-interface/' + _identity([domain['key'], list(line.coords)])[:24],
            'area_routing': 'EXACT_STITCH', 'clearance_m': .25,
            'source_status': 'COMPUTED_WITHIN_UNCHANGED_SOURCE_SUPPORTED_OMEGA',
            'numeric_tolerance_m': EPS})
    return result


def build_connectivity_overlay(faces, source_graph, local_region, common, cfg=None,
                               mode='EXACT_STITCH', base_overlay=None, base_evidence=None):
    """Return an additive overlay and JSON-serializable interface evidence.

    B1's frozen build_overlay may be passed as base_overlay/base_evidence. B3
    accepts the B2 pair, thereby reusing all previous visibility arcs. Accepted
    candidates contain graph_node_ids, and all new parent splits are directed.
    """
    if mode not in ('EXACT_STITCH', 'CONDITIONAL_SEAMS'):
        raise ValueError('UNKNOWN_CONNECTIVITY_MODE')
    cfg = cfg or {}; tick = perf_counter()
    maximum = float(cfg.get('seam_max_m', 2.))
    if maximum not in (.5, 2., 5.):
        raise ValueError('SEAM_MAX_M_MUST_BE_FROZEN_0_5_2_OR_5')
    if float(cfg.get('seam_probe_m', 10.)) != 10.:
        raise ValueError('SEAM_PROBE_M_MUST_BE_10')
    common = common if 'contract' in common else parsed_contract(common)
    if not shape(common['contract']['domain']).equals(shape(common['contract']['coverage_geometry'])):
        raise ValueError('CONNECTIVITY_REQUIRES_FULL_SOURCE_CONSTRAINTS_NOT_D30')
    local = local_region.internal if hasattr(local_region, 'internal') else local_region
    if base_overlay is None:
        base_overlay, base_evidence = build_overlay(faces, source_graph, local, common, cfg)
    base_evidence = base_evidence or {}
    bases = list(base_overlay) if isinstance(base_overlay, (list, tuple)) else [base_overlay]
    overlay = nx.DiGraph(); stats = defaultdict(int)
    def node(ident, xy):
        original = next((g.nodes[ident] for g in [source_graph, local, *bases, overlay] if ident in g), {})
        if original and tuple(original['xy']) != tuple(xy):
            raise ValueError('STITCH_SOURCE_NODE_COORDINATE_DRIFT')
        overlay.add_node(ident, **{**original, 'xy': tuple(xy), 'tags': original.get('tags', {})})
    def add_arc(u, v, segments):
        identity = _identity(segments)
        if any(g.has_edge(u, v) and any(_identity(o) == identity for o in _options(g[u][v])) for g in bases):
            return
        _add_arc(overlay, u, v, segments, stats=stats)
    domains, face_relations, point_contacts, removed = _domains(faces, common)
    legal_union = unary_union([d['poly'] for d in domains])
    interfaces = []; seams = []; splits = []; certificates = []; requests = {}; numeric_rejections = []
    def numerical_rejection(reason, details):
        if not any(r['reason'] == reason for r in numeric_rejections):
            numeric_rejections.append({'reason': reason, **details})
    prior_exact = base_evidence.get('connectivity_mode') in ('EXACT_STITCH', 'CONDITIONAL_SEAMS')
    if prior_exact:
        interfaces.extend(base_evidence.get('interfaces', []))
    for domain in domains:
        poly = domain['poly']
        required = [r.get('xy', r) if isinstance(r, dict) else r
                    for face in domain['faces'] for r in face.get('required_points', [])]
        domain['model'] = VisibilityRoadmap(poly, lambda line, d=domain:
            not _domain_conflicts(line, d, common), required,
            prefix=domain['prefix'])
        for p in base_evidence.get('portals', []) + base_evidence.get('stitch_portals', []):
            belongs = p.get('domain_key') == domain['key']
            for face in domain['faces']:
                if p.get('source_area_id') != face['source_id']:
                    continue
                original = ([r['geometry'] for r in face['components']] if face.get('components')
                            else list(polygon_parts(face['omega'])))
                ci = p.get('component', 0)
                belongs = belongs or (ci < len(original) and original[ci].intersection(poly).area > 0)
            if belongs and poly.covers(Point(p['xy'])):
                domain['model'].add_point(p['id'], p['xy'])
                domain['portals'][p['id']] = tuple(p['xy'])

    def portal(domain, ident, xy):
        xy = tuple(xy)
        if not domain['poly'].covers(Point(xy)):
            return False
        existing = next((g.nodes[ident] for g in [overlay, *bases] if ident in g), None)
        if existing is not None and tuple(existing['xy']) != xy:
            raise ValueError('STITCH_PORTAL_COORDINATE_DRIFT')
        domain['model'].add_point(ident, xy); domain['portals'][ident] = xy
        return True

    def split_request(channel, graph, u, v, segments, position, ident, xy):
        key = (channel, u, v, _identity(segments))
        item = requests.setdefault(key, {'channel': channel, 'graph': graph, 'u': u, 'v': v,
            'segments': segments, 'contacts': [], 'parent': _line(segments)})
        item['contacts'].append((position, ident, tuple(xy)))

    domain_index = STRtree([d['poly'] for d in domains])
    if not prior_exact:
        for channel, graph in [('SOURCE', source_graph), ('LOCAL_REGION', local)]:
            for u, v, row in graph.edges(data=True):
                for segments in _options(row):
                    if not _ground(graph, u, v, segments):
                        continue
                    line = _line(segments)
                    if line.length == 0:
                        continue
                    native = all(s['layer'] == 'native' for s in segments)
                    for index in domain_index.query(line, predicate='intersects'):
                        domain = domains[int(index)]; poly = domain['poly']
                        raw = [(line.project(Point(xy)), xy) for xy in
                               _contact_points(line.intersection(poly.boundary))]
                        positions = sorted({0., line.length, *[p for p, _ in raw]})
                        nodes = []
                        for ident, pos in [(u, 0.), (v, line.length)]:
                            xy = tuple(graph.nodes[ident]['xy'])
                            if not poly.covers(Point(xy)):
                                continue
                            at_point_junction = any(Point(xy).equals(Point(p)) for p in point_contacts)
                            positive = line.intersection(poly).length > 0
                            # At an endpoint, require the covered initial parent
                            # interval rather than an unrelated later crossing.
                            inward = _split_record_segments(segments, 0, positions[1]) if pos == 0 else \
                                     _split_record_segments(segments, positions[-2], line.length)
                            positive = bool(inward) and poly.covers(_line(inward))
                            if (not native or at_point_junction) and not positive:
                                continue
                            if portal(domain, ident, xy):
                                nodes.append(ident)
                        for pos, xy in raw:
                            if pos <= EPS or line.length - pos <= EPS:
                                continue
                            if not native and any(Point(xy).equals(Point(p)) for p in point_contacts):
                                continue
                            cert = _certified_parent_contact(segments, line, poly, pos, xy, positions)
                            if cert is None:
                                stats['rejected_uncertified_parent_contacts'] += 1
                                numerical_rejection('NO_STRICT_PARENT_CONTACT_CERTIFICATE', {
                                    'channel': channel, 'u': u, 'v': v, 'geometry': mapping(line),
                                    'raw_xy': list(xy), 'parent_position_m': pos, 'domain_key': domain['key'],
                                    'parent_break_positions_m': positions, 'roundoff_limit_m': CONTACT_ROUNDOFF_LIMIT_M})
                                continue
                            position = cert['position_m']; xy = cert['xy']
                            ident = 'stitch/parent/' + _identity([channel, sorted(s['source_id'] for s in segments),
                                min(list(line.coords), list(line.coords)[::-1]), xy])[:24]
                            # A certified frozen portal at this exact parent
                            # coordinate is already the correct graph identity.
                            existing = [i for i, q in domain['portals'].items() if q == tuple(xy)]
                            if existing:
                                ident = sorted(existing)[0]
                            if not portal(domain, ident, xy):
                                continue
                            split_request(channel, graph, u, v, segments, position, ident, xy)
                            nodes.append(ident); certificates.append({**cert, 'channel': channel,
                                'u': u, 'v': v, 'portal_id': ident, 'domain_key': domain['key']})
                        if nodes:
                            interfaces.append({'id': 'interface/' + _identity([channel, u, v, _identity(segments), domain['key']])[:24],
                                'kind': 'SOURCE_SUPPORTED_INTERFACE', 'geometry': mapping(line.intersection(poly)), 'relation':
                                'LINE_FACE_COVERAGE' if line.intersection(poly).length > 0 else 'LINE_END_ON_BOUNDARY',
                                'parent_u': u, 'parent_v': v, 'channel': channel,
                                'source_ids': sorted({s['source_id'] for s in segments}),
                                'source_area_ids': sorted(f['source_id'] for f in domain['faces']),
                                'p_distance_m': min(line.distance(_raw(f)) for f in domain['faces']),
                                'omega_distance_m': line.distance(poly), 'covered_length_m': line.intersection(poly).length,
                                'accepted': True, 'status': 'ACCEPTED', 'reason': 'EXACT_SOURCE_PARENT_INTERFACE',
                                'entered_graph': True, 'graph_node_ids': sorted(set(nodes))})

    if mode == 'CONDITIONAL_SEAMS':
        constraints = common['contract'].get('constraints', [])
        # Same .25m non-barrier areal clearance as face construction. Barrier
        # openings and permission areas retain their existing distinct rules.
        clearance_masks = []
        for constraint in constraints:
            geometry = shape(constraint.get('source_geometry', constraint['geometry']))
            if (geometry.area > EPS and constraint.get('kind') != 'BARRIER' and
                    constraint.get('physical_barrier_asserted') is not False and
                    constraint.get('kind') != 'SOURCE_RESTRICTED_ACCESS_AREA'):
                clearance_masks.append(geometry.buffer(.25, quad_segs=16))
        clearance = unary_union(clearance_masks)
        seen = set()

        def seam(a, b, side_a, side_b, parent=None):
            a, b = tuple(a), tuple(b); link = LineString([a, b]); distance = link.length
            key = _identity([sorted([list(a), list(b)]), side_a['key'], side_b.get('key')])
            if key in seen or distance > 10:
                return
            seen.add(key); reasons = []
            if distance == 0:
                reasons.append('POINT_ONLY_OR_ALREADY_EXACT_NO_GAP_LINK')
            if distance > maximum:
                reasons.append('ABOVE_FROZEN_SEAM_MAXIMUM')
            if not shape(common['contract']['coverage_geometry']).covers(link):
                reasons.append('INCOMPLETE_SOURCE_CONSTRAINT_COVERAGE')
            reasons.extend(edge_conflicts(link, common))
            reasons.extend(_barrier_conflicts(link, faces))
            if not removed.is_empty and link.intersection(removed).difference(legal_union).length > 0:
                reasons.append('NO_FILL_P_TO_OMEGA_REMOVAL')
            if not clearance.is_empty and link.relate(clearance)[0] == '1':
                reasons.append('AREAL_OBSTACLE_CLEARANCE_0_25')
            if not side_a['poly'].covers(Point(a)) or (parent is None and not side_b['poly'].covers(Point(b))):
                reasons.append('UNCERTIFIED_STRICT_DOMAIN_ENDPOINT')
            if parent is not None:
                # A line contained on the other side of a point-only face
                # junction cannot be used to evade that junction's refusal.
                for other in domains:
                    if other is side_a or not other['poly'].covers(Point(b)) or parent['line'].intersection(other['poly']).length == 0:
                        continue
                    contact = side_a['poly'].intersection(other['poly'])
                    if not contact.is_empty and contact.area == 0 and contact.length == 0:
                        reasons.append('POINT_ONLY_PARENT_FACE_NO_NEW_BRIDGE')
            record = {'id': 'conditional-seam/' + key[:24], 'kind': 'CONDITIONAL_GAP_LINK', 'layer': 'inferred',
                'geometry': mapping(link), 'distance_m': distance, 'probe_m': 10.,
                'seam_max_m': maximum, 'source_area_ids': sorted({f['source_id'] for d in
                    [side_a, side_b] if 'faces' in d for f in d['faces']}),
                'source_ids': sorted({s['source_id'] for s in parent['segments']}) if parent else [],
                'p_distance_m': min(_raw(f).distance(parent['line']) for f in side_a['faces']) if parent else
                    min(_raw(f).distance(_raw(g)) for f in side_a['faces'] for g in side_b['faces']),
                'omega_distance_m': distance, 'accepted': not reasons, 'entered_graph': False,
                'reasons': sorted(set(reasons)), 'status': 'REJECTED' if reasons else 'ACCEPTED', 'width_m': None,
                'width_semantics': 'LOGICAL_LINE_ONLY_UNKNOWN_SOURCE_WIDTH_NO_AREA_PROMOTION',
                'assumption_multiplier_F0': 1, 'assumption_multiplier_F1': 2}
            if parent:
                record['parent'] = {'u': parent['u'], 'v': parent['v'], 'position_m': parent['position'],
                    'option_sha256': _identity(parent['segments']), 'geometry': mapping(parent['line'])}
                record['parent_projection_certificate'] = parent['projection_certificate']
            if not reasons:
                ia = 'stitch/seam/face/' + _identity([side_a['key'], a])[:24]
                portal(side_a, ia, a)
                if parent:
                    graph, u, v = parent['graph'], parent['u'], parent['v']
                    pos = parent['position']; line = parent['line']
                    if pos == 0:
                        ib = u
                    elif pos == line.length:
                        ib = v
                    else:
                        ib = 'stitch/seam/parent/' + _identity([b,
                            sorted({s['source_id'] for s in parent['segments']}),
                            min(list(line.coords), list(line.coords)[::-1])])[:24]
                        split_request('SOURCE', graph, u, v, parent['segments'], pos, ib, b)
                    node(ib, b)
                else:
                    ib = 'stitch/seam/face/' + _identity([side_b['key'], b])[:24]
                    portal(side_b, ib, b)
                for ident, xy in [(ia, a), (ib, b)]:
                    node(ident, xy)
                for u, v, xy in [(ia, ib, [a, b]), (ib, ia, [b, a])]:
                    add_arc(u, v, [{'xy': [list(q) for q in xy], 'layer': 'inferred',
                        'source_id': 'conditional-seam/' + key[:24], 'source_area_ids': record['source_area_ids'],
                        'interface_id': record['id'], 'parent': record.get('parent'),
                        'length_m': distance, 'cost_m': distance, 'tags': {},
                        'geometry_kind': 'CONDITIONAL_GAP_LINK', 'area_routing': mode,
                        'source_status': 'LOCAL_GAP_ASSUMPTION_NOT_NATIVE_NOT_VERIFIED_PAVING',
                        'width_m': None, 'clearance_m': .25}])
                record.update(entered_graph=True, graph_node_ids=[ia, ib])
            seams.append(record)

        for i, a in enumerate(domains):
            for j in domain_index.query(a['poly'], predicate='dwithin', distance=10.):
                j = int(j)
                if j <= i:
                    continue
                b = domains[j]; p, q = nearest_points(a['poly'], b['poly'])
                seam(p.coords[0], q.coords[0], a, b)
        # Native line centres keep their independent identity, including grass
        # paths. The new gap itself receives no native background exception.
        for u, v, row in source_graph.edges(data=True):
            for segments in _options(row):
                if not _ground(source_graph, u, v, segments) or not all(s['layer'] == 'native' for s in segments):
                    continue
                line = _line(segments)
                if line.length == 0:
                    continue
                for index in domain_index.query(line, predicate='dwithin', distance=10.):
                    domain = domains[int(index)]
                    if line.intersects(domain['poly']):
                        continue
                    p, q = nearest_points(domain['poly'], line)
                    candidates = [(tuple(p.coords[0]), tuple(q.coords[0]))]
                    for point in [Point(line.coords[0]), Point(line.coords[-1])]:
                        r = nearest_points(domain['poly'], point)[0]
                        candidates.append((tuple(r.coords[0]), tuple(point.coords[0])))
                    for a, raw_b in candidates:
                        pos = line.project(Point(raw_b))
                        b = (tuple(source_graph.nodes[u]['xy']) if pos == 0 else
                             tuple(source_graph.nodes[v]['xy']) if pos == line.length else
                             _split_point(segments, pos, line.length))
                        if b is None or math.dist(raw_b, b) > CONTACT_ROUNDOFF_LIMIT_M:
                            stats['rejected_uncertified_gap_parent_projections'] += 1
                            numerical_rejection('GAP_PARENT_PROJECTION_EXCEEDS_CERTIFICATE_LIMIT', {
                                'u': u, 'v': v, 'geometry': mapping(line), 'raw_xy': list(raw_b),
                                'parent_xy': list(b) if b is not None else None,
                                'roundoff_limit_m': CONTACT_ROUNDOFF_LIMIT_M})
                            continue
                        seam(a, b, domain, {'key': 'parent/' + _identity([u, v])[:24]},
                            {'graph': source_graph, 'u': u, 'v': v, 'segments': segments,
                             'line': line, 'position': pos, 'projection_certificate': {
                                'raw_projection_xy': list(raw_b), 'stored_parent_xy': list(b),
                                'coordinate_shift_m': math.dist(raw_b, b), 'parent_position_m': pos,
                                'parent_length_m': line.length, 'roundoff_limit_m': CONTACT_ROUNDOFF_LIMIT_M,
                                'policy': 'EXACT_SOURCE_ENDPOINT_OR_UNCHANGED_PARENT_ARCLENGTH_SUBSTRING_NO_NATIVE_MOVEMENT'}})

    for item in requests.values():
        graph, u, v = item['graph'], item['u'], item['v']; line = item['parent']
        ordered = [(0., u, tuple(graph.nodes[u]['xy'])),
                   *sorted(set(item['contacts'])), (line.length, v, tuple(graph.nodes[v]['xy']))]
        total = 0.; arc_nodes = []
        for _, ident, xy in ordered:
            node(ident, xy)
        for (lo, a, _), (hi, b, _) in zip(ordered, ordered[1:]):
            pieces = _split_record_segments(item['segments'], lo, hi)
            if hi == lo:
                if a != b:
                    add_arc(a, b, [])
                continue
            if tuple(pieces[0]['xy'][0]) != tuple(overlay.nodes[a]['xy']) or tuple(pieces[-1]['xy'][-1]) != tuple(overlay.nodes[b]['xy']):
                raise ValueError('STITCH_SPLIT_ENDPOINT_COORDINATE_DRIFT')
            add_arc(a, b, pieces)
            total += sum(s['length_m'] for s in pieces); arc_nodes.append([a, b])
        if abs(total - line.length) > CONTACT_ROUNDOFF_LIMIT_M:
            raise ValueError('STITCH_PARENT_LENGTH_NOT_CONSERVED')
        splits.append({'channel': item['channel'], 'u': u, 'v': v, 'parent_length_m': line.length,
            'split_length_m': total, 'length_error_m': total - line.length,
            'split_positions_m': [p for p, _, _ in ordered], 'graph_arcs': arc_nodes,
            'option_sha256': _identity(item['segments']), 'direction_preserved': True,
            'source_ids': sorted({s['source_id'] for s in item['segments']})})

    old_nodes = set().union(*(set(g) for g in bases))
    for domain in domains:
        model = domain['model']; rows = list(model.points.items())
        for ident, xy in rows:
            node(ident, xy)
        for i, (u, a) in enumerate(rows):
            for v, b in rows[i + 1:]:
                if u in old_nodes and v in old_nodes and (len(domain['faces']) == 1 or prior_exact):
                    continue
                if a != b and not (model._tangent_at(u, b) and model._tangent_at(v, a)):
                    continue
                if not model.visible(a, b):
                    continue
                if a == b:
                    forward = reverse = []
                else:
                    forward = _derived_segments(LineString([a, b]), domain)
                    reverse = _derived_segments(LineString([b, a]), domain)
                    if forward is None or reverse is None:
                        stats['rejected_uncertified_derived_provenance'] += 1
                        numerical_rejection('NO_STRICT_COVERING_FACE_FOR_PARENT_SUBSTRING', {
                            'u': u, 'v': v, 'geometry': mapping(LineString([a, b])),
                            'domain_key': domain['key'], 'source_area_ids': sorted(f['source_id'] for f in domain['faces'])})
                        continue
                add_arc(u, v, forward)
                add_arc(v, u, reverse)
                for a_id, b_id, segments in [(u, v, forward), (v, u, reverse)]:
                    if segments:
                        interfaces.append({'id': segments[0]['interface_id'], 'kind': 'SOURCE_SUPPORTED_INTERFACE',
                            'relation': 'DERIVED_SOURCE_UNION_VISIBILITY', 'geometry': mapping(LineString(
                                [q for s in segments for q in s['xy']])),
                            'source_area_ids': sorted({s['source_area_id'] for s in segments}),
                            'source_ids': sorted({s['source_id'] for s in segments}),
                            'p_distance_m': 0., 'omega_distance_m': 0., 'accepted': True,
                            'status': 'ACCEPTED', 'reason': 'WHOLE_SEGMENT_SOURCE_DOMAIN_AND_CONSTRAINT_CHECK',
                            'entered_graph': True, 'graph_node_ids': [a_id, b_id]})
    overlay.remove_nodes_from([n for n in overlay if n in old_nodes and overlay.degree(n) == 0])
    for row in face_relations:
        if row['accepted']:
            keys = [d['key'] for d in domains if set(row['source_ids']).issubset({f['source_id'] for f in d['faces']})]
            row.update(entered_graph=bool(keys), domain_keys=keys)
        else:
            row['entered_graph'] = False
    evidence = {**base_evidence, 'mode': mode, 'connectivity_mode': mode,
        'interfaces': interfaces, 'face_relations': face_relations, 'seams': seams,
        'stitch_portals': [{'id': ident, 'xy': list(xy), 'domain_key': d['key'],
            'source_area_ids': sorted(f['source_id'] for f in d['faces'])}
            for d in domains for ident, xy in sorted(d['portals'].items())],
        'stitch_domains': [{'key': d['key'], 'geometry': mapping(d['poly']),
            'source_area_ids': sorted(f['source_id'] for f in d['faces']),
            'visibility_statistics': d['model'].stats} for d in domains],
        'stitch_directed_splits': base_evidence.get('stitch_directed_splits', []) + splits,
        'stitch_intersection_certificates': base_evidence.get('stitch_intersection_certificates', []) + certificates,
        'stitch_statistics': dict(stats), 'seam_max_m': maximum, 'seam_probe_m': 10.,
        'numeric_rejections': base_evidence.get('numeric_rejections', []) + numeric_rejections,
        'accepted': sum(r['accepted'] for r in seams), 'rejected': sum(not r['accepted'] for r in seams),
        'nodes': len(overlay), 'arcs': overlay.number_of_edges(), 'elapsed_s': perf_counter() - tick,
        'original_p_geometry_changed': False, 'mutated_source_graph': False, 'delta_only': True,
        'parent_overlay_count': len(bases),
        'query_or_reference_reads': False, 'width_model': 'UNKNOWN_WIDTH_LOGICAL_LINK_ONLY',
        'optimality': 'REUSED_COMPLETE_REFLEX_VISIBILITY_ON_POSITIVE_WIDTH_SOURCE_UNIONS; FINITE_NATIVE_AND_CONDITIONAL_INTERFACES'}
    return overlay, evidence


def validate_connectivity_segment(segment, faces, common, evidence):
    """Whole-segment replay check, independent of request-local D30 geometry."""
    common = common if 'contract' in common else parsed_contract(common)
    line = LineString(segment['xy']); kind = segment.get('geometry_kind')
    reasons = []
    if abs(line.length - segment['length_m']) > CONTACT_ROUNDOFF_LIMIT_M:
        reasons.append('LENGTH_GEOMETRY_MISMATCH')
    if kind == 'CONDITIONAL_GAP_LINK':
        if segment.get('layer') != 'inferred':
            reasons.append('CONDITIONAL_LINK_MUST_REMAIN_INFERRED')
        record = next((r for r in evidence.get('seams', []) if r['id'] == segment.get('interface_id')), None)
        if record is None or not record['accepted'] or not record['entered_graph']:
            reasons.append('NO_ACCEPTED_IN_GRAPH_SEAM_RECORD')
        elif not line.equals(shape(record['geometry'])):
            reasons.append('SEAM_RECORD_GEOMETRY_MISMATCH')
        if line.length > evidence.get('seam_max_m', 2.):
            reasons.append('ABOVE_FROZEN_SEAM_MAXIMUM')
        reasons.extend(edge_conflicts(line, common))
        reasons.extend(_barrier_conflicts(line, faces))
        if not shape(common['contract']['coverage_geometry']).covers(line):
            reasons.append('INCOMPLETE_SOURCE_CONSTRAINT_COVERAGE')
        legal = unary_union([f['omega'] for f in faces if _face_ok(f)])
        for face in faces:
            if _face_ok(face) and line.intersection(_raw(face).difference(face['omega'])).difference(legal).length > 0:
                reasons.append('NO_FILL_P_TO_OMEGA_REMOVAL')
        for constraint in common['contract'].get('constraints', []):
            geometry = shape(constraint.get('source_geometry', constraint['geometry']))
            if (geometry.area > EPS and constraint.get('kind') != 'BARRIER' and
                    constraint.get('physical_barrier_asserted') is not False and
                    constraint.get('kind') != 'SOURCE_RESTRICTED_ACCESS_AREA' and
                    line.relate(geometry.buffer(.25, quad_segs=16))[0] == '1'):
                reasons.append('AREAL_OBSTACLE_CLEARANCE_0_25')
    elif kind == 'SOURCE_SUPPORTED_INTERFACE':
        selected = [f for f in faces if f['source_id'] in segment.get('source_area_ids', [segment.get('source_area_id')])]
        if segment.get('layer') != 'derived' or not selected or not any(f['omega'].covers(line) for f in selected):
            reasons.append('NO_SOURCE_FACE_COVERS_COMPLETE_DERIVED_SEGMENT')
        reasons.extend(edge_conflicts(line, common))
        reasons.extend(_barrier_conflicts(line, selected))
    return sorted(set(reasons))
