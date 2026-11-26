"""Independent map identity checks; never imports a planner or constructs route graphs."""
import argparse
import collections
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import os
import math
import re
import zipfile
import xml.etree.ElementTree as ET

from pyproj import Transformer
from shapely.geometry import Polygon, Point, LineString, MultiLineString, box, shape
from shapely.ops import linemerge, polygonize, unary_union

ROOT=Path(__file__).resolve().parents[1]
RAW=Path(r'C:/Users/28489/.codex/visualizations/2026/10/10/01a12554-d978-7d60-bdf2-97caf96e0581/OSM_GEOAPIFY_PED_AREA_CONNECTIVITY_R1/data/scenes/sh-huangpu-01/source.osm.json')
RAW_SHA='3219eccb7a7d37ea463895c63cc98688d66e0abe6b85575d38ea53ec023afc91'
PROJECT=Transformer.from_crs(4326,32651,always_xy=True).transform

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(name,data):
    (ROOT/'audits'/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def canonical(data):return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def bindings():
    initial=read(ROOT/'audit/initial_binding.json');results=[]
    for record in initial['archives']:
        p=Path(record['path']);assert sha(p)==record['sha256']
        with zipfile.ZipFile(p)as z:
            assert z.testzip()is None
            m=json.loads(z.read('MANIFEST_SHA256.json'))
            for r in m['files']:
                b=z.read(r['path']);assert len(b)==r['bytes']and hashlib.sha256(b).hexdigest()==r['sha256'],r['path']
            results.append({'path':str(p),'sha256':sha(p),'members':len(z.namelist()),'manifest_files':len(m['files']),'CRC_all_bytes_SHA':'PASS'})
    assert sha(RAW)==RAW_SHA
    original=Path(initial['archives'][1]['path'])
    with zipfile.ZipFile(original)as z:
        for p in (ROOT/'data/frozen').rglob('*'):
            if p.is_file():assert p.read_bytes()==z.read(p.relative_to(ROOT/'data/frozen').as_posix())
    registry=[json.loads(x)for x in (ROOT/'data/frozen/audit/experiment_registry.jsonl').read_text().splitlines()]
    assert len(registry)==24 and sum(r['result']['solver_invoked']for r in registry)==22
    save('independent_binding.json',{'reviewer':'/root/recon_independent','checked_at':now(),'status':'PASS','archives':results,'original_raw_sha256':RAW_SHA,'historical_attempts':24,'historical_actual_solver_calls':22,'new_solver_calls':0,'routing_graph_rebuilds':0})

def identity():
    assert sha(RAW)==RAW_SHA
    raw=read(RAW);objects={(o['type'],o['id']):o for o in raw['elements']};nodes={o['id']:o for o in raw['elements']if o['type']=='node'}
    def xy(n):return PROJECT(nodes[n]['lon'],nodes[n]['lat'])
    target=objects['way',161090899];poly=Polygon([xy(n)for n in target['nodes']]);entrances=[]
    for n,role,coords in [(6897141353,'main',(121.4712158,31.2299607)),(6897145227,'exit',(121.4706605,31.2305674))]:
        node=objects['node',n];assert (node['lon'],node['lat'])==coords
        assert node['version']==2 and node['tags']['entrance']==role and n in target['nodes']
        projected=xy(n);dist=poly.boundary.distance(Point(projected));assert dist<1e-8
        entrances.append({'source_id':f'node/{n}','raw':node,'xy':projected,'native_member_of_target':True,'boundary_distance_m':dist})
    assert target['tags']['name']=='上海博物馆'and target['tags']['building']=='yes'and poly.is_valid
    assert target['tags']['addr:street']=='人民大道'and target['tags']['addr:housenumber']=='201'
    assert 'People Square'in target['tags'].get('name:pt','')
    candidates=[o for o in raw['elements']if o['type']=='way'and(o.get('tags',{}).get('name')=='黄陂北路'or o.get('tags',{}).get('name:zh')=='黄陂北路')]
    roads=[o for o in candidates if o['tags'].get('highway')=='tertiary'];platform=[o for o in candidates if o['tags'].get('highway')=='platform']
    assert len(roads)==7 and [o['id']for o in platform]==[478271881]
    assert {o['id']for o in roads}=={10628430,24576913,513272949,654297629,1074409256,1074771160,1125986386}
    endpoints=collections.Counter(n for o in roads for n in (o['nodes'][0],o['nodes'][-1]));merged=linemerge(MultiLineString([[xy(n)for n in o['nodes']]for o in roads]))
    assert merged.geom_type=='LineString' and sorted(n for n,c in endpoints.items()if c==1)==[132491635,476794486]
    road_rows=[]
    highway_ways=[o for o in raw['elements']if o['type']=='way'and o.get('tags',{}).get('highway')]
    for o in roads:
        line=LineString([xy(n)for n in o['nodes']]);intersections=[]
        for n in o['nodes']:
            others=[{'source_id':f"way/{q['id']}",'name':q.get('tags',{}).get('name'),'highway':q['tags']['highway']}for q in highway_ways if q['id']!=o['id']and n in q.get('nodes',[])]
            if others:intersections.append({'source_node_id':n,'same_native_node_highways':others})
        road_rows.append({'source_id':f"way/{o['id']}",'raw':o,'bounds_xy':line.bounds,'source_polyline_length_m':line.length,'shared_source_nodes':intersections})
    confounders=[{'source_id':f"{o['type']}/{o['id']}",'tags':o.get('tags',{})}for o in raw['elements']if('历史博物馆'in o.get('tags',{}).get('name','')or'上海大剧院'in o.get('tags',{}).get('name',''))]
    oldlock=read(ROOT/'data/frozen/audit/window_lock.json')
    oldwindow=next(w for w in oldlock['windows']if w['window_id']=='native')
    oldframe=box(*oldwindow['bounds_xy']);oldsidewalk=objects['way',39764359]
    assert oldsidewalk['tags']=={'footway':'sidewalk','highway':'footway'}and not oldframe.intersects(poly)
    frozen=read(ROOT/'data/frozen/maps/trial_map_data.json');diagnostic=next(w for w in frozen['windows']if w['window_id']=='native')
    diagnostic_node_ids={q[k]for q in diagnostic['queries']for k in ['start_node','end_node']}
    assert not diagnostic_node_ids&{6897141353,6897145227}
    previous={'old_anchor':'way/39764359','actual_source_tags':oldsidewalk['tags'],'old_window_bounds_xy':oldwindow['bounds_xy'],
              'old_window_intersects_target':False,'old_window_contains_target':False,'old_window_center_to_target_centroid_m':oldframe.centroid.distance(poly.centroid),
              'old_queries':diagnostic['queries'],'old_query_endpoints_are_museum_doors':False,
              'meaning':'Old northwestsidewalktopologydiagnostics retained unchanged; cannot be relabelled as Museumdoor routes. Correct source-to-render fidelity did not establish correct businessscene.'}
    out={'reviewer':'/root/recon_independent','checked_at':now(),'status':'PASS_SOURCE_TARGET_IDENTITY','source_sha256':RAW_SHA,'target_raw':target,'target_bounds_xy':poly.bounds,'target_centroid_xy':list(poly.centroid.coords)[0],'target_native_relation':'Standalone closed buildingway with13references includingrepeatclosure; bothregistereddoorsliteralwaymembers','entrances':entrances,'huangpi_road_ways':road_rows,'same_name_bus_platform_not_road':platform,'road_chain_geo_check':{'method':'GISlinemergeoforiginalsourcepolylines; notroutegraphorsearch','merged_geometry_type':merged.geom_type,'unpaired_source_end_nodes':[132491635,476794486],'bounds_xy':merged.bounds},'confounders':confounders,'prior_wrong_scene':previous,'scope_statement':'Frozen-sourceidentity verified usingnative buildingID,tags,address,PeopleSquarebranchtext,andexactdoor-membership; no independent currentfieldgeometry certification','algorithm_runs_added':0,'solver_calls_added':0,'BFS_calls_added':0,'routing_graph_rebuilds_added':0}
    save('independent_identity.json',out)

def protection():
    initial=read(ROOT/'audit/initial_binding.json');checks=[]
    for row in initial['old_git_indices']:
        p=Path(row['path']);ok=p.exists()==row['exists']and(sha(p)if p.exists()else None)==row['sha256'];checks.append({'path':str(p),'match':ok});assert ok,p
    env={**os.environ,'GIT_OPTIONAL_LOCKS':'0'}
    for row in initial['old_repositories']:
        p=Path(row['path']);head=subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],env=env,text=True).strip();status=subprocess.check_output(['git','--git-dir='+str(p/'.git'),'--work-tree='+str(p),'status','--porcelain'],env=env,text=True)
        assert head==row['HEAD']and status==row['status'];checks.append({'path':str(p),'match':True,'HEAD':head})
    for row in initial['archives']:
        assert sha(row['path'])==row['sha256'];checks.append({'path':row['path'],'match':True})
    assert sha(RAW)==RAW_SHA
    save('independent_protection.json',{'reviewer':'/root/recon_independent','checked_at':now(),'status':'PASS','checks':checks,'raw_sha256':RAW_SHA,'new_solver_calls':0})

def scene():
    """Independent raw primitive reconstruction, target extent and exported objects."""
    raw=read(RAW);objects={(o['type'],o['id']):o for o in raw['elements']}
    ns={o['id']:o for o in raw['elements']if o['type']=='node'}
    xy={n:PROJECT(o['lon'],o['lat'])for n,o in ns.items()}
    def geometry(o):
        if o['type']=='node':return Point(xy[o['id']])
        if o['type']=='way':
            ids=o.get('nodes',[])
            if len(ids)<2 or any(n not in xy for n in ids):return None
            coords=[xy[n]for n in ids];t=o.get('tags',{});closed=len(ids)>3 and ids[0]==ids[-1]
            area=closed and t.get('area')!='no'and(t.get('area')=='yes'or t.get('building')not in(None,'no')or t.get('building:part')not in(None,'no')or any(k in t for k in['landuse','landcover','leisure','area:highway'])or t.get('natural')in{'water','wetland','wood','scrub','sand','beach','grassland','heath'}or t.get('waterway')=='riverbank'or t.get('place')=='square'or t.get('amenity')in{'parking','school','hospital','university','kindergarten','place_of_worship','grave_yard','marketplace','college'})
            if area:
                p=Polygon(coords)
                if p.is_valid:return p
            return LineString(coords)
        if o.get('tags',{}).get('type')!='multipolygon':return None
        grouped={'outer':[],'inner':[]}
        for m in o.get('members',[]):
            role=m.get('role')or'outer'
            if m['type']!='way'or role not in grouped or('way',m['ref'])not in objects:return None
            w=objects['way',m['ref']];ids=w.get('nodes',[])
            if len(ids)<2 or any(n not in xy for n in ids):return None
            grouped[role].append(LineString([xy[n]for n in ids]))
        outer=unary_union(list(polygonize(grouped['outer'])));inner=unary_union(list(polygonize(grouped['inner'])))
        if outer.is_empty or(not inner.is_empty and not outer.covers(inner)):return None
        g=outer.difference(inner)
        return g if not g.is_empty and g.is_valid else None
    context=read(ROOT/'data/scene.json');frames=context['views'];full=box(*context['bounds_xy']);expected={};unresolved=[]
    for o in raw['elements']:
        if not o.get('tags'):continue
        g=geometry(o)
        if g is None:unresolved.append(f"{o['type']}/{o['id']}");continue
        if g.intersects(full):expected[f"{o['type']}/{o['id']}"]=(o,g)
    got={f['source_id']:f for f in context['features']};failures=[]
    if set(expected)!=set(got):failures.append({'raw_source_export_set':{'missing':sorted(set(expected)-set(got)),'extra':sorted(set(got)-set(expected))}})
    for sid,(o,g)in expected.items():
        if sid not in got:continue
        f=got[sid]
        if f['tags']!=o['tags']or f['source_version']!=o.get('version'):failures.append('rawmetadata:'+sid)
        gg=shape(f['geometry'])
        if not gg.equals(g)and not gg.equals_exact(g,1e-7):
            if gg.hausdorff_distance(g)>1e-7 or abs(gg.area-g.area)>1e-5:failures.append('rawgeometry:'+sid)
    target=shape(context['target']['geometry']);roadids=set(context['road']['road_way_ids'])
    assert roadids=={f'way/{n}'for n in[10628430,24576913,513272949,654297629,1074409256,1074771160,1125986386]}
    assert context['target']['building_id']=='way/161090899'and context['default_view']=='target_overview'
    assert context['target']['conflicting_place_ids']==['node/5530017322','way/39763758']
    doors={d['source_id']:d for d in context['target']['doors']}
    for sid,n,role in [('node/6897141353',6897141353,'main'),('node/6897145227',6897145227,'exit')]:
        d=doors[sid];assert d['tags']['entrance']==role and d['xy']==list(xy[n])and d['wgs84']==[ns[n]['lon'],ns[n]['lat']]
    targetplusroads=unary_union([target,*[expected[sid][1]for sid in roadids]])
    b=targetplusroads.bounds
    predicted=[__import__('math').floor((b[0]-120)/10)*10,__import__('math').floor((b[1]-120)/10)*10,__import__('math').ceil((b[2]+120)/10)*10,__import__('math').ceil((b[3]+120)/10)*10]
    assert predicted==context['bounds_xy']
    checks=[]
    for view in frames:
        fr=box(*view['bounds_xy']);ids=sorted(sid for sid,(_,g)in expected.items()if g.intersects(fr))
        assert ids==sorted(view['source_ids'])and len(ids)==view['source_count']
        assert fr.covers(target)and all(fr.covers(Point(d['xy']))for d in doors.values())
        assert view['width_m']==view['bounds_xy'][2]-view['bounds_xy'][0]and view['height_m']==view['bounds_xy'][3]-view['bounds_xy'][1]
        h=hashlib.sha256(json.dumps(view['bounds_xy'],separators=(',',':')).encode()).hexdigest();assert h==view['viewport_hash']
        if view['id']in{'block_context','huangpi_detail'}:assert all(fr.covers(expected[sid][1])for sid in roadids)
        checks.append({'view_id':view['id'],'objects':len(ids),'target_fully_inside':True,'both_original_doors_inside':True,'bounds_xy':view['bounds_xy'],'viewport_hash':h})
    assert all(not f['is_target_building']or f['source_id']=='way/161090899'for f in got.values())
    assert [f['source_id']for f in got.values()if f['is_target_building']]==['way/161090899']
    packaged=ROOT/'data/source/sh-huangpu-01.osm.json'
    assert sha(packaged)==RAW_SHA
    packaged_raw=read(packaged)
    for o in packaged_raw['elements']:assert o==objects[o['type'],o['id']]
    out={'reviewer':'/root/recon_independent','checked_at':now(),'status':'PASS_SOURCE_SCENE_AND_TARGET_ANCHORED_VIEWS'if not failures else'FAIL','source_sha256':RAW_SHA,'raw_drawable_objects_in_block':len(expected),'exported_context_objects':len(got),'packaged_full_raw_records_checked_against_original':len(packaged_raw['elements']),'packaged_full_source_sha256':RAW_SHA,'source_object_failures':failures,'views':checks,'all_target_identity_and_original_door_checks':True,'all7roads_complete_in_block_and_road_detail':True,'block_window_independent_union_rule':predicted,'same_name_platform_not_in_roadset':'way/478271881','independent_current_field_reference':'REAL_WORLD_GEOMETRY_UNVERIFIED','algorithm_runs_added':0,'solver_calls_added':0,'BFS_calls_added':0,'routing_graph_rebuilds_added':0}
    save('independent_scene.json',out)
    if failures:raise AssertionError(failures)

def figures():
    context=read(ROOT/'data/scene.json');views={v['id']:v for v in context['views']};features={f['source_id']:f for f in context['features']}
    frozen=read(ROOT/'data/frozen/maps/trial_map_data.json');old=next(w for w in frozen['windows']if w['window_id']=='native');query=old['queries'][0]
    manifest=read(ROOT/'audit/figure_manifest.json');checks=[];failures=[];vertices=0;door_checks=0;outside=0
    number=r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'
    def svg_xy(path):
        nums=[float(v)for v in re.findall(number,path.get('d',''))]
        return list(zip(nums[::2],nums[1::2]))
    def same_points(a,b,tol=.0012):
        return len(a)==len(b)and all(math.dist(x,y)<=tol for x,y in zip(a,b))
    assert len(manifest['figures'])==8
    for fig in manifest['figures']:
        view=views[fig['view_id']];extent=view['bounds_xy'];frame=box(*extent)
        assert fig['extent_xy']==extent
        for row in fig['files']:assert (ROOT/row['path']).is_file()and (ROOT/row['path']).stat().st_size==row['bytes']and sha(ROOT/row['path'])==row['sha256'],row['path']
        svgfile=ROOT/next(r['path']for r in fig['files']if r['path'].endswith('.svg'));tree=ET.parse(svgfile);xml=tree.getroot();groups={e.get('id'):e for e in xml.iter()if e.get('id')}
        all_ids=[e.get('id')for e in xml.iter()if e.get('id')];assert len(all_ids)==len(set(all_ids)),svgfile
        assert not any(e.tag.endswith('image')for e in xml.iter()),'Unexpected raster backgroundinSVG'
        basehashes=set();viewporthashes=set()
        for panel in fig['panels']:
            assert panel['base']['source_ids']==sorted(view['source_ids'])
            assert panel['base']['extent_xy']==extent
            selected=[f for f in context['features']if f['source_id']in view['source_ids']]
            assert canonical(selected)==panel['base_map_hash']==view['base_map_hash']
            assert panel['viewport_hash']==view['viewport_hash'];basehashes.add(panel['base_map_hash']);viewporthashes.add(panel['viewport_hash'])
            t=panel['world_to_svg_points'];prefix=t['svg_id_prefix'];assert abs(t['scale_x']+t['scale_y'])<1e-9
            def transform(xy):return(t['scale_x']*xy[0]+t['offset_x'],t['scale_y']*xy[1]+t['offset_y'])
            targetid=prefix+'verified_museum_way_161090899_0';assert targetid in groups,targetid
            targetpaths=[e for e in groups[targetid].iter()if e.tag.endswith('path')and e.get('d')];assert targetpaths
            actual=svg_xy(targetpaths[0]);expected=[transform(xy)for xy in context['target']['geometry']['coordinates'][0]]
            # SVG closes polygon withz, so compare unique realvertices regardlesswinding.
            for point in expected:
                assert min(math.dist(point,q)for q in actual)<.0012,(svgfile,targetid,point)
            assert panel['target']['target_id']=='way/161090899'and panel['target']['target_fully_inside']
            for door in context['target']['doors']:
                group=groups[prefix+'original_door_'+door['source_id'].replace('/','_')]
                uses=[e for e in group.iter()if e.tag.endswith('use')and e.get('x')is not None]
                assert len(uses)==1
                point=(float(uses[0].get('x')),float(uses[0].get('y')))
                assert math.dist(point,transform(door['xy']))<.0012
                assert next(d for d in panel['target']['door_markers']if d['source_id']==door['source_id'])['xy']==door['xy'];door_checks+=1
            variant=panel['variant'];overlay=panel['overlay']
            if variant is not None:
                graph=old['variants'][variant];ed={e['edge_id']:e for e in graph['edges']}
                assert overlay['frozen_edges_sha256']==canonical(graph['edges'])
                assert overlay['edge_ids']==[e['edge_id']for e in graph['edges']]
                assert overlay['route_edge_ids']==query['results'][variant].get('edge_ids',[])
                assert overlay['status']==query['results'][variant]['status']and overlay['query_id']==query['query_id']
                visible=sorted(e['edge_id']for e in graph['edges']if LineString(e['xy']).intersects(frame));assert sorted(panel['visible_frozen_edge_ids'])==visible
                for kind,ids in [('edge_',overlay['edge_ids']),('saved_route_',overlay['route_edge_ids'])]:
                    for eid in ids:
                        e=ed[eid];key=prefix+kind+eid.replace('/','_').replace(':','_');group=groups.get(key)
                        if group is None:
                            # Artistmaybeculledonlywhenwhollyoutsideaxes; visiblegeometrymustremain.
                            assert eid not in visible,(svgfile,key);outside+=1;continue
                        paths=[p for p in group.iter()if p.tag.endswith('path')and p.get('d')]
                        expected=[transform(p)for p in e['xy']]
                        a=[p for p in paths if re.search(r'\bM\s',p.get('d',''))]
                        if not a:
                            assert eid not in visible;outside+=1;continue
                        actual=svg_xy(a[-1])
                        if not same_points(actual,expected):
                            # Matplotlib clips line output to canvas+1point margin, notworldgeometry.
                            w=float(xml.get('width').replace('pt',''));h=float(xml.get('height').replace('pt',''));clip=LineString(expected).intersection(box(-1,-1,w+1,h+1))
                            coords=list(clip.coords)if clip.geom_type=='LineString'and not clip.is_empty else[]
                            if not same_points(actual,coords):failures.append({'figure':fig['name'],'artist':key,'actual':actual,'expected':expected,'canvas_clipped':coords})
                        if e['geometry_status']=='SCHEMATIC'or e.get('hypothesis'):
                            assert any('stroke-dasharray'in p.get('style','')for p in paths),(svgfile,key)
                        vertices+=1
            assert panel['target']['target_geometry_sha256']==canonical(context['target']['geometry'])
        assert len(basehashes)==len(viewporthashes)==1
        checks.append({'figure':fig['name'],'panels':len(fig['panels']),'same_target':True,'both_original_markers_correct':True,'base_hash':next(iter(basehashes)),'viewport_hash':next(iter(viewporthashes)),'same_base_extent_scale':True,'svg_unique_ids':True})
    out={'reviewer':'/root/recon_independent','checked_at':now(),'status':'PASS_STATIC_MAP_TARGET_AND_FROZEN_OVERLAYS'if not failures else'FAIL','figure_pairs':len(checks),'checks':checks,'target_polygon_checks':sum(len(f['panels'])for f in manifest['figures']),'original_door_marker_checks':door_checks,'actual_saved_overlay_artist_checks':vertices,'outside_canvas_artists':outside,'failures':failures,'real_world_geometry_status':'REAL_WORLD_GEOMETRY_UNVERIFIED','solver_calls_added':0,'routing_graph_rebuilds_added':0}
    save('independent_figures.json',out)
    if failures:raise AssertionError(failures[:3])

def browser():
    from playwright.sync_api import sync_playwright
    out={'reviewer':'actual independent /root/recon_independent','checked_at':now(),'views':[],'page_errors':[],'external_requests':[],'solver_calls_added':0,'routing_graph_rebuilds_added':0}
    scene_data=read(ROOT/'data/scene.json');byview={v['id']:v for v in scene_data['views']};doors={d['source_id']:d for d in scene_data['target']['doors']}
    with sync_playwright()as pw:
        b=pw.chromium.launch(channel='chrome',headless=True)
        page=b.new_page(viewport={'width':1740,'height':1240},accept_downloads=True)
        page.on('pageerror',lambda e:out['page_errors'].append(str(e)))
        def route(r):
            if r.request.url.startswith(('http://127.0.0.1:53531/','file:','blob:','data:')):r.continue_()
            else:out['external_requests'].append(r.request.url);r.abort()
        page.route('**/*',route)
        for transport,url in [('HTTP','http://127.0.0.1:53531/'),('OFFLINE',(ROOT/'web/index.html').as_uri())]:
            page.goto(url,wait_until='domcontentloaded');page.wait_for_selector('#map-context .target-outline')
            d=page.evaluate('window.RECON_MAP_DIAGNOSTICS');assert d['view_id']=='target_overview'and d['target_building_id']=='way/161090899'
            body=page.locator('body').inner_text()
            assert '西北'in body and'不是本轮上海博物馆到门路线'in body
            hero=page.locator('#map-context .target-outline').bounding_box()
            assert hero and 0<hero['y']+hero['height']/2<1240 and hero['width']>80
            if transport=='HTTP':
                out['initial_firstscreen_target_box']=hero
                page.screenshot(path=str(ROOT/'audits/independent_initial_target.png'),full_page=False)
            for viewid,v in byview.items():
                page.select_option('#view',viewid)
                for qi in range(2):
                    page.select_option('#query',str(qi));d=page.evaluate('window.RECON_MAP_DIAGNOSTICS')
                    assert d['target_visible']and d['target_fully_inside']and all(d['doors_visible'].values())and d['base_sets_equal']
                    assert d['extent']==v['bounds_xy']
                    assert len({p['base_map_sha256']for p in d['panels']})==1 and len({p['viewport_sha256']for p in d['panels']})==1
                    for p in d['panels']:assert sorted(p['source_ids'])==sorted(v['source_ids'])
                    scales=page.evaluate("Array.from(document.querySelectorAll('svg.map')).map(s=>1/Math.abs(s.getScreenCTM().a))")
                    assert len(scales)==4 and all(abs(s-p['meters_per_css_px'])<1e-6 for s,p in zip(scales,d['panels']))
                    # Originalmarkerdisplaycentres must map to unchanged projected sourcepoints.
                    for sid,door in doors.items():
                        element=page.locator('#map-context .target-marker[data-door-id="'+sid+'"]')
                        assert element.get_attribute('data-door-role')==door['tags']['entrance']
                        marker=element.locator('circle,path').first
                        if marker.evaluate('(e)=>e.tagName')=='circle':
                            loc=[float(marker.get_attribute('cx')),float(marker.get_attribute('cy'))]
                        else:
                            nums=[float(x)for x in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',marker.get_attribute('d'))]
                            loc=[(min(nums[::2])+max(nums[::2]))/2,(min(nums[1::2])+max(nums[1::2]))/2]
                        # DOMgetBBox uses reducedprecision for largeworldcoords;
                        # compare original SVG coordinateattributes instead.
                        assert math.dist(loc,[door['xy'][0],-door['xy'][1]])<1e-6
                    # The four source maps must have identical actuald/pointgeometry andstyle, not merelyIDcounters.
                    bases=page.evaluate("['context','R0','R1','R2'].map(v=>Array.from(document.querySelectorAll('#map-'+v+' .source-feature')).map(g=>[g.dataset.sourceId,g.innerHTML]).sort((a,b)=>a[0].localeCompare(b[0])))")
                    assert all(bases[0]==x for x in bases[1:])
                    out['views'].append({'transport':transport,'view_id':viewid,'query_id':d['query_id'],'target':'way/161090899','both_doors_original':True,'actual_base_geometry_equal':True,'source_objects':len(d['panels'][0]['source_ids']),'extent':d['extent'],'source_layers':d['panels'][0].get('base_map_sha256')})
            if transport=='HTTP':
                page.select_option('#view','target_overview');page.select_option('#query','0')
                outline=page.locator('#map-context .target-outline');outline.click()
                evidence=json.loads(page.locator('#evidence').inner_text());assert '161090899'in json.dumps(evidence)
                page.locator('#map-context .target-marker[data-door-id="node/6897145227"] path').first.click()
                evidence=json.loads(page.locator('#evidence').inner_text());assert 'exit'in json.dumps(evidence)and'6897145227'in json.dumps(evidence)
                with page.expect_download()as dl:page.click('#export-evidence')
                dl.value.save_as(str(ROOT/'audits/independent_door_evidence.json'))
                with page.expect_download()as dl:page.click('#export')
                dl.value.save_as(str(ROOT/'audits/independent_view_export.json'))
                with page.expect_download()as dl:page.click('#export-svg')
                dl.value.save_as(str(ROOT/'audits/independent_view_export.svg'));ET.parse(ROOT/'audits/independent_view_export.svg')
                if not page.locator('#layer-controls').evaluate('(e)=>e.open'):page.click('#layer-controls-toggle')
                for key in ['buildings','R2']:
                    loc=page.locator('#layers input[data-layer="'+key+'"]')
                    if loc.is_enabled():loc.uncheck();assert page.locator('#map-context .target-outline').count()==1;loc.check()
                page.locator('#history').evaluate('(e)=>{const p=e.closest("details");if(p)p.open=true}')
                for value in page.locator('#history option').evaluate_all('(a)=>a.map(x=>x.value)'):
                    before=page.evaluate('window.RECON_MAP_DIAGNOSTICS');page.select_option('#history',value);after=page.evaluate('window.RECON_MAP_DIAGNOSTICS');assert before==after
                page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(ROOT/'audits/independent_target_browser.png'),full_page=False)
        # Common smallerdesktopviewport must also show actualtargetwithoutinitialscroll.
        page.set_viewport_size({'width':1366,'height':900});page.goto('http://127.0.0.1:53531/',wait_until='domcontentloaded');page.wait_for_selector('#map-context .target-outline')
        small=page.locator('#map-context .target-outline').bounding_box();assert small and 0<small['y']+small['height']/2<900 and small['width']>60
        out['smaller_firstscreen_target_box']=small
        b.close()
    out.update({'status':'PASS_INDEPENDENT_ACTUAL_TARGET_BROWSER','default_is_actual_museum':True,'HTTP_query_views':10,'offline_query_views':10,'target_and_door_clicks':'PASS','exports':'JSON_EVIDENCE_JSON_VIEW_SVG_PASS','history_does_not_rebind_original_results':'PASS','real_world_geometry_status':'REAL_WORLD_GEOMETRY_UNVERIFIED','HTML_sha256':sha(ROOT/'web/index.html'),'JS_sha256':sha(ROOT/'web/viewer.js'),'CSS_sha256':sha(ROOT/'web/viewer.css')})
    assert not out['page_errors']and not out['external_requests']
    save('independent_browser.json',out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['bindings','identity','protection','scene','figures','browser']);args=p.parse_args()
    {'bindings':bindings,'identity':identity,'protection':protection,'scene':scene,'figures':figures,'browser':browser}[args.mode]()
    print(json.dumps({'mode':args.mode,'status':'PASS','solver_calls_added':0}))
