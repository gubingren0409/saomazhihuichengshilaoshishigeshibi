"""Recompute frozen endpoints and separation metrics; no routing calls."""
import csv
from math import isclose

from shapely.geometry import LineString,Point

from .geometry import ROOT,Evidence,distance,dump,length,project


def write_csv(path,rows):
    with path.open("w",encoding="utf-8-sig",newline="") as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze(e):
    a,b=e.local,e.hosted
    base=project(LineString(a)); hosted=project(LineString(b))
    a_first,b_first=distance(e.start,a[0]),distance(e.start,b[0])
    a_last,b_last=distance(e.target,a[-1]),distance(e.target,b[-1])
    snap=e.failure["snap_end"]
    # Eligibility comes from the retained R1 run. Recompute that stored snap's geometry independently.
    way=e.way(snap["way_id"])
    ref=project(Point(e.target))
    building=project(e.target_building)
    plaza=project(e.plaza())
    measure=project(LineString([e.target,a[-1]]))
    ids=e.ways[snap["way_id"]]["nodes"]
    nearest_node=min(ids,key=lambda n:distance(e.coord(n),e.target))
    assert isclose(distance(e.coord(nearest_node),a[-1]),0,abs_tol=.001)
    official=e.probe["route"]
    output={
        "crs":"EPSG:4326 WGS84 [lon,lat]; EPSG:32651 for planar geometry; WGS84 ellipsoid for distances",
        "building_way_id":e.scene["building_native_id"],"entrance_node_id":e.scene["entry_native_id"],
        "northwest_exit_node_id":"node/6897145227",
        "entrance_tags":e.nodes[int(e.scene["entry_native_id"].split("/")[-1])]["tags"],
        "northwest_exit_tags":e.nodes[6897145227]["tags"],
        "reference_evidence":"OSM native node on the building perimeter and south plaza outer ring; R1 museum public guidance names the south entrance, no surveyed coordinate/current public access.",
        "reference_status":"REFERENCE_UNCERTAIN_FOR_PHYSICAL_DOOR_OR_CURRENT_ACCESS",
        "point_on_building_boundary_error_m":building.boundary.distance(ref),
        "plaza_boundary_error_m":plaza.boundary.distance(ref),
        "eligible_snap_way_id":"way/"+str(snap["way_id"]),
        "eligible_snap_node_id":"node/"+str(nearest_node),
        "eligible_snap_tags":e.ways[snap["way_id"]]["tags"],"eligible_snap_wgs84":snap["position"],
        "eligible_snap_way_to_reference_m_planar":project(way).distance(ref),
        "local_r1_snap_distance_m":e.failure["snap_end_m"],
        "frozen_threshold_m":e.scene["path_snap_max_m"],
        "threshold_frozen_before_route":e.scene["frozen_before_route"],
        "gap_measurement_chord_inside_building_m_planar":measure.intersection(building.buffer(-.25)).length,
        "origin_wgs84":e.start,"target_reference_wgs84":e.target,
        "local":{"role":"DIAGNOSTIC_TO_NETWORK","main_request_status":e.failure["failure_reason"],
                 "length_m":length(a),"start_offset_m":a_first,"target_gap_m":a_last,
                 "origin_wgs84":a[0],"end_wgs84":a[-1],"vertices":len(a),
                 "overlap_within_1m_of_other_route_fraction":base.intersection(hosted.buffer(1)).length/base.length,
                 "target_building_interior_intersection_m":base.intersection(building.buffer(-.25)).length},
        "hosted":{"role":"PROVIDER_ROUTE","http_status":e.probe["receipt"]["status_code"],
                  "provider_distance_m":official["provider_distance_m"],"provider_duration_s":official["provider_duration_s"],
                  "length_m":length(b),"start_offset_m":b_first,"target_gap_m":b_last,
                  "origin_wgs84":b[0],"end_wgs84":b[-1],"vertices":len(b),
                  "entrance_field":official["entrance"],"entrance_identity":official["entrance_identity"],
                  "overlap_within_1m_of_other_route_fraction":hosted.intersection(base.buffer(1)).length/hosted.length,
                  "target_building_interior_intersection_m":hosted.intersection(building.buffer(-.25)).length},
        "paired_start_distance_m":distance(a[0],b[0]),"paired_end_distance_m":distance(a[-1],b[-1]),
        "whole_route_hausdorff_m_planar":base.hausdorff_distance(hosted),
        "nearest_node_is_nearest_on_snap_way":True,
        "geoapify_internal_route_graph":"UNKNOWN","field_validation":0,
    }
    return output


def main():
    e=Evidence()
    result=analyze(e)
    dump(ROOT/"analysis/endpoint_metrics.json",result)
    rows=[]
    def gap(source,item,id_,value,method,status="RECOMPUTED"):
        rows.append({"branch":source,"item":item,"native_ref":id_,"value":value,
                     "method_or_basis":method,"evidence_status":status})
    gap("shared","entrance_reference",result["entrance_node_id"],e.target,"WGS84 native OSM node")
    gap("shared","boundary_residual",result["building_way_id"],result["point_on_building_boundary_error_m"],"EPSG:32651 metres")
    gap("local","nearest_eligible_edge",result["eligible_snap_way_id"],result["eligible_snap_way_to_reference_m_planar"],"EPSG:32651 planar edge distance")
    gap("local","nearest_on_snap_way_node",result["eligible_snap_node_id"],result["local"]["end_wgs84"],"native node, WGS84")
    gap("local","historical_threshold","runs/pilot_plan.json",result["frozen_threshold_m"],"frozen metres","OBSERVED")
    gap("local","diagnostic_terminal_to_reference",result["eligible_snap_node_id"],result["local"]["target_gap_m"],"WGS84 ellipsoid metres")
    gap("hosted","returned_terminal_to_reference","R1 normalized GeoJSON",result["hosted"]["target_gap_m"],"WGS84 ellipsoid metres")
    gap("paired","terminal_distance","R1 frozen route geometries",result["paired_end_distance_m"],"WGS84 ellipsoid metres")
    gap("shared","not_a_path_measurement_interior","museum footprint",result["gap_measurement_chord_inside_building_m_planar"],"EPSG:32651 line length intersecting building inner 0.25m buffer")
    gap("hosted","provider_entrance","R1 response receipt","","provider does not expose verified entrance identity","UNKNOWN")
    write_csv(ROOT/"endpoint_gap_audit.csv",rows)
    rows=[]
    for name in ("local","hosted"):
        item=result[name]
        for k,tag in (("origin_wgs84","WGS84 [lon,lat]"),("end_wgs84","WGS84 [lon,lat]"),
                      ("start_offset_m","WGS84 ellipsoid m"),("target_gap_m","WGS84 ellipsoid m"),("length_m","WGS84 ellipsoid m")):
            rows.append({"branch":name,"measurement":k,"value":item[k],"method":tag,"evidence_status":"RECOMPUTED"})
    for k in ("origin_wgs84","target_reference_wgs84","frozen_threshold_m"):
        rows.append({"branch":"shared","measurement":k,"value":result[k],"method":"R1 locked contract","evidence_status":"OBSERVED"})
    rows.append({"branch":"hosted","measurement":"declared_provider_distance_m","value":result["hosted"]["provider_distance_m"],
                 "method":"retained provider response summary","evidence_status":"OBSERVED"})
    rows.append({"branch":"paired","measurement":"whole_route_hausdorff_m","value":result["whole_route_hausdorff_m_planar"],
                 "method":"EPSG:32651 planar m","evidence_status":"RECOMPUTED"})
    write_csv(ROOT/"coordinate_and_snap_audit.csv",rows)
    print(result["local"]["length_m"],result["hosted"]["length_m"],result["local"]["target_gap_m"],
          result["hosted"]["target_gap_m"],result["paired_end_distance_m"])


if __name__=="__main__":
    main()
