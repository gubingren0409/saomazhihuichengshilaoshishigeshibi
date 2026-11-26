"""Recheck the component gap in the frozen New World City local route."""
import json
from pathlib import Path

import networkx as nx

from .frozen_r1.local_route import _build_graph, _segments, _snap, _snap_metadata


def check(root):
    scene_id = "sh-newworld"
    contract = json.loads((root / "runs/scene_contracts.json").read_text(encoding="utf-8"))
    scene = next(row for row in contract["scenes"] if row["scene_id"] == scene_id)
    data = json.loads((root / scene["osm_clip"]).read_text(encoding="utf-8"))
    segments, endings, _ = _segments(data)
    start = _snap(scene["start"], segments)
    target = _snap(scene["target"], segments)
    graph, (a, b) = _build_graph(segments, endings, (start, target))
    weak_graph = graph.to_undirected(as_view=True)
    ways = {row["id"]: row["tags"] for row in data["elements"] if row["type"] == "way"}

    return {
        "scene_id": scene_id,
        "scope": "AUTHOR_RECHECK_OF_FROZEN_LOCAL_PROFILE",
        "start_snap": _snap_metadata(start),
        "target_snap": _snap_metadata(target),
        "forward_path": nx.has_path(graph, a, b),
        "reverse_path": nx.has_path(graph, b, a),
        "undirected_path": nx.has_path(weak_graph, a, b),
        "start_weak_component_nodes": len(nx.node_connected_component(weak_graph, a)),
        "target_weak_component_nodes": len(nx.node_connected_component(weak_graph, b)),
        "start_snap_way_tags": ways[start[0].way],
        "target_snap_way_tags": ways[target[0].way],
        "interpretation": "Component gap under this snapshot, clip and profile. Physical accessibility and missing-edge causes remain unverified.",
    }


if __name__ == "__main__":
    print(json.dumps(check(Path(__file__).resolve().parents[1]), indent=2, ensure_ascii=False))
