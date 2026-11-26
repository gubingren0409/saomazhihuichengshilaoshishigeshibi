"""Build the offline FREE-SPACE paired maps from saved geometries.

SVG geometry helpers retain the preceding CONTEXT review's affine metre mapping.
Display-only backgrounds and evaluator references are never predictor inputs.
"""
import argparse
import base64
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re

from shapely import make_valid, unary_union
from shapely.geometry import LineString, Point, box, shape

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('M1-C', 'F0', 'F1')
STATE = {'NATIVE_WALKABLE':'state-native', 'INFERRED_WALKABLE':'state-inferred',
         'RESTRICTED':'state-restricted', 'UNKNOWN':'state-unknown'}
PREFERRED = ('Wc4183046a70','W6daddd19fdb','W745941f0f92')


def read(p, default=None):
    if not p.is_file() and default is not None:
        return default
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    return sha256(p.read_bytes()).hexdigest()


def geom(g):
    s=shape(g)
    return s if s.is_valid else make_valid(s)


def fmt(p,a):
    return [round(p[0]-a[0],3),round(a[1]-p[1],3)]


def draw(g,a):
    if g.is_empty:
        return []
    def path(coords,closed=False):
        pts=[fmt(p,a) for p in coords]
        return 'M'+','.join(map(str,pts[0]))+''.join('L'+','.join(map(str,p)) for p in pts[1:])+('Z' if closed else '')
    if g.geom_type=='Point':
        return [{'point':fmt(g.coords[0],a)}]
    if g.geom_type in ('LineString','LinearRing'):
        return [{'d':path(g.coords)}]
    if g.geom_type=='Polygon':
        return [{'d':path(g.exterior.coords,True)+''.join(path(r.coords,True) for r in g.interiors),'area':True}]
    return [v for part in getattr(g,'geoms',[]) for v in draw(part,a)]


def feature(layer,g,a,**props):
    parts=draw(g,a)
    return {'layer':layer,'shape':parts,'props':props} if parts else None


def category(group,kind,tags):
    k=kind.upper()
    if 'BUILDING' in k or tags.get('building'):
        return 'building'
    if 'WATER' in k or tags.get('natural')=='water' or tags.get('water'):
        return 'water'
    if group=='background' or tags.get('landuse') in {'grass','flowerbed'} or tags.get('natural') in {'grassland','scrub'}:
        return 'grass'
    if tags.get('barrier'):
        return 'obstacle'
    if 'PARK' in k or tags.get('leisure') in {'park','garden','recreation_ground'}:
        return 'park'
    if group=='support':
        return 'plaza'
    return 'obstacle'


def visible(obs,anchor,frame,role='OBSERVED_OBJECT'):
    out=[]
    counts=Counter()
    for group,objects in obs.get('context',{}).items():
        for o in objects:
            g=geom(o['geometry']).intersection(frame)
            tags=o.get('tags',{})
            layer=category(group,o.get('kind',''),tags)
            out.append(feature(layer,g,anchor,source_id=o.get('id'),tags=tags,kind=o.get('kind'),observation=role))
            counts[layer]+=1
            name=tags.get('name:zh') or tags.get('name')
            if name and not g.is_empty:
                out.append(feature('label',g.representative_point(),anchor,source_id=o.get('id'),label=name,observation=role))
    nodes={n['id']:n for n in obs.get('nodes',[])}
    seen=set()
    for e in obs.get('edges',[]):
        if e.get('kind','').startswith('DERIVED'):
            counts['derived']+=1
            continue
        u,v=e['u'],e['v']
        key=(frozenset((u,v)),e.get('source_id'),e.get('source_segment_index'))
        if key in seen or u not in nodes or v not in nodes:
            continue
        seen.add(key)
        line=LineString([nodes[u]['xy'],nodes[v]['xy']])
        if line.length<1e-6:
            continue
        out.append(feature('way',line.intersection(frame),anchor,source_id=e.get('source_id'),id=e['id'],
                           tags=e.get('tags',{}),kind=e.get('kind'),observation=role))
        counts['line_m']+=line.length
    for n in nodes.values():
        k=n.get('endpoint_kind','NATIVE_ENDPOINT')
        if isinstance(k,list):
            k=next((v for v in k if v!='NATIVE_ENDPOINT'),k[0] if k else '')
        layer={'CONTEXT_CLIP_ENDPOINT':'clip','MASK_BOUNDARY_ENDPOINT':'mask-end','SOURCE_CROP_LIMIT':'source-limit'}.get(k)
        if layer:
            out.append(feature(layer,Point(n['xy']),anchor,id=n['id'],endpoint_kind=k,observation=role))
    door=obs.get('registered_entrance')
    if door and door.get('xy'):
        out.append(feature('exit' if door.get('tags',{}).get('entrance')=='exit' else 'endpoint',Point(door['xy']),anchor,
                           **door,observation=role))
    rank={'park':0,'plaza':1,'grass':2,'water':3,'building':4,'obstacle':5,'way':6,'label':9}
    return sorted(filter(None,out),key=lambda v:rank.get(v['layer'],8)),{
        'nodes':len(nodes),'arcs':len(obs.get('edges',[])),'segments':len(seen),
        'road_length_m':counts['line_m'],'derived_arcs_aggregated_for_display':counts['derived']}


def routes(doc,anchor):
    out={}
    for ident,r in doc.items():
        fs=[];points=[]
        for e in r.get('edges',[]):
            xy=e.get('xy',[])
            if len(xy)<2 or LineString(xy).length<=1e-6:
                continue
            layer=str(e.get('layer','native')).lower().replace('_','-')
            if layer in {'assumed','default','assumed-passable'}:
                layer='inferred'
            fs.append(feature('route-'+layer,LineString(xy),anchor,**{k:v for k,v in e.items() if k not in {'xy','layer'}}))
            points.extend(fmt(p,anchor) for p in xy)
        out[str(ident)]={k:v for k,v in r.items() if k not in {'edges'}}
        out[str(ident)].update(lines=list(filter(None,fs)),extent=[min(p[0] for p in points),min(p[1] for p in points),
            max(p[0] for p in points),max(p[1] for p in points)] if points else None)
    return out


def surface(doc,anchor,reference):
    states=defaultdict(list);cells=[]
    added=[]
    for c in doc.get('cells',[]):
        g=geom(c['geometry'])
        state=c.get('walkability_state','UNKNOWN')
        states[state].append(g)
        if state=='INFERRED_WALKABLE':
            added.append(g)
        props={k:v for k,v in c.items() if k not in {'geometry','g','xy'}}
        cells.append(feature('cell',g,anchor,**props))
    zones=[feature(STATE.get(k,'state-unknown'),unary_union(v),anchor,walkability_state=k,
                   area_m2=doc.get('area_m2',{}).get(k)) for k,v in states.items()]
    if added and reference is not None:
        proxy=reference.buffer(1) if reference.area==0 else reference
        outside=unary_union(added).difference(proxy)
        zones.append(feature('unverified-expansion',outside,anchor,reason='UNVERIFIED_EXPANSION',
                             interpretation='参考外未证实扩张，不自动计错或计成功；线参考使用1m代理buffer，非实测路宽'))
    return list(filter(None,zones)),list(filter(None,cells))


def guard_features(path,anchor,frame):
    doc=read(path,{})
    entries=doc.get('constraints',doc.get('guards',doc.get('features',doc.get('road_centerlines',[]))))
    out=[]
    for e in entries:
        g=e.get('geometry')
        if not isinstance(g,dict) or not g.get('type'):
            continue
        props={k:v for k,v in e.items() if k!='geometry'}
        kind=str(e.get('kind',''))+' '+str(e.get('restriction_role',''))
        kind=kind.lower()
        layer='road-guard' if 'road' in kind or 'carriage' in kind else 'common-guard'
        out.append(feature(layer,geom(g).intersection(frame),anchor,**props,observation='OBSERVED_COMMON_GUARDS'))
    return list(filter(None,out))


def background_roads(root,parent,anchor,frame):
    doc=read(root/'data/visual_background'/f'{parent}.json',{})
    out=[]
    for e in doc.get('road_centerlines',[]):
        g=geom(e['geometry']).intersection(frame)
        out.append(feature('road',g,anchor,source_id=e['source_id'],tags=e.get('tags',{}),
                           observation='DISPLAY_ONLY_160M_MOTOR_CENTERLINE',source_timestamp=doc.get('source_timestamp')))
        tags=e.get('tags',{});name=tags.get('name:zh') or tags.get('name')
        if name and not g.is_empty:
            out.append(feature('label',g.representative_point(),anchor,label=name,source_id=e['source_id'],
                               observation='DISPLAY_ONLY_160M_MOTOR_CENTERLINE'))
    full=[feature(e['layer'],geom(e['geometry']),anchor,source_id=e['source_id'],tags=e.get('tags',{}),
                  observation=e['role']) for e in doc.get('full_features',[])]
    return list(filter(None,out)),doc.get('source_timestamp'),list(filter(None,full))


def historical_model(root,pred,contract,ident,anchor,ref,observed_sha,cache):
    """Render a sealed R0 result, without running its classifier or router."""
    doc=read(pred);s=doc['surface']
    if doc['input_id']!=ident or doc['observed_sha256']!=observed_sha:
        raise ValueError('Historical observation binding differs')
    h=sha256(json.dumps(contract,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if doc['constraint_sha256']!=h:
        raise ValueError('Historical constraint binding differs')
    key=(s['sha256'],anchor)
    if key not in cache:cache[key]=surface(s,anchor,ref)
    states,cells=cache[key];graph=doc['graph']
    graph_details={k:v for k,v in graph.items() if k not in {'interfaces','terminals'}}
    if graph_details.get('graph_path'):
        graph_details['historical_run_graph_path']=graph_details.pop('graph_path')
    portals=[feature('interface',Point(a['xy']),anchor,**a) for a in graph.get('interfaces',[]) if a.get('xy')]
    return {'_anchor':anchor,'sha256':s['sha256'],'graph_sha256':graph['unweighted_graph_sha256'],
        'area':s['area_m2'],'states':states,'cells':cells,'routes':routes(doc['routes'],anchor),
        'base_routes':routes(doc['base_routes'],anchor),'metrics':{},'features':doc.get('features',{}),
        'portals':list(filter(None,portals)),'graph':graph_details,'lambda':doc['lambda_value'],
        'stage':'R0_HISTORICAL','prediction_path':pred.relative_to(root).as_posix()}


def private_measurements(folder,ident,area):
    overlaps={};lengths={}
    for method in METHODS:
        doc=read(folder/ident/f'{method}.json')
        overlaps[method]={s:sum(geom(c['geometry']).intersection(area).area for c in doc['surface']['cells']
                                 if c['walkability_state']==s) for s in STATE}
        lengths[method]={qid:sum(LineString(e['xy']).intersection(area.buffer(-1e-7)).length for e in r.get('edges',[])
                                 if len(e.get('xy',[]))>=2) for qid,r in doc['routes'].items()}
    return overlaps,lengths


def assemble(root):
    manifest=read(root/'data/task_manifest.json')
    release=read(root/'config/visual_release.json',{})
    fix=release.get('stage')=='R1_PRIVATE_GUARD_V3'
    if fix:
        for review in release['reviews']:
            file=root/review['path'];content=read(file)
            if sha(file)!=review['sha256'] or not str(content.get('status','')).startswith('PASS'):
                raise ValueError('Private-fix source/evaluation release gate differs: '+str(file))
    cases={};models=[];index=[];surface_cache={}
    frozen=root/'frozen_context'
    for x in manifest['instances']:
        ident=x['id'];parent=x.get('parent_task_id',ident)
        if not any((root/'data/predictions'/ident/f'{method}.json').is_file() for method in METHODS):
            continue
        p=root/x['observed']
        if not p.is_file():
            continue
        o=read(p);anchor=tuple(o['domain']['anchor_xy']);radius=int(x.get('context_radius_m',80))
        frame=box(anchor[0]-175,anchor[1]-175,anchor[0]+175,anchor[1]+175)
        refdoc=read(root/x['reference'],{}) if x.get('reference') else {}
        ref=geom(refdoc['geometry']) if refdoc.get('geometry') else None
        qdoc=read(root/x['query'],{})
        qs={q['query_id']:[feature('endpoint',Point(q[k]['xy']),anchor,**q[k],query_side=k)
                           for k in ('source','target')] for q in qdoc.get('queries',[])}
        natural=bool(x.get('natural')) or parent=='NORTH'
        mode='NATURAL' if natural else str(x.get('masking_mode','G')).split('_')[0]
        v,counts=visible(o,anchor,frame)
        background_path=frozen/'data/observed'/f'{parent}_{mode}_160.json'
        background=[]
        if background_path.is_file() and radius<160:
            background,_=visible(read(background_path),anchor,frame,'DISPLAY_ONLY_160M_CONTEXT')
        item={'id':ident,'radius':radius,'mode':mode,'visible':v,'counts':counts,'inventory':{},'models':{},
              'background':background,'observed_sha256':sha(p),'evaluation_sha256':x.get('evaluation_domain_sha256'),
              'reference_sha256':x.get('reference_sha256'),'query_sha256':x.get('query_sha256'),
              'guards':guard_features(root/f'data/constraints/{ident}.json',anchor,frame)}
        contract=read(root/f'data/constraints/{ident}.json',{})
        if contract.get('coverage_geometry'):
            boundary=geom(contract['coverage_geometry']).boundary.intersection(frame)
            item['source_boundary']=feature('source-boundary',boundary,anchor,
                observation='ACQUIRED_CLIP_COVERAGE_NOT_COMPLETE_REAL_WORLD_SURVEY')
        domain=None
        for method in METHODS:
            pred=root/'data/predictions'/ident/f'{method}.json'
            if not pred.is_file():
                continue
            doc=read(pred);s=doc['surface'];key=(s['sha256'],anchor)
            if doc.get('input_id')!=ident or doc.get('observed_sha256')!=item['observed_sha256']:
                raise ValueError('Displayed prediction/input binding differs: '+ident+' '+method)
            canonical=sha256(json.dumps(contract,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
            if contract.get('sha256') and doc.get('constraint_sha256')!=canonical:
                raise ValueError('Displayed prediction/constraint binding differs: '+ident+' '+method)
            if key not in surface_cache:
                surface_cache[key]=surface(s,anchor,ref)
            states,cells=surface_cache[key]
            domain=geom(s['domain'])
            graph=doc.get('graph',{})
            interfaces=graph.get('interfaces',[])
            if isinstance(interfaces,int):
                interfaces=doc.get('interfaces',[])
            portals=[feature('interface',Point(a['xy']),anchor,**a) for a in interfaces if isinstance(a,dict) and a.get('xy')]
            value={'_anchor':anchor,'sha256':s.get('sha256'),'graph_sha256':doc.get('unweighted_graph_sha256',graph.get('unweighted_graph_sha256')),
                   'area':s.get('area_m2',{}),'states':states,'cells':cells,'routes':routes(doc.get('routes',{}),anchor),
                   'base_routes':routes(doc.get('base_routes',{}),anchor),'metrics':doc.get('metrics',{}),
                   'features':doc.get('features',{}),'portals':list(filter(None,portals)),
                   'graph':{k:v for k,v in graph.items() if k not in {'interfaces','terminals'}},'lambda':doc.get('lambda_value'),
                   'stage':'R1_CURRENT' if fix and ident=='W7a6b5a10076_G_080' else 'UNCHANGED_CURRENT',
                   'prediction_path':pred.relative_to(root).as_posix()}
            item['models'][method]=len(models);models.append(value)
            index.append({'input_id':ident,'method':method,'prediction_path':pred.relative_to(root).as_posix(),
                          'prediction_sha256':sha(pred),'surface_sha256':s.get('sha256'),
                          'cells':len(cells),'route_segments':sum(len(a['lines']) for a in value['routes'].values())})
        if domain is None:
            continue
        if parent not in cases:
            roads,date,full=background_roads(root,parent,anchor,frame)
            cases[parent]={'parent':parent,'group':x.get('group','sh-huangpu-01'),'kind':x.get('kind','NATURAL_REGISTERED_EXIT'),
                'label':'NATURAL' if natural else x.get('label'),'split':x.get('split','development'),
                'anchor':anchor,'inputs':{},'context_road':roads,'full_background':full,'snapshot':date,'window':feature('score-domain',domain,anchor,
                 observation='FIXED_30M_PREDICTION_SCORE_DOMAIN'),
                'reference':feature('reference',ref,anchor,observation='EVALUATION_ONLY') if ref is not None else None,
                'queries':qs,'methods':[]}
        cases[parent]['inputs'].setdefault(mode,{})[str(radius)]=item
        cases[parent]['methods']=list(dict.fromkeys(cases[parent]['methods']+list(item['models'])))
        if fix and ident=='W7a6b5a10076_G_080':
            old=root/release['historical_root']
            old_contract=read(old/f'data/constraints/{ident}.json')
            item['historical_guards']=guard_features(old/f'data/constraints/{ident}.json',anchor,frame)
            item['historical_models']={}
            for method in METHODS:
                pred=old/'data/predictions'/ident/f'{method}.json'
                value=historical_model(root,pred,old_contract,ident,anchor,ref,item['observed_sha256'],surface_cache)
                item['historical_models']['R0-'+method]=len(models);models.append(value)
                index.append({'input_id':ident,'method':'R0-'+method,'role':'HISTORICAL_SEALED_R0',
                    'prediction_path':pred.relative_to(root).as_posix(),'prediction_sha256':sha(pred),
                    'surface_sha256':value['sha256'],'cells':len(value['cells']),
                    'route_segments':sum(len(a['lines']) for a in value['routes'].values())})
    if not cases:
        raise ValueError('No actual saved predictions available; no placeholder map written')
    shared=[];surface_index={}
    for model in models:
        key=model['sha256']
        # Same surface means same metric coordinates and same classification;
        # the renderer's affine anchor differs by parent, so include it in key.
        token=(key,tuple(model.pop('_anchor')))
        if token not in surface_index:
            surface_index[token]=len(shared)
            shared.append({'states':model['states'],'cells':model['cells']})
        model['surface_index']=surface_index[token]
        del model['states'];del model['cells']
    post_audit=None
    area_file=root/'data/access_area_interpretations.json'
    impact_file=root/'audits/access_area_prediction_impact.json'
    if area_file.is_file() and impact_file.is_file():
        source=read(area_file);impact=read(impact_file)
        area=next(a for a in source['areas'] if a['source_id']==impact['source_id'])
        affected=[a for a in impact['results'] if a['domain_private_overlap_m2']>1e-6]
        for ident in sorted({a['input_id'] for a in affected}):
            parent=next(x['parent_task_id'] for x in manifest['instances'] if x['id']==ident)
            if parent not in cases:
                continue
            case=cases[parent]
            rows=[a for a in affected if a['input_id']==ident]
            current_overlaps={a['method']:a['state_area_overlaps_m2'] for a in rows}
            current_lengths={a['method']:{q['query_id']:q['private_interior_m'] for q in a['routes']} for a in rows}
            old_overlaps,old_lengths=current_overlaps,current_lengths
            if fix:
                current_overlaps,current_lengths=private_measurements(root/'data/predictions',ident,geom(area['geometry']))
                old_overlaps,old_lengths=private_measurements(root/release['historical_root']/'data/predictions',ident,geom(area['geometry']))
            overlay=feature('post-audit-restriction',geom(area['geometry']),tuple(case['anchor']),
                observation='SOURCE_RESTRICTION_V3_PARITY_REVIEW' if fix else 'POST_AUDIT_SOURCE_RESTRICTION',predictor_input=fix,
                source_id=area['source_id'],source_tags=area['source_tags'],source_clip_sha256=area['source_clip_sha256'],
                original_source_area_m2=area['area_m2'],fixed_domain_overlap_m2=rows[0]['domain_private_overlap_m2'],
                algorithm_input_status='V3_NEGATIVE_CONSTRAINT_ACTUALLY_PROVIDED_TO_CURRENT_PREDICTOR' if fix else 'OMITTED_RESTRICTED_AREA_DURING_OBSERVED_EXPORT; NOT_REPAIRED_IN_THIS_RUN',
                native_boundary_exception=area['boundary_exceptions'],
                per_method_state_overlaps=current_overlaps,
                per_method_route_private_interior_m=current_lengths,
                r0_per_method_state_overlaps=old_overlaps,r0_per_method_route_private_interior_m=old_lengths,
                evidence_scope='SOURCE_ACCESS_TAG_AUDIT_NOT_FIELD_AUTHORIZATION',
                input_region_graph_unchanged=not fix)
            case['post_audit_features']=[overlay]
            case['post_audit_note']='审后发现：private停车面有128.39m²落在30m域内，原导出遗漏。F0/F1放行了该区域；本例2条新增路线均未进入其内部。红斜纹是审后限制，算法未看到；原区域/图未修。'
            case['post_audit_history_note']=case['post_audit_note']
            if fix:
                case['post_audit_note']='R1当前：V3已将128.39m²原生private停车面加入共同负约束，M1-C/F0/F1均为RESTRICTED。原R0误放保留作历史；本例2条查询仍可达且均不进入其内部。此项修复不证明未标障碍不存在。'
            post_audit={'case':parent,'input_id':ident,'source_id':area['source_id'],
                'affected_main_tasks':1,'main_task_denominator':25,'overlap_m2':rows[0]['domain_private_overlap_m2'],
                'source_table_sha256':sha(area_file),'impact_table_sha256':sha(impact_file),
                'status':'R1_SOURCE_RESTRICTION_FIXED_AFTER_INDEPENDENT_PASS' if fix else 'PARTIAL_WITH_EVIDENCE_LOCAL_EXPORT_GAP_NOT_REPAIRED',
                'role':'SOURCE_V3_CONSTRAINT_PARITY_REVIEW' if fix else 'POST_AUDIT_ONLY_NOT_PREDICTOR_INPUT',
                'fixed':fix}
    semantic=read(root/'audits/s1_regression_actual.json',{})
    return {'cases':cases,'models':models,'surfaces':shared,'semantic_regression':semantic.get('actual'),
            'preset':PREFERRED,'natural':'NORTH' if 'NORTH' in cases else None,'post_audit':post_audit,'private_fix':release if fix else None,
            'negative':next((p for p,c in cases.items() if c['label']=='NEGATIVE'),None),
            'source':'© OpenStreetMap contributors · 冻结真实裁片 · EPSG:32651 · 本轮新外部请求 0',
            'build_index':index}


def main(args):
    data=assemble(args.root)
    index=data.pop('build_index')
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
    template=(args.root/'src/free_map.html').read_text(encoding='utf-8')
    script=(args.root/'src/free_map.js').read_text(encoding='utf-8')
    output=args.output or args.root/'visuals/index.html'
    output.parent.mkdir(parents=True,exist_ok=True)
    if data.get('private_fix'):
        original=args.root/data['private_fix']['historical_atlas']
        history=args.root/'visuals/r0_index.html'
        if history.exists():
            if sha(history)!=sha(original):raise ValueError('Existing R0 atlas differs from sealed archive copy')
        else:
            history.write_bytes(original.read_bytes())
    output.write_text(template.replace('__PAYLOAD__',base64.b64encode(gzip.compress(payload,mtime=0)).decode()).replace('__SCRIPT__',script),encoding='utf-8')
    receipt={'status':'BUILT','cases':len(data['cases']),'models':len(data['models']),
             'html_sha256':sha(output),'html_bytes':output.stat().st_size,'raw_json_bytes':len(payload),'index':index,
             'display_only_context_policy':'160m previous observed only; never sent to predictor; references off by default'}
    (args.root/'audits/visual_build.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='index'},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path)
    main(parser.parse_args())
