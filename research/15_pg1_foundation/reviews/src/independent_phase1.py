"""Independently compare authored lineage/render data to SHA-bound raw ZIP objects.

No author code imports. Projection uses pyproj; geometry uses Shapely.
"""
from pathlib import Path
from collections import Counter
import argparse, gzip, hashlib, json, zipfile,os
from pyproj import Transformer
from shapely.geometry import Point, LineString, Polygon, shape

ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser();parser.add_argument('--require-six',action='store_true');args=parser.parse_args()
projection=Transformer.from_crs(4326,32651,always_xy=True)
PEDS={'footway','path','pedestrian','steps','living_street','bridleway','cycleway'}
results=[]
with zipfile.ZipFile(Path(os.environ.get('PG1_REVIEW_R1_ZIP',ROOT.parent/'PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip'))) as z:
    for folder in sorted((ROOT/'phase1/data').iterdir()):
        if not (folder/'scene.json').exists(): continue
        sid=folder.name;rawbytes=z.read(f'data/scenes/{sid}/source.osm.json');raw=json.loads(rawbytes)
        objects={f"{e['type']}/{e['id']}":e for e in raw['elements']}
        nodes={e['id']:projection.transform(e['lon'],e['lat']) for e in raw['elements'] if e['type']=='node'}
        scene=json.loads((folder/'scene.json').read_text(encoding='utf8'))
        summary=json.loads((folder/'summary.json').read_text(encoding='utf8'))
        lineage=[json.loads(l) for l in gzip.decompress((folder/'object_lineage.jsonl.gz').read_bytes()).splitlines()]
        admission=[json.loads(l) for l in gzip.decompress((folder/'native_admission.jsonl.gz').read_bytes()).splitlines()]
        topology_nodes=set()
        for segment in admission:
            source_way=objects[segment['source_id']];i=segment['segment_index'];nativeids=source_way['nodes'][i:i+2]
            assert segment['source_node_ids']==nativeids
            if segment['status']=='KEEP_NATIVE':topology_nodes.update(nativeids)
        features={f['properties']['source_id']:f for f in scene['features']}
        lineages={r['source_id']:r for r in lineage};fail=[];checks=Counter()
        if set(lineages)!=set(objects):fail.append('lineage_source_id_set')
        if len(lineages)!=len(lineage):fail.append('duplicate_lineage')
        if hashlib.sha256(rawbytes).hexdigest()!=summary['source_sha256']:fail.append('source_hash')
        for ident,r in lineages.items():
            obj=objects[ident];tags=obj.get('tags',{})
            if r['raw']['tags']!=tags:fail.append(f'{ident}:raw_tags')
            if set(r['import']['tags_retained'])|set(r['import']['tags_dropped_from_context'])!=set(tags):fail.append(f'{ident}:tag_partition')
            if bool(r['render']['new_review_render'])!=(ident in features):fail.append(f'{ident}:render_presence')
            if ident not in features: continue
            feature=features[ident];prop=feature['properties']
            if prop['tags']!=tags:fail.append(f'{ident}:feature_tags')
            if prop['source_clip_sha256']!=summary['source_sha256']:fail.append(f'{ident}:feature_sha')
            if prop['source_version']!=obj.get('version'):fail.append(f'{ident}:source_version')
            if obj['type']=='node' and prop['native_topology_endpoint']!=(obj['id']in topology_nodes):fail.append(f'{ident}:native_topology_endpoint')
            expected=None
            if obj['type']=='node':expected=Point(nodes[obj['id']])
            elif obj['type']=='way' and len(obj.get('nodes',[]))>=2 and all(n in nodes for n in obj['nodes']):
                xy=[nodes[n] for n in obj['nodes']]
                if feature['geometry']['type']=='Polygon':expected=Polygon(xy)
                elif feature['geometry']['type']=='LineString':expected=LineString(xy)
            if expected is not None:
                checks['source_to_feature_geometries']+=1
                if shape(feature['geometry']).hausdorff_distance(expected)>1e-6:fail.append(f'{ident}:source_geometry_changed')
            else:checks['relation_geometry_not_reconstructed']+=1
            if bool(feature.get('import_geometry'))!=bool(prop['imported_context']):fail.append(f'{ident}:import_geometry_presence')
            if bool(feature.get('diagnostic_geometry'))!=bool(prop['diagnostic_render']):fail.append(f'{ident}:diagnostic_geometry_presence')
            if obj['type']=='way' and len(obj.get('nodes',[]))>=2 and all(n in nodes for n in obj['nodes']):
                xy=[nodes[n] for n in obj['nodes']]
                for stage in ['import_geometry','diagnostic_geometry']:
                    stagegeo=feature.get(stage)
                    if stagegeo is None:continue
                    checks[stage+'_original_way']+=1
                    if stagegeo['type']=='Polygon':
                        assert obj['nodes'][0]==obj['nodes'][-1]
                        expected_stage=Polygon(xy)
                    elif stagegeo['type']=='LineString':expected_stage=LineString(xy)
                    else:checks[stage+'_other_type_not_reconstructed']+=1;continue
                    if shape(stagegeo).hausdorff_distance(expected_stage)>1e-6:fail.append(f'{ident}:{stage}:source_coordinates')
            checks['all_feature_tags']+=1
        for edge in scene['native_edges']:
            props=edge['properties'];ident=props['source_id'];obj=objects[ident];idx=props['segment_index']
            checks['native_source_segments']+=1
            a,b=obj['nodes'][idx:idx+2]
            if shape(edge['geometry']).hausdorff_distance(LineString([nodes[a],nodes[b]]))>1e-6:fail.append(f'{ident}:{idx}:native_geometry')
            if obj.get('tags',{}).get('foot') in {'no','private'}:fail.append(f'{ident}:native_explicit_foot_conflict')
        for family,values in summary['counts'].items():
            subset=[r for r in lineage if family in r['families']]
            if len(subset)!=values['raw_objects']:fail.append(f'{family}:summary_raw_count')
            if sum(bool(r['render']['new_review_render']) for r in subset)!=values['review_render']:fail.append(f'{family}:summary_render_count')
        roadway_ids={i for i,o in objects.items() if o['type']=='way' and o.get('tags',{}).get('highway')}
        visible_roadway_ids=set(features)&roadway_ids
        classes=Counter(objects[i]['tags']['highway'] for i in roadway_ids)
        nativeids={e['properties']['source_id']for e in scene['native_edges']}
        nativeclass=Counter(objects[i].get('tags',{}).get('highway','NO_HIGHWAY_TAG')for i in nativeids)
        nativeevidence=Counter(e['properties']['evidence']for e in scene['native_edges'])
        results.append({'scene_id':sid,'source_raw_objects':len(objects),'lineage_rows':len(lineage),'render_features':len(features),'raw_highway_ways':len(roadway_ids),'render_highway_ways':len(visible_roadway_ids),'highway_missing_render':sorted(roadway_ids-set(features)),'road_classes':dict(sorted(classes.items())),'checks':dict(checks),'failures':fail,'native_render_edges':len(scene['native_edges']),'native_admitted_source_way_classes':dict(sorted(nativeclass.items())),'native_segment_evidence_counts':dict(sorted(nativeevidence.items())),'native_road_scientific_limit':'Source-derived admitted linear segments include vehicle-road axes and SHARED_STREET_ASSUMPTION; not all dedicated footways/sidewalks or verified legal pedestrian passage. Existing road admission unchanged.','historical_route_scope':scene['info']['history']['status'],'summary_sha256':hashlib.sha256((folder/'summary.json').read_bytes()).hexdigest()})
out={'scope':'All per-object tags / original IDs / point-way geometry / native segment coordinates; relation geometry not independently reconstructed; semantic admission math and global VG not recomputed','scenes':results,'six_scenes_present':len(results)==6,'failure_count':sum(len(r['failures']) for r in results)}
(ROOT/'reviews/independent_phase1.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'scenes':len(results),'failure_count':out['failure_count'],'checked_geometries':sum(r['checks'].get('source_to_feature_geometries',0) for r in results)}))
assert not out['failure_count']
if args.require_six:assert len(results)==6
