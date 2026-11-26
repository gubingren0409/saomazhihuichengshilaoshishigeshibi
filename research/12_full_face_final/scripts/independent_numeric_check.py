"""Bounded rational audit of floating polygon-cover counterexamples.

Binary float vertices are interpreted as exact rationals. Partition a query
line by every polygon-edge intersection, then exact point-in-polygon each
open interval. This is independent of GEOS covers/difference predicates.
Only a small fixed number of candidate edges is checked, not a route solver.
"""
from pathlib import Path
from fractions import Fraction as F
import argparse,json,sys,time
from itertools import chain
from shapely.geometry import shape,LineString,Point
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from independent_face_check import save,file_sha,polygons

def xy(p):return tuple(F(x)for x in p)
def sub(a,b):return(a[0]-b[0],a[1]-b[1])
def cross(a,b):return a[0]*b[1]-a[1]*b[0]
def between(p,a,b):return cross(sub(p,a),sub(b,a))==0 and min(a[0],b[0])<=p[0]<=max(a[0],b[0])and min(a[1],b[1])<=p[1]<=max(a[1],b[1])
def inside_ring(p,ring):
    inside=False
    for a,b in zip(ring,ring[1:]):
        if between(p,a,b):return 0  # exact boundary
        if(a[1]>p[1])!=(b[1]>p[1]):
            cut=a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1])
            if cut>p[0]:inside=not inside
    return 1 if inside else -1
def exact_covers(poly,a,b):
    a,b=xy(a),xy(b);d=sub(b,a);rings=[[xy(p)for p in r.coords]for r in[poly.exterior,*poly.interiors]]
    events={F(0),F(1)}
    for ring in rings:
        for c,e in zip(ring,ring[1:]):
            v=sub(e,c);den=cross(d,v);w=sub(c,a)
            if den:
                t=cross(w,v)/den;u=cross(w,d)/den
                if 0<=t<=1 and 0<=u<=1:events.add(t)
            elif cross(w,d)==0:
                axis=0 if d[0]else 1
                if d[axis]:
                    for p in[c,e]:
                        t=(p[axis]-a[axis])/d[axis]
                        if 0<=t<=1:events.add(t)
    def contained(t):
        p=(a[0]+t*d[0],a[1]+t*d[1])
        return inside_ring(p,rings[0])>=0 and all(inside_ring(p,r)<=0 for r in rings[1:])
    ordered=sorted(events)
    probes=ordered+[(x+y)/2 for x,y in zip(ordered,ordered[1:])]
    outside=[t for t in probes if not contained(t)]
    return {'covered':not outside,'event_count':len(events),'outside_first_t':str(outside[0])if outside else None}

def check(path,source_id=None):
    before=file_sha(path);saved=json.loads(path.read_text(encoding='utf-8'));rows=[];tick=time.perf_counter()
    for f in saved.get('mapped_faces',saved.get('faces',[])):
        if source_id and f['source_id']!=source_id:continue
        if f.get('status')!='ADMITTED':continue
        omega=shape(f['omega']);parts=[shape(r['geometry'])for r in f['components']];cases=[]
        for component_id,p in enumerate(parts):
            vertices=list(dict.fromkeys(tuple(c)for ring in[p.exterior,*p.interiors]for c in list(ring.coords)[:-1]))
            vertices+=list(dict.fromkeys(tuple(r['xy'])for r in saved.get('face_network',{}).get('portals',[])if r['source_area_id']==f['source_id']and r['component']==component_id))
            # Adjacent boundary edges first, then lexicographic complete pairs.
            adjacent=[(tuple(a),tuple(b))for ring in[p.exterior,*p.interiors]for a,b in zip(list(ring.coords),list(ring.coords)[1:])]
            pairs=chain(adjacent,((a,b)for i,a in enumerate(vertices)for b in vertices[i+1:]))
            for a,b in pairs:
                line=LineString([a,b]);pc=p.covers(line);oc=omega.covers(line)
                if pc and oc:continue
                outside_component=line.difference(p).length;outside_omega=line.difference(omega).length
                if max(outside_component,outside_omega)>1e-6:continue
                exactp=exact_covers(p,a,b)
                exacto=next((exact_covers(q,a,b)for q in polygons(omega)if q.covers(Point(a))),None)
                cases.append({'component':component_id,'a':a,'b':b,'component_covers':pc,'omega_covers':oc,
                    'outside_component_m':outside_component,'outside_omega_m':outside_omega,'component_relate':p.relate(line),
                    'omega_relate':omega.relate(line),'exact_component':exactp,'exact_omega':exacto})
                if len(cases)>=5:break
            if len(cases)>=5:break
        rows.append({'source_id':f['source_id'],'omega_equals_component_union':all(omega.equals(p)for p in parts)if len(parts)==1 else None,'cases':cases})
    result={'reviewer':'/root/face_review','role':'INDEPENDENT_EXACT_BINARY_POLYGON_EDGE_CHECK','input_file':str(path),'input_sha256':before,
        'source_stable':before==file_sha(path),'rows':rows,'elapsed_s':time.perf_counter()-tick,'APP_solver_calls':0,
        'limits':'First five lexicographic/adjacent small-outside candidate edges per face only, not a whole-roadmap or continuous-world proof'}
    save(ROOT/'audits/independent_numeric_predicates.json',result)
    print(json.dumps({'faces':[(r['source_id'],len(r['cases']),sum(c['exact_component']['covered']for c in r['cases']),sum(c['exact_omega']is not None and c['exact_omega']['covered']for c in r['cases']))for r in rows],'elapsed_s':result['elapsed_s']},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--source');a=p.parse_args();check(a.input,a.source)
