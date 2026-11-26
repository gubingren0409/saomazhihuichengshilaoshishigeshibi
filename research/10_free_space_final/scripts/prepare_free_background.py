"""Derive small DISPLAY_ONLY street backgrounds from frozen clips.

Uses the same whole-source dependency exclusions as the guard exporter, but
160m instead of the algorithm's 80m. These files are never predictor inputs.
"""
import argparse
import json
from pathlib import Path

from prepare_common import export_guard, read, sign, PROJECT
from shapely import make_valid
from shapely.geometry import Point, LineString, Polygon, mapping

ROOT=Path(__file__).resolve().parents[1]


def main(args):
    m=read(ROOT/'data/task_manifest.json')
    frozen=ROOT/'frozen_context'
    old=read(frozen/'data/task_manifest.json')
    ledger={(r['parent_task_id'],r['masking_mode']):r for r in
        (json.loads(l) for l in (frozen/'data/mask_dependency_ledger.jsonl').read_text(encoding='utf-8').splitlines())}
    wanted={r['parent_task_id']:r for r in m['instances']}
    records=[]
    for clip in sorted({r.get('source_clip','sh-huangpu-01.osm.json') for r in wanted.values()}):
        path=args.source_dir/clip
        expected={r['source_clip_sha256'] for r in old['instances'] if r.get('source_clip')==clip}
        if {sign(path)}!=expected:
            raise ValueError('Source identity mismatch '+clip)
        source=read(path)
        for parent,row in sorted(wanted.items()):
            if row.get('source_clip','sh-huangpu-01.osm.json')!=clip:
                continue
            row=dict(row,context_radius_m=160,source_clip=clip,source_clip_sha256=sign(path))
            obs=read(ROOT/row['observed'])
            guard=export_guard(row,obs,source,ledger.get((parent,row.get('masking_mode')),{}))
            data={'role':'DISPLAY_ONLY_160M_STREET_CONTEXT_NEVER_PREDICTOR_INPUT',
                  'source_clip':clip,'source_sha256':row['source_clip_sha256'],
                  'source_timestamp':guard.get('source_timestamp'),
                  'source_dependency_check':guard['source_dependency_check'],
                  'road_centerlines':guard['road_centerlines']}
            if parent=='NORTH':
                # Natural unmasked case only. Broader reading context is not
                # an expansion of the 30m inferred surface or predictor input.
                frame=Point(obs['domain']['anchor_xy']).buffer(1000,quad_segs=32)
                nodes={n['id']:PROJECT(n['lon'],n['lat']) for n in source['elements'] if n['type']=='node'}
                fs=[]
                for way in source['elements']:
                    if way['type']!='way':continue
                    tags=way.get('tags',{});refs=way.get('nodes',[])
                    if len(refs)<2 or any(n not in nodes for n in refs):continue
                    xy=[nodes[n] for n in refs];layer=None
                    if len(xy)>=4 and refs[0]==refs[-1]:
                        if tags.get('building'):layer='building'
                        elif tags.get('natural')=='water' or tags.get('water'):layer='water'
                        elif tags.get('landuse') in {'grass','flowerbed'}:layer='grass'
                        elif tags.get('leisure') in {'park','garden'}:layer='park'
                    if layer:g=make_valid(Polygon(xy))
                    elif tags.get('highway'):
                        layer='way' if tags['highway'] in {'footway','path','pedestrian','steps','corridor','crossing'} else 'road'
                        g=LineString(xy)
                    else:continue
                    g=g.intersection(frame)
                    if g.is_empty:continue
                    fs.append({'layer':layer,'geometry':mapping(g),'source_id':'way/'+str(way['id']),
                               'tags':tags,'role':'DISPLAY_ONLY_UNMASKED_NATURAL_FULL_ROUTE_BACKGROUND'})
                data['full_features']=fs
                data['full_features_limitations']='Closed native ways and highway lines only. Multipolygon relations are not reconstructed; background is not a complete obstacle audit.'
            target=ROOT/'data/visual_background'/f'{parent}.json';target.parent.mkdir(exist_ok=True,parents=True)
            target.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
            records.append({'parent':parent,'file':target.relative_to(ROOT).as_posix(),'sha256':sign(target),
                            'roads':len(data['road_centerlines'])})
        del source
    (ROOT/'audits/visual_background.json').write_text(json.dumps({'role':'DISPLAY_ONLY','records':records},indent=2)+'\n',encoding='utf-8')
    print('DISPLAY_ONLY backgrounds',len(records))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-dir',type=Path,required=True);main(p.parse_args())
