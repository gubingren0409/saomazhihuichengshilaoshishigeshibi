"""Export only independent common road guards from already frozen OSM clips.

This is a data-construction role. The predictor never imports this script,
source clips, mask ledger, query or reference. No geometry is cut around an
answer: forbidden source objects are omitted whole.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.common_constraints import digest, denied, explicit_non_ground

MOTOR = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
         "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
         "residential", "service", "living_street", "road"}
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sign(path):
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        f.write("\n")


def coverage(bounds):
    west, south, east, north = bounds
    corners = [(west, south), (east, south), (east, north), (west, north)]
    out = []
    for a, b in zip(corners, corners[1:]+corners[:1]):
        for n in range(32):
            t=n/32
            out.append(PROJECT(a[0]*(1-t)+b[0]*t, a[1]*(1-t)+b[1]*t))
    return Polygon(out)


def forbidden_ids(ledger):
    ids=set()
    for key in ("hidden_relation_member_ids", "removed_context_source_ids"):
        ids.update(ledger.get(key, []))
    if ledger.get('masking_mode')=='H':ids.update(ledger.get('historical_hidden_way_ids', []))
    for key in ledger.get("historical_hidden_segments", []):
        m=re.match(r"((?:node|way|relation)/\d+)",key)
        if m: ids.add(m.group(1))
    return ids


def export_guard(row, observed, source, ledger):
    nodes={x["id"]:x for x in source["elements"] if x["type"]=="node"}
    ways={x["id"]:x for x in source["elements"] if x["type"]=="way"}
    forbidden=forbidden_ids(ledger)
    disk=Point(observed["domain"]["anchor_xy"]).buffer(row["context_radius_m"],quad_segs=32)
    roads, excluded, missing, ground_disjoint = [], [], [], []
    # No target-shaped clipping: only the fixed, pre-existing context window.
    for ident, way in sorted(ways.items()):
        tags=way.get("tags",{})
        if tags.get("highway") not in MOTOR or tags.get("area")=="yes":
            continue
        refs=way.get("nodes", [])
        if len(refs)<2 or any(n not in nodes for n in refs):
            missing.append("way/"+str(ident));continue
        xy=[PROJECT(nodes[n]["lon"],nodes[n]["lat"]) for n in refs]
        line=LineString(xy)
        if not line.intersects(disk):continue
        native_id="way/"+str(ident)
        if native_id in forbidden:
            # The entire independent object is left out; do not encode a hole.
            excluded.append({"source_id":native_id,"reason":"FORBIDDEN_SOURCE_DEPENDENCY_WHOLE_OBJECT_OMITTED"});continue
        if explicit_non_ground(tags):
            # Grade-separated roads do not form known ground-carriageway barriers.
            ground_disjoint.append({"source_id":native_id,"tags":tags,"reason":"EXPLICIT_NON_GROUND_ROAD_NOT_PROJECTED_AS_GROUND_BARRIER"});continue
        cut=line.intersection(disk)
        if cut.is_empty or cut.length<=1e-6:continue
        roads.append({"source_id":native_id,"kind":"MOTOR_ROAD_CENTERLINE",
            "geometry":mapping(cut),"tags":tags,"source_geometry_sha256":digest(mapping(line)),
            "geometry_role":"TOPOLOGICAL_NO_NEW_FREE_CROSSING_NOT_CARRIAGEWAY_WIDTH",
            "crop":"FIXED_OBSERVATION_DISK_ONLY"})
    # Original shared source nodes, never arbitrary line intersections or nearest snaps.
    seen_road={int(r["source_id"].split('/')[1]) for r in roads}
    node_roads={}
    for ident in seen_road:
        for n in ways[ident].get("nodes",[]):node_roads.setdefault(n,[]).append("way/"+str(ident))
    access=[]
    visible={n["id"]:n for n in observed["nodes"]}
    connected={e[k] for e in observed["edges"] for k in ("u","v") if not denied(e.get("tags",{}))}
    for key,n in sorted(visible.items()):
        m=re.fullmatch(r"node/(\d+)",key)
        if not m or key not in connected:continue
        raw_id=int(m.group(1))
        if raw_id in node_roads and not denied(n.get("tags",{})) and not explicit_non_ground(n.get("tags",{})):
            access.append({"id":key,"xy":n["xy"],"source_ids":sorted(node_roads[raw_id]),
                           "tags":n.get("tags",{}),"evidence":"EXACT_SHARED_ORIGINAL_ROAD_AND_OBSERVED_GRAPH_NODE"})
    gates={}
    for objects in observed["context"].values():
        for obj in objects:
            if obj.get("kind")!="BARRIER" or not obj["id"].startswith("way/"):continue
            ident=int(obj["id"].split('/')[1]); way=ways.get(ident,{})
            for nid in way.get("nodes",[]):
                node=nodes.get(nid);key="node/"+str(nid)
                if node is None or key in forbidden:continue
                tag=node.get("tags",{})
                if tag.get("barrier") not in {"gate","lift_gate","swing_gate","kissing_gate","bollard","cycle_barrier","entrance"}:continue
                gates.setdefault(obj["id"],[]).append({"id":key,"xy":PROJECT(node["lon"],node["lat"]),
                    "tags":tag,"allowed":not denied(tag) and not explicit_non_ground(tag),
                    "evidence":"SOURCE_GATE_NODE_MEMBER_OF_BARRIER_WAY",
                    "permission_status":"SOURCE_CONDITIONAL_NOT_FIELD_VERIFIED"})
    return {"guard_version":"OBSERVED_COMMON_GUARDS_V1","id":row["id"],
        "observed_sha256":row["observed_sha256"],"crs":"EPSG:32651",
        "source_clip":row["source_clip"],"source_sha256":row["source_clip_sha256"],
        "source_parse_status":"PARSED","source_bounds_wsen":source["bounds_wsen"],
        "source_timestamp":source.get("osm3s",{}).get("timestamp_osm_base"),
        "coverage_geometry":mapping(coverage(source["bounds_wsen"])),
        "coverage_semantics":"ACQUIRED_CLIP_PARSEABLE_GEOMETRY_NOT_COMPLETE_PHYSICAL_SURVEY",
        "road_centerlines":roads,"barrier_gates":gates,"native_road_access_points":access,
        "source_dependency_check":{"included_road_ids_disjoint_forbidden":all(r["source_id"] not in forbidden for r in roads),
            "forbidden_id_count":len(forbidden),"excluded_whole_objects":excluded,
            "missing_road_node_objects":missing,"non_ground_roads":ground_disjoint,
            "hidden_geometry_read_for_clipping":False,"reference_files_read":[],
            "independent_road_shared_target_node_policy":"RETAIN_INDEPENDENT_ROAD_GEOMETRY_WITHOUT_SERIALIZING_NODE_IDS_OR_MEMBER_ARRAYS",
            "source_node_arrays_serialized":False,"source_relation_arrays_serialized":False},
        "constraints_not_covered":["UNMAPPED_REAL_WORLD_OBSTACLES","UNMAPPED_PERMISSION_OR_HEIGHT_CHANGE",
            "EXACT_CARRIAGEWAY_WIDTH_NOT_AVAILABLE"]}


def main():
    p=argparse.ArgumentParser();p.add_argument("--frozen",type=Path,default=ROOT/"frozen_context")
    p.add_argument("--source-dir",type=Path,required=True)
    p.add_argument("--all",action="store_true",help="Prepare permitted supplemental H/radius guards too")
    p.add_argument("--version",default="v2",choices=["v2"],help="v1 overly omitted independent roads sharing target nodes; retained in separate directory")
    args=p.parse_args()
    manifest=read(args.frozen/"data/task_manifest.json")
    rows=[r for r in manifest["instances"] if r["masking_mode"] in {"G","N"} and r["context_radius_m"]==80]
    if args.all:
        chosen={r["id"] for r in rows}
        rows += [r for r in manifest["instances"] if r["id"] not in chosen and
                 ((r["context_radius_m"]==80 and r["masking_mode"]=="H") or
                  (r["parent_task_id"] in {"Wc4183046a70","W6daddd19fdb","W745941f0f92","W0440b97497a"}
                   and r["masking_mode"] in {"G","N"} and r["context_radius_m"] in {40,160}))]
    ledgers={(r["parent_task_id"],r["masking_mode"]):r for r in
             (json.loads(l) for l in (args.frozen/"data/mask_dependency_ledger.jsonl").read_text(encoding="utf-8").splitlines())}
    north=read(args.frozen/"data/e5/task_manifest.json")["instances"][0]
    north=dict(north,source_clip="sh-huangpu-01.osm.json",source_clip_sha256=next(r["source_clip_sha256"] for r in rows if r["group"]=="sh-huangpu-01"))
    rows.append(north)
    evidence=[]
    for clip in sorted({r["source_clip"] for r in rows}):
        path=args.source_dir/clip
        actual=sign(path)
        expected={r["source_clip_sha256"] for r in rows if r["source_clip"]==clip}
        if expected!={actual}:raise ValueError((clip,actual,expected))
        source=read(path)
        for row in (r for r in rows if r["source_clip"]==clip):
            target=ROOT/("data/common_guards_"+args.version)/(row["id"]+".json")
            if target.exists():continue
            obs=read(args.frozen/row["observed"])
            if sign(args.frozen/row["observed"])!=row["observed_sha256"]:raise ValueError("observed identity mismatch")
            guard=export_guard(row,obs,source,ledgers.get((row["parent_task_id"],row["masking_mode"]),{}))
            write(target,guard)
            evidence.append({"id":row["id"],"path":target.relative_to(ROOT).as_posix(),
                "sha256":sign(target),"source_clip_sha256":actual,"observed_sha256":row["observed_sha256"],
                "road_count":len(guard["road_centerlines"]),"source_dependency_check":guard["source_dependency_check"]})
            print(row["id"],len(guard["road_centerlines"]),"road guards",flush=True)
            del obs
        del source
    # Merge completed records only for this new task. Do not modify historic data.
    out=ROOT/("data/constraint_evidence_"+args.version+".jsonl")
    previous=[json.loads(s) for s in out.read_text(encoding="utf-8").splitlines()] if out.exists() else []
    byid={r["id"]:r for r in previous+evidence}
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",encoding="utf-8",newline="\n") as f:
        for row in sorted(byid.values(),key=lambda r:r["id"]):f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
    contract=ROOT/("config/constraint_contract_"+args.version+".json")
    if not contract.exists():write(contract,{"version":"COMMON_GUARDS_V1","crs":"EPSG:32651",
        "source_policy":"FROZEN_INDEPENDENT_MOTOR_CENTERLINES_ONLY; NO_NEW_SOURCE_REQUEST",
        "common_to":["M1-C","F0","F1"],"hard_line_clearance_m":.15,"gates_buffer_radius_m":.30,
        "road_width_m":None,"road_policy":"NO_NEW_FREE_CROSSING_ZERO_WIDTH_SOURCE_CENTERLINE",
        "native_exception":"UNCHANGED_VALID_SOURCE_LINE_ONLY; NO_AREA_DILATION",
        "coverage":"ACQUIRED_PARSEABLE_SOURCE_CLIP_FOOTPRINT; REAL_MAP_OMISSIONS_REMAIN_UNKNOWN",
        "reference_geometry_used":False,"positive_admission_gate_used_for_F0":False})
    print('TOTAL',len(byid),flush=True)


if __name__=="__main__":main()
