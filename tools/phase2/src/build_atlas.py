"""Offline source-schema audit and real-geometry atlas; input identities stay external.
Usage: python build_atlas.py --root PATH --config PATH
Requires shapely. No network calls, tiles, generated geometry, routes or labels.
"""
import argparse, collections, csv, hashlib, html, json, math, pathlib
from shapely.geometry import shape, box
from shapely.ops import transform

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write_json(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def csv_rows(path, rows):
    if not rows: return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader();writer.writerows(rows)
def observed(count): return isinstance(count,int) and count>0

def build(root, config):
    root=pathlib.Path(root); scenes=json.loads(pathlib.Path(config).read_text(encoding='utf-8'))
    ledger=[json.loads(s) for s in (root/'request_log.jsonl').read_text(encoding='utf-8').splitlines()]
    by_path={x['path']:x for x in ledger if x['status']=='RETAINED'}
    registry=[]; layer_audit=[]; fields=[]; dimensions=[]; map_panels=[]; objects=[]
    for scene in scenes:
        counts={}; ids=[]; sourcehash={}; feature_layers=[]; missing=[]; geom_bounds=[]
        w,s,e,n=scene['bounds_wsen']; coslat=math.cos(math.radians((s+n)/2)); width=1000
        extent_width=(e-w)*coslat; extent_height=n-s
        scale=(width-60)/extent_width; frame_height=extent_height*scale; height=frame_height+110
        def xy(x,y,z=None): return (30+(x-w)*coslat*scale,30+(n-y)*scale)
        panel=[]
        for stem in scene['files']:
            layer=stem.replace('_crsfix','').split('_')[-1]; path=root/'samples'/f'{stem}.json'; rel=f'samples/{stem}.json'
            if not path.exists(): counts[layer]='UNKNOWN';missing.append(layer);continue
            payload=json.loads(path.read_text(encoding='utf-8')); feats=payload.get('features',[])
            sourcehash[rel]=digest(path); counts[layer]=len(feats)
            invalid=0; null=0; outside=0; rings=0; all_fields=collections.Counter(); observed_values={}
            for f in feats:
                props=f.get('properties') or {}; all_fields.update(k for k,v in props.items() if v is not None)
                for k,v in props.items():
                    if v is not None: observed_values.setdefault(k,collections.Counter())[str(v)]+=1
                ident=str(f.get('id') or props.get('objectid') or props.get('source_id') or props.get('id') or 'UNKNOWN')
                qualified=f"{scene['provider']}:{layer}:{ident}";ids.append(qualified)
                if not f.get('geometry'): null+=1;continue
                geom=shape(f['geometry']);invalid+=int(not geom.is_valid);outside+=int(not geom.intersects(box(w,s,e,n)))
                geom_bounds.append(geom.bounds)
                if geom.geom_type in ('Polygon','MultiPolygon'):
                    rings+=sum(len(g.interiors) for g in (geom.geoms if geom.geom_type=='MultiPolygon' else [geom]))
                objects.append(dict(scene_id=scene['scene_id'],layer=layer,source_object_id=qualified,geometry_type=geom.geom_type,valid=geom.is_valid,source_sha256=digest(path)))
                color={'buildings':'#c8bdd1','sidewalk':'#f3cf87','pedestrian':'#f3cf87','roads':'#94a1ad','green':'#abd3b7'}.get(layer,'#dddddd')
                title=html.escape(json.dumps(dict(source_object_id=qualified,properties=props),ensure_ascii=False))
                # Exact original rings retained; projection is local equirectangular DISPLAY ONLY.
                svg=transform(xy,geom).svg(scale_factor=.45,fill_color=color,opacity=.85)
                svg=svg.replace('<path ','<path fill-rule="evenodd" ').replace('stroke="#555555"','stroke="#596675"')
                panel.append(f'<g class="layer-{layer}"><title>{title}</title>{svg}</g>')
            for field in sorted(set(k for f in feats for k in (f.get('properties') or {}))):
                fields.append(dict(scene_id=scene['scene_id'],layer=layer,field=field,feature_count=len(feats),nonnull_count=all_fields[field],observed_values=json.dumps(observed_values.get(field,{}).most_common(8),ensure_ascii=False)))
            cap=500 if scene['provider']=='NYC' else 400
            matched=payload.get('numberMatched','UNKNOWN');truncated=(len(feats)>=cap or isinstance(matched,int) and matched>len(feats))
            layer_audit.append(dict(scene_id=scene['scene_id'],layer=layer,features=len(feats),geometry_null=null,geometry_invalid=invalid,features_not_intersecting_request_bbox=outside,polygon_inner_rings=rings,number_matched=matched,truncated=truncated,source_sha256=digest(path),query_crs='EPSG:4326 bbox lonlat explicit' if scene['provider']=='HELSINKI' else 'SoQL WKT lonlat',output_crs=payload.get('crs','GeoJSON RFC7946'),source_date=payload.get('timeStamp',by_path.get(rel,{}).get('utc','UNKNOWN'))))
        actual_bounds=[min(b[0] for b in geom_bounds),min(b[1] for b in geom_bounds),max(b[2] for b in geom_bounds),max(b[3] for b in geom_bounds)] if geom_bounds else None
        dims={
           'building_geometry':('SILVER' if observed(counts.get('buildings')) else 'BRONZE','Actual municipal polygon sample with source IDs and ring/validity checks; independent boundary ground truth not yet available.' if observed(counts.get('buildings')) else 'NO_OBSERVATION: metadata extent only, no successful feature sample for this scene.'),
           'building_identity':('SILVER' if observed(counts.get('buildings')) else 'BRONZE','Object IDs read; named target association and official register reliability require per-object review.' if observed(counts.get('buildings')) else 'UNKNOWN: metadata extent only; no feature identity was read.'),
           'registered_entrance_geometry':('BRONZE','UNKNOWN: these sampled layers contain no entrance reference layer; no entrances inferred from outlines.'),
           'entrance_role':('BRONZE','UNKNOWN: official Oodi arrival page lists three facade-side entrances but no coordinate identities; no spatial door match yet.' if scene['scene_id']=='hel_oodi' else 'UNKNOWN: independent source not read.'),
           'public_access_opening':('SILVER' if scene['scene_id']=='hel_oodi' else 'BRONZE','Official Oodi arrival page supplies opening hours at audit time; applies to named library, not every block object; geometry/public status kept separate.' if scene['scene_id']=='hel_oodi' else 'UNKNOWN: mapped footprint does not demonstrate public entry permission.'),
           'pedestrian_network_topology':('BRONZE','UNKNOWN: sidewalk/pedestrian polygons are not a verified line network; no crossing topology reference.'),
           'sidewalk_area_geometry':('SILVER' if observed(counts.get('sidewalk',counts.get('pedestrian'))) else 'BRONZE','Structured authoritative area sample; completeness and legal traversal are not established.' if observed(counts.get('sidewalk',counts.get('pedestrian'))) else 'UNKNOWN: no retained successful sidewalk/pedestrian-area sample.'),
           'crossing_geometry_topology':('BRONZE','UNKNOWN: no separate crossing layer fetched.'),
           'pedestrian_open_area':('SILVER' if scene['provider']=='HELSINKI' and observed(counts.get('pedestrian')) else 'BRONZE','UNKNOWN: YLRE responses exceeded preview budget and were not retained; no complete feature evidence.' if scene['provider']=='HELSINKI' else 'UNKNOWN: sidewalk source excludes some plazas and ignores landscaping openings; no plaza layer fetched.'),
           'road_carriageway_context':('SILVER' if observed(counts.get('roads')) else 'BRONZE','UNKNOWN: road layer not retained; negative space is not road geometry.'),
           'obstacles_access_levels':('BRONZE','Partial buildings/green areas only; water, fences, barriers, legal access, level and opening conflicts UNKNOWN.'),
           'spatial_independence':('BRONZE','Provisional geographic groups only; network closure not acquired. Same-city candidates conservatively grouped; no frozen split.')}
        for dim,(tier,evidence) in dims.items():dimensions.append(dict(scene_id=scene['scene_id'],dimension=dim,tier=tier,evidence=evidence,missing_reference=('NONE' if dim=='public_access_opening' and scene['scene_id']=='hel_oodi' else 'Independent reference or semantics review pending'),source_sha256=json.dumps(sourcehash)))
        entry={**scene,'retrieval_date':'2026-11-12','status':'EXPOSED_DISCOVERY_CANDIDATE' if geom_bounds else 'EXPOSED_METADATA_EXTENT_ONLY','evaluation_split':'UNASSIGNED_NOT_FROZEN','candidate_unit':'street_block/site; not yet independently identified target building','target_building_object_id':'UNKNOWN','category_status':'sampling intent; per-building type/name association not fully verified','object_counts':counts,'entrance_count':'UNKNOWN','registered_entrance_reference_status':'NOT_ACQUIRED','entrance_role':'UNKNOWN','public_opening':'official Oodi page only; not spatially matched' if scene['scene_id']=='hel_oodi' else 'UNKNOWN','road_sidewalk_crossing_area_obstacle_fields':'see field_inventory.csv / layer_audit.json / dimension_contract.csv','source_hashes':sourcehash,'source_object_ids':sorted(set(ids)),'observed_geometry_bounds_wsen':actual_bounds,'coverage_gaps':missing+['entrances','crossing topology','line network','access/levels','comprehensive obstacles'],'redistribution':'LOCAL_REVIEW_ONLY; public source redistribution decision pending','exposure':'AUTHOR_AND_REVIEWER_SOURCE_AND_MAP_EXPOSED; never call this candidate blind','prior_project_tuning':'UNKNOWN historical prior inspection; no new method evaluation or tuning in this phase','provisional_group':'NEW_YORK_NETWORK_UNKNOWN' if scene['provider']=='NYC' else 'HELSINKI_NETWORK_UNKNOWN','dimensions':{k:v[0] for k,v in dims.items()}}
        registry.append(entry)
        bar=100/111320*coslat*scale/coslat
        clipid='clip-'+scene['scene_id']
        layercontrols=' '.join(f'<label><input type="checkbox" checked onchange="toggleLayer(this,\'{layer}\',\'{scene["scene_id"]}\')">{layer} {count}</label>' for layer,count in counts.items())
        no_data=f'<text x="80" y="{frame_height/2}" font-size="24">METADATA EXTENT ONLY — NO VERIFIED GEOMETRY</text>' if not geom_bounds else ''
        panel_svg=f'<svg id="map-{scene["scene_id"]}" viewBox="0 0 {width} {height}" role="img"><defs><clipPath id="{clipid}"><rect x="30" y="30" width="940" height="{frame_height}"/></clipPath></defs><rect width="1000" height="{height}" fill="#f8fafc"/><g clip-path="url(#{clipid})">'+''.join(panel)+no_data+f'</g><rect x="30" y="30" width="940" height="{frame_height}" fill="none" stroke="#516174"/><text x="945" y="22">N ↑</text><path d="M40,{frame_height+50} h{bar:.1f}" stroke="#263445" stroke-width="3"/><text x="40" y="{frame_height+75}">100 m (局部显示近似)</text><text x="350" y="{frame_height+75}">{html.escape(scene["scene_id"])} · EPSG:4326 · local display</text></svg>'
        license_url='https://creativecommons.org/licenses/by/4.0/' if scene['provider']=='HELSINKI' else 'https://data.cityofnewyork.us/stories/s/Terms-of-Use/k9k7-3cje'
        evidence_links=' · '.join(f'<a href="{html.escape(rel)}">{html.escape(pathlib.Path(rel).stem)}</a>' for rel in sourcehash)
        map_panels.append(f'<section id="{scene["scene_id"]}"><h2>{html.escape(scene["name"])}</h2><p>{html.escape(" / ".join(scene["categories"]))} · EXPOSED · UNASSIGNED · {html.escape(scene["license"])}</p><div class="controls">{layercontrols}</div>{panel_svg}<p>原始真实矢量；鼠标悬停读取对象ID/字段。完整源对象可能越出请求框，显示按请求框裁切，未删源几何。未读取图层与入口计数 UNKNOWN。此图不是注册入口/可通行/建筑真值审计。</p><p>{html.escape(scene["attribution"])}</p><p><a href="{license_url}">许可原文</a> · <a href="sources.json">官方来源与许可审计</a> · 原始本地样本 {evidence_links or "UNKNOWN"}</p><small>请求范围WSEN={scene["bounds_wsen"]}; 图层/字段/缺失证据见机器可读表。</small></section>')
    write_json(root/'candidate_registry.json',registry);write_json(root/'layer_audit.json',layer_audit)
    csv_rows(root/'field_inventory.csv',fields);csv_rows(root/'object_inventory.csv',objects);csv_rows(root/'dimension_contract.csv',dimensions)
    summary=[]
    for r in registry:
        summary.append(dict(scene_id=r['scene_id'],city=r['city'],categories='|'.join(r['categories']),candidate_unit=r['candidate_unit'],target_building_object_id=r['target_building_object_id'],status=r['status'],split=r['evaluation_split'],object_counts=json.dumps(r['object_counts']),entrance_count='UNKNOWN',license=r['license'],redistribution=r['redistribution'],source_hashes=json.dumps(r['source_hashes']),exposure=r['exposure'],provisional_group=r['provisional_group']))
    csv_rows(root/'candidate_registry.csv',summary)
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>PG1 G2 候选真实地图图册</title><style>body{font:16px/1.6 system-ui,sans-serif;background:#f0f4f8;color:#203246;margin:0 auto;max-width:1300px;padding:28px}h1{font-size:28px}section{background:white;margin:25px 0;padding:22px;border:1px solid #d7e0e8;border-radius:10px}svg{width:100%;height:auto}small{overflow-wrap:anywhere}.controls label{display:inline-block;margin:8px}a{color:#175b9c}.warning{background:#fff1d4;padding:18px}.legend{display:flex;gap:22px}.dot{display:inline-block;width:20px;height:12px}</style><h1>PG1 · G2 候选地图图册</h1><p class="warning">本地审查样本；尚未冻结Validation或Blind。所有展示候选均已暴露。实际取得的市政矢量图不等于完整步行路网、注册入口或独立真值。候选类别是采样目标，目标建筑关联仍待逐对象核定。禁止以这些图宣称盲测。</p><p>只含两个市政来源的5个小街区；OSM许可已审，但首轮Overpass超时未生成伪地图。Helsinki首轮12个空响应由bbox未声明CRS导致；原件保留，显式EPSG:4326修复后另存并渲染。NYC仅建筑/人行道，未读取的车行道/过街/障碍保持UNKNOWN。</p><div class="legend"><span><i class="dot" style="background:#c8bdd1"></i>建筑</span><span><i class="dot" style="background:#f3cf87"></i>人行道/轻交通面</span><span><i class="dot" style="background:#94a1ad"></i>车行道路面</span><span><i class="dot" style="background:#abd3b7"></i>绿地登记面</span></div><p>地图不请求在线瓦片。<a href="candidate_registry.csv">候选表</a> · <a href="dimension_contract.csv">逐维合同</a> · <a href="field_inventory.csv">字段非空统计</a> · <a href="spatial_pairs.csv">空间pair表</a> · <a href="README.md">来源/复现/限制</a></p>'''+''.join(map_panels)+'''<script>function toggleLayer(el,layer,id){document.querySelectorAll('#map-'+id+' .layer-'+layer).forEach(n=>n.style.display=el.checked?'':'none')}</script></html>'''
    (root/'index.html').write_text(document,encoding='utf-8')
    write_json(root/'atlas_build_receipt.json',dict(author_check_only=True,scene_count=len(registry),real_geometry_maps=sum(bool(r['observed_geometry_bounds_wsen']) for r in registry),metadata_only_panels=sum(not bool(r['observed_geometry_bounds_wsen']) for r in registry),feature_count=len(objects),http_requests=len(ledger),known_received_bytes=sum(x.get('bytes_received',0) for x in ledger),retained_file_bytes=sum(x.get('bytes_received',0) for x in ledger if x['status']=='RETAINED'),vector_requests=sum(x['path'].startswith('samples/') for x in ledger),vector_known_response_bytes=sum(x.get('bytes_received',0) for x in ledger if x['path'].startswith('samples/')),failed_vector_transfer_bytes='UNKNOWN for original OSM timeout; reserve 3,000,000 in budget',api_cost=0,source_code_sha256=digest(pathlib.Path(__file__)),index_sha256=digest(root/'index.html')))
    print('Built',sum(bool(r['observed_geometry_bounds_wsen']) for r in registry),'real geometry maps;',len(objects),'feature records; metadata-only panels',sum(not bool(r['observed_geometry_bounds_wsen']) for r in registry))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--config',type=pathlib.Path,required=True);a=p.parse_args();build(a.root,a.config)
