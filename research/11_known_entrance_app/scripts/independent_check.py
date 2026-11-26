"""Independent numerical/source checks; never imports the author planner/scorer.

This checker deliberately reports its source scope. It is not a field audit and
does not reconstruct every source parser decision or claim topology completeness.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, shape
from shapely import make_valid
from shapely.ops import unary_union, polygonize
from shapely.strtree import STRtree

EPS = 1e-6
DENIED = {'no', 'private', 'customers', 'destination', 'delivery', 'permit',
          'restricted', 'agricultural', 'forestry'}
PUBLIC = {'yes', 'designated', 'permissive', 'official'}
STRUCTURES = {'wall', 'fence', 'hedge', 'retaining_wall', 'chain', 'city_wall', 'jersey_barrier'}
GATES = {'gate', 'lift_gate', 'swing_gate', 'turnstile', 'kissing_gate'}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def denied(tags):
    return (tags.get('foot', tags.get('access')) in DENIED or tags.get('locked') == 'yes' or
            any(k.endswith(':conditional') and k.split(':')[0] in {'foot', 'access', 'oneway'} for k in tags))


def non_ground(tags):
    return any(tags.get(k) not in (None, '', '0', 'no', 'false')
               for k in ('level', 'layer', 'bridge', 'tunnel', 'indoor', 'repeat_on'))


def area_role(tags):
    return tags.get('area') != 'no' and (tags.get('area') == 'yes' or
            tags.get('amenity') in {'parking', 'parking_space'} or
            'landuse' in tags or 'leisure' in tags or
            tags.get('building') not in (None, 'no') or
            tags.get('natural') in {'water', 'wetland'})


class IndependentSource:
    """Own source projection/ring reconstruction, no source adapter import."""
    def __init__(self, path):
        self.path = Path(path)
        raw = read(path)
        self.raw = raw
        self.objects = {f"{o['type']}/{o['id']}": o for o in raw['elements']}
        tx = Transformer.from_crs('EPSG:4326', 'EPSG:32651', always_xy=True)
        self.nodes = {o['id']: o for o in raw['elements'] if o['type'] == 'node'}
        self.xy = {n: tx.transform(o['lon'], o['lat']) for n, o in self.nodes.items()}
        self.ways = {o['id']: o for o in raw['elements'] if o['type'] == 'way'}
        self.lines = {}
        self.areas = {}
        self.unparsed = []
        for n, w in self.ways.items():
            ns = w.get('nodes', [])
            if len(ns) < 2 or any(k not in self.xy for k in ns):
                continue
            self.lines[f'way/{n}'] = LineString([self.xy[k] for k in ns])
            if len(ns) >= 4 and ns[0] == ns[-1]:
                self.areas[f'way/{n}'] = make_valid(Polygon([self.xy[k] for k in ns]))
        for sid, o in self.objects.items():
            if o['type'] != 'relation' or o.get('tags', {}).get('type') != 'multipolygon':
                continue
            outer, inner = [], []
            for m in o.get('members', []):
                g = self.lines.get(f"way/{m['ref']}") if m['type'] == 'way' else None
                if g is None:
                    continue
                (inner if m.get('role') == 'inner' else outer).append(g)
            try:
                op = unary_union(list(polygonize(unary_union(outer))))
                ip = unary_union(list(polygonize(unary_union(inner))))
                if not op.is_empty:
                    self.areas[sid] = make_valid(op.difference(ip))
                else:
                    self.unparsed.append(sid)
            except Exception as e:
                self.unparsed.append({'id': sid, 'error': type(e).__name__})

    def limits(self):
        rows = []
        for sid, g in self.areas.items():
            t = self.objects[sid].get('tags', {})
            kind = ('BUILDING' if t.get('building') not in (None, 'no') or t.get('building:part') not in (None, 'no') else
                    'WATER' if t.get('natural') in {'water', 'wetland'} or t.get('waterway') in {'riverbank', 'dock'} or t.get('landuse') in {'reservoir', 'basin'} else
                    'PERMISSION' if area_role(t) and denied(t) else None)
            if kind:
                rows.append((sid, kind, g, t))
        for sid, g in self.lines.items():
            o = self.objects[sid]
            t = o.get('tags', {})
            if t.get('barrier') in STRUCTURES | GATES:
                openings = []
                for n in o.get('nodes', []):
                    tag = self.nodes[n].get('tags', {})
                    if tag.get('barrier') in GATES | {'bollard', 'cycle_barrier', 'entrance'} and not denied(tag) and not non_ground(tag):
                        openings.append(Point(self.xy[n]).buffer(.30))
                barrier = g.buffer(.15).difference(unary_union(openings))
                rows.append((sid, 'PHYSICAL_BARRIER', barrier, t))
            elif denied(t) and not (sid in self.areas and area_role(t)):
                rows.append((sid, 'RESTRICTED_LINEAR', g.buffer(.15), t))
        for n, o in self.nodes.items():
            t = o.get('tags', {})
            allowed_gate = t.get('barrier') in GATES and not non_ground(t) and not denied(t) and (t.get('foot') in PUBLIC or t.get('access') in PUBLIC)
            if t.get('barrier') in STRUCTURES | GATES and not allowed_gate:
                rows.append((f'node/{n}', 'PHYSICAL_BARRIER_POINT', Point(self.xy[n]).buffer(.15), t))
        return rows

    def door(self, sid):
        o = self.objects.get(sid)
        if o is None or o['type'] != 'node':
            return {'source_node_exists': False}
        t = o.get('tags', {})
        return {'source_node_exists': True, 'original_xy': self.xy[o['id']],
                'tags': t, 'registered_entrance': t.get('entrance') not in (None, 'no')}


def route_metrics(edges, expected_start=None, expected_end=None, multiplier=1):
    """Recompute all polyline vertex lengths, never trust saved length fields."""
    total, layers, cost, continuity, saved_errors = 0., defaultdict(float), 0., [], []
    last = None
    for index, edge in enumerate(edges):
        xy = edge.get('xy') or edge.get('geometry', {}).get('coordinates')
        if not xy or len(xy) < 2:
            saved_errors.append({'edge': index, 'error': 'MISSING_POLYLINE'})
            continue
        length = sum(math.dist(a, b) for a, b in zip(xy, xy[1:]))
        if last is not None:
            gap = math.dist(last, xy[0])
            if gap > EPS:
                continuity.append({'before_edge': index, 'gap_m': gap})
        last = xy[-1]
        layer = edge.get('layer', edge.get('evidence_layer', 'UNKNOWN'))
        layers[layer] += length
        total += length
        cost += length * (multiplier if layer in {'inferred', 'assumed', 'unknown'} else 1)
        for field, measured in [('length_m', length), ('cost_m', length * (multiplier if layer in {'inferred', 'assumed', 'unknown'} else 1))]:
            if field in edge and abs(edge[field] - measured) > EPS:
                saved_errors.append({'edge': index, 'field': field, 'saved': edge[field], 'measured': measured})
    first_xy = (edges[0].get('xy') or edges[0].get('geometry', {}).get('coordinates'))[0] if edges else None
    return {'length_m': total, 'layer_lengths': dict(layers), 'cost_m': cost,
            'continuity_gaps': continuity, 'saved_segment_errors': saved_errors,
            'start_residual_m': math.dist(first_xy, expected_start) if first_xy is not None and expected_start is not None else None,
            'end_residual_m': math.dist(last, expected_end) if last is not None and expected_end is not None else None}


def source_route_check(source, edges, *, gate_buffer_m=.30):
    """Independent direct source check of areas, native provenance and lawn.

    Raw barrier way-member openings follow the frozen .15/.30m geometry policy;
    this numerical policy is not a source-measured barrier width. Missing level
    tags remain unknown; this checker never upgrades them to ground facts.
    """
    limits = source.limits()
    idx = STRtree([r[2] for r in limits])
    grass = [(sid, g) for sid, g in source.areas.items()
             if source.objects[sid].get('tags', {}).get('landuse') in {'grass', 'meadow', 'flowerbed', 'flower_bed'} or
             source.objects[sid].get('tags', {}).get('leisure') == 'flowerbed' or
             source.objects[sid].get('tags', {}).get('landcover') in {'grass', 'flowerbed'} or
             source.objects[sid].get('tags', {}).get('garden:type') == 'flower_bed']
    conflicts, native_errors, grass_conflicts, derived_errors, direction_errors = [], [], [], [], []
    for index, edge in enumerate(edges):
        xy = edge.get('xy') or edge.get('geometry', {}).get('coordinates')
        line = LineString(xy)
        sid = edge.get('source_id')
        layer = edge.get('layer')
        native = layer == 'native'
        tags = source.objects.get(sid, {}).get('tags', {})
        bridge = native and (tags.get('bridge') not in (None, 'no', '0', 'false') or tags.get('tunnel') not in (None, 'no', '0', 'false'))
        if native and sid in source.lines:
            excess = line.difference(source.lines[sid].buffer(EPS)).length
            if excess > EPS:
                native_errors.append({'edge': index, 'source_id': sid, 'off_source_m': excess})
            one = tags.get('oneway:foot')
            if one is None and tags.get('highway') in {'footway', 'path', 'steps'}:
                one = tags.get('oneway')
            direction = source.lines[sid].project(Point(xy[-1])) - source.lines[sid].project(Point(xy[0]))
            if (one in {'yes', 'true', '1'} and direction < -EPS) or (one in {'-1', 'reverse'} and direction > EPS):
                direction_errors.append({'edge': index, 'source_id': sid, 'oneway_foot': one, 'signed_source_progress_m': direction})
        elif native:
            native_errors.append({'edge': index, 'source_id': sid, 'error': 'NATIVE_SOURCE_WAY_MISSING'})
        elif layer == 'derived' and sid in source.areas:
            excess = line.difference(source.areas[sid].buffer(EPS)).length
            if excess > EPS:
                derived_errors.append({'edge': index, 'source_id': sid, 'outside_source_face_m': excess})
        for k in idx.query(line):
            object_id, kind, g, t = limits[k]
            inside = line.intersection(g.buffer(-1e-7)).length
            if inside > EPS and not (bridge and kind != 'PERMISSION'):
                conflicts.append({'edge': index, 'source_id': object_id, 'kind': kind, 'inside_m': inside})
            if kind == 'PERMISSION':
                shared = line.intersection(g.boundary).length
                if shared > EPS and not (native and tags.get('foot') in PUBLIC and not denied(tags)):
                    conflicts.append({'edge': index, 'source_id': object_id, 'kind': 'PERMISSION_BOUNDARY_NO_EXPLICIT_NATIVE_FOOT', 'shared_m': shared})
        if not native:
            for object_id, g in grass:
                hit = line.intersection(g).length
                if hit > EPS:
                    grass_conflicts.append({'edge': index, 'source_id': object_id, 'length_m': hit})
    return {'source_sha256': digest(source.path), 'source_constraint_geometry_count': len(limits),
            'area_conflicts': conflicts, 'native_source_errors': native_errors,
            'new_lawn_conflicts': grass_conflicts, 'derived_source_errors': derived_errors,
            'explicit_direction_errors': direction_errors, 'unparsed_multipolygons': source.unparsed,
            'scope': 'DIRECT_RAW_BUILDING_WATER_PERMISSION_AREA_AND_LINE_BARRIER_GEOMETRY_WITH_FROZEN_GATE_BUFFER_POLICY; NATIVE_LINE_AND_DERIVED_FACE_PROVENANCE; NOT_FIELD_OR_COMPLETE_UNKNOWN_LAYER_VERIFICATION'}


def check_run(run, source):
    route = run.get('route') or run.get('result', {}).get('route') or run
    edges = route.get('edges') or route.get('segments') or []
    target = run.get('door', run.get('target', run.get('entrance', {})))
    target_id = target.get('id', target.get('native_id'))
    door = source.door(target_id) if target_id else None
    method = run.get('method', run.get('normalized_request', {}).get('method', run.get('input', {}).get('method', 'F0')))
    multiplier = 2 if method == 'F1' else 1
    start = run.get('start', {}).get('network_xy', route.get('start_xy'))
    end = door['original_xy'] if door and door.get('source_node_exists') else route.get('end_xy')
    metrics = route_metrics(edges, start, end, multiplier)
    for field, measured in [('length_m', metrics['length_m']), ('cost_weighted_m', metrics['cost_m'])]:
        if edges and field in route:
            metrics[field + '_saved_error'] = abs(route[field] - measured)
    purpose = run.get('normalized_request', {}).get('purpose', run.get('input', {}).get('purpose'))
    role_error = bool(door and door.get('tags', {}).get('entrance') == 'exit' and purpose == 'ENTER_BUILDING' and edges)
    return {'reviewer': '/root/e2e_review', 'author_functions_called': False,
            'request_id': run.get('request_id'), 'method': method, 'door_source_check': door,
            'metrics': metrics, 'exit_inbound_route_error': role_error,
            'source_check': source_route_check(source, edges) if edges else None,
            'limitations': ['No field/public-current-access verification', 'Does not assert unrecorded obstacles absent',
                            'Barrier widths use frozen policy buffers, not measurements; full unknown-level/source-completeness verification is outside scope']}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = check_run(read(args.run), IndependentSource(args.source))
    result.update(run_sha256=digest(args.run), run_path=args.run.as_posix())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
