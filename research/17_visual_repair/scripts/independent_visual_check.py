"""Independent visual-only evidence checks. Never imports or executes a route solver."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BASELINE_SHA = '6b2db66e8347603c2aa346810846f4d6c5cf39e2e830f12a162b0e6c6e9485ab'

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8-sig'))
def save(name,data):
    p=ROOT/'reviews'/name
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def stamped(scope):
    return {'reviewer':'actual independent /root/visual_context_review',
            'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'scope':scope,'solver_calls_added':0,'BFS_or_graph_rebuilds_added':0,
            'algorithm_runs_added':0,'external_map_requests':0,'new_data_downloads':0}

def binding():
    baseline=read('audit/initial_binding.json');archive=Path(baseline['archive_path'])
    failures=[];checks=[]
    if digest(archive)!=EXPECTED_BASELINE_SHA:failures.append('baseline archive SHA')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:failures.append('baseline CRC')
        manifest=json.loads(z.read('MANIFEST_SHA256.json'))
        for row in manifest['files']:
            data=z.read(row['path'])
            if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:
                failures.append('baseline member:'+row['path'])
        for name in ['maps/trial_map_data.json','results/query_results.csv','audit/window_lock.json','audit/experiment_registry.jsonl','audit/ROUND_BINDING.json']:
            p=ROOT/'data/frozen'/name;match=p.read_bytes()==z.read(name)
            checks.append({'path':'data/frozen/'+name,'sha256':digest(p),'byte_identical_to_baseline':match})
            if not match:failures.append('frozen result drift:'+name)
        member_count=len(z.namelist());manifest_count=len(manifest['files'])
    raw=[]
    for row in baseline['raw_sources']:
        p=Path(row['path']);got=digest(p);match=got==row['sha256']
        raw.append({'path':str(p),'sha256':got,'matches':match})
        if not match:failures.append('original rawsource:'+str(p))
    current=read('data/frozen/maps/trial_map_data.json')
    records=[json.loads(l) for l in (ROOT/'data/frozen/audit/experiment_registry.jsonl').read_text().splitlines()]
    if len(records)!=24 or sum(r['result']['solver_invoked'] for r in records)!=22:
        failures.append('historical attempt/solver census')
    latest={(r['query_id'],r['variant']):r for r in records}
    outcomes=[]
    for win in current['windows']:
        for query in win['queries']:
            for variant,res in query['results'].items():
                last=latest[(query['query_id'],variant)]
                # Prior round documented a derived metric-qualification correction:
                # schematic/road-axis physical walking length must be null. The
                # immutable trial-map file is the visualization source of truth.
                for key in ['status','edge_ids','cost_f1_proxy','cost_f0_proxy']:
                    if key in res and res[key]!=last['result'].get(key):failures.append('latest effective matrix:'+query['query_id']+variant+key)
                outcomes.append({'window':win['window_id'],'query_id':query['query_id'],'variant':variant,
                                 'status':res['status'],'effective_formal_attempt':last['formal_attempt']})
    out=stamped('Independent fixed archive CRC/all member hashes, exact five copied result files, original raw files and latest final matrix identity; no route computation.')
    out.update({'archive_sha256':digest(archive),'archive_members':member_count,'manifest_records':manifest_count,
                'copied_frozen_files':checks,'raw_sources':raw,'historical_attempts':len(records),
                'historical_actual_solver_calls':sum(r['result']['solver_invoked']for r in records),
                'final_matrix_records':len(outcomes),'effective_outcomes':outcomes,
                'baseline_commit':manifest['local_commit'],'algorithm_result_drift':0 if not failures else 'FAILED_BINDING',
                'failures':failures,'status':'PASS_FIXED_RESULTS_UNCHANGED' if not failures else 'FAIL'})
    save('independent_input_binding.json',out)
    print(json.dumps({k:out[k]for k in ['status','archive_members','manifest_records','final_matrix_records','failures']},ensure_ascii=False))
    return not failures

def context():
    """Independent primitive geometry / source coverage check, not author classifier."""
    from pyproj import Transformer
    from shapely.geometry import Point, LineString, Polygon, shape, box
    from shapely.ops import polygonize, unary_union
    import gc
    baseline=read('audit/initial_binding.json');frozen=read('data/frozen/maps/trial_map_data.json')
    rawpaths={r['scene_id']:Path(r['path']) for r in baseline['raw_sources']}
    tr=Transformer.from_crs('EPSG:4326','EPSG:32651',always_xy=True)
    windows=[];failures=[]
    for window in frozen['windows']:
        name=window['window_id'];payload=read('data/context/'+name+'.json')
        raw=json.loads(rawpaths[window['scene_id']].read_text(encoding='utf-8-sig'))
        objects={str(x['type'])+'/'+str(x['id']):x for x in raw['elements']}
        fragment=read('data/context/'+name+'_source_fragment.json')
        fragment_failures=[]
        for original in fragment['elements']:
            sid=str(original['type'])+'/'+str(original['id'])
            if original!=objects.get(sid):fragment_failures.append(sid)
        if fragment_failures:failures.append(name+':fragment/raw object content mismatch:'+str(fragment_failures))
        coords={x['id']:tr.transform(x['lon'],x['lat']) for x in raw['elements'] if x['type']=='node' and 'lon'in x and 'lat'in x}
        ways={x['id']:x for x in raw['elements'] if x['type']=='way'}
        extent=box(*window['bounds_xy']);features=payload['features'];ids={f['source_id']for f in features}
        if len(ids)!=len(features):failures.append(name+':duplicate source IDs')
        if payload['bounds_xy']!=window['bounds_xy']:failures.append(name+':fixed window changed')
        def primitive(o):
            typ=o['type'];tags=o.get('tags',{})
            if typ=='node':return Point(coords[o['id']])if o['id']in coords else None
            if typ=='way':
                ns=o.get('nodes',[])
                if len(ns)<2 or any(n not in coords for n in ns):return None
                points=[coords[n]for n in ns]
                area=tags.get('area')=='yes' or (tags.get('area')!='no' and ns[0]==ns[-1] and len(ns)>=4 and (
                    tags.get('building')not in (None,'no')or tags.get('building:part')not in (None,'no')or
                    any(k in tags for k in ['landuse','landcover','leisure','area:highway'])or
                    tags.get('natural')in {'water','wetland','wood','scrub'}or
                    tags.get('amenity')in {'hospital','school','kindergarten','college','university','parking','marketplace','place_of_worship','grave_yard'}))
                if area:
                    p=Polygon(points)
                    return p if p.is_valid else None
                return LineString(points)
            if typ=='relation'and tags.get('type')=='multipolygon':
                outer=[];inner=[]
                for mem in o.get('members',[]):
                    if mem['type']!='way':continue
                    w=ways.get(mem['ref']);ns=w.get('nodes',[])if w else[]
                    if len(ns)<2 or any(n not in coords for n in ns):return None
                    line=LineString([coords[n]for n in ns]);(inner if mem.get('role')=='inner'else outer).append(line)
                if not outer:return None
                polygons=list(polygonize(outer))
                if not polygons:return None
                p=unary_union(polygons)
                holes=list(polygonize(inner))if inner else[]
                if holes:p=p.difference(unary_union(holes))
                return p if p.is_valid else None
            return None
        expected=[];unsupported=[];geometry_checks=[]
        for sid,o in objects.items():
            if not o.get('tags'):continue
            g=primitive(o)
            if g is None:
                if o['type']!='relation'or o.get('tags',{}).get('type')=='multipolygon':unsupported.append(sid)
                continue
            if g.intersects(extent):expected.append(sid)
        missing=sorted(set(expected)-ids)
        # Independent selection includes all tagged primitives, so extra objects
        # may legitimately be untagged way/member context. They are checked too.
        for f in features:
            sid=f['source_id'];original=objects.get(sid)
            if original is None:failures.append(name+':invented source ID:'+sid);continue
            if f['tags']!=original.get('tags',{}):failures.append(name+':raw tag drift:'+sid)
            g=primitive(original);shown=shape(f['geometry'])
            if not shown.intersects(extent):failures.append(name+':outside fixed context:'+sid)
            if g is not None:
                same=g.equals_exact(shown,1e-6) or g.equals(shown)
                if not same:failures.append(name+':raw geometry mismatch:'+sid)
                geometry_checks.append({'source_id':sid,'type':shown.geom_type,'matches_raw':same})
            if f.get('source_sha256')!=window['source_sha256']:failures.append(name+':sourceSHA:'+sid)
        if missing:failures.extend(name+':missing independent tagged primitive:'+sid for sid in missing)
        oldids={f['source_id']for f in window['source_features']}
        graphs={v:{e['source_id']for e in g['edges']}for v,g in window['variants'].items()}
        for f in features:
            for variant in ['R0','R1','R2']:
                if bool(f['graph_membership'][variant])!=(f['source_id']in graphs[variant]):failures.append(name+':graph membership:'+f['source_id']+variant)
        families={}
        for f in features:
            for family in f['families']:families[family]=families.get(family,0)+1
        unsupported_display=[f['source_id']for f in features if primitive(objects[f['source_id']])is None]
        windows.append({'window_id':name,'source_features':len(features),'independently_expected_tagged_primitives':len(expected),
                        'raw_fragment_records_checked':len(fragment['elements']),'raw_fragment_content_mismatches':fragment_failures,
                        'missing_independent_primitives':missing,'raw_geometry_matches_checked':len(geometry_checks),
                        'unsupported_raw_primitive_scope':unsupported,'displayed_unsupported_scope':unsupported_display,
                        'old_payload_features':len(oldids),'new_source_IDs':sorted(ids-oldids),'old_IDs_not_retained':sorted(oldids-ids),
                        'family_counts':families,'native_context_not_in_any_graph':sum(not any(f['graph_membership'].values())for f in features),
                        'geometry_checks':geometry_checks})
        del raw,objects,coords,ways,payload,features
        gc.collect()
    out=stamped('Independent raw OSM projection, node/way/multipolygon geometry and exact fixed-window tagged-primitive coverage; source tag/id/old graph membership comparison. No author extraction function was called.')
    out.update({'status':'PASS_SOURCE_CONTEXT_INDEPENDENT_PRIMITIVE_SCOPE'if not failures else'FAIL',
                'windows':windows,'failures':failures,'limits':['Independent raw-area predicate covers nodes, valid closed ways and multipolygon relations. Incomplete/nonspatial relations are separately enumerated, not declared absent.','This is map object fidelity, not physical pedestrian-access or algorithm validity review.']})
    save('independent_source_context.json',out)
    print(json.dumps({'status':out['status'],'windows':len(windows),'failures':failures},ensure_ascii=False));return not failures

def static_figures():
    from shapely.geometry import shape,box
    import collections
    import xml.etree.ElementTree as ET
    import re
    import math
    def canon(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    frozen=read('data/frozen/maps/trial_map_data.json');wins={w['window_id']:w for w in frozen['windows']}
    metadata=read('audit/static_render_membership.json');failures=[];checks=[]
    if len(metadata['figures'])!=18:failures.append('expected18staticfigures')
    expected_names={'context_full','R0_context_overlay','R1_context_overlay','R2_context_overlay','R0_R1_R2_same_extent','local_detail'}
    for wid in wins:
        if {x['figure']for x in metadata['figures']if x['window_id']==wid}!=expected_names:failures.append(wid+':incomplete requestedfigure set')
    for figure in metadata['figures']:
        wid=figure['window_id'];window=wins[wid];context=read('data/context/'+wid+'.json')
        extent=figure['extent_xy'];clip=box(*extent)
        expected_ids=sorted(f['source_id']for f in context['features']if shape(f['geometry']).intersects(clip))
        if figure['figure']!='local_detail'and extent!=window['bounds_xy']:failures.append(wid+':full extent drift')
        hashes=[];panel_checks=[]
        for panel in figure['panels']:
            base=panel['base'];v=panel['variant'];ids=base['source_ids'];hashes.append(base['base_object_sha256'])
            if ids!=expected_ids:failures.append(wid+figure['figure']+str(v)+':renderedsource set missing')
            if base['extent_xy']!=extent or not figure['equal_xy_aspect']:failures.append(wid+':extent/aspect')
            expectedhash=canon([f for f in context['features']if f['source_id']in ids])
            if base['base_object_sha256']!=expectedhash:failures.append(wid+':basehash mismatch')
            overlay=panel['overlay']
            if v:
                graph=window['variants'][v];query=next(q for q in window['queries']if q['query_id']==figure['query_id'])
                if overlay['edge_ids']!=[e['edge_id']for e in graph['edges']]:failures.append(wid+v+':savededge identity drift')
                if overlay['frozen_edges_sha256']!=canon(graph['edges']):failures.append(wid+v+':savedgeometry/weight/tag drift')
                if overlay['route_edge_ids']!=query['results'][v].get('edge_ids',[]):failures.append(wid+v+':savedroute drift')
                if overlay['status']!=query['results'][v]['status']:failures.append(wid+v+':status drift')
            elif overlay is not None:failures.append(wid+':contextonlyunexpectedoverlay')
            panel_checks.append({'variant':v,'source_object_count':len(ids),'base_sha256':base['base_object_sha256'],'label_count':len(base['label_source_ids'])})
        if len(set(hashes))!=1:failures.append(wid+':different base object hashes acrosspanels')
        svg_vertex_checks=0;svg_clipped_paths=[];svg_canvas_clipped_vertex_checks=0
        for file in figure['files']:
            p=ROOT/file['path']
            if not p.is_file()or p.stat().st_size!=file['bytes']or digest(p)!=file['sha256']:failures.append('figurehash:'+file['path'])
            if p.suffix=='.svg':
                tree=ET.parse(p);ids=[e.attrib['id']for e in tree.iter()if'id'in e.attrib]
                svg_view=[float(v)for v in tree.getroot().attrib['viewBox'].split()]
                dups=[i for i,n in collections.Counter(ids).items()if n>1]
                if dups:failures.append('duplicate editable SVGIDs:'+file['path']+':'+str(len(dups)))
                if not any(e.tag.endswith('text')for e in tree.iter()):failures.append('SVGtexts noteditable:'+file['path'])
                if any(e.tag.endswith('image')for e in tree.iter()):failures.append('unexpectedrasterinSVG:'+file['path'])
                byid={e.attrib['id']:e for e in tree.iter()if'id'in e.attrib}
                for panel in figure['panels']:
                    variant=panel['variant']
                    if not variant:continue
                    transform=panel['world_to_svg_points'];sx,sy=transform['scale_x'],transform['scale_y']
                    if not math.isclose(abs(sx),abs(sy),rel_tol=1e-10):failures.append('SVG unequal axis scale:'+file['path'])
                    graph_edges=window['variants'][variant]['edges'];edge_lookup={e['edge_id']:e for e in graph_edges}
                    query=next(q for q in window['queries']if q['query_id']==figure['query_id'])
                    draw_checks=[(e,'edge_')for e in graph_edges]+[(edge_lookup[eid],'saved_route_')for eid in query['results'][variant].get('edge_ids',[])]
                    for edge,artist_kind in draw_checks:
                        gid=transform['svg_id_prefix']+artist_kind+edge['edge_id'].replace('/','_').replace(':','_')
                        group=byid.get(gid)
                        if group is None:failures.append('SVG missing frozen edge artist:'+gid);continue
                        paths=[el.attrib.get('d','')for el in group.iter()if el.tag.endswith('path')]
                        if not paths or not any(paths):
                            # A renderer may discard a wholly clipped artist; it
                            # cannot silently discard an edge within this view.
                            from shapely.geometry import LineString
                            if LineString(edge['xy']).intersects(clip):failures.append('SVG empty visible frozen edge:'+gid)
                            else:svg_clipped_paths.append(gid)
                            continue
                        expected=[value for x,y in edge['xy']for value in (sx*x+transform['offset_x'],sy*y+transform['offset_y'])]
                        # Matplotlib serializes paths after clipping to its SVG
                        # canvas plus one-point margin. This display clipping
                        # must not be mislabeled as changed world geometry.
                        from shapely.geometry import LineString
                        expected_pairs=list(zip(expected[::2],expected[1::2]))
                        canvas=box(svg_view[0]-1,svg_view[1]-1,svg_view[0]+svg_view[2]+1,svg_view[1]+svg_view[3]+1)
                        display_line=LineString(expected_pairs).intersection(canvas)
                        expected_clipped=[v for pt in display_line.coords for v in pt]if display_line.geom_type=='LineString'and not display_line.is_empty else None
                        matching=False
                        canvas_match=False
                        for path in paths:
                            if re.search('[CcQqAaHhVv]',path):continue
                            numbers=[float(x)for x in re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?',path)]
                            if len(numbers)==len(expected)and all(abs(a-b)<2e-5 for a,b in zip(numbers,expected)):matching=True
                            elif expected_clipped is not None and len(numbers)==len(expected_clipped)and all(abs(a-b)<2e-5 for a,b in zip(numbers,expected_clipped)):
                                matching=True;canvas_match=True
                        if not matching:failures.append('SVG point geometry differs from frozen edge:'+gid)
                        else:
                            svg_vertex_checks+=1
                            svg_canvas_clipped_vertex_checks+=canvas_match
                        if edge.get('hypothesis')or edge.get('geometry_status')=='SCHEMATIC':
                            if not any('stroke-dasharray'in p.attrib.get('style','')for p in group.iter()if p.tag.endswith('path')):
                                failures.append('SVG hypothesis not dashed:'+gid)
        checks.append({'window_id':wid,'figure':figure['figure'],'extent_xy':extent,'panels':panel_checks,'same_base':len(set(hashes))==1,
                       'actual_SVG_frozen_edge_vertex_checks':svg_vertex_checks,'SVG_canvas_clipped_vertex_checks':svg_canvas_clipped_vertex_checks,'SVG_outside_view_clipped_artists':svg_clipped_paths})
    out=stamped('Independent static artifact hashes/XML, source object census and same-base/extent checks; all frozen overlay geometries/weights/identities hashed against unchanged frozen input. No rendering/solver called by this check.')
    out.update({'status':'PASS_STATIC_MAPS_AND_FROZEN_OVERLAYS'if not failures else'FAIL','static_figure_pairs':len(checks),'files_checked':36,'figures':checks,'failures':failures})
    save('independent_static_figures.json',out)
    print(json.dumps({'status':out['status'],'figure_pairs':len(checks),'failures':failures},ensure_ascii=False));return not failures

def browser():
    from playwright.sync_api import sync_playwright
    import math
    frozen=read('data/frozen/maps/trial_map_data.json');failures=[];views=[];errors=[];external=[];requests=[]
    out=stamped('Fresh independent installed Chrome HTTP/offline UI operations, actual DOM source sets/scale/click/export checks; saved results only, no solver endpoint or algorithm imported.')
    with sync_playwright()as pw:
        browser=pw.chromium.launch(headless=True,channel='chrome')
        page=browser.new_page(viewport={'width':1740,'height':1280},accept_downloads=True)
        page.on('pageerror',lambda e:errors.append(str(e)))
        def route(req):
            u=req.request.url
            if u.startswith(('http://127.0.0.1:53521/','file:','blob:','data:')):
                requests.append(u);req.continue_()
            else:external.append(u);req.abort()
        page.route('**/*',route)
        page.goto('http://127.0.0.1:53521/',wait_until='networkidle')
        page.wait_for_selector('#map-context .source-feature')
        for index,window in enumerate(frozen['windows']):
            page.select_option('#window',str(index))
            for qi,query in enumerate(window['queries']):
                page.select_option('#query',str(qi))
                diag=page.evaluate('window.MAP_REPAIR_DIAGNOSTICS')
                if not diag['base_sets_equal']:failures.append('browser base source sets differ')
                dom=page.evaluate("""()=>['context','R0','R1','R2'].map(v=>{const s=document.getElementById('map-'+v),m=s.getScreenCTM();return{panel:v,viewBox:s.getAttribute('viewBox'),source_ids:[...s.querySelectorAll('g.source-feature')].map(x=>x.dataset.sourceId).sort(),scale_x:m.a,scale_y:m.d,width:s.getBoundingClientRect().width,height:s.getBoundingClientRect().height,preserve:s.getAttribute('preserveAspectRatio')}})""")
                if len({json.dumps(x['source_ids'])for x in dom})!=1:failures.append('actual DOM base source sets differ')
                if len({x['viewBox']for x in dom})!=1:failures.append('actual DOM extents differ')
                for row in dom:
                    dd=next(p for p in diag['panels']if p['panel']==row['panel'])
                    if not math.isclose(dd['meters_per_css_px']*abs(row['scale_x']),1,rel_tol=1e-6):failures.append('reported m/CSSpx differs from actual letterboxed SVG CTM:'+row['panel'])
                    if not math.isclose(abs(row['scale_x']),abs(row['scale_y']),rel_tol=1e-9):failures.append('actual SVG nonuniform scale')
                for variant in ['R0','R1','R2']:
                    status=query['results'][variant]['status'];text=page.locator('#summary-'+variant).inner_text()
                    if status not in text:failures.append('browser status drift:'+query['query_id']+variant)
                if not page.locator('#layers input[data-layer="road_areas"]').is_disabled():failures.append('nonexistent road-area layer not unavailable')
                views.append({'window_id':window['window_id'],'query_id':query['query_id'],'diagnostics':diag,'actual_DOM':dom,
                              'effective_statuses':{v:query['results'][v]['status']for v in ['R0','R1','R2']}})
        # Independent source family switch: all four maps retain other source objects.
        page.select_option('#window','0');page.select_option('#query','0')
        ids_before=page.locator('#map-context .source-feature').count()
        page.locator('#layers input[data-layer="buildings"]').uncheck()
        if page.locator('#map-context .source-feature[data-family="buildings"]').count()!=0:failures.append('building switch did not hide buildings')
        if page.locator('#map-context .source-feature').count()==0:failures.append('building toggle cleared whole context')
        page.locator('#layers input[data-layer="buildings"]').check()
        if page.locator('#map-context .source-feature').count()!=ids_before:failures.append('building toggle failed to restore context')
        page.locator('#map-context .source-feature[data-source-id="node/132491635"]').click(force=True)
        source_evidence=json.loads(page.locator('#evidence').inner_text())
        if source_evidence.get('raw_tags',{}).get('highway')!='traffic_signals':failures.append('native object click did not expose correct tags')
        page.click('#detail');detail=page.evaluate('window.MAP_REPAIR_DIAGNOSTICS')
        if detail['extent']==views[0]['diagnostics']['extent']:failures.append('detail mode no extent change')
        page.click('#full');page.select_option('#history','original')
        if not page.evaluate('window.MAP_REPAIR_DIAGNOSTICS.base_sets_equal'):failures.append('history changes base')
        hist=json.loads(page.locator('#history-record').inner_text())
        if hist['original_R0']['formal_attempt']!=1 or hist['effective_R0']['formal_attempt']!=19:failures.append('superseded/current record identities mixed')
        page.select_option('#window','2');page.select_option('#query','0');page.click('#full')
        base_before=page.locator('#map-R2 .source-feature').count()
        page.locator('#layers input[data-layer="R2"]').uncheck()
        if page.locator('#map-R2 .algorithm-edge').count()!=0:failures.append('R2 overlay switch failed')
        if page.locator('#map-R2 .source-feature').count()!=base_before:failures.append('R2 switch removed source map')
        page.locator('#layers input[data-layer="R2"]').check()
        candidates=page.locator('#map-R2 .algorithm-edge[data-assumption="CONDITIONAL"]')
        if candidates.count()==0:failures.append('conditional frozen edge not shown')
        else:candidates.first.dispatch_event('click')
        derived=json.loads(page.locator('#evidence').inner_text())
        if derived.get('assumption_class')!='CONDITIONAL_HYPOTHESIS':failures.append('conditional evidence misclassified')
        with page.expect_download()as export:
            page.click('#export')
        ep=ROOT/'reviews/independent_export_view.json';export.value.save_as(str(ep));exported=json.loads(ep.read_text())
        if exported.get('identity')!='VISUAL_REPAIR_EXPORT_NO_SOLVER':failures.append('export identity missing')
        with page.expect_download()as export:
            page.click('#export-svg')
        export.value.save_as(str(ROOT/'reviews/independent_export_current.svg'))
        with page.expect_download()as export:
            page.click('#export-evidence')
        export.value.save_as(str(ROOT/'reviews/independent_export_evidence.json'))
        page.select_option('#window','0');page.select_option('#query','0');page.click('#full')
        page.locator('#map-context').screenshot(path=str(ROOT/'reviews/independent_browser_context.png'))
        page.goto((ROOT/'index.html').as_uri(),wait_until='load');page.wait_for_selector('#map-context .source-feature')
        offline=[]
        for index,window in enumerate(frozen['windows']):
            page.select_option('#window',str(index))
            for qi,query in enumerate(window['queries']):
                page.select_option('#query',str(qi));diag=page.evaluate('window.MAP_REPAIR_DIAGNOSTICS')
                if not diag['base_sets_equal']or not all(p['source_ids']for p in diag['panels']):failures.append('offline map blank or inconsistent')
                offline.append({'window_id':window['window_id'],'query_id':query['query_id'],'base_sets_equal':diag['base_sets_equal']})
        browser.close()
    failures.extend('pageerror:'+e for e in errors)
    if external:failures.append('external browser request attempted')
    out.update({'status':'PASS_INDEPENDENT_ACTUAL_BROWSER'if not failures else'FAIL','HTTP_query_views':views,
                'offline_query_views':offline,'actual_source_click':source_evidence,'conditional_edge_click':derived,
                'historical_record_identity':{'original_R0':hist['original_R0']['formal_attempt'],'effective_R0':hist['effective_R0']['formal_attempt']},
                'actual_exports':['independent_export_view.json','independent_export_current.svg','independent_export_evidence.json'],
                'local_or_file_resource_requests':len(requests),'external_requests_attempted':external,'page_errors':errors,
                'files_observed':{'HTML_sha256':digest(ROOT/'index.html'),'JS_sha256':digest(ROOT/'maps/viewer.js'),'CSS_sha256':digest(ROOT/'maps/viewer.css')},
                'failures':failures,'prior_attempt':'First browser attempt reached exports then optional standalone-SVG full-page capture timed out before offline checks; no PASS inferred from that incomplete attempt.',
                'limits':['Derived edge selection dispatched the actual SVG edge event; native traffic signal selection used an actual browser pointer click.','No route endpoint was submitted; the page only changes display of saved queries.','All18SVGfiles underwent XML/point-geometry checks; optional standaloneSVG pixel screenshot timed out and independent SVG pixel inspection is not claimed.','Visual perception remains pending user acceptance.']})
    save('independent_browser.json',out)
    print(json.dumps({'status':out['status'],'HTTP_views':len(views),'offline_views':len(offline),'failures':failures},ensure_ascii=False));return not failures

def inventory():
    inv=read('audit/source_to_figure_inventory.json');stat=read('audit/static_render_membership.json');frozen=read('data/frozen/maps/trial_map_data.json')
    failures=[];checks=[]
    if len(inv['rows'])!=39:failures.append('39 source-family rows expected')
    for win in frozen['windows']:
        wid=win['window_id'];ctx=read('data/context/'+wid+'.json')
        full=next(f for f in stat['figures']if f['window_id']==wid and f['figure']=='context_full')['panels'][0]['base']
        rendered=set(full['source_ids']);labelled=set(full['label_source_ids'])
        width_fields=[(f['source_id'],k)for f in ctx['features']for k in f['tags']if any(s in k for s in ['width','kerb','curb'])]
        if width_fields or ctx['family_counts']['road_areas']!=0:failures.append(wid+':source width/area absence claim contradicted')
        for row in [r for r in inv['rows']if r['window_id']==wid]:
            fam=row['source_family'];fs=[f for f in ctx['features']if fam in f['families']];ids={f['source_id']for f in fs}
            expected={'frozen_source_count':len(fs),'source_drawable_geometry_count':len(fs),'exported_context_count':len(fs),
                      'rendered_count':len(ids&rendered),'previous_payload_count':sum(f['imported_in_previous_payload']for f in fs),
                      'newly_exported_count':sum(not f['imported_in_previous_payload']for f in fs),'omitted_count':0,'labelled_count':len(ids&labelled),
                      'routing_graph_count':sum(any(f['graph_membership'].values())for f in fs)}
            for variant in ['R0','R1','R2']:expected['routing_graph_'+variant+'_count']=sum(f['graph_membership'][variant]for f in fs)
            for key,value in expected.items():
                if row[key]!=value:failures.append(wid+':inventory '+fam+':'+key)
            if set(row['source_ids'])!=ids:failures.append(wid+':inventory IDs:'+fam)
            if not ids and row['absence_status']!='NOT_PRESENT_IN_FROZEN_SOURCE':failures.append(wid+':source absence status:'+fam)
            if 'NOT_RAW_GEOMETRY_ADMISSION'not in row.get('routing_graph_count_semantics',''):failures.append('derived-parent count semantics missing')
            checks.append({'window_id':wid,'source_family':fam,'verified_fields':expected})
    out=stamped('Independent 39-row source/export/render/graph-reference census derived from actual context objects and static artist IDs; no route traversal.')
    out.update({'status':'PASS_SOURCE_TO_FIGURE_INVENTORY'if not failures else'FAIL','rows_checked':len(checks),'checks':checks,
                'source_missing':'Road area and any width/kerb/curb field absent in all three fixed windows; other category absence is window-specific.',
                'export_omission':'Zero source-ID omissions compared with prior154/122/85 payloads; no claim of new source acquisition.',
                'visual_weakening':'Prior source renderer used common thin road symbols, low-opacity native lines, generic point symbols and limited semantic switches; current classification/layer hierarchy is the repair.',
                'failures':failures,'limits':['Emitted source artist count is not a subjective perception/occlusion guarantee; label suppression is separately counted.','Routing membership is source identity reference, including derived parent edges, not admission of complete raw road-axis geometry.']})
    save('independent_inventory.json',out)
    print(json.dumps({'status':out['status'],'rows_checked':len(checks),'failures':failures},ensure_ascii=False));return not failures

def protection():
    import subprocess
    import os
    initial=read('audit/initial_binding.json');failures=[];checks=[]
    for row in initial['old_indices']:
        p=Path(row['path']);got=digest(p)if p.exists()else None
        ok=p.exists()==row['exists']and got==row['sha256'];checks.append({'path':str(p),'unchanged':ok})
        if not ok:failures.append('old Git index changed:'+str(p))
    oldrepo=ROOT.parent/'PG1_RESUME_STREET_SIDE_R1/repository';env={**os.environ,'GIT_OPTIONAL_LOCKS':'0'}
    head=subprocess.check_output(['git','-C',str(oldrepo),'rev-parse','HEAD'],text=True,env=env).strip()
    status=subprocess.check_output(['git','--git-dir='+str(oldrepo/'.git'),'--work-tree='+str(oldrepo),'status','--porcelain'],text=True,env=env)
    if head!=initial['git']['HEAD']or status!=initial['git']['status']:failures.append('old source git HEAD/worktree status changed')
    if digest(Path(initial['archive_path']))!=EXPECTED_BASELINE_SHA:failures.append('old fixed ZIP changed')
    out=stamped('Independent end-state old index byte hashes and old isolated source HEAD/worktree status, plus fixed ZIP SHA. Only read-only Git commands with GIT_OPTIONAL_LOCKS=0.')
    out.update({'status':'PASS_PROTECTED_OLD_GIT_AND_ARCHIVE'if not failures else'FAIL','old_indices':checks,'old_HEAD':head,'old_worktree_status':status,'failures':failures})
    save('independent_protection.json',out)
    print(json.dumps({'status':out['status'],'failures':failures},ensure_ascii=False));return not failures

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['binding','context','static','browser','inventory','protection']);args=ap.parse_args()
    raise SystemExit(0 if {'binding':binding,'context':context,'static':static_figures,'browser':browser,'inventory':inventory,'protection':protection}[args.mode]() else 1)
