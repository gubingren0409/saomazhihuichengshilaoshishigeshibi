"""Validate bundled frozen sources and execute shared APP source preparation.

This program builds no routes, reads no benchmark reference, and makes no network
requests. The source/face graph files are bundled, so replay needs no personal
Windows path or old project directory.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.scene_data import list_scenes, load_scene, file_sha, source_negative_areas


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--scene',help='One frozen scene; omitted means all six')
    p.add_argument('--output',type=Path,default=ROOT/'AUDIT/source_preparation.json')
    args=p.parse_args();rows=[];grass=set();started=time.perf_counter()
    for record in list_scenes()['scenes']:
        if args.scene and record['scene_id']!=args.scene:continue
        scene=load_scene(record['scene_id'])
        row={'scene_id':record['scene_id'],'source_sha256':file_sha(ROOT/record['source_path']),
            'mapped_edges_sha256':file_sha(ROOT/record['mapped_edges_path']),
            'registered_doors':scene['doors'],'source_preparation':scene['source_info'],
            'permission_negative_area_ids':[a['source_id']for a in source_negative_areas(record['scene_id'])],
            'full_context_counts':{k:len(v)for k,v in scene['full_observed']['context'].items()},
            'source_graph_nodes':scene['combined_source_graph'].number_of_nodes(),
            'source_graph_arcs':scene['combined_source_graph'].number_of_edges()}
        grass.update(tuple(k)for k in row['source_preparation']['native_grass_segment_keys'])
        rows.append(row)
        print(json.dumps({'scene_id':row['scene_id'],'doors':len(scene['doors']),
            'source_graph_nodes':row['source_graph_nodes'],'source_prepare_s':scene['source_info']['time_s']},ensure_ascii=False),flush=True)
    report={'role':'AUTHOR_SOURCE_PREPARATION_NO_ROUTE_SOLVER','channel':'APP_NATURAL_QUERY',
        'sources':rows,'unique_grass_native_segments':len(grass),
        'unique_grass_segment_keys':[list(k)for k in sorted(grass)],
        'new_external_requests':0,'routes_computed':0,'elapsed_s':time.perf_counter()-started,
        'scope':'Source SHA, exact target-building door identity, full-source S1 native graph, frozen R4-REV1 mapped edges, all implicit restrictive areas; no field verification'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'prepared_scenes':len(rows),'unique_grass_segments':len(grass),'output':str(args.output),'elapsed_s':report['elapsed_s']}),flush=True)


if __name__=='__main__':main()
