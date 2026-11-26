"""Run natural registered-door inference or observed-only controlled predictions."""
import argparse
import csv
from hashlib import file_digest, sha256
import json
from pathlib import Path
import sys
from time import perf_counter

from shapely.geometry import Point, LineString, mapping
from shapely.ops import transform

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.inference import (DERIVED, INFERRED, INVERSE, NATIVE, WALK_TYPES, access_conflict,
                           mapping as geo_mapping, run_observed)

ROOT = Path(__file__).resolve().parents[1]
NORTH_SCENE = "sh-huangpu-01"
NORTH_DOOR = "node/6897145227"
EXPORTED = ("runs/inference.json", "data/inference_routes.geojson", "data/inference_candidates.geojson",
            "data/inference_context.geojson", "data/inference_candidates.csv")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def write(root, relative, value):
    path = root / relative
    path.parent.mkdir(exist_ok=True, parents=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def collection(items):
    return {"type": "FeatureCollection", "features": items}


def feature(geom, **props):
    return {"type": "Feature", "geometry": geom, "properties": props}


def route_features(result):
    out = []
    for variant, model in result["methods"].items():
        route = model["route"]
        if route is None:
            continue
        for n, row in enumerate(route["edges"]):
            out.append(feature({"type": "LineString", "coordinates": row["wgs84"]}, variant=variant, sequence=n,
                               role="route_segment", kind=row["kind"], source_id=row["source_id"], edge_id=row["id"],
                               length_m=row["length_m"], tags=row["tags"], hypothesis=row["hypothesis"]))
        out.append(feature({"type": "Point", "coordinates": route["end_wgs84"]}, variant=variant,
                           role="route_end", status=model["status"], residual_m=model["residual_m"]))
    door = result["target"]
    out.append(feature({"type": "Point", "coordinates": door.get("wgs84") or INVERSE(*door["xy"])},
                       role="registered_exit", source_id=door["id"], tags=door["tags"], inbound="NOT_ELIGIBLE_EXIT"))
    return out


def candidate_features(result):
    out = []
    for variant, model in result["methods"].items():
        for row in model["candidates"]:
            properties = {k: v for k, v in row.items() if k not in {"xy", "candidate_xy", "node"}}
            properties.update(variant=variant, role="candidate_connector")
            geom = {"type": "LineString", "coordinates": [INVERSE(*p) for p in row["candidate_xy"]]}
            out.append(feature(geom, **properties))
            out.append(feature({"type": "Point", "coordinates": INVERSE(*row["xy"])}, variant=variant,
                               role="candidate_anchor", source_id=row["source_id"], status=row["status"],
                               id=row["id"], route_selected=row["route_selected"]))
    return out


def context_features(observed, result):
    from shapely.geometry import shape
    to_world = lambda geom: geo_mapping(transform(INVERSE, shape(geom)))
    out = [feature(to_world(result["window"]), role="independent_search_window"),
           feature(to_world(result["domain"]), role="independent_allowed_domain")]
    for group, rows in observed["context"].items():
        for row in rows:
            out.append(feature(to_world(row["geometry"]), role=group, source_id=row["id"], kind=row["kind"],
                               tags=row.get("tags", {})))
    return out


def obj_record(ident, kind, geom, tags, **props):
    return dict(id=ident, kind=kind, geometry=mapping(geom), tags=tags, **props)


def natural_context(source, native, center, radius):
    from src.semantics import obstacle_kind

    point = Point(center)
    context = {"hard": [], "background": [], "support": []}
    for row in native.obstacles:
        geom = row["geometry"]
        if geom.distance(point) > radius:
            continue
        kind = obstacle_kind(row)
        group = "background" if kind in {"BACKGROUND_GRASS", "FLOWERBED"} else "hard"
        context[group].append(obj_record(row["id"], "GRASS" if kind == "BACKGROUND_GRASS" else kind,
                                         geom, row.get("tags", {}), gates=row.get("gates", [])))
    seen = {(key, row["id"]) for key, items in context.items() for row in items}
    for kind, objects in (("way", source.ways), ("relation", source.relations)):
        for number, row in objects.items():
            tags = row.get("tags", {})
            typ = tags.get("highway")
            is_area = tags.get("area") == "yes" or tags.get("type") == "multipolygon" or "area:highway" in tags
            support = None
            if tags.get("leisure") == "park" or tags.get("landuse") == "recreation_ground":
                support = "PARK"
            elif typ == "pedestrian" and is_area or tags.get("area:highway") in WALK_TYPES:
                support = "PEDESTRIAN_AREA"
            elif is_area and tags.get("surface") in {"paving_stones", "paved", "concrete", "sett"} and not typ:
                support = "PAVING"
            hard = ("RESTRICTED_LINEAR_ACCESS" if access_conflict(tags) and not is_area else
                    "MOTOR_ROAD_WITHOUT_MAPPED_CROSSING" if typ in {"trunk", "primary", "secondary", "tertiary"} else None)
            if not (support or hard) or kind == "relation" and hard and not support:
                continue
            ident = f"{kind}/{number}"
            if support:
                geo = source.area(ident)
                if geo is not None and geo.distance(point) <= radius:
                    context["support"].append(obj_record(ident, support, geo, tags))
            if hard and kind == "way" and ("hard", ident) not in seen:
                xy = source.known_coords(row)
                if len(xy) < 2 or len(xy) != len(row["nodes"]):
                    continue
                geo = LineString(xy)
                if geo.distance(point) <= radius:
                    context["hard"].append(obj_record(ident, hard, geo, tags))
    return context


def node_id(key):
    if isinstance(key, tuple) and len(key) == 3 and isinstance(key[0], int):
        a, layer, level = key
        return f"node/{a}" if (str(layer), str(level)) == ("0", "0") else f"node/{a}@{layer}:{level}"
    return str(key)


def make_observation(scene, graph, native, entrance, cfg):
    from inputs.rev1.src.native_adapter import node_number

    source = native.source
    ident = entrance["native_id"]
    target_n = node_number(ident)
    nodes = []
    for k, attributes in graph.nodes(data=True):
        tags = source.nodes.get(k[0], {}).get("tags", {}) if isinstance(k, tuple) else {}
        if isinstance(k, tuple) and tuple(map(str, k[1:])) != ("0", "0"):
            tags = dict(tags)
            for name, value in zip(("layer", "level"), k[1:]):
                if str(value) != "0" and name not in tags:
                    tags[name] = value
        nodes.append(dict(id=node_id(k), xy=attributes["xy"], wgs84=attributes["coord"], tags=tags))
    edges = []
    for n, (a, b, _, e) in enumerate(graph.edges(keys=True, data=True)):
        way = e.get("osm_way_id")
        area = e.get("source_area_id")
        tags = source.ways[way].get("tags", {}) if way is not None else (
            source.obj(area).get("tags", {}) if area else {})
        source_id = f"way/{way}" if way is not None else area or "native/shared_node"
        kind = e["kind"]
        edges.append(dict(id=e.get("edge_id") or f"native/{n}", u=node_id(a), v=node_id(b),
                          kind=kind, source_id=source_id, tags=tags, segment_index=e.get("segment_index"),
                          evidence=e.get("semantic_reasons")))
    target = dict(id=ident, xy=source.projected[target_n], wgs84=source.coord(ident),
                  tags=source.nodes[target_n]["tags"], registered=True,
                  building_id=entrance["target_building_native_id"])
    return dict(schema_version=1, task_id=scene["scene_id"] + "/north", kind="REGISTERED_DOOR_TASK",
                crs="EPSG:32651", target=target, origin=scene["start_native_id"], nodes=nodes, edges=edges,
                context=natural_context(source, native, target["xy"], cfg["radius_m"]+cfg["clearance_m"]))


def historical_summary(root):
    path = root / "north/runs/experiment.json"
    doc = read(path)
    variants = {k: {key: row[key] for key in ("status", "length_m", "native_m", "connector_m", "residual_m",
                                            "entrance_role", "inbound_eligibility") if key in row}
                for k, row in doc["variants"].items()}
    return dict(role="HISTORICAL_H0_N0_N1_N2", source="inputs/north/runs/experiment.json",
                sha256=sha(path), variants=variants)


def write_candidate_csv(path, result):
    path.parent.mkdir(exist_ok=True, parents=True)
    fields = ["variant", "anchor_id", "source_id", "source_segment_index", "source_kind", "source_tags",
              "anchor_wgs84", "candidate_wgs84", "status", "reason", "length_m", "cost_m",
              "route_selected", "context", "direct_conflicts", "grade_status"]
    with path.open("x", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for variant, model in result["methods"].items():
            for row in model["candidates"]:
                d = dict(row, variant=variant, anchor_id=row["id"], anchor_wgs84=INVERSE(*row["xy"]),
                         candidate_wgs84=[INVERSE(*p) for p in row["candidate_xy"]])
                w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (tuple, list, dict)) else v
                            for k, v in d.items()})


def run_natural(input_root, out, config, config_path):
    from inputs.rev1.src.route_measure import overlay
    from src.semantics import build_native, load_area_graph

    if any((out / p).exists() for p in EXPORTED):
        raise FileExistsError("Use a fresh output root for inference runs")
    begin = perf_counter()
    rev = input_root / "rev1"
    frozen = rev / "frozen_r4"
    manifest = frozen / "runs/source_scene_contracts.json"
    scene = next(s for s in read(manifest)["scenes"] if s["scene_id"] == NORTH_SCENE)
    door = next(e for e in scene["r4_entrances"] if e["native_id"] == NORTH_DOOR)
    # The entire pre-existing frozen north face graph stays in the strict and conditional variants.
    old_area = load_area_graph(rev, NORTH_SCENE, {"relation/2153738"})
    new = build_native(frozen, scene, "S1")
    obs = make_observation(scene, overlay(new.graph, [old_area]), new, door, config)
    result = run_observed(obs, config)
    result["context_geometry_count"] = {k: len(v) for k, v in obs["context"].items()}
    ctx = context_features(obs, result)
    del new
    old = build_native(frozen, scene, "S0")
    ablated = make_observation(scene, overlay(old.graph, [old_area]), old, door, config)
    ab = run_observed(ablated, config, methods=("I2",))
    result["methods"]["ABL-S"] = dict(ab["methods"]["I2"], variant="ABL-S")
    result.update(status="EXECUTED_NATURAL_DEVELOPMENT", elapsed_seconds=round(perf_counter()-begin, 6),
                  historical=historical_summary(input_root), origin_native_id=scene["start_native_id"],
                  graph_scope="NATIVE_SEMANTIC_GRAPH_PLUS_UNCHANGED_FROZEN_NORTH_PEDESTRIAN_AREA",
                  configuration=config, config_sha256=sha(config_path), field_validation="NOT_VERIFIED",
                  implementation_tie_rule="PREFER_LESS_INFERRED_LENGTH_AT_EQUAL_COST",
                  read_log=[dict(path="inputs/"+name, bytes=(input_root / name).stat().st_size, sha256=sha(input_root / name))
                            for name in ["rev1/frozen_r4/runs/source_scene_contracts.json",
                                         "rev1/frozen_r4/"+scene["osm_clip"],
                                         "rev1/data/edge_evidence.jsonl", "north/runs/experiment.json"]
                            if (input_root / name).is_file()], external_requests=0)
    write(out, EXPORTED[0], result)
    write(out, EXPORTED[1], collection(route_features(result)))
    write(out, EXPORTED[2], collection(candidate_features(result)))
    write(out, EXPORTED[3], collection(ctx))
    write_candidate_csv(out / EXPORTED[4], result)
    print(json.dumps(dict(scene=NORTH_SCENE, variants={m: dict(status=r["status"],
                 length=r["route"]["length_m"] if r["route"] else None, admitted=r["admitted_edges"],
                 used=r["used_inferred_edges"], residual=r["residual_m"]) for m, r in result["methods"].items()})))


def run_masked(observed_root, out, config, config_path, scope, contrast=None):
    begin = perf_counter()
    pred = []
    log = []
    if observed_root.name != "observed" or not observed_root.is_dir() or observed_root.is_symlink():
        raise ValueError("Only a frozen observed directory may enter the masked predictor")
    for path in sorted(observed_root.rglob("*.json")):
        if contrast is not None and path.stem not in scope["development_task_ids"]:
            continue
        rel = path.relative_to(observed_root)
        if path.is_symlink() or not path.resolve().is_relative_to(observed_root.resolve()) or any(
                part.lower() in {"reference", "references", "full", "raw"} for part in rel.parts):
            raise ValueError("Masked prediction encountered a forbidden path")
        content = path.read_bytes()
        task = json.loads(content.decode("utf-8-sig"))
        if task["task_id"] != path.stem:
            raise ValueError("Task identity and observed file name must agree")
        if contrast is not None:
            methods = ("I2",)
        elif path.stem.startswith(tuple(scope["confirmation_task_prefixes"])):
            methods = ("I0", "I1", "I2")
        else:
            methods = ("I0", "I1", "I2", "ABL-I", "ABL-C")
        result = run_observed(task, config, methods=methods)
        pred.append(result)
        log.append(dict(task_id=task["task_id"], path=(Path("observed") / rel).as_posix(), bytes=len(content),
                        sha256=sha256(content).hexdigest(), phase="OBSERVED_ONLY_PREDICTOR_READ"))
    if not pred:
        raise ValueError("No observed masking tasks found")
    if contrast is not None and {r["task_id"] for r in pred} != set(scope["development_task_ids"]):
        raise ValueError("Incomplete locked development contrast")
    output = "runs/masked_predictions.json" if contrast is None else f"runs/sensitivity/{contrast}/predictions.json"
    write(out, output, dict(status="EXECUTED_OBSERVED_ONLY", predictions=pred, read_log=log,
          config_sha256=sha(config_path), active_configuration=config, contrast=contrast,
          confirmation_scope="I0_BASELINE_AND_I1_I2_PREDICTIVE_METHODS",
          methods_frozen=["I1", "I2"], elapsed_seconds=round(perf_counter()-begin, 6),
          reference_inputs_read=0, isolation="APPLICATION_INPUT_WHITELIST", external_requests=0,
          implementation_tie_rule="PREFER_LESS_INFERRED_LENGTH_AT_EQUAL_COST"))
    print(json.dumps(dict(predicted_tasks=len(pred), reference_inputs_read=0)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["natural", "masked"])
    p.add_argument("--input-root", type=Path, default=ROOT / "inputs")
    p.add_argument("--observed-root", type=Path, default=ROOT / "data/masking/observed")
    p.add_argument("--output-root", type=Path, default=ROOT)
    p.add_argument("--config", type=Path, default=ROOT / "config/inference.json")
    p.add_argument("--scope", type=Path, default=ROOT / "config/inference_sensitivity.json")
    p.add_argument("--contrast", help="Run one locked development-only sensitivity setting")
    args = p.parse_args()
    cfg = read(args.config)
    if cfg["status"] != "LOCKED_BEFORE_NATURAL_AND_CONTROLLED_PREDICTIONS":
        raise ValueError("The inference configuration must be frozen")
    if args.mode == "natural":
        if args.contrast:
            p.error("--contrast is available for controlled development observations only")
        run_natural(args.input_root.resolve(), args.output_root.resolve(), cfg["main"], args.config.resolve())
    else:
        scope = read(args.scope)
        config = dict(cfg["main"])
        if args.contrast:
            try:
                config.update(scope["contrasts"][args.contrast]["overrides"])
            except KeyError:
                p.error("Unregistered development contrast")
        run_masked(args.observed_root.resolve(), args.output_root.resolve(), config, args.config.resolve(),
                   scope, args.contrast)
