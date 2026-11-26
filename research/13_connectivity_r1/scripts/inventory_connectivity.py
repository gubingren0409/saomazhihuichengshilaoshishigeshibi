"""Serial, bounded source inventory. Run before any B1/B2/B3 route results."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import gc
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shapely.geometry import Point, mapping, shape
from src.common_constraints import build_contract, parsed_contract, digest
from src.connectivity_inventory import (feature, freeze_mechanisms, geometric_relations,
    inventory_scene, read, source_lines, supplemental_freeze, export_rejected_relations, write)
from src.face_geometry import compile_faces, serializable_face
from src.scene_data import load_scene, _prepared_scene


def immutable(path, payload):
    if path.exists() and read(path) != payload:
        raise ValueError('PRE_ROUTE_FREEZE_CHANGED:' + str(path))
    if not path.exists():
        write(path, payload)


def main():
    started = time.perf_counter()
    out = ROOT / 'data/connectivity'
    audit = ROOT / 'audits'
    manifest = read(ROOT / 'data/scene_manifest.json')
    old = {r['scene_id']: r for r in read(ROOT / 'data/face_selection_lock.json')['scenes']}
    summaries = []
    for row in manifest['scenes']:
        source, candidates, summary = inventory_scene(row, old[row['scene_id']]['area_ids'])
        write(out / f"{row['scene_id']}_source_inventory.json", candidates)
        write(out / f"{row['scene_id']}_inventory_summary.json", summary)
        summaries.append(summary)
        print(json.dumps({k: summary[k] for k in ('scene_id', 'old_count', 'selected_count', 'added_count', 'explicit_source_candidate_count', 'rejected_explicit_reasons')}, ensure_ascii=False), flush=True)
        del source, candidates
        gc.collect()
    lock = {'role': 'SOURCE_COMPLETE_PRE_ROUTE_FACE_POPULATION', 'crs': 'EPSG:32651',
        'route_results_read': False, 'new_api_calls': 0,
        'policy': 'UNCHANGED_AREA_REASON_SOURCE_MEMBERS_GROUND_PERMISSION_AND_FULL_COVERAGE; EXACT_COMPATIBLE_DUPLICATES_SUPPRESSED',
        'scenes': [{'scene_id': r['scene_id'], 'source_sha256': r['source_sha256'],
                    'area_ids': r['selected_area_ids'], 'old_area_ids': r['old_area_ids'],
                    'added_area_ids': r['added_area_ids']} for r in summaries]}
    immutable(out / 'source_selection_lock.json', lock)
    all_relations = []
    cfg = read(ROOT / 'config/frozen_region.json')
    for row in manifest['scenes']:
        scene_started = time.perf_counter()
        ident = row['scene_id']
        source, candidates, summary = inventory_scene(row, old[ident]['area_ids'])
        data = load_scene(ident)
        coverage = shape(data['full_guards']['coverage_geometry'])
        common = build_contract(data['full_observed'], data['full_guards'], cfg, domain=mapping(coverage))
        parsed = parsed_contract(common)
        faces = compile_faces(data, common, cfg, selected_area_ids=summary['selected_area_ids'])
        write(out / f'{ident}_faces.json', [serializable_face(f) for f in faces])
        write(out / f'{ident}_full_common.json', common)
        lines = source_lines(source, row)
        serial_lines = [{**r, 'geometry': mapping(r['geometry']) if r['geometry'] is not None else None} for r in lines]
        write(out / f'{ident}_native_lines.json', serial_lines)
        relations = geometric_relations(ident, source, faces, lines, parsed)
        write(out / f'{ident}_relations.json', relations)
        all_relations.extend(relations)
        features = []
        for face in faces:
            props = {'id': face['source_id'], 'source_id': face['source_id'], 'tags': face['tags'],
                'scene_id': ident, 'status': face['status'], 'old_population': face['source_id'] in old[ident]['area_ids'],
                'source_clip_sha256': row['source_sha256'], 'crs_of_measurements': 'EPSG:32651'}
            features.append(feature(face['source_geometry'], {**props, 'geometry_role': 'SOURCE_P'}))
            features.append(feature(face['omega'], {**props, 'geometry_role': 'LEGAL_OMEGA'}))
        write(out / f'{ident}_boundaries.geojson', {'type': 'FeatureCollection', 'features': features})
        if ident == 'sh-huangpu-01':
            door = Point(source.projected[6897141353])
            roi = door.buffer(450)
            museum_features = [f for f in features if shape(f['geometry']).is_empty is False and any(face['source_id'] == f['properties']['source_id'] and face['source_geometry'].intersects(roi) for face in faces)]
            for layer in data['map_layers']['features']:
                g = shape(layer['geometry'])
                if g.intersects(roi):
                    museum_features.append(feature(g, {**layer['properties'], 'geometry_role': 'SOURCE_CONTEXT', 'scene_id': ident}))
            relation_by_line = {}
            for relation in relations:
                if relation['kind'] == 'FACE_LINE':
                    relation_by_line.setdefault(relation['b_source_id'], []).append(relation)
            for line in lines:
                if line['geometry'] is not None and line['geometry'].intersects(roi):
                    museum_features.append(feature(line['geometry'], {k: v for k, v in line.items() if k != 'geometry'} | {
                        'id': line['source_id'], 'geometry_role': 'INDEPENDENT_NATIVE_SOURCE_LINE',
                        'relations': relation_by_line.get(line['source_id'], []), 'scene_id': ident}))
            for nid in (6897141353, 6897145227):
                museum_features.append(feature(Point(source.projected[nid]), {'id': f'node/{nid}', 'tags': source.nodes[nid].get('tags', {}), 'geometry_role': 'UNCHANGED_REGISTERED_DOOR', 'scene_id': ident}))
            write(out / 'museum_diagnostic.geojson', {'type': 'FeatureCollection', 'features': museum_features,
                'screenshot_binding': 'SCREENSHOT_REQUEST_UNBOUND', 'user_observation': 'PENDING_USER_OBSERVATION'})
        print(json.dumps({'scene_id': ident, 'faces': len(faces), 'statuses': dict(Counter(f['status'] for f in faces)),
            'source_lines': len(lines), 'relations': len(relations), 'time_s': time.perf_counter() - scene_started}, ensure_ascii=False), flush=True)
        del data, common, parsed, faces, source, lines, serial_lines, candidates
        _prepared_scene.cache_clear()
        gc.collect()
    immutable(out / 'relations_lock.json', {'role': 'PRE_NEW_ROUTE_SOURCE_RELATION_FREEZE',
        'source_selection_sha256': sha256((out / 'source_selection_lock.json').read_bytes()).hexdigest(),
        'probe_radius_m': 10, 'crs': 'EPSG:32651', 'relation_count': len(all_relations),
        'relations_sha256': digest(all_relations), 'route_results_read': False})
    immutable(out / 'mechanism_queries_lock.json', freeze_mechanisms(all_relations))
    supplemental_freeze()
    export_rejected_relations()
    write(audit / 'source_inventory_execution.json', {'role': 'SOURCE_INVENTORY_AUTHOR_SELF_CHECK',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'wall_time_s': time.perf_counter() - started,
        'scene_summaries': summaries, 'relation_count': len(all_relations),
        'mechanisms': read(out / 'mechanism_queries_lock.json'), 'map_api_calls': 0, 'new_geodata': False,
        'routes_computed': 0, 'source_bytes_modified': False, 'user_observation': 'PENDING_USER_OBSERVATION',
        'screenshot_binding': 'SCREENSHOT_REQUEST_UNBOUND',
        'limitations': ['Geometry classification is source-map evidence, not a field survey.',
            'Raw line tag eligibility is distinct from segment-level routing admission.',
            'Point touches never independently establish a positive-width passage.']})
    print('SOURCE_AND_RELATION_AND_MECHANISM_FREEZE_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
