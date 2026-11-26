"""Source-layer scope, clipping, and provenance checks for the context exporter."""
from types import SimpleNamespace

from shapely.geometry import LineString, Point, box, shape
from shapely.strtree import STRtree

from src.build_observed import context_visible, endpoint, interval_pieces, line_mask, local_masks, prove_nested


def seg(way, index=0, ground=True):
    return SimpleNamespace(way=way,index=index,a=(way*10,"0","0" if ground else "1"),
                           b=(way*10+1,"0","0" if ground else "1"),evidence="MAPPED_PEDESTRIAN_WAY",
                           directions=(1,-1))


def test_old_whole_way_and_revised_mask_are_single_source_controls():
    native=LineString([(-15,0),(15,0)])
    s=seg(7)
    clip=SimpleNamespace(lines=[native],segs=[s],line_tree=STRtree([native]))
    contract={"core":box(-3,-4,3,4),"line_parts":[],"strong_ids":{"way/7"},"hidden_edges":set(),"old_nodes":set()}
    linework, cuts=local_masks(clip,{"kind":"AREA_CASE","group":"fixture"},Point(0,0),contract,set())
    assert linework["H"]==[]
    lo_hi=[(round(a,2),round(b,2)) for _,_,a,b,_ in linework["G"]]
    assert lo_hi==[(0,12),(18,30)]
    assert round(cuts["G"][0]["removed_m"],2)==6.00


def test_local_line_mask_removes_partial_parallel_shadow_not_transverse_way():
    source=LineString([(-2,0),(2,0)])
    bands=[source.buffer(.05,cap_style="flat")]
    contract={"line_parts":[(source,(4,0))]}
    parallel=LineString([(-10,.01),(10,.01)])
    transverse=LineString([(0,-10),(0,10)])
    assert line_mask(transverse,contract,bands) is None
    hidden=line_mask(parallel,contract,bands)
    assert interval_pieces(parallel,parallel.difference(hidden))==[(0.,8.),(12.,20.)]


def test_background_polygon_is_not_punched_and_known_hazard_survives():
    broad=box(-20,-20,20,20)
    reference=box(-2,-2,2,2)
    build=lambda i,k,g:{"id":i,"kind":k,"geometry":g,"tags":{}}
    clip=SimpleNamespace(hard=[build("way/3","BUILDING",reference)],bg=[],
                         support=[build("relation/1","PARK",broad),build("way/2","PAVING",reference)])
    contract={"core":reference,"full_ids":{"way/2","way/3"},"strong_ids":set()}
    layers, removed=context_visible(clip,{},"G",contract,Point(0,0).buffer(40))
    assert shape(layers["support"][0]["geometry"]).equals(broad)
    assert shape(layers["hard"][0]["geometry"]).equals(reference)
    assert [x["source_id"] for x in removed]==["way/2"]


def test_synthetic_cut_does_not_weld_coincident_ways_or_levels():
    native=LineString([(-10,0),(10,0)])
    clip=SimpleNamespace()
    a=endpoint(seg(1),native,clip,box(-20,-20,20,20),10,"MASK_BOUNDARY_ENDPOINT")
    b=endpoint(seg(2,ground=False),native,clip,box(-20,-20,20,20),10,"MASK_BOUNDARY_ENDPOINT")
    c=endpoint(seg(1),native,clip,box(-20,-20,0,20),10,"CONTEXT_CLIP_ENDPOINT")
    assert a["xy"]==b["xy"]==c["xy"]
    assert a["id"]!=b["id"]
    assert a["endpoint_kind"]=="MASK_BOUNDARY_ENDPOINT"
    assert c["endpoint_kind"]=="SOURCE_CROP_LIMIT"


def test_nested_coverage_is_computed_in_native_segment_measure():
    ident={"source_id":"way/1","source_segment_index":3}
    prove_nested([(40,[dict(ident,source_range_m=(4,7))]),
                  (80,[dict(ident,source_range_m=(2,9))]),
                  (160,[dict(ident,source_range_m=(0,20))])])



def test_true_transverse_contact_at_face_boundary_is_retained_in_both_modes():
    native=LineString([(0,0),(-4,0)])
    s=seg(7)
    clip=SimpleNamespace(lines=[native],segs=[s],line_tree=STRtree([native]))
    contract={"core":box(0,-4,4,4),"line_parts":[],"strong_ids":set(),"hidden_edges":set(),"old_nodes":set()}
    work,cuts=local_masks(clip,{"kind":"AREA_CASE","group":"fixture"},Point(0,0),contract,set())
    assert not cuts["H"] and not cuts["G"]
    assert [(a,b) for _,_,a,b,_ in work["H"]]==[(0,4)]
    assert [(a,b) for _,_,a,b,_ in work["G"]]==[(0,4)]
