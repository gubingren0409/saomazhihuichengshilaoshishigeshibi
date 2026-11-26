"""Build the offline R4-CONTEXT review from scoped observations, outputs and evaluator references."""
import argparse
import base64
from collections import Counter, defaultdict
from functools import lru_cache
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re

from pyproj import Transformer
from shapely import make_valid, unary_union
from shapely.geometry import LineString, Point, Polygon, box, shape

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
STATE = {"NATIVE_WALKABLE": "state-native", "INFERRED_WALKABLE": "state-inferred",
         "RESTRICTED": "state-restricted", "UNKNOWN": "state-unknown"}
ORDER = {name: i for i, name in enumerate(("park", "plaza", "grass", "water", "building", "obstacle", "road",
                                         "way", "clip", "mask-end", "source-limit", "gate", "label"))}
ROADS = {"trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service",
         "living_street", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
PREFERRED = ("Wc4183046a70", "W6daddd19fdb", "W745941f0f92")


def read(path, fallback=None):
    if not path.is_file() and fallback is not None:
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def fmt(point, anchor):
    return [round(point[0]-anchor[0], 3), round(anchor[1]-point[1], 3)]


def draw(geometry, anchor):
    """Relative SVG ordinates in metres, the same affine transform for both panes."""
    if geometry.is_empty:
        return []
    def path(points, closed=False):
        commands = ["M"+",".join(f"{v:g}" for v in fmt(points[0], anchor))]
        commands.extend("L"+",".join(f"{v:g}" for v in fmt(p, anchor)) for p in points[1:])
        return "".join(commands)+("Z" if closed else "")
    match geometry.geom_type:
        case "Point":
            return [{"point": fmt(geometry.coords[0], anchor)}]
        case "LineString" | "LinearRing":
            return [{"d": path(list(geometry.coords))}]
        case "Polygon":
            return [{"d": path(list(geometry.exterior.coords), True) +
                     "".join(path(list(r.coords), True) for r in geometry.interiors), "area": True}]
        case _:
            return [entry for part in getattr(geometry, "geoms", ()) for entry in draw(part, anchor)]


def row(layer, geom, anchor, **props):
    pieces = draw(geom, anchor)
    return {"layer": layer, "shape": pieces, "props": props} if pieces else None


def geom(value):
    result = shape(value)
    return result if result.is_valid else make_valid(result)


def category(group, kind, tags, geometry):
    kind = kind.upper()
    if "BUILDING" in kind or tags.get("building"):
        return "building"
    if "WATER" in kind or tags.get("natural") == "water" or tags.get("water"):
        return "water"
    if group == "background" or "GRASS" in kind or "FLOWER" in kind:
        return "grass"
    if tags.get("barrier") and geometry.area == 0:
        return "obstacle"
    if "PARK" in kind or tags.get("leisure") in {"park", "garden", "recreation_ground"}:
        return "park"
    if group == "support":
        return "plaza"
    return "obstacle"


def node_kind(node):
    kind = node.get("endpoint_kind", "NATIVE_ENDPOINT")
    if isinstance(kind, (list, tuple)):
        return next((x for x in kind if x != "NATIVE_ENDPOINT"), kind[0] if kind else "NATIVE_ENDPOINT")
    return kind


def raw_way(edge):
    text = str(edge.get("source_id") or edge.get("id") or "")
    return re.match(r"way/\d+", text).group() if re.match(r"way/\d+", text) else text


def visible(observed, anchor, context_radius, frame):
    circle = Point(anchor).buffer(context_radius, quad_segs=32)
    by_id = {n["id"]: n for n in observed.get("nodes", [])}
    paths, sizes, labels, evidence = [], Counter(), set(), set()
    for group, objects in observed.get("context", {}).items():
        for obj in objects:
            raw = geom(obj["geometry"])
            shape_ = raw.intersection(frame)
            tags = obj.get("tags", {})
            layer = category(group, obj.get("kind", ""), tags, raw)
            key = obj.get("id", obj.get("source_id"))
            paths.append(row(layer, shape_, anchor, source_id=key, kind=obj.get("kind"), tags=tags,
                             observation="OBSERVED_OBJECT", full_geometry_outside_circle=raw.difference(circle).area > 0.01))
            sizes[layer] += 1
            evidence.add(key)
            name = tags.get("name:zh") or tags.get("name")
            if name and not shape_.is_empty and name not in labels:
                labels.add(name)
                paths.append(row("label", shape_.representative_point(), anchor,
                                 label=name, source_id=key, observation="OBSERVED_OBJECT"))
    seen, visible_nodes = set(), set()
    for edge in observed.get("edges", []):
        u, v = edge["u"], edge["v"]
        if edge.get("kind", "").startswith("DERIVED"):
            sizes["derived_arcs"] += 1
            continue
        visible_nodes.update((u, v))
        if u not in by_id or v not in by_id:
            raise ValueError(f"Unbound observed edge {edge['id']}")
        ident = raw_way(edge)
        key = (frozenset((u, v)), ident, edge.get("source_segment_index"))
        if key in seen:
            continue
        seen.add(key)
        xy = [by_id[u]["xy"], by_id[v]["xy"]]
        lengths = LineString(xy)
        if lengths.length <= 0.0001:
            continue
        e = row("way", lengths.intersection(frame), anchor, source_id=ident, id=edge["id"],
                source_segment_index=edge.get("source_segment_index"), source_direction=edge.get("source_direction"),
                endpoint_kinds=[node_kind(by_id[u]), node_kind(by_id[v])], tags=edge.get("tags", {}),
                length_m=round(lengths.length, 3), observation="OBSERVED_NETWORK")
        if e:
            paths.append(e)
        sizes["line_m"] += lengths.length
        evidence.add(ident)
    marker = {"CONTEXT_CLIP_ENDPOINT": "clip", "MASK_BOUNDARY_ENDPOINT": "mask-end", "SOURCE_CROP_LIMIT": "source-limit"}
    for node in by_id.values():
        kind = node_kind(node)
        sizes[kind] += 1
        if kind in marker and node["id"] in visible_nodes:
            paths.append(row(marker[kind], Point(node["xy"]), anchor, id=node["id"],
                             source_id=node.get("source_id"), endpoint_kind=kind, xy=node["xy"]))
    entrance = observed.get("registered_entrance")
    if entrance and entrance.get("xy"):
        paths.append(row("exit" if entrance.get("tags", {}).get("entrance")=="exit" else "endpoint",
                         Point(entrance["xy"]), anchor, **entrance))
    return sorted(filter(None, paths), key=lambda x: ORDER.get(x["layer"], 99)), {
        "nodes": len(by_id), "arcs": len(observed.get("edges", [])), "segments": len(seen),
        "road_length_m": round(sizes["line_m"], 3), "buildings": sizes["building"],
        "support": sizes["park"]+sizes["plaza"], "cuts": sizes["CONTEXT_CLIP_ENDPOINT"],
        "mask_cuts": sizes["MASK_BOUNDARY_ENDPOINT"], "source_limits": sizes["SOURCE_CROP_LIMIT"],
        "native_endpoints": sizes["NATIVE_ENDPOINT"], "entrances": int(bool(entrance)),
        "source_ids": sorted(str(x) for x in evidence if x is not None), "derived_arcs_aggregated_for_display": sizes["derived_arcs"]}


def snapshot(root, group):
    source = root/"frozen_r3/inputs/rev1/frozen_r4/data/source"/f"{group}.osm.json"
    if not source.is_file():
        return None
    return read(source)


@lru_cache(maxsize=4)
def raw_map(root, group):
    original = snapshot(root, group)
    if original is None:
        return (), None
    elements = original.get("elements", [])
    coords = {x["id"]: PROJECT(x["lon"], x["lat"]) for x in elements if x.get("type") == "node"}
    ways = [w for w in elements if w.get("type") == "way" and w.get("tags", {}).get("highway") in ROADS and
            w.get("tags", {}).get("foot") not in {"yes", "designated", "permissive"}]
    return tuple((f"way/{w['id']}", w["tags"], LineString([coords[n] for n in w["nodes"] if n in coords]))
                 for w in ways if len(w.get("nodes", []))>=2 and all(n in coords for n in w["nodes"])), (
        original.get("osm3s", {}).get("timestamp_osm_base"))


def display_roads(root, group, anchor, frame, ref):
    features, names = [], set()
    buffer = ref.buffer(.15) if ref is not None else None
    roads, timestamp = raw_map(root, group)
    for source_id, tags, road in roads:
        if not road.intersects(frame) or buffer is not None and road.intersection(buffer).length > .2:
            continue
        line = road.intersection(frame)
        features.append(row("road", line, anchor, source_id=source_id, tags=tags,
                            observation="DISPLAY_ONLY_MOTOR_ROAD"))
        name = tags.get("name:zh") or tags.get("name")
        if name and name not in names:
            names.add(name)
            features.append(row("label", line.representative_point(), anchor, label=name,
                                source_id=source_id, observation="DISPLAY_ONLY_MOTOR_ROAD"))
    return list(filter(None,features)),timestamp


def cells_and_surface(surface, anchor):
    buckets = defaultdict(list)
    detail = []
    for cell in surface.get("cells", []):
        state = cell["walkability_state"]
        geometry = geom(cell["geometry"])
        if geometry.is_empty:
            continue
        buckets[state].append(geometry)
        if state == "INFERRED_WALKABLE":
            props = {k: v for k, v in cell.items() if k not in {"geometry", "xy", "center", "representative_xy"}}
            detail.append(row("cell", geometry, anchor, **props))
    states = [row(STATE[k], unary_union(buckets[k]), anchor, walkability_state=k, area_m2=surface.get("area_m2", {}).get(k))
              for k in STATE if k in buckets]
    return list(filter(None,states)), list(filter(None,detail))


def draw_routes(groups, anchor):
    out = {}
    for ident, result in groups.items():
        lines, points=[], []
        for e in result.get("edges", []):
            xy=e.get("xy", [])
            if len(xy)<2 or LineString(xy).length <= 1e-6:
                continue
            points.extend(fmt(p,anchor) for p in xy)
            layer = e.get("layer", "native").lower().replace("_", "-")
            props = {k:v for k,v in e.items() if k not in {"xy","layer","wgs84"}}
            lines.append(row("route-"+layer, LineString(xy), anchor, **props))
        bounds=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)] if points else None
        out[str(ident)] = {"lines": list(filter(None,lines)), "extent":bounds, "status": result.get("status"),
                           "reached": result.get("reached", result.get("valid_reached")),
                           "length_m": result.get("length_m"), "layer_lengths": result.get("layer_lengths")}
    return out


def query_points(doc, anchor):
    out = {}
    for q in doc.get("queries", []):
        qid = q.get("query_id")
        if qid is None:
            continue
        shapes=[]
        for k in ("source", "target"):
            e=q.get(k)
            if e and e.get("xy"):
                shapes.append(row("endpoint", Point(e["xy"]), anchor, **e, query_side=k))
        out[str(qid)] = [f for f in shapes if f]
    return out


def short_metrics(value):
    keep = {"reference_area_m2","reference_area_covered_m2","area_recall","reference_length_m",
            "reference_length_covered_m","line_recall","unknown_area_m2","inferred_area_m2",
            "hard_conflict_area_m2","off_reference_area_m2","route_total","route_reached","route_new_with_inference",
            "route_alternatives","outside_route_count","geometry_match","boundary_p90_m"}
    return {k:v for k,v in value.items() if k in keep}


_SURFACE_CACHE = {}


def model(path, anchor, metrics, ident=None, observed_sha=None):
    x=read(path)
    if ident and x.get("input_id",ident)!=ident:
        raise ValueError(f"Prediction input ID does not match the displayed instance: {path}")
    if observed_sha and x.get("observed_sha256",observed_sha)!=observed_sha:
        raise ValueError(f"Prediction observation fingerprint does not match the displayed instance: {path}")
    surface=x.get("surface", {})
    key = (surface.get("sha256"), anchor)
    if key[0] and key not in _SURFACE_CACHE:
        _SURFACE_CACHE[key] = cells_and_surface(surface, anchor)
    states, cells = _SURFACE_CACHE[key] if key[0] else cells_and_surface(surface, anchor)
    trace=x.get("features",{})
    feature_counts={k:v for k,v in trace.items() if isinstance(v,(str,int,float,bool))} if isinstance(trace,dict) else {}
    scored=metrics.get("routes",[])
    summary=short_metrics(metrics.get("metrics",metrics))
    if "routes" in metrics:
        summary.update(route_total=len(scored),route_reached=sum(q["valid_reached"] for q in scored),
                       route_new_with_inference=sum(q["locally_recovered_query"] for q in scored),
                       route_alternatives=sum(q["alternative_with_inference"] for q in scored),
                       outside_route_count=sum(q["native_outer_detour_only"] for q in scored))
    return {"sha256":surface.get("sha256"), "area":surface.get("area_m2", {}), "states":states, "cells":cells,
            "routes":draw_routes(x.get("routes", {}), anchor), "base_routes":draw_routes(x.get("base_routes", {}), anchor),
            "metrics":summary, "features":feature_counts,
            "route_audit":{q["query_id"]:{k:q.get(k) for k in ("valid_reached","locally_recovered_query",
                         "native_outer_detour_only","uses_inferred_inside")} for q in scored},
            "witnesses":trace.get("witnesses",{}) if isinstance(trace,dict) else {}}


def grouped_jsonl(path):
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]


def mode_family(mode):
    if str(mode).startswith("H0"):
        return "H0"
    return str(mode).split("_")[0]


def index_metrics(path):
    entries=read(path,{}).get("rows", [])
    return {(str(x.get("input_id", x.get("id"))),x["method"]):x for x in entries}


def explicit_mask(ledger, key, anchor):
    item=ledger.get(key, {})
    # A task-declared cut envelope is safe to depict. Never draw hidden target geometry as a boundary.
    for field in ("mask_window_geometry","local_mask_window","mask_envelope_geometry","cut_domain"):
        g=item.get(field)
        if isinstance(g,dict) and g.get("type"):
            return row("mask-domain", geom(g), anchor, observation="DECLARED_MASK_SCOPE")
    return None


def assemble(root, task_set=None, manifest_path=None, prediction_root=None, metrics_path=None):
    manifest_path = manifest_path or root/"data/task_manifest.json"
    manifest = read(manifest_path)
    prediction_root = prediction_root or root/"data/predictions"
    instances = manifest["instances"]
    groups = defaultdict(list)
    for x in instances:
        parent=x["parent_task_id"]
        if not task_set or parent in task_set:
            groups[parent].append(x)
    inventory = {str(x.get("input_id",x.get("id"))):x for x in grouped_jsonl(manifest_path.parent/"context_inventory.jsonl")}
    ledger = {(x.get("parent_task_id"), mode_family(x.get("masking_mode", x.get("mode")))):x
              for x in grouped_jsonl(manifest_path.parent/"mask_dependency_ledger.jsonl")}
    metrics=index_metrics(metrics_path or root/"runs/context_metrics.json")
    cases,models,bycase={},[],{}
    for parent, entries in groups.items():
        first=entries[0]
        path=root/(first.get("observed") or f"data/observed/{first['id']}.json")
        if not path.is_file():
            continue
        obs=read(path)
        anchor=tuple(obs["domain"]["anchor_xy"])
        frame=box(anchor[0]-175,anchor[1]-175,anchor[0]+175,anchor[1]+175)
        ref_path=root/(first.get("reference") or f"data/reference/{parent}.json")
        query_path=root/(first.get("query") or f"data/queries/{parent}.json")
        refdoc=read(ref_path,{})
        querydoc=read(query_path,{})
        if first.get("reference_sha256") and sha(ref_path)!=first["reference_sha256"]:
            raise ValueError(f"Reference differs from frozen display binding: {parent}")
        if first.get("query_sha256") and sha(query_path)!=first["query_sha256"]:
            raise ValueError(f"Query differs from frozen display binding: {parent}")
        ref=geom(refdoc["geometry"]) if refdoc.get("geometry") else None
        window = geom(refdoc["domain_geometry"]) if refdoc.get("domain_geometry") else Point(anchor).buffer(30,quad_segs=32)
        roads, date = display_roads(root,first["group"],anchor,frame,ref)
        case={"parent":parent,"group":first["group"],"kind":first.get("kind"),"label":first.get("label"),
              "split":first.get("split"),"anchor":anchor,"inputs":{}, "context_road":roads,"snapshot":date,
              "window":row("score-domain",window,anchor,observation="FIXED_30_M_PREDICTION_AND_EVALUATION"),
              "reference":row("reference",ref,anchor,source_ids=refdoc.get("source_ids"), label=refdoc.get("label"),
                              observation="EVALUATION_ONLY") if ref is not None else None,
              "queries":query_points(querydoc,anchor),"methods":set()}
        for x in entries:
            ident=x["id"]
            source=root/(x.get("observed") or f"data/observed/{ident}.json")
            if not source.is_file():
                continue
            obs=read(source)
            seen_sha=sha(source)
            if x.get("observed_sha256",seen_sha)!=seen_sha:
                raise ValueError(f"Observation differs from frozen display binding: {ident}")
            if x.get("reference_sha256")!=first.get("reference_sha256"):
                raise ValueError(f"Reference changes across one parent display: {ident}")
            if tuple(obs["domain"]["anchor_xy"])!=anchor:
                raise ValueError(f"Inconsistent fixed center {ident}")
            mode=mode_family(x.get("masking_mode"))
            raw_radius=x.get("context_radius_m")
            radius=int(raw_radius or 40)
            old=mode=="H0"
            shapes,counts=visible(obs,anchor,radius,frame)
            inv=inventory.get(ident,{})
            mask_info=ledger.get((parent,mode),{})
            mask_hidden=mask_info.get("hidden_geometry")
            coverage=inv.get("source_coverage_geometry")
            observation_boundary=inv.get("observation_requested_geometry")
            restored=[row("continuation",geom(seg["geometry"]),anchor,**{k:v for k,v in seg.items() if k!="geometry"})
                      for seg in inv.get("restored_source_fragments",[])]
            item={"id":ident,"mode":mode,"radius":radius,"old":old,"visible":shapes,
                  "counts":counts,"inventory":{k:v for k,v in inv.items()
                      if "geometry" not in k and k not in {"source_ids","restored_source_fragments"}},
                  "restored":list(filter(None,restored)),
                  "mask_scope":explicit_mask(ledger,(parent,mode),anchor),
                  "mask_reveal":row("mask-domain",geom(mask_hidden).intersection(frame),anchor,
                                    observation="AUDIT_ONLY_EXACT_MASK",mask_basis=mask_info.get("mask_basis")) if mask_hidden else None,
                  "source_boundary":row("source-boundary",geom(coverage).boundary.intersection(frame),anchor,
                                        observation=inv.get("source_extent_status")) if coverage and
                                        inv.get("source_available_fraction",1)<.999999 else None,
                  "mask_basis":mask_info.get("mask_basis"),
                  "context_outline":draw(geom(observation_boundary),anchor) if observation_boundary else [],
                  "models":{},
                  "observed_sha256":seen_sha,
                  "mask_sha256":x.get("mask_sha256"),"evaluation_sha256":x.get("evaluation_domain_sha256"),
                  "reference_sha256":x.get("reference_sha256")}
            for m in ("M0", "M1", "M1_ABL", "ABL", "S_NAIVE"):
                pred=prediction_root/ident/f"{m}.json"
                if not pred.is_file():
                    continue
                payload=model(pred,anchor,metrics.get((ident,m),{}),ident,seen_sha)
                token=sha256(json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
                if token not in bycase:
                    bycase[token]=len(models)
                    models.append(payload)
                item["models"][m]=bycase[token]
                case["methods"].add(m)
            case["inputs"].setdefault(mode,{})[str(radius)]=item
        case["methods"]=sorted(case["methods"])
        if case["inputs"]:
            cases[parent]=case
    natural = add_north(root, cases, models, prediction_root) if not task_set or "NORTH" in task_set else None
    negative=next((k for k,v in cases.items() if v["label"]=="NEGATIVE"),None)
    example=next(({"id":v["parent"],"mode":mode,"radius":radius,"method":method}
                  for v in cases.values() for mode,sets in v["inputs"].items() if mode in ("H","G","S")
                  for radius,x in sets.items() for method,i in x["models"].items()
                  if (models[i].get("metrics",{}).get("area_recall") or
                      models[i].get("metrics",{}).get("line_recall") or 0)>0),None)
    return {"cases":cases,"models":models,"preset":PREFERRED,"negative":negative,"example":example,
            "natural":natural,"semantic_status":manifest.get("neutral_semantic_mode"),"source":"© OpenStreetMap contributors · 冻结裁片 · EPSG:32651"}


def add_north(root, cases, models, prediction_root):
    """Natural run is linked only if actual saved observed and prediction files exist."""
    north_candidates={p.stem:p for parent in (root/"data/observed",root/"data/e5/observed")
                      for p in sorted(parent.glob("*.json")) if "NORTH" in p.stem.upper()}
    if not north_candidates:
        return None
    candidates=list(north_candidates.values())
    parent="NORTH"
    first=read(candidates[0])
    anchor=tuple(first["domain"]["anchor_xy"])
    frame=box(anchor[0]-175,anchor[1]-175,anchor[0]+175,anchor[1]+175)
    window=Point(anchor).buffer(30,quad_segs=32)
    roads,date=display_roads(root,"sh-huangpu-01",anchor,frame,None)
    case={"parent":parent,"group":"sh-huangpu-01","kind":"NATURAL_REGISTERED_EXIT","label":"NATURAL",
          "split":"business_regression","anchor":anchor,"inputs":{},"context_road":roads,"snapshot":date,
          "window":row("score-domain",window,anchor,observation="FIXED_30_M_PREDICTION"),
          "reference":None,"queries":{},"methods":[]}
    for p in candidates:
        o=read(p)
        if tuple(o["domain"]["anchor_xy"])!=anchor:
            continue
        ident=p.stem
        radius=next((int(x) for x in ident.split("_") if x in {"040","080","160","40","80"}),160)
        v,c=visible(o,anchor,radius,frame)
        item={"id":ident,"mode":"NATURAL","radius":radius,"old":False,"visible":v,
              "counts":c,"inventory":{},"models":{},"observed_sha256":sha(p)}
        for m in ("M0","M1","M1_ABL","ABL"):
            pred=prediction_root/ident/f"{m}.json"
            if pred.is_file():
                item["models"][m]=len(models)
                models.append(model(pred,anchor,{},ident,item["observed_sha256"]))
                if m not in case["methods"]:
                    case["methods"].append(m)
        case["inputs"].setdefault("NATURAL",{})[str(radius)]=item
    for name in ("NORTH","north",candidates[0].stem):
        q=next((f for f in (root/"data/e5/queries"/f"{name}.json",root/"data/queries"/f"{name}.json") if f.is_file()),None)
        if q:
            case["queries"]=query_points(read(q),anchor)
            break
    cases[parent]=case
    return parent


def main(args):
    data=assemble(args.root,set(args.tasks) if args.tasks else None,args.manifest,args.prediction_root,args.metrics)
    if not data["cases"]:
        raise ValueError("No display cases found")
    js=(ROOT/"src/context_map.js").read_text(encoding="utf-8")
    template=(ROOT/"src/context_map.html").read_text(encoding="utf-8")
    text=json.dumps(data,ensure_ascii=False,separators=(",",":")).encode()
    payload=base64.b64encode(gzip.compress(text,mtime=0)).decode("ascii")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(template.replace("__PAYLOAD__",payload).replace("__SCRIPT__",js),encoding="utf-8")
    print(json.dumps({"cases":len(data["cases"]),"model_payloads":len(data["models"]),"raw_json_bytes":len(text),
                      "html_bytes":args.output.stat().st_size,"sha256":sha(args.output)},ensure_ascii=False))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--tasks",nargs="+")
    parser.add_argument("--manifest",type=Path)
    parser.add_argument("--prediction-root",type=Path)
    parser.add_argument("--metrics",type=Path)
    args=parser.parse_args()
    args.output=args.output or args.root/"visuals/index.html"
    main(args)
