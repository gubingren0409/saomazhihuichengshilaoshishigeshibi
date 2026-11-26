"""Independent union-find/Kosaraju counts from bound source/local/overlay IDs.

No source compiler, visibility builder, APP or shortest-path solver is imported.
Full attributed graph identity is the separately declared author precondition;
this audit independently verifies its PREP/response bindings and every count.
"""
import csv
import gzip
import hashlib
import json
from pathlib import Path
from independent_connectivity_source import ROOT, digest, read, write


def structure(path, expected, structural=None):
    assert digest(path) == expected, "TOPOLOGY_OR_OVERLAY_ARCHIVE_SHA"
    nodes, arcs = set(), set()
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["kind"] == "node":
                nodes.add(row["id"])
            elif row["kind"] == "arc":
                arcs.add((row["u"], row["v"]))
            else:
                raise ValueError("UNKNOWN_TOPOLOGY_RECORD")
    assert all(u in nodes and v in nodes for u, v in arcs), "ARC_WITHOUT_EXPLICIT_SNAPSHOT_NODE"
    if structural:
        h = hashlib.sha256()
        for ident in sorted(nodes):
            h.update(json.dumps(["node", ident], separators=(",", ":")).encode() + b"\n")
        for u, v in sorted(arcs):
            h.update(json.dumps(["arc", u, v], separators=(",", ":")).encode() + b"\n")
        assert h.hexdigest() == structural, "CANONICAL_TOPOLOGY_SHA"
    return nodes, arcs


def count_components(names, edges):
    names = sorted(names); index = {n: i for i, n in enumerate(names)}; n = len(names)
    parent = list(range(n)); sizes = [1] * n
    outgoing = [[] for _ in names]; incoming = [[] for _ in names]
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for u, v in edges:
        a, b = index[u], index[v]
        outgoing[a].append(b); incoming[b].append(a)
        x, y = root(a), root(b)
        if x != y:
            if sizes[x] < sizes[y]:
                x, y = y, x
            parent[y] = x; sizes[x] += sizes[y]
    minima = {}
    for i, name in enumerate(names):
        r = root(i); minima[r] = min(name, minima.get(r, name))
    weak = {name: minima[root(i)] for i, name in enumerate(names)}
    seen = bytearray(n); finish = []
    for start in range(n):
        if seen[start]:
            continue
        seen[start] = 1; stack = [(start, 0)]
        while stack:
            u, cursor = stack[-1]
            if cursor == len(outgoing[u]):
                stack.pop(); finish.append(u); continue
            v = outgoing[u][cursor]; stack[-1] = (u, cursor + 1)
            if not seen[v]:
                seen[v] = 1; stack.append((v, 0))
    seen = bytearray(n); strong = {}; sc = 0
    for start in reversed(finish):
        if seen[start]:
            continue
        sc += 1; stack = [start]; seen[start] = 1; component = []
        while stack:
            u = stack.pop(); component.append(u)
            for v in incoming[u]:
                if not seen[v]:
                    seen[v] = 1; stack.append(v)
        label = min(names[i] for i in component)
        strong.update((names[i], label) for i in component)
    return weak, strong, len(minima), sc


def main():
    table = ROOT / "results/component_statistics.csv"
    author_receipt_path = ROOT / "results/component_analysis_receipt.json"
    author_receipt = read(author_receipt_path)
    rows = list(csv.DictReader(table.open(encoding="utf-8-sig", newline="")))
    members_path = ROOT / "results/interface_component_membership.csv"
    members = list(csv.DictReader(members_path.open(encoding="utf-8-sig", newline="")))
    membership_groups = {}
    for row in members:
        membership_groups.setdefault((row["scene_id"], row["door_id"], row["mode"]), []).append(row)
    logs = {}
    for path in (ROOT / "runs/preprocessing").glob("*.json"):
        body = read(path)
        if body.get("cache_key"):
            logs[body["cache_key"]] = body
    responses = {}
    for name in ("formal_registry.jsonl", "formal_replay_registry.jsonl"):
        path = ROOT / "results" / name
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                responses[row["result_sha256"]] = row
    def expected_chain(key):
        pp = logs[key]; chain = []
        if pp.get("mode") in {"EXACT_STITCH", "CONDITIONAL_SEAMS"}:
            chain.extend(expected_chain(pp["parent_cache_key"]))
        chain.append({"path": pp.get("stored_overlay", pp.get("derived_overlay_path")),
            "sha256": pp.get("stored_overlay_sha256", pp.get("derived_overlay_sha256"))})
        return chain
    checks = []; previous = None; previous_namespace = None
    for row in rows:
        namespace = (row["scene_id"], row["door_id"])
        if namespace != previous_namespace:
            previous = None; previous_namespace = namespace
        nodes, arcs = set(), set(); errors = []
        pp = logs[row["original_PREP_cache_key"]]
        if pp["graph_sha256"] != row["prepared_graph_sha256"]:
            errors.append("PREP_GRAPH_IDENTITY")
        response = responses[row["bound_response_sha256"]]
        body_path = ROOT / response["path"]
        if digest(body_path) != row["bound_response_sha256"] or read(body_path).get("preprocessing_cache", {}).get("key") != row["original_PREP_cache_key"]:
            errors.append("ACTUAL_RESPONSE_SHA_OR_PREP_KEY")
        sources = [json.loads(row[k]) for k in ("source_topology", "local_topology")]
        for source in sources:
            ns, es = structure(ROOT / source["path"], source["sha256"], source["structural_sha256"])
            if len(ns) != source["nodes"] or len(es) != source["arcs"]:
                errors.append("BASE_TOPOLOGY_DECLARED_COUNTS")
            nodes.update(ns); arcs.update(es)
        overlays = json.loads(row["overlays"])
        if overlays != expected_chain(row["original_PREP_cache_key"]):
            errors.append("ACTUAL_FULL_PARENT_OVERLAY_CHAIN")
        for overlay in overlays:
            ns, es = structure(ROOT / overlay["path"], overlay["sha256"])
            nodes.update(ns); arcs.update(es)
        weak, strong, wc, sc = count_components(nodes, arcs)
        measured = {"nodes": len(nodes), "arcs": len(arcs), "weak_components": wc, "strong_components": sc}
        if any(int(row[k]) != measured[k] for k in measured):
            errors.append("INDEPENDENT_COMPONENT_OR_GRAPH_COUNTS")
        checked_members = 0
        for member in membership_groups.get((*namespace, row["mode"]), []):
            ids = json.loads(member["graph_node_ids"])
            expected = {"new_weak_component_labels": [weak.get(n) for n in ids],
                "new_strong_component_labels": [strong.get(n) for n in ids],
                "old_weak_component_labels": [previous["weak"].get(n) for n in ids] if previous else None,
                "old_strong_component_labels": [previous["strong"].get(n) for n in ids] if previous else None}
            if any((json.loads(member[k]) if member[k] else None) != v for k, v in expected.items()):
                errors.append("INTERFACE_COMPONENT_LABEL:" + member["id"])
            checked_members += 1
        if previous and (row.get("parent_comparison_mode") != previous["mode"] or int(row["weak_component_count_change"]) != wc - previous["wc"] or int(row["strong_component_count_change"]) != sc - previous["sc"]):
            errors.append("PARENT_MODE_COMPONENT_DELTA")
        checks.append({"namespace": namespace, "mode": row["mode"], "prepared_graph_sha256": row["prepared_graph_sha256"],
            "measured": measured, "interface_membership_records_checked": checked_members, "errors": errors})
        previous = {"mode": row["mode"], "weak": weak, "strong": strong, "wc": wc, "sc": sc}
        print(json.dumps({"namespace": namespace, "mode": row["mode"], "counts": measured, "errors": len(errors)}), flush=True)
    result = {"reviewer": "/root/connectivity_review", "scope": "Independent union-find WCC and iterative Kosaraju SCC, all isolated IDs retained, source/local canonical topology SHA and actual overlay PREP/response chain bound; before query terminal binding",
        "APP_solver_calls": 0, "route_solver_calls": 0, "visibility_rebuilds": 0,
        "author_component_receipt_sha256": digest(author_receipt_path), "component_csv_sha256": digest(table), "membership_csv_sha256": digest(members_path),
        "rows": checks, "author_declared_full_attribute_identity_failures": author_receipt.get("identity_failures", []),
        "status": "PASS_FOR_REPORTED_BOUND_COMPONENT_COUNTS" if checks and all(not r["errors"] for r in checks) and not author_receipt.get("identity_failures") else "REQUIRES_INSPECTION",
        "limits": ["Topology-only snapshots cannot independently recreate full attributed graph SHA; author reconstruction requires that equality first and this audit verifies its original PREP and response bindings", "Directed model components do not establish physical passage, public access, continuous-domain components or registered-door eligibility", "No query endpoint binding or shortest-path invocation performed"]}
    write(ROOT / "audits/independent_component_review.json", result)
    print(result["status"], flush=True)


if __name__ == "__main__":
    main()
