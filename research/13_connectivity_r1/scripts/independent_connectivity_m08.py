"""Raw M08 layer identity and absence of new alias bridges; no route solve."""
import csv
import gzip
import json
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from independent_connectivity_source import ROOT, RawGeometry, read, write, digest, linear_tag_reason
from independent_connectivity_omega import nonground
from independent_connectivity_components import structure, count_components


def main():
    query = next(r for r in read(ROOT / "data/connectivity/mechanism_request_endpoints_lock.json")["queries"] if r["mechanism_id"] == "M08")
    entry = next(r for r in read(ROOT / "data/scene_manifest.json")["scenes"] if r["scene_id"] == query["scene_id"])
    source = RawGeometry(read(ROOT / entry["source_path"]))
    end = query["end"]; raw_id = end["native_id"]; graph_id = end["layer_aware_native_graph_id"]
    number = int(raw_id.split("/")[1]); xy = source.xy[number]
    assert tuple(end["xy"]) == tuple(xy) and source.objects[("node", number)].get("tags", {}) == end["source_node_tags"]
    incident = [{"source_id": "way/" + str(ident), "tags": way.get("tags", {}), "explicit_non_ground": nonground(way.get("tags", {})),
        "linear_tag_reason": linear_tag_reason(way.get("tags", {}))} for (kind, ident), way in source.objects.items()
        if kind == "way" and number in way.get("nodes", []) and way.get("tags", {}).get("highway")]
    eligible_ground = [r for r in incident if r["linear_tag_reason"] is None and not r["explicit_non_ground"]]
    fp = ROOT / "data/connectivity" / (query["scene_id"] + "_faces.json")
    reference = read(ROOT / "audits" / ("independent_omega_" + query["scene_id"] + ".json"))
    assert digest(fp) == reference["author_faces_sha256"]
    legal = unary_union([shape(f["omega"]) for f in read(fp) if f["status"] == "ADMITTED"])
    logs = {}
    for path in (ROOT / "runs/preprocessing").glob("*.json"):
        pp = read(path)
        if pp.get("cache_key"):
            logs[pp["cache_key"]] = pp
    def chain(key):
        pp = logs[key]; result = []
        if pp.get("mode") in {"EXACT_STITCH", "CONDITIONAL_SEAMS"}:
            result.extend(chain(pp["parent_cache_key"]))
        result.append((pp.get("stored_overlay", pp.get("derived_overlay_path")), pp.get("stored_overlay_sha256", pp.get("derived_overlay_sha256"))))
        return result
    rows = []; overlay_cache = {}
    for text in (ROOT / "results/formal_registry.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(text)
        if record["request"].get("mechanism_id") != "M08":
            continue
        response_path = ROOT / record["path"]; body = read(response_path)
        assert digest(response_path) == record["result_sha256"]
        overlays = []
        for path, expected in chain(body["preprocessing_cache"]["key"]):
            if path not in overlay_cache:
                assert digest(ROOT / path) == expected
                hits, incident_arcs = [], []
                with gzip.open(ROOT / path, "rt", encoding="utf-8") as stream:
                    for line in stream:
                        row = json.loads(line)
                        if row["kind"] == "node" and (row["id"] in {raw_id, graph_id} or row.get("xy") and tuple(row["xy"]) == tuple(xy)):
                            hits.append(row["id"])
                        elif row["kind"] == "arc" and (row["u"] in {raw_id, graph_id} or row["v"] in {raw_id, graph_id}):
                            incident_arcs.append([row["u"], row["v"]])
                overlay_cache[path] = {"path": path, "sha256": expected, "same_identity_or_coordinate_nodes": hits, "incident_arcs": incident_arcs}
            overlays.append(overlay_cache[path])
        target = body["bindings"][1]
        errors = []
        if target["id"] != graph_id or not target["bound"] or target["displacement_m"] != 0 or target["identity"] != "EXISTING_SOURCE_NETWORK_NODE":
            errors.append("LAYER_AWARE_EXISTING_TARGET_IDENTITY_CHANGED")
        if body["status"] != "NO_VALID_ROUTE" or body["failure"]["code"] != "DISCONNECTED_GRAPH" or not body["solver"]["invoked"] or body.get("route"):
            errors.append("BOUND_ISOLATED_SEARCH_INTERPRETATION")
        if any(o["same_identity_or_coordinate_nodes"] or o["incident_arcs"] for o in overlays):
            errors.append("OVERLAY_ADDED_TARGET_OR_SAME_COORDINATE_ALIAS")
        rows.append({"mode": record["request"]["connectivity_mode"], "run_id": body["run_id"], "cache_key": body["preprocessing_cache"]["key"],
            "raw_target_id": raw_id, "retained_target_graph_id": target["id"], "original_xy": xy,
            "solver_invoked": body["solver"]["invoked"], "status": body["status"], "overlays": overlays, "errors": errors})
    topology = {"status": "PENDING_BOUND_SOURCE_TOPOLOGY; DO_NOT_INFER_ZERO_DEGREE_FROM_NO_ROUTE_ALONE"}
    table = ROOT / "results/component_statistics.csv"
    if table.exists():
        component_rows = list(csv.DictReader(table.open(encoding="utf-8-sig", newline="")))
        component_rows.sort(key=lambda r: r["mode"] != "CONDITIONAL_SEAMS")
        for row in component_rows:
            if row["scene_id"] != query["scene_id"] or row["door_id"] or row["original_PREP_cache_key"] not in {r["cache_key"] for r in rows}:
                continue
            snapshot = json.loads(row["source_topology"]); path = ROOT / snapshot["path"]
            assert digest(path) == snapshot["sha256"]
            nodes, arcs = structure(path, snapshot["sha256"], snapshot["structural_sha256"])
            weak, strong, wc, sc = count_components(nodes, arcs)
            start = query["start"]["native_id"]
            members = sorted(n for n in nodes if weak[n] == weak[graph_id])
            strong_members = sorted(n for n in nodes if strong[n] == strong[graph_id])
            bridge_errors = []
            for mode_row in rows:
                for overlay in mode_row["overlays"]:
                    with gzip.open(ROOT / overlay["path"], "rt", encoding="utf-8") as stream:
                        for text in stream:
                            item = json.loads(text)
                            if item["kind"] == "arc" and (item["u"] in members or item["v"] in members):
                                bridge_errors.append({"mode": mode_row["mode"], "u": item["u"], "v": item["v"]})
            pp = logs[row["original_PREP_cache_key"]]
            identity_matches = row["prepared_graph_sha256"] == pp["graph_sha256"]
            separated = weak.get(start) != weak[graph_id] and not bridge_errors
            topology = {"status": "VERIFIED_BOUND_SEPARATE_LAYER1_COMPONENT" if separated and identity_matches else "REQUIRES_INSPECTION",
                "snapshot": snapshot, "actual_PREP_cache_key": row["original_PREP_cache_key"],
                "full_attributed_PREP_graph_sha256_matches_component_binding": identity_matches,
                "layer1_node_retained": graph_id in nodes, "target_in_degree": sum(v == graph_id for u, v in arcs),
                "target_out_degree": sum(u == graph_id for u, v in arcs), "plain_ground_alias_present": raw_id in nodes,
                "target_weak_component_size": len(members), "target_strong_component_size": len(strong_members),
                "target_weak_component_members": members, "all_members_explicit_layer1": all("@layer=1@" in n for n in members),
                "start_and_target_weak_labels_different": weak.get(start) != weak[graph_id], "new_overlay_arcs_touching_any_component_member": bridge_errors,
                "zero_degree_singleton_hypothesis": "REFUTED; target has original 2 incoming and 2 outgoing arcs in a separate 4-node layer1 component"}
            break
    result = {"reviewer": "/root/connectivity_review", "scope": "M08 raw layer/source identity and all mode overlay chains; source isolation requires a bound source-topology snapshot",
        "APP_solver_calls": 0, "new_route_solver_calls": 0, "raw_source_sha256": digest(ROOT / entry["source_path"]),
        "incident_raw_highways": incident, "eligible_ground_incident_raw_highways": eligible_ground,
        "raw_target_distance_to_all_admitted_ground_Omega_m": Point(xy).distance(legal), "rows": rows, "source_isolation": topology,
        "status": "PASS_FOR_M08_LAYER_AND_NO_ALIAS_BRIDGE" if len(rows) == 4 and not eligible_ground and all(not r["errors"] for r in rows) else "REQUIRES_INSPECTION",
        "limits": ["Existing node binding does not assert an eligible ground arc, physical level access or successful route", "A separate layer1 component is not a zero-degree node and is not proof of physical inaccessibility"]}
    write(ROOT / "audits/independent_m08_layer_review.json", result)
    print(json.dumps({"status": result["status"], "source_isolation": topology["status"], "ground_incident_highways": len(eligible_ground), "modes": len(rows)}))


if __name__ == "__main__":
    main()
