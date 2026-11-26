"""Exact polygonal visibility roadmaps and finite-source-interface overlays.

No route answers, benchmark references, source IDs used as allowlists, snapping,
or post-route smoothing. Euclidean bends need only free-space reflex vertices;
every submitted segment is checked in its complete polygon component.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
import math
from fractions import Fraction
from time import perf_counter

import networkx as nx
from shapely.geometry import GeometryCollection, LineString, Point, Polygon
from shapely.ops import substring
from shapely.prepared import prep

from src.region import access_conflict, non_ground

EPS = 1e-6  # inherited metre-scale numerical tolerance, never a domain buffer
CONTACT_ROUNDOFF_LIMIT_M = 1e-8  # GEOS-derived intersections only, never a snap


def polygon_parts(g):
    if g.geom_type == 'Polygon':
        if g.area > EPS * EPS:
            yield g
    else:
        for child in getattr(g, 'geoms', ()):
            yield from polygon_parts(child)


def _identity(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _reflex_corner_map(poly):
    """All necessary Euclidean bends, with no non-collinear simplification.

    Exterior reflex turns and hole convex turns are reflex for the free domain.
    Exact zero cross-products remove only exactly collinear ring vertices.
    """
    result={}
    for hole,ring in [(False,poly.exterior),*[(True,r)for r in poly.interiors]]:
        xy=list(ring.coords)[:-1]
        winding=1 if ring.is_ccw else -1
        for i,b in enumerate(xy):
            a,c=xy[i-1],xy[(i+1)%len(xy)]
            turn=_orientation(a,b,c)
            if turn*winding*(1 if hole else -1)>0:
                result[tuple(b)]=(tuple(a),tuple(c))
    return result


def reflex_vertices(poly):
    return sorted(_reflex_corner_map(poly))


def _orientation(a,b,c):
    """Robust orientation of binary input coordinates, not a geometry buffer."""
    x,y=b[0]-a[0],b[1]-a[1];u,v=c[0]-a[0],c[1]-a[1]
    left,right=x*v,y*u;det=left-right
    if abs(det)>(abs(left)+abs(right))*2**-48:
        return 1 if det>0 else -1
    ax,ay=Fraction(a[0]),Fraction(a[1]);bx,by=Fraction(b[0]),Fraction(b[1]);cx,cy=Fraction(c[0]),Fraction(c[1])
    exact=(bx-ax)*(cy-ay)-(by-ay)*(cx-ax)
    return (exact>0)-(exact<0)


class VisibilityRoadmap:
    """One positive-area polygon component; never joins point-touching parts."""
    def __init__(self,poly,edge_allowed=None,required_points=(),prefix='visibility',tangent_filter=True):
        if poly.geom_type!='Polygon' or not poly.is_valid:
            raise ValueError('Visibility domain must be one valid Polygon')
        self.poly=poly;self.prepared=prep(poly);self.edge_allowed=edge_allowed
        self.graph=nx.DiGraph();self.prefix=prefix;self.points={};self.corner_neighbors={};self.tangent_filter=tangent_filter
        self.stats={'visibility_checks':0,'domain_rejections':0,'constraint_rejections':0,
                    'numeric_tolerance_admissions':0,'reflex_vertices':0,'required_points':0,'pair_candidates':0,'local_tangent_rejections':0}
        corners=_reflex_corner_map(poly);bends=sorted(corners);self.stats['reflex_vertices']=len(bends)
        for k,xy in enumerate(bends):
            ident=f'{prefix}/v/{k}';self.add_point(ident,xy,kind='POLYGON_FREE_REFLEX_VERTEX');self.corner_neighbors[ident]=corners[xy]
        for k,xy in enumerate(required_points):
            if poly.covers(Point(xy)):
                self.add_point(f'{prefix}/required/{k}',xy,kind='SOURCE_REQUIRED_GATE_POINT')
                self.stats['required_points']+=1

    def visible(self,a,b):
        a,b=tuple(a),tuple(b)
        self.stats['visibility_checks']+=1
        line=LineString([a,b])
        if a==b:
            accepted=self.prepared.covers(Point(a))
        else:
            accepted=self.prepared.covers(line)
        if not accepted:self.stats['domain_rejections']+=1
        elif self.edge_allowed is not None and not self.edge_allowed(line):
            accepted=False;self.stats['constraint_rejections']+=1
        return accepted

    def _tangent_at(self,node,other):
        if node not in self.corner_neighbors:return True
        a,c=self.corner_neighbors[node];p=self.points[node]
        return _orientation(p,other,a)*_orientation(p,other,c)>=0

    def add_point(self,ident,xy,kind='PORTAL'):
        xy=tuple(float(x)for x in xy)
        if ident in self.points:
            if self.points[ident]!=xy:raise ValueError('Visibility vertex ID coordinate drift')
            return
        if not self.poly.covers(Point(xy)) and Point(xy).distance(self.poly)>EPS:
            raise ValueError('Point outside visibility component')
        self.points[ident]=xy;self.graph.add_node(ident,xy=xy,kind=kind)

    def connect_all(self):
        rows=list(self.points.items())
        for i,(a,p)in enumerate(rows):
            for b,q in rows[i+1:]:
                self.stats['pair_candidates']+=1
                # A Euclidean shortest path cannot turn at a polygon corner on
                # a non-supporting departure: that corner can be shortened away.
                # Portal/gate endpoints are never removed by this criterion.
                if self.tangent_filter and p!=q and not(self._tangent_at(a,q)and self._tangent_at(b,p)):
                    self.stats['local_tangent_rejections']+=1;continue
                if self.visible(p,q):
                    length=math.dist(p,q)
                    self.graph.add_edge(a,b,cost=length,length_m=length)
                    self.graph.add_edge(b,a,cost=length,length_m=length)
        return self.graph

    def path(self,a,b):
        try:ids=nx.shortest_path(self.graph,a,b,weight='cost')
        except(nx.NetworkXNoPath,nx.NodeNotFound):return None
        points=[self.points[n]for n in ids]
        return {'points':points,'length_m':sum(math.dist(p,q)for p,q in zip(points,points[1:])),'node_ids':ids}


def shortest_path(domain,start,end,edge_allowed=None,required_points=()):
    """Specified endpoints; component-wise full reflex visibility, not funnel."""
    start,end=tuple(start),tuple(end);tick=perf_counter();answers=[];stats=[]
    for k,poly in enumerate(polygon_parts(domain)):
        if not poly.covers(Point(start))or not poly.covers(Point(end)):continue
        model=VisibilityRoadmap(poly,edge_allowed,required_points,prefix=f'component/{k}')
        model.add_point('start',start);model.add_point('end',end);model.connect_all()
        result=model.path('start','end')
        stats.append(model.stats)
        if result:answers.append(result)
    best=min(answers,key=lambda r:r['length_m'])if answers else None
    return {'status':'ROUTED'if best else'NO_PATH','reached':bool(best),
            'length_m':best['length_m']if best else None,'points':best['points']if best else [],
            'stats':stats,'elapsed_s':perf_counter()-tick,
            'optimality':'POLYGON_COMPONENT_UNIFORM_LENGTH_WITH_COMPLETE_REFLEX_VISIBILITY; FLOATING_GEOMETRY; EXTRA_EDGE_RULES_AND_REQUIRED_GATES_LIMIT_CONTINUOUS_CLAIM' }


def _linear_parts(g):
    if g.geom_type=='LineString':
        if g.length>EPS:yield g
    else:
        for c in getattr(g,'geoms',()):yield from _linear_parts(c)


def _contact_points(g):
    if g.is_empty:return []
    if g.geom_type=='Point':return [tuple(g.coords[0])]
    if g.geom_type=='LineString':return [tuple(g.coords[0]),tuple(g.coords[-1])]
    return [p for c in getattr(g,'geoms',())for p in _contact_points(c)]


def _ground_arc(graph,u,v,row):
    if any(non_ground(graph.nodes[n].get('tags',{}))or access_conflict(graph.nodes[n].get('tags',{}))for n in (u,v)):return False
    return all(not non_ground(s.get('tags',{}))and not access_conflict(s.get('tags',{}))for s in row['segments'])


def _point_contacts(geometry):
    if geometry.geom_type=='Point':yield geometry
    elif geometry.geom_type not in ('Polygon','LineString','LinearRing'):
        for part in getattr(geometry,'geoms',()):yield from _point_contacts(part)


def _positive_parent_entry(graph,ident,adjacent,poly):
    """A nonnative local point needs a covered interval, not a corner touch."""
    xy=tuple(graph.nodes[ident]['xy'])
    for u,v,row in adjacent:
        for option in _arc_options(row):
            coordinates=[tuple(q)for s in option for q in s['xy']]
            if v==ident:coordinates=coordinates[::-1]
            if not coordinates or coordinates[0]!=xy:continue
            next_point=next((q for q in coordinates[1:]if q!=xy),None)
            if next_point is None:continue
            segment=LineString([xy,next_point])
            stack=[segment.intersection(poly)]
            while stack:
                part=stack.pop()
                if part.geom_type=='LineString':
                    if part.length>0 and part.covers(Point(xy)):return True
                else:stack.extend(getattr(part,'geoms',()))
    return False


def _split_record_segments(segments,begin,end):
    """Clip complete original polylines, keeping provenance and cost ratios."""
    out=[];offset=0
    for s in segments:
        line=LineString(s['xy']);length=line.length
        if abs(length-s['length_m'])>EPS:raise ValueError('Original edge length/geometry mismatch')
        lo=max(0,begin-offset);hi=min(length,end-offset);offset+=length
        if hi<=lo:continue
        piece=substring(line,lo,hi);r={**s,'xy':[list(p)for p in piece.coords],
            'length_m':piece.length,'cost_m':piece.length*(s.get('cost_m',length)/length if length else 1),
            'topology_split':'EXACT_LINE_FACE_INTERSECTION; ORIGINAL_DIRECTION_PRESERVED'}
        out.append(r)
    return out


def _arc_options(row):
    return row.get('routing_alternatives',[row['segments']])


def _add_arc(graph,u,v,segments,source_graph=None,stats=None):
    """Preserve geometric alternatives; F0 unit cost cannot dominate F1 cost."""
    options=[]
    if source_graph is not None and source_graph.has_edge(u,v):options.extend(_arc_options(source_graph[u][v]))
    if graph.has_edge(u,v):options.extend(_arc_options(graph[u][v]))
    options=list({_identity(option):option for option in options}.values())
    known={_identity(option)for option in options};key=_identity(segments)
    if key in known:return
    if options and stats is not None:
        stats['same_uv_distinct_candidates']+=1
        signature=lambda ss:tuple(sorted({(s['layer'],s.get('geometry_kind',''))for s in ss}))
        if any(signature(ss)!=signature(segments)for ss in options):stats['different_layer_or_geometry_candidates']+=1
        cost=lambda ss,w:sum(s['length_m']*(w if s['layer']in('inferred','assumed','unknown')else 1)for s in ss)
        old=min(options,key=lambda ss:cost(ss,1));c0,c1=cost(segments,1),cost(segments,2)
        if c0>=cost(old,1)and c1<cost(old,2):stats['unitcost_discard_would_lose_F1_candidate']+=1
        if c0==cost(old,1)and c1<cost(old,2):stats['equal_F0_derived_or_native_wins_F1']+=1
    options.append(segments)
    # Canonical F0 record remains for old consumers. Request-time code MUST
    # choose its actual segments using the same cost as its solver callback.
    canonical=min(options,key=lambda ss:sum(s['cost_m']for s in ss))
    graph.add_edge(u,v,cost=sum(s['cost_m']for s in canonical),segments=canonical,routing_alternatives=options)


def _split_point(segments,position,total):
    """Coordinates are exactly those that the final source-arc split stores."""
    left=_split_record_segments(segments,0,position)
    right=_split_record_segments(segments,position,total)
    if not left or not right:return None
    a=tuple(left[-1]['xy'][-1]);b=tuple(right[0]['xy'][0])
    if a!=b:raise ValueError('Parent split generated inconsistent shared coordinates')
    return a


def _certified_parent_contact(segments,line,poly,position,raw_xy,break_positions):
    """Normalize only computed line/boundary roundoff along its parent arc.

    No source vertex, gate, query endpoint or polygon is moved. A valid contact
    needs a positive-length parent interval within this same component. Pure
    point touches therefore do not become new cross-component connections.
    """
    total=line.length;before=position;answers=[]
    lower=max((d for d in break_positions if d<position),default=0.)
    upper=min((d for d in break_positions if d>position),default=total)
    for other in ((lower+position)/2,(upper+position)/2):
        if other==position:continue
        probe=_split_point(segments,other,total)
        if probe is None or not poly.covers(Point(probe)):continue
        direction=1 if other>position else -1
        step=max(abs(math.nextafter(position,other)-position),math.ulp(max(abs(x)for x in raw_xy)),1e-12)
        trial_positions=[position]
        for k in range(32):
            delta=min(step*2**k,CONTACT_ROUNDOFF_LIMIT_M)
            p=position+direction*delta
            if min(position,other)<=p<=max(position,other):trial_positions.append(p)
            if delta==CONTACT_ROUNDOFF_LIMIT_M:break
        accepted=None;last_bad=position
        for p in trial_positions:
            xy=_split_point(segments,p,total)
            if xy is None:continue
            pieces=_split_record_segments(segments,min(p,other),max(p,other))
            inside=LineString([q for s in pieces for q in s['xy']])
            if poly.covers(Point(xy))and poly.covers(inside):
                accepted=(p,xy);break
            last_bad=p
        if accepted is None:continue
        # Refine toward the original parameter, retaining only strict covers.
        good,xy=accepted
        for _ in range(24):
            middle=(last_bad+good)/2
            if middle in (last_bad,good):break
            q=_split_point(segments,middle,total)
            pieces=_split_record_segments(segments,min(middle,other),max(middle,other))
            if q is not None and poly.covers(Point(q))and poly.covers(LineString([r for s in pieces for r in s['xy']])):good,xy=middle,q
            else:last_bad=middle
        shift=math.dist(raw_xy,xy)
        if shift<=CONTACT_ROUNDOFF_LIMIT_M and abs(good-before)<=CONTACT_ROUNDOFF_LIMIT_M:
            answers.append({'xy':xy,'position_m':good,'raw_intersection_xy':list(raw_xy),'parent_position_before_m':before,
                            'parent_position_after_m':good,'coordinate_shift_m':shift,'parameter_shift_m':good-before,
                            'roundoff_limit_m':CONTACT_ROUNDOFF_LIMIT_M,'positive_parent_interval_witness_m':[min(good,other),max(good,other)],
                            'policy':'DERIVED_GEOS_BOUNDARY_INTERSECTION_ON_SAME_PARENT_ARC; STRICT_COMPONENT_COVERS; NO_SOURCE_OR_DOMAIN_MOVEMENT'})
    return min(answers,key=lambda r:(r['coordinate_shift_m'],abs(r['parameter_shift_m'])))if answers else None


def build_overlay(faces,source_graph,local_region,common,cfg=None):
    """Add complete-face roadmaps at source-supported finite interfaces.

    Existing arcs are never removed. Exact intersections split old arcs into
    equivalent directed pieces; no distance-based snapping is used. Old mapped
    grid interiors are not promoted wholesale into O(N²) visibility portals.
    """
    tick=perf_counter();overlay=nx.DiGraph();reports=[];all_portals=[];split_records=[]
    option_stats=defaultdict(int);contact_stats=defaultdict(int);contact_certificates=[]
    if not faces:
        return overlay,{'mode':'FULL_FACE','faces':[],'portals':[],'exact_directed_splits':[],
            'nodes':0,'arcs':0,'elapsed_s':perf_counter()-tick,'fallback':'NO_ELIGIBLE_MAPPED_FACE_KEEP_OLD_GRAPH',
            'mutated_source_graph':False,'reference_or_saved_route_reads':False}
    from src.face_geometry import face_edge_conflicts
    region_graph=local_region.internal if hasattr(local_region,'internal')else local_region
    candidate_graphs=[('SOURCE',source_graph),('LOCAL_REGION',region_graph)]
    all_components=[(fi,ci,r['geometry'])for fi,f in enumerate(faces)for ci,r in enumerate(f.get('components')or[{'geometry':p}for p in polygon_parts(f['omega'])])]
    point_junctions=defaultdict(list)
    for ai,(fi,ci,poly)in enumerate(all_components):
        for fj,cj,other in all_components[ai+1:]:
            if not poly.intersects(other):continue
            for contact in _point_contacts(poly.intersection(other)):
                point_junctions[(fi,ci)].append(contact);point_junctions[(fj,cj)].append(contact)
    for fi,face in enumerate(faces):
        source_id=face.get('source_id',face.get('id'));omega=face['omega']
        face_report={'source_id':source_id,'status':face.get('status','ADMITTED'),'components':[],'geometry_hash':face.get('geometry_hash')}
        components=[r['geometry']for r in face['components']]if face.get('components')else list(polygon_parts(omega))
        for ci,poly in enumerate(components):
            prefix=f'fullface/{source_id}/component/{ci}'
            accepted=lambda line: not face_edge_conflicts(line,face,common)
            required=[r.get('xy',r)if isinstance(r,dict)else r for r in face.get('required_points',[])]
            model=VisibilityRoadmap(poly,accepted,required,prefix=prefix);portals={};pmeta={};native_portals=set();local_stats=defaultdict(int)
            bound=poly.bounds;boundary=poly.boundary
            def add_portal(ident,xy,evidence):
                xy=tuple(xy)
                if not poly.covers(Point(xy))and Point(xy).distance(poly)>EPS:return False
                if ident in portals and portals[ident]!=xy:raise ValueError('Portal source coordinate mismatch')
                portals[ident]=xy;pmeta.setdefault(ident,[]).append(evidence);return True
            # Eligible original nodes are true source interfaces, not nearest
            # positions; entire original edges remain available outside the face.
            for ident,row in source_graph.nodes(data=True):
                xy=row['xy']
                if not(bound[0]-EPS<=xy[0]<=bound[2]+EPS and bound[1]-EPS<=xy[1]<=bound[3]+EPS):continue
                adjacent=list(source_graph.in_edges(ident,data=True))+list(source_graph.out_edges(ident,data=True))
                native=[(u,v,r)for u,v,r in adjacent if any(s['layer']=='native'for s in r['segments'])and _ground_arc(source_graph,u,v,r)]
                if native and any(contact.equals(Point(xy))for contact in point_junctions[(fi,ci)])and not _positive_parent_entry(source_graph,ident,native,poly):
                    local_stats['rejected_native_junction_without_positive_source_interval']+=1;continue
                if native and add_portal(ident,xy,{'kind':'EXACT_GROUND_NATIVE_NODE_IN_FACE','source_ids':sorted({s['source_id']for _,_,r in native for s in r['segments']if s['layer']=='native'})}):native_portals.add(ident)
            # Keep every existing grid/source interface that can leave this face.
            # Interior region cells stay in the original graph and need not all
            # become visibility vertices: only transitions affect the whole route.
            for ident,row in region_graph.nodes(data=True):
                xy=row['xy'];p=Point(xy)
                if not poly.covers(p):continue
                adjacent=list(region_graph.in_edges(ident,data=True))+list(region_graph.out_edges(ident,data=True))
                outside=any(not poly.covers(Point(region_graph.nodes[v if u==ident else u]['xy']))for u,v,_ in adjacent)
                if ident not in source_graph and not outside:continue
                if ident not in native_portals:
                    if any(contact.equals(p)for contact in point_junctions[(fi,ci)]):
                        local_stats['rejected_non_native_point_only_component_junction']+=1;continue
                    if not _positive_parent_entry(region_graph,ident,adjacent,poly):
                        local_stats['rejected_no_positive_covered_parent_interval']+=1;continue
                else:local_stats['existing_native_topology_exceptions']+=1
                add_portal(ident,xy,{'kind':'EXACT_EXISTING_LOCAL_REGION_INTERFACE','adjacent_outside_face':outside,
                                    'positive_covered_parent_interval':ident in native_portals or _positive_parent_entry(region_graph,ident,adjacent,poly),
                                    'existing_native_topology_exception':ident in native_portals})
            # Source and regional arcs can enter between old vertices. Their
            # intersection coordinates are inserted with unchanged direction.
            for channel,graph in candidate_graphs:
                for u,v,row in graph.edges(data=True):
                    if not _ground_arc(graph,u,v,row):continue
                    coordinates=[p for s in row['segments']for p in s['xy']]
                    if len(coordinates)<2:continue
                    line=LineString(coordinates);x0,y0,x1,y1=line.bounds
                    if x1<bound[0]or x0>bound[2]or y1<bound[1]or y0>bound[3]or not line.intersects(boundary):continue
                    contacts=[]
                    raw_contacts=[(line.project(Point(xy)),xy)for xy in _contact_points(line.intersection(boundary))]
                    break_positions=sorted({0.,line.length,*[d for d,_ in raw_contacts]})
                    for pos,raw_xy in raw_contacts:
                        if pos<=EPS or line.length-pos<=EPS:continue
                        contact_stats['raw_boundary_intersections']+=1
                        certified=_certified_parent_contact(row['segments'],line,poly,pos,raw_xy,break_positions)
                        if certified is None:
                            contact_stats['rejected_no_strict_parent_interval_or_roundoff_limit']+=1;continue
                        xy=certified['xy'];pos=certified['position_m']
                        contact_stats['certified_contacts']+=1
                        if certified['coordinate_shift_m'] or certified['parameter_shift_m']:contact_stats['roundoff_normalized_contacts']+=1
                        ident='faceportal/'+_identity([source_id,ci,xy])[:24]
                        certificate={**certified,'channel':channel,'u':u,'v':v,'source_area_id':source_id,'component':ci,
                                     'parent_source_ids':sorted({s['source_id']for s in row['segments']})}
                        contact_certificates.append(certificate)
                        if add_portal(ident,xy,{'kind':'CERTIFIED_PARENT_LINE_FACE_INTERSECTION','channel':channel,'u':u,'v':v,
                                              'source_ids':certificate['parent_source_ids'],'intersection_certificate':certificate}):contacts.append((pos,ident,xy))
                    if not contacts:continue
                    ordered=[(0,u,graph.nodes[u]['xy']),*sorted(set((d,i,tuple(p))for d,i,p in contacts)),(line.length,v,graph.nodes[v]['xy'])]
                    for _,ident,xy in ordered:overlay.add_node(ident,xy=tuple(xy),tags=graph.nodes[ident].get('tags',{})if ident in graph else{})
                    for (a,na,_),(b,nb,_)in zip(ordered,ordered[1:]):
                        pieces=_split_record_segments(row['segments'],a,b)
                        if pieces:
                            if tuple(pieces[0]['xy'][0])!=tuple(overlay.nodes[na]['xy'])or tuple(pieces[-1]['xy'][-1])!=tuple(overlay.nodes[nb]['xy']):
                                raise ValueError('Source split endpoint differs from certified graph portal')
                            _add_arc(overlay,na,nb,pieces,source_graph,option_stats)
                    split_records.append({'source_area_id':source_id,'component':ci,'channel':channel,'u':u,'v':v,'parent_length_m':line.length,'split_positions_m':[d for d,_,_ in ordered]})
            for ident,xy in sorted(portals.items()):model.add_point(ident,xy)
            model.connect_all()
            for ident,attrs in model.graph.nodes(data=True):overlay.add_node(ident,xy=attrs['xy'],tags={})
            for u,v,row in model.graph.edges(data=True):
                a,b=model.points[u],model.points[v];length=row['length_m']
                segs=[]if length==0 else [{'xy':[list(a),list(b)],'layer':'derived','source_id':source_id,'source_area_id':source_id,
                    'length_m':length,'cost_m':length,'tags':face.get('tags',{}),'geometry_kind':'DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE',
                    'area_routing':'FULL_FACE','omega_sha256':face.get('geometry_hash'),'component':ci,'clearance_m':face.get('clearance_m',.25),
                    'source_status':'COMPUTED_VISIBILITY_NOT_NATIVE_WAY','numeric_tolerance_m':EPS}]
                _add_arc(overlay,u,v,segs,source_graph,option_stats)
            ports=[{'id':ident,'xy':list(xy),'source_area_id':source_id,'component':ci,'evidence':pmeta[ident]}for ident,xy in sorted(portals.items())]
            all_portals.extend(ports)
            face_report['components'].append({'component':ci,'area_m2':poly.area,'hole_count':len(poly.interiors),'portal_count':len(ports),
                'roadmap_nodes':len(model.graph),'roadmap_arcs':model.graph.number_of_edges(),'local_interface_statistics':dict(local_stats),**model.stats})
        reports.append(face_report)
    evidence={'mode':'FULL_FACE','faces':reports,'portals':all_portals,'exact_directed_splits':split_records,
        'intersection_certificates':contact_certificates,'intersection_statistics':dict(contact_stats),'arc_alternative_statistics':dict(option_stats),
        'nodes':len(overlay),'arcs':overlay.number_of_edges(),'elapsed_s':perf_counter()-tick,
        'portal_policy':'ALL_ELIGIBLE_NATIVE_NODES_AND_EXACT_NATIVE/LOCAL_BOUNDARY_INTERSECTIONS; ALL_EXISTING_EXTERNAL_LOCAL_INTERFACES; NO_GLOBAL16_CAP',
        'optimality':'UNIFORM_FACE_LOCALLY_TANGENT_REFLEX_VISIBILITY_AT_FINITE_SOURCE_INTERFACES; FULL_NETWORK_GRAPH_OPTIMUM_NOT_CONTINUOUS_GLOBAL_ACCESS_OPTIMUM',
        'mutated_source_graph':False,'reference_or_saved_route_reads':False}
    if not any(r['components']for r in reports):evidence['fallback']='NO_LEGAL_COMPONENT_KEEP_OLD_GRAPH'
    elif not all_portals:evidence['fallback']='NO_SOURCE_OR_LOCAL_INTERFACE_KEEP_OLD_GRAPH'
    return overlay,evidence
