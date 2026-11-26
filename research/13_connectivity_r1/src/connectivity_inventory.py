"""Frozen-source object inventory and geometric relations; never reads routes."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from shapely import shortest_line
from shapely.geometry import GeometryCollection, LineString, Point, mapping, shape
from shapely.ops import transform
from shapely.strtree import STRtree

from src.common_constraints import denied, digest, edge_conflicts, explicit_non_ground
from src.face_geometry import EPS, area_reason, geometry_sha, metrics, source_ring_audit
from src.frozen_scene.native_adapter import INVERSE, Source
from src.frozen_scene.local_route import _evidence, _directions
from src.scene_data import source_coverage

ROOT = Path(__file__).resolve().parents[1]
PROBE_M = 10.0
WALK = {'pedestrian', 'footway', 'path'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':'), allow_nan=False), encoding='utf-8')


def explicit_face(tags):
    return tags.get('area:highway') in WALK or (tags.get('area') == 'yes' and tags.get('highway') in WALK)


def candidate_reason(tags):
    if explicit_face(tags):
        return 'EXPLICIT_PEDESTRIAN_AREA'
    if tags.get('highway') in WALK and (tags.get('type') == 'multipolygon' or tags.get('area') == 'yes'):
        return 'PEDESTRIAN_AREA_LIKE_BUT_FROZEN_EXPLICIT_TAG_RULE_NOT_MET'
    if tags.get('area:highway') or (tags.get('area') == 'yes' and tags.get('highway')):
        return 'OTHER_EXPLICIT_HIGHWAY_AREA'
    if (tags.get('leisure') in {'park', 'garden', 'recreation_ground', 'flowerbed'} or
            tags.get('landuse') in {'grass', 'flowerbed', 'flower_bed', 'meadow'} or
            tags.get('landcover') in {'grass', 'flowerbed'}):
        return 'CONTEXT_AREA_NOT_AUTOMATIC_WALKABLE_FACE'
    return None


def object_record(obj):
    return {'type': obj['type'], 'id': obj['id'], 'version': obj.get('version'),
            'version_status': 'PRESENT' if 'version' in obj else 'NOT_PRESENT_IN_FROZEN_SOURCE',
            'tags': obj.get('tags', {}), 'nodes': obj.get('nodes', []),
            'members': obj.get('members', []), 'source_object_sha256': digest(obj)}


def all_nodes(source, ident):
    obj = source.obj(ident)
    if obj['type'] == 'way':
        return set(obj.get('nodes', []))
    return {n for m in obj.get('members', []) if m['type'] == 'way' and m['ref'] in source.ways
            for n in source.ways[m['ref']].get('nodes', [])}


def members_record(source, obj):
    if obj['type'] == 'way':
        return []
    return [{**m, 'object': object_record(source.ways[m['ref']])
             if m['type'] == 'way' and m['ref'] in source.ways else None}
            for m in obj.get('members', [])]


def inventory_scene(row, old_ids):
    path = ROOT / row['source_path']
    actual = sha256(path.read_bytes()).hexdigest()
    if actual != row['source_sha256']:
        raise ValueError('FROZEN_SOURCE_HASH_CHANGED:' + row['scene_id'])
    raw = read(path)
    source = Source(raw)
    coverage = source_coverage(raw['bounds_wsen'])
    candidates = []
    geometry = {}
    for obj in [*source.ways.values(), *source.relations.values()]:
        basis = candidate_reason(obj.get('tags', {}))
        if basis is None:
            continue
        ident = f"{obj['type']}/{obj['id']}"
        audit = source_ring_audit(source, ident)
        try:
            p = source.area(ident)
        except Exception:
            p = None
        reason = area_reason(obj.get('tags', {}), p)
        missing = p.difference(coverage).area if p is not None else None
        if reason is None and missing > EPS:
            reason = 'INCOMPLETE_SOURCE_COVERAGE'
        record = {'scene_id': row['scene_id'], 'source_id': ident, **object_record(obj),
                  'source_clip_sha256': actual, 'source_path': row['source_path'],
                  'candidate_basis': basis, 'explicit_frozen_admission_tags': explicit_face(obj.get('tags', {})),
                  'old_population': ident in old_ids, 'status': reason or 'ADMITTED',
                  'ring_audit': audit, 'member_objects': members_record(source, obj),
                  'coverage_complete': missing is not None and missing <= EPS,
                  'outside_coverage_area_m2': missing, 'source_bounds_wsen': raw['bounds_wsen'],
                  'source_metrics': metrics(p) if p is not None else None,
                  'source_geometry_sha256': geometry_sha(p) if p is not None else None,
                  'source_geometry': mapping(p) if p is not None else None,
                  'new_admission_identity': 'OLD_SOURCE_PRESENT_BUT_OLD_SELECTION_OMITTED'
                  if reason is None and ident not in old_ids else None}
        candidates.append(record)
        if p is not None:
            geometry[ident] = p
    admitted = [r for r in candidates if r['status'] == 'ADMITTED']
    duplicates = []
    # Suppress only exact geometry duplicates with identical semantic tags.
    # Being a relation member or merely overlapping does not erase a lawful line.
    for i, a in enumerate(sorted(admitted, key=lambda r: (r['type'] != 'relation', r['source_id']))):
        if a['status'] != 'ADMITTED':
            continue
        for b in sorted(admitted, key=lambda r: r['source_id']):
            if b['source_id'] == a['source_id'] or b['status'] != 'ADMITTED':
                continue
            if a['tags'] == b['tags'] and geometry[a['source_id']].equals(geometry[b['source_id']]):
                b.update(status='DUPLICATE_EXACT_COMPATIBLE_SOURCE_FACE', duplicate_of=a['source_id'])
                duplicates.append({'kept': a['source_id'], 'duplicate': b['source_id'],
                                   'reason': 'EQUAL_POLYGON_AND_IDENTICAL_SOURCE_TAGS'})
    selected = sorted(r['source_id'] for r in candidates if r['status'] == 'ADMITTED')
    relation_membership = []
    for relation in source.relations.values():
        if not explicit_face(relation.get('tags', {})):
            continue
        for member in relation.get('members', []):
            if member['type'] != 'way' or member['ref'] not in source.ways:
                continue
            way = source.ways[member['ref']]
            relation_membership.append({'relation_id': f"relation/{relation['id']}",
                'member_id': f"way/{member['ref']}", 'role': member.get('role') or 'outer',
                'member_tags': way.get('tags', {}), 'member_is_explicit_face': explicit_face(way.get('tags', {})),
                'member_retains_independent_line_role': bool(way.get('tags', {}).get('highway')) and way.get('tags', {}).get('area') != 'yes'})
    summary = {'scene_id': row['scene_id'], 'label': row['label'], 'old_area_ids': sorted(old_ids),
               'selected_area_ids': selected, 'added_area_ids': sorted(set(selected) - set(old_ids)),
               'old_count': len(old_ids), 'selected_count': len(selected),
               'added_count': len(set(selected) - set(old_ids)),
               'explicit_source_candidate_count': sum(r['explicit_frozen_admission_tags'] for r in candidates),
               'all_relevant_candidate_count': len(candidates),
               'rejected_explicit_reasons': dict(Counter(r['status'] for r in candidates
                   if r['explicit_frozen_admission_tags'] and r['status'] != 'ADMITTED')),
               'source_sha256': actual, 'duplicates': duplicates,
               'coverage_geometry': mapping(coverage), 'source_bounds_wsen': raw['bounds_wsen'],
               'source_timestamp': raw.get('osm3s', {}).get('timestamp_osm_base'),
               'member_relationships': relation_membership}
    return source, candidates, summary


def source_lines(source, row):
    rows = []
    for number, obj in sorted(source.ways.items()):
        tags = obj.get('tags', {})
        if not tags.get('highway'):
            continue
        refs = obj.get('nodes', [])
        missing = [n for n in refs if n not in source.projected]
        if len(refs) < 2 or missing:
            rows.append({'source_id': f'way/{number}', **object_record(obj), 'geometry': None,
                         'status': 'INCOMPLETE_NATIVE_LINE_GEOMETRY', 'missing_node_ids': missing})
            continue
        line = LineString([source.projected[n] for n in refs])
        evidence = _evidence(tags)
        reason = ('SOURCE_AREA_BOUNDARY_NOT_INDEPENDENT_NATIVE_LINE' if tags.get('area') == 'yes' else
                  'RESTRICTED_OR_CONDITIONAL_LINE' if denied(tags) else
                  'NON_GROUND_OR_UNRESOLVED_LAYER' if explicit_non_ground(tags) or tags.get('highway') in {'steps', 'elevator'} else
                  'FROZEN_NATIVE_ENGINE_NO_PEDESTRIAN_EVIDENCE' if evidence is None else None)
        rows.append({'source_id': f'way/{number}', **object_record(obj), 'geometry': line,
                     'source_clip_sha256': row['source_sha256'], 'length_m': line.length,
                     'status': reason or 'ELIGIBLE_NATIVE_LINEAR_TAGS', 'evidence': evidence,
                     'directions': list(_directions(tags)), 'geometry_sha256': geometry_sha(line),
                     'line_identity_preserved': True})
    return rows


def line_relation(poly, line):
    if poly is None or poly.is_empty:
        return {'distance_m': None, 'class': 'EMPTY_GEOMETRY', 'intersection_length_m': 0,
                'boundary_overlap_length_m': 0, 'interior_length_m': 0}
    distance = poly.distance(line)
    hit = poly.intersection(line)
    boundary = poly.boundary.intersection(line)
    inside = line.difference(poly.boundary).intersection(poly).length
    if distance > EPS:
        kind = 'NONZERO_GAP'
    elif boundary.length > EPS:
        kind = 'BOUNDARY_OVERLAP'
    elif poly.covers(line):
        kind = 'LINE_WITHIN_FACE'
    elif inside > EPS:
        kind = 'LINE_ENTERS_OR_CROSSES_FACE'
    elif any(poly.boundary.distance(Point(c)) <= EPS for c in (line.coords[0], line.coords[-1])):
        kind = 'LINE_ENDPOINT_ON_BOUNDARY'
    else:
        kind = 'POINT_TOUCH'
    return {'distance_m': distance, 'class': kind, 'intersection_length_m': hit.length,
            'boundary_overlap_length_m': boundary.length, 'interior_length_m': inside,
            'endpoint_inside': [poly.contains(Point(c)) for c in (line.coords[0], line.coords[-1])],
            'endpoint_boundary_distance_m': [poly.boundary.distance(Point(c)) for c in (line.coords[0], line.coords[-1])],
            'intersection_geometry': mapping(hit)}


def polygon_relation(a, b):
    if a.is_empty or b.is_empty:
        return {'distance_m': None, 'class': 'EMPTY_GEOMETRY', 'overlap_area_m2': 0, 'shared_boundary_length_m': 0}
    distance = a.distance(b)
    hit = a.intersection(b)
    length = a.boundary.intersection(b.boundary).length
    kind = ('NONZERO_GAP' if distance > EPS else 'AREA_OVERLAP' if hit.area > EPS else
            'SHARED_BOUNDARY' if length > EPS else 'POINT_TOUCH')
    return {'distance_m': distance, 'class': kind, 'overlap_area_m2': hit.area,
            'shared_boundary_length_m': length, 'intersection_geometry': mapping(hit)}


def restriction_contacts(connector, face, common):
    if connector.is_empty or connector.length <= EPS:
        return []
    contacts = []
    if connector.intersects(shape(face.get('clearance_mask_geometry', mapping(GeometryCollection())))):
        contacts.append('FACE_AREAL_OR_SOURCE_HOLE_CLEARANCE_MASK')
    contacts.extend(edge_conflicts(connector, common, native=False,
                                  tags=face['tags'], source_id=face['source_id']))
    for barrier in face.get('barriers', []):
        barrier_geometry = barrier['geometry'] if hasattr(barrier['geometry'], 'geom_type') else shape(barrier['geometry'])
        if connector.intersects(barrier_geometry):
            contacts.append('SOURCE_BARRIER:' + barrier['id'])
    return sorted(set(contacts))


def geometric_relations(scene_id, source, faces, lines, common):
    valid_lines = [r for r in lines if r['geometry'] is not None]
    tree = STRtree([r['geometry'] for r in valid_lines])
    rows = []
    museum_anchor = Point(source.projected[6897141353]) if scene_id == 'sh-huangpu-01' else None
    for face in faces:
        p, omega = face['source_geometry'], face['omega']
        if p is None:
            continue
        face_nodes = all_nodes(source, face['source_id'])
        for index in tree.query(p.buffer(PROBE_M), predicate='intersects'):
            record = valid_lines[int(index)]
            line = record['geometry']
            if p.distance(line) > PROBE_M:
                continue
            pr, om = line_relation(p, line), line_relation(omega, line)
            shared = sorted(face_nodes.intersection(record['nodes']))
            gap = shortest_line(omega, line) if not omega.is_empty else GeometryCollection()
            conflicts = restriction_contacts(gap, face, common)
            rows.append({'scene_id': scene_id, 'relation_id': f"{scene_id}|{face['source_id']}|{record['source_id']}",
                'kind': 'FACE_LINE', 'a_source_id': face['source_id'], 'b_source_id': record['source_id'],
                'a_tags': face['tags'], 'b_tags': record['tags'], 'a_status': face['status'],
                'b_status': record['status'], 'P': pr, 'omega': om,
                'shared_native_node_ids': [f'node/{n}' for n in shared],
                'a_ground_permission_eligible': face['status'] == 'ADMITTED',
                'b_ground_permission_eligible': record['status'] == 'ELIGIBLE_NATIVE_LINEAR_TAGS',
                'museum_diagnostic_roi': museum_anchor is not None and p.distance(museum_anchor) <= 450 and line.distance(museum_anchor) <= 450,
                'separation_introduced_by_omega': pr['distance_m'] <= EPS and (om['distance_m'] is None or om['distance_m'] > EPS),
                'removed_intersection_length_m': max(0, pr['intersection_length_m'] - om['intersection_length_m']),
                'nearest_omega_connector': mapping(gap), 'nearest_connector_conflicts': conflicts,
                'native_line_identity_retained': True, 'probe_radius_m': PROBE_M,
                'graph_inclusion': 'NOT_EVALUATED_BEFORE_SOURCE_FREEZE', 'route_use': 'NOT_EVALUATED'})
    for i, a in enumerate(faces):
        if a['source_geometry'] is None:
            continue
        for b in faces[i + 1:]:
            if b['source_geometry'] is None or a['source_geometry'].distance(b['source_geometry']) > PROBE_M:
                continue
            pr = polygon_relation(a['source_geometry'], b['source_geometry'])
            om = polygon_relation(a['omega'], b['omega'])
            gap = shortest_line(a['omega'], b['omega']) if not a['omega'].is_empty and not b['omega'].is_empty else GeometryCollection()
            conflicts = sorted(set(restriction_contacts(gap, a, common) + restriction_contacts(gap, b, common)))
            rows.append({'scene_id': scene_id, 'relation_id': f"{scene_id}|{a['source_id']}|{b['source_id']}",
                'kind': 'FACE_FACE', 'a_source_id': a['source_id'], 'b_source_id': b['source_id'],
                'a_tags': a['tags'], 'b_tags': b['tags'], 'a_status': a['status'], 'b_status': b['status'],
                'a_ground_permission_eligible': a['status'] == 'ADMITTED',
                'b_ground_permission_eligible': b['status'] == 'ADMITTED',
                'museum_diagnostic_roi': museum_anchor is not None and a['source_geometry'].distance(museum_anchor) <= 450 and b['source_geometry'].distance(museum_anchor) <= 450,
                'P': pr, 'omega': om, 'shared_native_node_ids': [f'node/{n}' for n in sorted(all_nodes(source, a['source_id']).intersection(all_nodes(source, b['source_id'])))],
                'separation_introduced_by_omega': pr['distance_m'] <= EPS and (om['distance_m'] is None or om['distance_m'] > EPS),
                'nearest_omega_connector': mapping(gap), 'nearest_connector_conflicts': conflicts,
                'probe_radius_m': PROBE_M, 'graph_inclusion': 'NOT_EVALUATED_BEFORE_SOURCE_FREEZE', 'route_use': 'NOT_EVALUATED'})
    return sorted(rows, key=lambda r: r['relation_id'])


def feature(geometry, properties):
    return {'type': 'Feature', 'geometry': mapping(transform(INVERSE, geometry)), 'properties': properties}


def freeze_mechanisms(relations):
    """Stable ID selection by source relation type, before any new routing result."""
    categories = [
        ('LINE_CROSS_WITHOUT_SHARED_NODES', lambda r: r['kind'] == 'FACE_LINE' and r['omega']['class'] == 'LINE_ENTERS_OR_CROSSES_FACE' and not r['shared_native_node_ids']),
        ('LINE_INTERIOR', lambda r: r['kind'] == 'FACE_LINE' and r['omega']['class'] == 'LINE_WITHIN_FACE'),
        ('LINE_COMMON_EDGE', lambda r: r['kind'] == 'FACE_LINE' and r['omega']['class'] == 'BOUNDARY_OVERLAP'),
        ('FACE_OVERLAP_OR_COMMON_EDGE', lambda r: r['kind'] == 'FACE_FACE' and r['omega']['class'] in {'AREA_OVERLAP', 'SHARED_BOUNDARY'}),
        ('POINT_TOUCH', lambda r: r['omega']['class'] == 'POINT_TOUCH'),
        ('SMALL_GAP_0_2M', lambda r: r['omega']['distance_m'] is not None and EPS < r['omega']['distance_m'] <= 2 and not r['nearest_connector_conflicts']),
        ('CONSTRAINT_SEPARATION', lambda r: r['separation_introduced_by_omega']),
        ('LAYER_OR_PERMISSION_REJECTION', lambda r: r['b_status'] in {'RESTRICTED_OR_CONDITIONAL_LINE', 'NON_GROUND_OR_UNRESOLVED_LAYER'})]
    selected, missing, used = [], [], set()
    for label, predicate in categories:
        pool = [r for r in relations if predicate(r) and r['relation_id'] not in used and
                (label == 'LAYER_OR_PERMISSION_REJECTION' or r['b_ground_permission_eligible'])]
        if not pool:
            missing.append(label)
            continue
        chosen = sorted(pool, key=lambda r: (not r.get('museum_diagnostic_roi', False), r['relation_id']))[0]
        used.add(chosen['relation_id'])
        selected.append({'mechanism_id': f'M{len(selected) + 1:02d}', 'category': label,
                         'relation_id': chosen['relation_id'], 'scene_id': chosen['scene_id'],
                         'a_source_id': chosen['a_source_id'], 'b_source_id': chosen['b_source_id'],
                         'P_class': chosen['P']['class'], 'omega_class': chosen['omega']['class'],
                         'P_distance_m': chosen['P']['distance_m'], 'omega_distance_m': chosen['omega']['distance_m'],
                         'selection_rule': 'MUSEUM_450M_SOURCE_ROI_FIRST_THEN_STABLE_RELATION_ID_IN_CATEGORY; NO_ROUTE_RESULTS_READ'})
    return {'max_queries': 8, 'selection_basis': 'SOURCE_GEOMETRY_CATEGORIES_MUSEUM_ROI_THEN_STABLE_IDS_BEFORE_NEW_MODE_ROUTES',
            'selected': selected, 'missing_categories': missing, 'route_results_read': False,
            'no_entrance_generation': True}


def supplemental_freeze():
    """Global source identity and exact native endpoint certificates, never scores."""
    out = ROOT / 'data/connectivity'
    lock = read(out / 'source_selection_lock.json')
    unique, old, scene_added = {}, set(), set()
    line_counts = Counter()
    endpoint_requests = []
    mechanisms = read(out / 'mechanism_queries_lock.json')
    for scene in lock['scenes']:
        ident = scene['scene_id']
        summary = read(out / f'{ident}_inventory_summary.json')
        candidates = {r['source_id']: r for r in read(out / f'{ident}_source_inventory.json')}
        lines = read(out / f'{ident}_native_lines.json')
        for line in lines:
            line_counts[line['status']] += 1
        timestamp = summary['source_timestamp']
        for sid in scene['area_ids']:
            record = candidates[sid]
            key = (sid, record['version'], timestamp)
            unique.setdefault(key, []).append(ident)
            (old if sid in scene['old_area_ids'] else scene_added).add(key)
        selected = [m for m in mechanisms['selected'] if m['scene_id'] == ident]
        if not selected:
            continue
        source_row = next(s for s in read(ROOT / 'data/scene_manifest.json')['scenes'] if s['scene_id'] == ident)
        source = Source(read(ROOT / source_row['source_path']))
        legal_faces = {r['source_id']: shape(r['omega']) for r in read(out / f'{ident}_faces.json')}
        by_line = {line['source_id']: line for line in lines}
        eligible_nodes = {n for line in lines if line['status'] == 'ELIGIBLE_NATIVE_LINEAR_TAGS' for n in line['nodes']}
        def endpoint_for_face(sid, other):
            p = shape(candidates[sid]['source_geometry'])
            nodes = [n for n in eligible_nodes if n in source.projected and p.covers(Point(source.projected[n]))]
            if not nodes:
                nodes = [n for n in source.outline(sid) if n in source.projected and legal_faces[sid].covers(Point(source.projected[n]))]
                if not nodes:
                    return {'status': 'NO_OMEGA_LEGAL_ORIGINAL_BOUNDARY_NODE', 'source_area_id': sid}
                number = min(nodes)
                return {**endpoint(number, 'ORIGINAL_SOURCE_FACE_OUTER_BOUNDARY_NODE; NO_INDEPENDENT_ELIGIBLE_LINE_NODE_AVAILABLE'),
                    'network_binding_class': 'SOURCE_BOUNDARY_INTERFACE_QUERY; FACE_ATTACHMENT_REQUIRED_IF_ABSENT_FROM_NATIVE_GRAPH',
                    'mode_binding': 'SAME_ORIGINAL_NODE_AND_COORDINATE; ATTACH_ONLY_TO_ADMITTED_CONTAINING_FACE; NO_BINDING_WHEN_FACE_ABSENT',
                    'source_area_id': sid, 'omega_covers': True,
                    'selection_rule': 'LOWEST_ORIGINAL_NODE_ID_AMONG_OMEGA_COVERED_OUTER_BOUNDARY_NODES'}
            number = sorted(nodes, key=lambda n: (-other.distance(Point(source.projected[n])), n))[0]
            return endpoint(number, 'ORIGINAL_SOURCE_NODE_ON_INDEPENDENT_ELIGIBLE_LINE_WITHIN_SOURCE_P')
        def endpoint(number, basis):
            node = source.nodes[number]
            return {'id': f'node/{number}', 'native_id': f'node/{number}',
                    'xy': list(source.projected[number]), 'wgs84': [node['lon'], node['lat']],
                    'source_node_tags': node.get('tags', {}), 'source_node_version': node.get('version'),
                    'basis': basis, 'coordinates_moved': False,
                    'mode_binding': 'EXACT_SAME_NATIVE_NODE_ID_AND_COORDINATE_ALL_MODES; MISSING_GRAPH_NODE_IS_A_REPORTED_FAILURE'}
        for mechanism in selected:
            a, b = mechanism['a_source_id'], mechanism['b_source_id']
            line = by_line.get(b)
            if line is not None:
                geometry = shape(line['geometry'])
                start = endpoint_for_face(a, geometry)
                # Use a distinct native line endpoint far from face A; no snapping.
                refs = list(dict.fromkeys(line['nodes']))
                if refs:
                    number = sorted(refs, key=lambda n: (-shape(candidates[a]['source_geometry']).distance(Point(source.projected[n])), n))[0]
                    end = endpoint(number, 'ORIGINAL_SOURCE_NODE_ON_B_LINE; FARTHEST_FROM_A_SOURCE_FACE_THEN_NODE_ID')
                else:
                    end = {'status': 'NO_COMPLETE_NATIVE_LINE_NODE'}
                layer = line['tags'].get('layer', '0')
                level = line['tags'].get('level', '0')
                if 'id' in end and (layer != '0' or level != '0'):
                    end['layer_aware_native_graph_id'] = f"{end['id']}@layer={layer}@level={level}"
            else:
                start = endpoint_for_face(a, shape(candidates[b]['source_geometry']))
                end = endpoint_for_face(b, shape(candidates[a]['source_geometry']))
            endpoint_requests.append({**mechanism, 'start': start, 'end': end,
                'task_role': 'LOCAL_MECHANISM_QUERY_NO_DOOR_OR_ENTRANCE_ASSERTION',
                'selection_uses_route_reachability': False, 'source_clip_sha256': scene['source_sha256']})
    global_record = {'scene_id_area_count': sum(len(s['area_ids']) for s in lock['scenes']),
        'added_scene_id_area_count': sum(len(s['added_area_ids']) for s in lock['scenes']),
        'global_unique_type_id_version_timestamp_count': len(unique),
        'global_old_unique_count': len(old), 'global_new_vs_any_old_unique_count': len(set(unique) - old),
        'globally_repeated_across_clips_count': sum(len(v) > 1 for v in unique.values()),
        'unique_area_identity': 'TYPE/ID + SOURCE_VERSION + OSM_BASE_TIMESTAMP; CROSS_CLIP COPIES ARE NOT INDEPENDENT_AREA_EVIDENCE',
        'objects': [{'source_id': k[0], 'version': k[1], 'source_timestamp': k[2], 'scenes': v} for k, v in sorted(unique.items())],
        'raw_highway_line_scene_id_count': sum(line_counts.values()), 'raw_highway_line_status_counts': dict(line_counts)}
    write(out / 'global_source_identity.json', global_record)
    endpoint_lock = {'role': 'PRE_NEW_ROUTE_EXACT_NATIVE_ENDPOINT_FREEZE', 'route_results_read': False,
        'mechanism_lock_sha256': sha256((out / 'mechanism_queries_lock.json').read_bytes()).hexdigest(),
        'queries': sorted(endpoint_requests, key=lambda r: r['mechanism_id']),
        'limitations': ['Tag-eligible source nodes are selected before graph reachability is inspected.',
            'The rejection case may be absent from the ground graph by design.',
            'All endpoints are existing source nodes, never generated building entrances.']}
    endpoint_path = out / 'mechanism_request_endpoints_lock.json'
    if endpoint_path.exists() and read(endpoint_path) != endpoint_lock:
        raise ValueError('PRE_ROUTE_ENDPOINT_LOCK_CHANGED')
    write(endpoint_path, endpoint_lock)
    return global_record, endpoint_lock


def export_rejected_relations():
    """Rejection diagnostics are separate from the frozen admitted population."""
    out = ROOT / 'data/connectivity'
    counts = {}
    for row in read(ROOT / 'data/scene_manifest.json')['scenes']:
        ident = row['scene_id']
        source = Source(read(ROOT / row['source_path']))
        rejected = [r for r in read(out / f'{ident}_source_inventory.json')
                    if r['explicit_frozen_admission_tags'] and r['status'] != 'ADMITTED' and r['source_geometry'] is not None]
        rejected_ids = {r['source_id'] for r in rejected}
        faces = [{**r, 'source_geometry': shape(r['source_geometry']), 'omega': shape(r['omega'])}
                 for r in read(out / f'{ident}_faces.json')]
        faces.extend({'source_id': r['source_id'], 'tags': r['tags'], 'status': r['status'],
                      'source_geometry': shape(r['source_geometry']), 'omega': GeometryCollection()}
                     for r in rejected)
        lines = [{**r, 'geometry': shape(r['geometry']) if r['geometry'] is not None else None}
                 for r in read(out / f'{ident}_native_lines.json')]
        common = read(out / f'{ident}_full_common.json')
        # Parsed once, without importing or constructing a routing graph.
        from src.common_constraints import parsed_contract
        rows = [r for r in geometric_relations(ident, source, faces, lines, parsed_contract(common))
                if r['a_source_id'] in rejected_ids or r['b_source_id'] in rejected_ids]
        write(out / f'{ident}_rejected_relations.json', rows)
        counts[ident] = {'rejected_explicit_faces_with_source_P': len(rejected), 'diagnostic_relations': len(rows)}
    write(ROOT / 'audits/source_inventory_rejected_relations.json', {'scope': 'ADDITIONAL_REJECTED_SOURCE_GEOMETRY_DIAGNOSTICS; NOT_NEW_GRAPH_CANDIDATES',
          'route_results_read': False, 'counts': counts})
    return counts
