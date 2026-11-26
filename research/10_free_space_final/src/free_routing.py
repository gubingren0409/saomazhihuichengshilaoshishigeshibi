"""A common graph builder, shared by M1-C/F0, with cost-only F1 reweighting."""
from collections import defaultdict
import math
import networkx as nx
from shapely.geometry import LineString,Point
from shapely.strtree import STRtree
from src.region import NATIVE,INFERRED,RESTRICTED,UNKNOWN,union,non_ground,access_conflict
from src.region_routing import (RegionGraph,coords,segment,bidirectional,surface_parts,
                               native_graph,empty,route)
from src.common_constraints import edge_conflicts,parsed_contract

EPS=1e-6

def checked_native(observed,common):
    common=parsed_contract(common) if 'contract' not in common else common
    graph=native_graph(observed)
    rejected=[]
    for u,v,rec in list(graph.edges(data=True)):
        reasons=[]
        for s in rec['segments']:
            reasons.extend(edge_conflicts(LineString(s['xy']),common,native=True,tags=s.get('tags',{}),source_id=s.get('source_id')))
        if reasons:
            rejected.append(dict(u=u,v=v,reasons=reasons,segments=rec['segments']))
            graph.remove_edge(u,v)
    return graph,rejected

def build_graph(surface,network,cfg,common,method):
    common=parsed_contract(common) if 'contract' not in common else common
    graph=nx.DiGraph()
    rows=[c for c in surface.cells if c['walkability_state'] in (NATIVE,INFERRED)]
    points=[c['g'].representative_point() for c in rows]
    index=STRtree(points)
    ij=defaultdict(list)
    for k,c in enumerate(rows):
        graph.add_node(c['region_id'],xy=coords(points[k]),state=c['walkability_state'])
        ij[c['ij']].append(k)
    stats={'active_cells':len(rows),'interface_candidates':0,'interface_rejected':0,'rejected_edges':0}
    def measure(line,label,budget=0):
        if edge_conflicts(line,common,native=False): return None
        return surface_parts(surface,line,cfg,budget,label)
    for k,c in enumerate(rows):
        i,j=c['ij']
        for pair in ((i,j),(i+1,j),(i,j+1)):
            for n in ij.get(pair,[]):
                if pair==(i,j) and n<=k: continue
                d=rows[n]
                if c['g'].intersection(d['g']).length<=EPS: continue
                line=LineString([points[k],points[n]])
                if line.difference(c['g'].union(d['g'])).length>EPS: continue
                measured=measure(line,c['region_id']+'|'+d['region_id'])
                if measured: bidirectional(graph,c['region_id'],d['region_id'],measured)
                else: stats['rejected_edges']+=1
    active=union(c['g'] for c in rows)
    live={node for node,degree in graph.degree() if degree}
    candidates=[]
    xmin,ymin,xmax,ymax=surface.domain.bounds
    for ident,n in network.nodes(data=True):
        x,y=n['xy']; tags=n.get('tags',{})
        if not xmin<=x<=xmax or not ymin<=y<=ymax or non_ground(tags) or access_conflict(tags) or not network.degree(ident):continue
        p=Point(x,y)
        # Same interface policy in every arm; only the actual feasible surface differs.
        distance=active.distance(p)
        if distance>cfg['interface_reach_m'] or surface.masks[RESTRICTED].contains(p): continue
        adjacent=list(network.in_edges(ident,data=True))+list(network.out_edges(ident,data=True))
        source_ids=sorted({s['source_id'] for _,_,r in adjacent for s in r['segments'] if not non_ground(s.get('tags',{}))})
        if source_ids:candidates.append((distance,ident,p,source_ids))
    interfaces=[]
    stats['interface_candidates']=len(candidates)
    for distance,ident,p,sources in sorted(candidates,key=lambda x:(x[0],x[1])):
        if any(p.distance(Point(old['xy']))<cfg['interface_separation_m'] for old in interfaces):continue
        accepted=None
        for k in sorted(index.query(p,predicate='dwithin',distance=cfg['interface_reach_m']),key=lambda k:(p.distance(points[k]),rows[k]['region_id'])):
            c=rows[k]
            if c['region_id'] not in live:continue
            line=LineString([p,points[k]])
            budget=cfg['unknown_portal_budget_m'] if method=='M1-C' else 0
            measured=measure(line,c['region_id'],budget) if line.length>EPS else []
            if measured is None:continue
            if not measured:measured=[segment([coords(p),coords(points[k])],'derived' if c['walkability_state']==NATIVE else 'inferred',c['region_id'],geometry_kind='EXACT_REGION_PORTAL')]
            accepted=c,measured
            break
        if not accepted:
            stats['interface_rejected']+=1;continue
        c,measured=accepted
        graph.add_node(ident,xy=coords(p),tags=network.nodes[ident].get('tags',{}))
        bidirectional(graph,ident,c['region_id'],measured)
        interfaces.append(dict(id=ident,xy=coords(p),source_ids=sources,source_id=sources[0],cell_id=c['region_id'],
                               distance_to_allowed_m=distance,unknown_m=sum(s['length_m'] for s in measured if s['layer']=='unknown'),
                               evidence='SOURCE_NETWORK_NODE_WITH_FULL_SEGMENT_COMMON_CONSTRAINT_CHECK'))
        if len(interfaces)>=cfg['max_interfaces']:break
    stats.update(internal_arcs=graph.number_of_edges(),components=nx.number_weakly_connected_components(graph),interface_count=len(interfaces))
    return RegionGraph(graph,interfaces,active,[(c['region_id'],points[k],c['walkability_state']) for k,c in enumerate(rows)],index,surface,stats)

def reweight(graph,lambda_):
    for _,_,r in graph.edges(data=True):
        for s in r['segments']:
            s['cost_m']=s['length_m']*(lambda_ if s['layer'] in ('inferred','unknown','assumed') else 1)
        r['cost']=sum(s['cost_m'] for s in r['segments'])

def bind(end,region,cfg,common,method,verified_source=None):
    p=Point(end['xy']);key=end['id']
    if key in region.internal and p.distance(Point(region.internal.nodes[key]['xy']))<=EPS:return key,None
    if end.get('role') not in ('REGISTERED_EXIT','REGISTERED_DOOR','CONTROL_INTERIOR_POINT') and verified_source is None:return key,None
    tags={**end.get('tags',{}),**(verified_source.get('tags',{}) if verified_source else {})}
    if access_conflict(tags) or non_ground(tags):return key,None
    for k in sorted(region.index.query(p,predicate='dwithin',distance=cfg['interface_reach_m']),key=lambda k:(p.distance(region.points[k][1]),region.points[k][0])):
        target,point,state=region.points[k]
        if not region.internal.degree(target):continue
        line=LineString([p,point])
        if edge_conflicts(line,common,native=False):continue
        budget=cfg['unknown_portal_budget_m'] if method=='M1-C' else 0
        measured=surface_parts(region.surface,line,cfg,budget,label=target) if line.length>EPS else []
        if measured is None:continue
        if not measured:measured=[segment([coords(p),coords(point)],'inferred' if state==INFERRED else 'derived',target,geometry_kind='EXACT_REGION_PORTAL')]
        return key,(target,measured)
    return key,None

def queries_on_graph(base,region,queries,cfg,common,method,lambda_,visible_source=None):
    common=parsed_contract(common) if 'contract' not in common else common
    combined=nx.compose(base,region.internal)
    outcomes={};terminals=[]
    for q in queries:
        graph=region.internal if q.get('scope')=='LOCAL_REGION_ONLY' else combined
        added=[];ids=[]
        for end in (q['source'],q['target']):
            verified=None
            if q.get('scope')=='LOCAL_REGION_ONLY' and visible_source is not None and end['id'] in visible_source:
                candidate=visible_source.nodes[end['id']]
                adjacent=list(visible_source.in_edges(end['id'],data=True))+list(visible_source.out_edges(end['id'],data=True))
                ground=any(not non_ground(s.get('tags',{})) and not access_conflict(s.get('tags',{})) for _,_,r in adjacent for s in r['segments'])
                if math.dist(candidate['xy'],end['xy'])<=EPS and ground and not non_ground(candidate.get('tags',{})) and not access_conflict(candidate.get('tags',{})):
                    verified=candidate
            key,stitch=bind(end,region,cfg,common,method,verified)
            ids.append(key)
            if key in graph:
                if math.dist(graph.nodes[key]['xy'],end['xy'])>EPS:raise ValueError('Endpoint ID coordinate drift')
            elif stitch:
                attach,measured=stitch
                for s in measured:s['cost_m']=s['length_m']*(lambda_ if s['layer'] in ('inferred','unknown') else 1)
                graph.add_node(key,xy=tuple(end['xy']),tags=end.get('tags',{}))
                bidirectional(graph,key,attach,measured)
                added.append(key)
                terminals.append(dict(query_id=q['query_id'],id=key,attach=attach,xy=end['xy'],segments=measured,
                    binding_evidence='EXACT_VISIBLE_OBSERVED_GRAPH_ID_AND_COORDINATE' if verified is not None else 'ORIGINAL_AUTHORIZED_QUERY_ROLE',
                    endpoint_identity='NATIVE_OSM_NODE' if key.startswith('node/') else 'MAPPED_AREA_DERIVED_OR_EXPLICIT_CONTROL_POINT'))
        result=route(graph,*ids)
        result.update(query_scope=q.get('scope','FULL_NETWORK'),surface_sha256=region.surface.sha256,
                      uses_inferred_region=result['layer_lengths']['inferred']>EPS,
                      terminal_error_m=0 if result['reached'] else None,
                      approximate_terminal=False,endpoint_displacement_m=0,
                      generalized_cost_units='WEIGHTED_METRE_NOT_GEOMETRIC_LENGTH')
        outcomes[q['query_id']]=result
        graph.remove_nodes_from(added)
    return outcomes,terminals

def graph_record(graph):
    return dict(nodes=[dict(id=n,**v) for n,v in sorted(graph.nodes(data=True))],
                edges=[dict(u=u,v=v,segments=[{k:v for k,v in s.items() if k!='cost_m'} for s in r['segments']]) for u,v,r in sorted(graph.edges(data=True))])
