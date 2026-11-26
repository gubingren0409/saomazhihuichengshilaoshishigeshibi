"""Two-axis planning surfaces; prediction does not read endpoints or references."""
import math
from collections import defaultdict
from shapely import normalize, make_valid
from shapely.geometry import shape, mapping, box
from shapely.ops import split
from src.region import (Surface, NATIVE, INFERRED, RESTRICTED, UNKNOWN, STATES,
                        digest, polygons, union)

EPS=1e-8

def partition_roads(g, roads):
    pieces=list(polygons(g))
    for road in roads:
        line=shape(road.get('geometry',road))
        new=[]
        for part in pieces:
            if part.intersects(line):
                try: new.extend(polygons(split(part,line)))
                except ValueError: new.append(part)
            else: new.append(part)
        pieces=new
    # GEOS split can polygonize a near-degenerate ring as a full sliver/triangle.
    # Re-intersect every split result with the actual input fragment. The source
    # fragment, rather than split's ring interpretation, is authoritative.
    return [p for part in pieces for p in polygons(part.intersection(g))]

def build_free_surface(base, common, *, default=False):
    """F0 is exactly valid minus blocked, with no positive admission criteria."""
    domain=base.domain
    # The common contract is already validated/clipped. Repeated clipping of
    # nearly coincident outer rings can change polygonization despite tiny area
    # differences. Use the one serialized shared contract as the authority.
    valid=shape(common['valid_geometry'])
    blocked=shape(common['blocked_geometry'])
    native=base.masks[NATIVE].intersection(valid).difference(blocked)
    assumed=(valid.difference(blocked).difference(native) if default else
             base.masks[INFERRED].intersection(valid).difference(blocked))
    unknown=domain.difference(blocked).difference(native).difference(assumed)
    masks={NATIVE:native,INFERRED:assumed,RESTRICTED:blocked,UNKNOWN:unknown}
    constraints=[(r,shape(r['geometry'])) for r in common.get('constraints',[]) if 'geometry' in r]
    cells=[]
    base_by_grid=defaultdict(list)
    for c in base.cells: base_by_grid[c['ij']].append(c)
    x0,y0,x1,y1=domain.bounds
    for i in range(math.floor(x0),math.ceil(x1)):
        for j in range(math.floor(y0),math.ceil(y1)):
            tile=box(i,j,i+1,j+1).intersection(domain)
            if tile.area<=EPS: continue
            for state in STATES:
                fragments=partition_roads(tile.intersection(masks[state]),common.get('road_centerlines',[]))
                # Check against the complete source mask, not just the tile's
                # intermediate ring. This also removes degenerate split ghosts.
                for g in (p for part in fragments for p in polygons(part.intersection(masks[state]))):
                    if g.area<=EPS: continue
                    ids=sorted({r.get('source_id',r.get('constraint_id','')) for r,h in constraints if h.intersection(g).area>EPS})
                    no_data=g.intersection(valid).area<=EPS
                    is_native=state==NATIVE
                    is_assumed=state==INFERRED
                    reason=('SOURCE_MAPPED_AREA' if is_native else
                            'DEFAULT_FREE_POLICY_V1' if is_assumed and default else
                            'FROZEN_M1_POSITIVE_EVIDENCE' if is_assumed else
                            'COMMON_SOURCE_OR_POLICY_RESTRICTION' if state==RESTRICTED else
                            'MAP_DATA_UNAVAILABLE' if no_data else 'M1_NO_POSITIVE_ADMISSION')
                    evidence=('NATIVE_SUPPORTED' if is_native else 'EXPLICIT_SOURCE_OR_POLICY_OBJECT' if state==RESTRICTED else
                              'MAP_DATA_UNAVAILABLE' if no_data else 'UNLABELLED_UNVERIFIED')
                    planning=('NATIVE_PASSABLE' if is_native else 'ASSUMED_PASSABLE' if is_assumed else
                              'FORBIDDEN' if state==RESTRICTED else 'NO_DATA' if no_data else 'NOT_ADMITTED')
                    supports=sorted({r['id'] for r in base.context['native'] if r['g'].intersection(g).area>EPS}) if is_native else []
                    old_support=[r for r in base_by_grid[(i,j)] if r['walkability_state']==INFERRED and r['g'].intersection(g).area>EPS] if is_assumed and not default else []
                    if old_support: supports=sorted({s for r in old_support for s in r['evidence_sources']})
                    cells.append(dict(region_id=f'cell/{i}/{j}/{len(cells)}',ij=(i,j),g=g,
                        geometry=mapping(normalize(g)),walkability_state=state,
                        source_evidence_state=evidence,planning_state=planning,
                        reason_code=reason,decision_reason=reason,policy_id='DEFAULT_FREE_POLICY_V1' if default and is_assumed else 'COMMON_CONSTRAINT_V1',
                        observed_source_ids=supports if is_native or is_assumed else ids,evidence_sources=supports if is_native or is_assumed else ids,
                        positive_reason_codes=sorted({r['decision_reason'] for r in old_support}),
                        assumptions=['LOCAL_OUTDOOR_CONTINUITY_UNVERIFIED','ACCESS_AND_LEVEL_NOT_FIELD_VERIFIED'] if is_assumed else [],
                        constraint_ids=ids,hard_conflicts=ids if state==RESTRICTED else [],
                        map_coverage_status='DATA_UNAVAILABLE' if no_data else 'ACQUIRED_CLIP_NOT_COMPLETE_SURVEY',
                        component_id=None,uncertainty_level='CONDITIONAL_UNCALIBRATED' if is_assumed else 'SOURCE_OR_POLICY',
                        source_status='native' if is_native else 'inferred' if is_assumed else 'derived',area_m2=g.area))
    # Component identity is a geometry property, never derived from the eventual query.
    components=list(polygons(union((native,assumed))))
    for c in cells:
        if c['walkability_state'] in (NATIVE,INFERRED):
            c['component_id']=next((f'component/{k}' for k,g in enumerate(components) if g.covers(c['g'].representative_point())),None)
    area={s:masks[s].area for s in STATES}
    canonical=[{k:v for k,v in c.items() if k!='g'} for c in cells]
    return Surface(domain,cells,masks,base.context,digest(canonical),area,
        dict(cell_fragments=len(cells),classified_m2=sum(area.values()),search_domain_m2=domain.area,
             valid_area_m2=valid.area,no_data_m2=domain.difference(valid).area,
             inferred_components=len(list(polygons(assumed))),passable_components=len(components),
             admission='VALID_MINUS_COMMON_BLOCKED' if default else 'FROZEN_M1_INTERSECT_COMMON',
             road_constraint='ZERO_WIDTH_TOPOLOGICAL_BARRIER_NOT_MEASURED_WIDTH'),1)
