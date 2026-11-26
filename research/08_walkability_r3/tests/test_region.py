"""Synthetic fixtures: policy and geometry, separate from map evidence."""
import json
from pathlib import Path

from shapely.geometry import LineString, Point, box, mapping

from src.region import INFERRED, NATIVE, RESTRICTED, UNKNOWN, Surface, build_surface
from src.region_routing import native_graph, region_graph, routed_queries, surface_parts
from src.semantics import KEEP, REJECT, segment_decision

CFG={**json.loads((Path(__file__).parents[1]/"config/region.json").read_text()),"domain_radius_m":12}
WALK={"highway":"footway"}


def obj(ident,kind,g,tags=None,**extra):
    return {"id":ident,"kind":kind,"geometry":mapping(g),"tags":tags or {},**extra}


def observed(park=True,door=True):
    rows=[{"id":i,"xy":[-6,y],"tags":{}} for i,y in [("a",-6),("b",0),("c",6)]]
    edges=[{"id":f"way/10/{a}/{b}","u":a,"v":b,"kind":"NATIVE_LINEAR","tags":WALK}
           for a,b in [("a","b"),("b","a"),("b","c"),("c","b")]]
    hard=[obj("way/11","BUILDING",box(0,-4,10,4),{"building":"yes"})]
    support=[obj("way/12","PARK",box(-11,-9,0,9),{"leisure":"park"})] if park else []
    return {"task_id":"synthetic","crs":"EPSG:32651","domain":{"anchor_xy":[0,0],"anchor_role":"FIXED"},
            "registered_entrance":{"id":"exit","xy":[0,0],"tags":{"entrance":"exit"},
                                   "registered":True,"building_id":"way/11"} if door else None,
            "nodes":rows,"edges":edges,"context":{"hard":hard,"background":[],"support":support}}


def semantic_obstacle(ident,kind,geom,tags=None):
    return {"id":ident,"kind":kind,"geometry":geom,"tags":tags or {}}


def test_grass_native_centerline_remains():
    grass=semantic_obstacle("grass","AREA",box(1,-1,3,1),{"landuse":"grass"})
    line=LineString([(0,0),(4,0)])
    assert segment_decision(line,WALK,[grass],"S0")["status"]==REJECT
    assert segment_decision(line,WALK,[grass],"S1")["status"]==KEEP


def test_grass_without_walkway_cannot_be_inferred():
    inp=observed()
    inp["context"]["background"]=[obj("grass","GRASS",box(-5,-3,-1,3),{"landuse":"grass"})]
    s=build_surface(inp,CFG)
    assert s.masks[RESTRICTED].covers(Point(-3,0))
    assert not s.masks[INFERRED].covers(Point(-3,0))


def test_registered_frontage_has_nonzero_area_before_queries():
    s=build_surface(observed(),CFG)
    assert s.area_m2[INFERRED]>5
    assert s.masks[INFERRED].distance(Point(0,0))<1e-6
    assert s.area_m2[UNKNOWN]>0
    assert abs(sum(s.area_m2.values())-s.domain.area)<1e-5


def test_park_far_from_network_stays_unknown():
    inp=observed(park=False,door=False)
    inp["context"]["support"]=[obj("far","PARK",box(-3,8,3,11),{"leisure":"park"})]
    s=build_surface(inp,CFG)
    assert s.masks[UNKNOWN].covers(Point(0,9))
    assert s.area_m2[INFERRED]==0


def test_wall_without_opening_blocks_full_region_stitch():
    inp=observed()
    inp["context"]["hard"].append(obj("wall","BARRIER",LineString([(-3,-5),(-3,5)])))
    s=build_surface(inp,CFG)
    assert surface_parts(s,LineString([(-4,0),(-2,0)]),CFG) is None


def test_wall_requires_real_shared_gate_for_native_path():
    wall=semantic_obstacle("wall","BARRIER",LineString([(2,-1),(2,1)]))
    wall["gates"]=[{"id":"node/12","allowed":True,"xy":[2,0]}]
    line=LineString([(0,0),(2,0)])
    assert segment_decision(line,WALK,[wall],"S1",native_nodes=(11,13))["status"]==REJECT
    assert segment_decision(line,WALK,[wall],"S1",native_nodes=(11,12))["status"]==KEEP


def test_building_interior_and_foot_no_are_not_open():
    inp=observed()
    inp["context"]["support"].append(obj("private","PAVING",box(-9,-3,-8,3),{"foot":"no"}))
    s=build_surface(inp,CFG)
    assert s.masks[RESTRICTED].covers(Point(2,0))
    assert s.masks[RESTRICTED].covers(Point(-8.5,0))


def test_unbridged_water_blocks_region():
    inp=observed()
    inp["context"]["hard"].append(obj("water","WATER",box(-4,-1,-3,1)))
    s=build_surface(inp,CFG)
    assert surface_parts(s,LineString([(-5,0),(-2,0)]),CFG) is None


def test_native_tagged_bridge_over_water_retained():
    water=semantic_obstacle("water","AREA",box(1,-1,3,1),{"natural":"water"})
    line=LineString([(0,0),(4,0)])
    assert segment_decision(line,{**WALK,"bridge":"yes","layer":"1"},[water],"S1")["status"]==KEEP


def test_explicit_level_not_used_as_ground_support():
    inp=observed()
    for edge in inp["edges"]:
        edge["tags"]={**WALK,"level":"1"}
    s=build_surface(inp,CFG)
    assert s.area_m2[INFERRED]==0


def test_unknown_allowed_only_for_bounded_portal_with_cost():
    domain=box(0,0,3,1)
    masks={NATIVE:box(0,0,0,0),INFERRED:box(.5,0,3,1),RESTRICTED:box(0,0,0,0),UNKNOWN:box(0,0,.5,1)}
    s=Surface(domain,[],masks,{},"synthetic",{}, {},1)
    line=LineString([(0,.5),(1,.5)])
    assert surface_parts(s,line,CFG) is None
    accepted=surface_parts(s,line,CFG,CFG["unknown_portal_budget_m"])
    assert [part["layer"] for part in accepted]==["unknown","inferred"]
    assert accepted[0]["cost_m"]>accepted[0]["length_m"]
    assert surface_parts(s,line,CFG,.4) is None


def test_multiple_queries_reuse_identical_region_and_existing_nodes():
    inp=observed()
    s=build_surface(inp,CFG)
    base=native_graph(inp)
    r=region_graph(s,base,CFG)
    assert len(r.interfaces)>=3
    ports=[{"id":p["id"],"xy":p["xy"]} for p in r.interfaces]
    queries=[{"query_id":str(i),"source":ports[i],"target":ports[i+1],"scope":"LOCAL_REGION_ONLY"}
             for i in (0,1)]
    result=routed_queries(base,r,queries,CFG)
    assert all(v["reached"] and v["uses_inferred_region"] and v["surface_sha256"]==s.sha256 for v in result.values())
    assert result==routed_queries(base,r,list(reversed(queries)),CFG)
