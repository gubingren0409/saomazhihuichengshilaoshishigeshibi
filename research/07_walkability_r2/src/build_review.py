"""Render the offline map from the frozen base and the actual output geometries."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ORDER = ["park", "plaza", "grass", "water", "building", "road", "walk", "fence", "label", "observed"]
LABELS = {"I0": "不补线", "I1": "最近直连", "I2": "多接点受约束推断", "ABL-S": "保留草地旧规则",
          "ABL-I": "移除推断边", "ABL-C": "移除地图上下文门槛"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def geometry_records(base, source, layers):
    return [(layers(feature["properties"]), base.metric(feature["geometry"]), feature["properties"])
            for feature in source if feature.get("geometry")]


def paint(base, records, anchor, clip):
    result = []
    for layer, geometry, properties in records:
        if not layer or not geometry.intersects(clip):
            continue
        geometry = geometry.intersection(clip)
        if parts := base.normalize(geometry, anchor):
            result.append({"layer": layer, "shape": parts, "props": properties})
    return result


def views(base, near, full, anchor):
    return {"near": base.camera_bounds(near, anchor), "full": base.camera_bounds(full, anchor)}


def map_point(layer, base, lonlat, **props):
    return layer, base.metric({"type": "Point", "coordinates": lonlat}), dict(wgs84=lonlat, **props)


def numeric(n):
    return "—" if n is None else f"{n:,.2f}"


def table(title, headers, rows):
    return dict(title=title, headers=headers, rows=rows)


def load_basemap(root, base, frame):
    frozen = root / "inputs/rev1/frozen_r4"
    raw = read(frozen / "data/source/sh-huangpu-01.osm.json")
    items = [("label" if layer == "road_label" else layer, g, props)
             for layer, g, props in base.basemap(raw, frame)]
    for item in read(frozen / "runs/source_open_spaces.json")["features"]:
        if item["scene_id"] != "sh-huangpu-01" or not item.get("geometry"):
            continue
        layer = {"PEDESTRIAN_AREA": "plaza", "PARK_GARDEN_OR_RECREATION": "park"}.get(item["category"])
        if layer:
            items.append((layer, base.metric(item["geometry"]), base.area_properties(item)))
    items.sort(key=lambda item: ORDER.index(item[0]) if item[0] in ORDER else len(ORDER))
    return items


def build_museum(root, base, north_run):
    semantics = read(root / "runs/semantics.json")
    sem = read(root / "data/semantics_routes.geojson")["features"]
    route = read(root / "data/inference_routes.geojson")["features"]
    candidates = read(root / "data/inference_candidates.geojson")["features"]
    ctx = read(root / "data/inference_context.geojson")["features"]
    building = base.metric(next(f["geometry"] for f in ctx if f["properties"].get("kind") == "BUILDING"))
    anchor = building.centroid.coords[0]
    north_routes = [f for f in route if f["properties"]["role"] == "route_segment"]
    s_routes = [f for f in sem if f["properties"]["role"] == "route" and f["properties"]["target"] == "north_fixed"]
    original = s_routes[0]["properties"]
    source_grass = next(base.metric(f["geometry"]) for f in sem if f["properties"]["role"] == "source_grass")
    full = base.fit_bounds([building, *(base.metric(f["geometry"]) for f in north_routes)], 29)
    smap = load_basemap(root, base, full)
    origin = map_point("origin", base, original["start_wgs84"], source_id=north_run["origin_native_id"])
    door = map_point("door", base, north_run["target"]["wgs84"], source_id=north_run["target"]["id"],
                     tags=north_run["target"]["tags"])
    fixed_end = map_point("anchor", base, original["end_wgs84"], label="固定北侧路网接点", source_id="way/178719573")
    target_label = ("label", building.representative_point(), {"label": "上海博物馆"})
    smap.extend([target_label])
    native_layers = { "NATIVE_LINEAR": "native", "DERIVED_FROM_TAGGED_PEDESTRIAN_AREA": "derived",
                      "DERIVED_TERMINAL_CONNECTOR": "derived"}
    grass_near = base.fit_bounds([source_grass], 18)
    grass = {"title": "草地内的已标步道", "intro": "同一起点和北侧路网接点。背景草地与原生步道可以在图上重叠。只修复已标步道被误排，北门缺口仍由第二页单独检查。",
             "base": paint(base, smap, anchor, full), "views": views(base, grass_near, full, anchor)}
    grass["pair"] = {}
    for side, variant in (("left", "S0"), ("right", "S1")):
        props = semantics["variants"][variant]["north_fixed"]
        route_features = [f for f in s_routes if f["properties"]["variant"] == variant]
        restored = [f for f in sem if f["properties"]["role"] == "restored_edge"]
        records = (geometry_records(base, route_features, lambda _: "native") +
                   geometry_records(base, restored, lambda _: "rejected" if variant == "S0" else "restored"))
        grass["pair"][side] = {"title": variant + (" · 草地旧排除" if variant == "S0" else " · 保留原生步道"),
                               "note": f"固定接点路线 {numeric(props['length_m'])} m",
                               "features": paint(base, [*records, origin, fixed_end], anchor, full)}
    grass["tables"] = [table("同一端点复算（米）", ["变体", "北侧固定接点", "南门既有对照"],
                              [[v, numeric(semantics["variants"][v]["north_fixed"]["length_m"]),
                                numeric(semantics["variants"][v]["south"]["length_m"])] for v in ("S0", "S1")])]
    ctx_layer = lambda p: {"independent_allowed_domain": "domain", "independent_search_window": "window"}.get(p["role"])
    north_near = base.fit_bounds([shape(north_run["window"])], 10)
    prior = read(root / "inputs/north/data/constraints.geojson")["features"]
    history = geometry_records(base, prior, lambda p: "historic" if p.get("role") == "N2_corridor" else None)
    rows = []
    for name, method in north_run["methods"].items():
        lengths = method["route"]
        rows.append([name, LABELS[name], numeric(lengths.get("length_m")), numeric(lengths.get("native_m")),
                     numeric(lengths.get("derived_m")), numeric(lengths.get("inferred_m")),
                     numeric(method["residual_m"]), numeric(lengths.get("cost_m"))])
    north = {"title": "北门多接点、取舍和完整路线",
             "intro": "起点和北侧登记出口坐标保持冻结。橙虚线是条件推断，紫线是既有登记步行面内派生边。地图上下文支持检索，最后一段的连续楼层和现场通行仍待核实。出口仍为 exit。",
             "base": paint(base, [*smap, *history], anchor, full), "views": views(base, north_near, full, anchor),
             "pairs": {}, "tables": [table("固定起点到登记出口或路网断点（米）",
                                         ["变体", "处理", "几何长度", "原生", "既有面派生", "推断", "余隙", "含惩罚代价"], rows)]}
    for name in ("I2", "I1", "ABL-S", "ABL-I", "ABL-C", "I0"):
        panels = {}
        for side, variant in (("left", "I0"), ("right", name)):
            method = north_run["methods"][variant]
            segments = [f for f in north_routes if f["properties"]["variant"] == variant]
            proposals = [f for f in candidates if f["properties"]["variant"] == variant]
            def proposal_layer(p):
                if p["role"] == "candidate_anchor":
                    return "anchor"
                if p["route_selected"]:
                    return None
                return "candidate" if p["status"] == "INFERRED_ALLOWED" else "rejected"
            extras = [origin, door]
            if method["residual_m"]:
                extras.extend([fixed_end, ("gap", LineString([fixed_end[1], door[1]]),
                                            {"label": "未接入间隙（测距）", "length_m": method["residual_m"]})])
            records = (geometry_records(base, ctx, ctx_layer) +
                       geometry_records(base, proposals, proposal_layer) +
                       geometry_records(base, segments, lambda p: native_layers.get(
                           p["kind"], "inferred" if p["hypothesis"] else "derived")))
            panels[side] = {"title": f"{variant} · {LABELS[variant]}",
                            "note": f"路线 {numeric(method['route']['length_m'])} m · 门前余隙 {numeric(method['residual_m'])} m",
                            "features": paint(base, [*records, *extras], anchor, full)}
        north["pairs"][name] = panels
    north["tables"].append(table("I2 接网取舍", ["接点", "原生对象", "接入长度 m", "前段代价 m", "地图上下文", "楼层", "结果"],
        [[c["id"], c["source_id"], numeric(c.get("length_m")), numeric(c.get("graph_distance_m")),
          ", ".join(str(s["source_id"]) for s in c.get("context", {}).get("support", [])),
          "连续楼层未知", "全程入选" if c["route_selected"] else "可条件接入，未入选" if c["status"] == "INFERRED_ALLOWED" else c["reason"]]
         for c in north_run["methods"]["I2"]["candidates"]]))
    return grass, north


def build_cases(root, base):
    path = root / "data/masking/review_cases.geojson"
    if not path.is_file():
        return []
    source = read(path)["features"]
    outcomes = {(r["task_id"],r["method"]): r for r in read(root / "runs/masking_evaluation.json")["outcomes"]}
    predictions_by_id = {r["task_id"]: r for r in read(root / "runs/masked_predictions.json")["predictions"]}
    priority = ["P-newworld-02", "N-newworld-02", "P-newworld-03", "P-library-01"]
    case_ids = sorted({f["properties"]["task_id"] for f in source},
                      key=lambda ident: (priority.index(ident) if ident in priority else len(priority), ident))
    cases = []
    for ident in case_ids:
        subset = [f for f in source if f["properties"]["task_id"] == ident]
        ref = next(f for f in subset if f["properties"]["role"] in {"reference_hidden", "blocked_control"})
        rp = ref["properties"]
        is_positive = rp["role"] == "reference_hidden"
        label = "遮蔽原生步道" if is_positive else "明确障碍负例"
        ref_geom = base.metric(ref["geometry"])
        target = next(f for f in subset if f["properties"]["role"] == "target")
        anchor = base.metric(target["geometry"]).coords[0]
        near = base.fit_bounds([ref_geom], 12, minimum=45)
        outcome = outcomes[ident, "I2"]
        actual_route = predictions_by_id[ident]["methods"]["I2"]["route"]
        route_records = []
        for segment in (actual_route or {}).get("edges", []):
            geometry = LineString(segment["xy"])
            route_records.append(("inferred" if segment["hypothesis"] else "native", geometry,
                                  {"source_id": segment["source_id"], "kind": segment["kind"],
                                   "length_m": segment["length_m"], "status": "实际入选路线"}))
        full = base.fit_bounds([ref_geom, *(g for _, g, _ in route_records), *(base.metric(f["geometry"]) for f in subset
                                           if f["properties"]["role"] in {"origin", "target", "observed_network"})], 9)
        common = [f for f in subset if f["properties"]["role"].startswith("observed") or
                  f["properties"]["role"] in {"origin", "target"}]
        layers = {"observed_network": "observed", "observed_background": "grass", "observed_support": "plaza",
                  "origin": "origin", "target": "door", "reference_hidden": "reference", "blocked_control": "rejected",
                  "inferred_selected": "inferred", "inferred_candidate": "candidate", "rejected": "rejected"}
        def kind(p):
            if p["role"] == "observed_obstacle":
                return {"BUILDING":"building", "WATER":"water"}.get(p.get("kind"), "fence")
            return layers[p["role"]]
        records = geometry_records(base, common, kind)
        records.sort(key=lambda item: ORDER.index(item[0]) if item[0] in ORDER else len(ORDER))
        predictions = [f for f in subset if f["properties"].get("method") == "I2"]
        rows = [[p.get("source_id"), p.get("status"), p.get("reason"), p.get("verdict")]
                for f in predictions if (p := f["properties"])]
        cases.append({"id": ident, "label": label + " · " + rp["split"], "title": f"{ident} · {label}",
                      "intro": "同一坐标视野。左图只含算法可见输入。右图加入 I2 输出及事后参考。拒绝反例来自冻结地图内的已标障碍，作为受控尝试。",
                      "base": paint(base, records, anchor, full), "views": views(base, near, full, anchor),
                      "pair": {"left": {"title":"遮蔽后的输入", "note":"参考线在运行时不可见", "features":[]},
                               "right":{"title":"I2 输出与隔离参考", "note":rp["split"] + " · " + rp["kind"],
                                        "features":paint(base, [*route_records, *geometry_records(base, [ref, *predictions], kind)], anchor, full)}},
                      "tables":[table("I2 判定", ["路线状态", "余隙 m", "参考覆盖", "恢复参考", "误接"],
                                      [[outcome["route_status"], numeric(outcome["residual_m"]),
                                        f"{outcome['reference_coverage']:.1%}" if is_positive else "—",
                                        str(outcome["controlled_recovery"]) if is_positive else "—",
                                        str(outcome["negative_false_connection"]) if not is_positive else "—"]]),
                                table("隔离参考", ["类别","参考对象","反例障碍","查询端点"],
                                      [[label, rp.get("source_id"), ", ".join(rp["negative_obstacles"]),
                                        "登记门" if target["properties"]["registered"] else "现有路网点"]]),
                                table("I2 候选", ["来源对象","状态","原因","受控恢复"], rows)]})
    return cases


def build_synthetic(base):
    from shapely.geometry import box
    from src.semantics import segment_decision
    walk = {"highway": "footway"}
    segment = LineString([(0, 0), (4, 0)])
    wall = {"id": "fixture/wall", "kind": "BARRIER", "geometry": LineString([(2, -1), (2, 1)]),
            "tags": {"barrier": "wall"}, "gates": []}
    water = {"id": "fixture/water", "kind": "AREA", "geometry": box(1, -1, 3, 1),
             "tags": {"natural": "water"}}
    checks = [
        ("wall", "墙无共同闸口", [wall], walk, {}, "fence"),
        ("water", "无桥梁标记穿水", [water], walk, {}, "water"),
        ("level", "端点明确分属两层", [], walk, {"endpoint_tags": ({"level":"0"}, {"level":"1"})}, None),
        ("foot", "明确禁止步行", [], {**walk, "foot": "no"}, {}, None),
    ]
    case_list = []
    for ident, caption, obstacles, tags, extra, layer in checks:
        decision = segment_decision(segment, tags, obstacles, "S1", **extra)
        frame = base.fit_bounds([segment], 3, minimum=11)
        anchor = (2, 0)
        props = {"status": decision["status"], "reason": ", ".join(decision["reasons"]), "tags": tags}
        left = [("observed", segment, {"label": "受测合成边", "tags": tags})]
        right = [("rejected", segment, props)]
        common = [("origin", Point(0, 0), {"label": "合成端点 A"}), ("anchor", Point(4, 0), {"label": "合成端点 B"})]
        if layer:
            common.extend((layer, o["geometry"], {"source_id": o["id"], "tags": o["tags"]}) for o in obstacles)
        ident = "SYN-" + ident
        case_list.append({"id": ident, "label": "合成单元反例 · " + caption,
                          "title": "合成单元反例 · " + caption, "intro": "仅用于确认规则行为，采用合成米制坐标。未计入真实地图正负例。",
                          "base": paint(base, common, anchor, frame), "views": views(base, frame, frame, anchor),
                          "pair": {"left":{"title":"测试输入", "note":"源代码定义的合成几何", "features":paint(base, left, anchor, frame)},
                                   "right":{"title":"语义判定", "note":props["reason"], "features":paint(base, right, anchor, frame)}},
                          "tables":[table("实际判定", ["状态", "原因", "端点标签"],
                                          [[decision["status"], props["reason"], str(extra.get("endpoint_tags", ""))]])]})
    return case_list


def main(root, output):
    spec = importlib.util.spec_from_file_location("frozen_basemap", root / "inputs/rev1/src/build_visuals.py")
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    north_run = read(root / "runs/inference.json")
    grass, north = build_museum(root, base, north_run)
    payload = json.dumps(dict(grass=grass, north=north, cases=build_cases(root, base) + build_synthetic(base)), ensure_ascii=False,
                         separators=(",", ":")).replace("<", "\\u003c")
    template = (ROOT / "src/review_template.html").read_text(encoding="utf-8")
    js = (ROOT / "src/review_script.js").read_text(encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace("__SCRIPT__", js).replace("__PAYLOAD__", payload), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    main(args.root, args.output or args.root / "visuals/index.html")
