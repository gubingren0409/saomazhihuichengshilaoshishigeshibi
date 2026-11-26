"""Keep native walking topology distinct from background and physical restrictions."""
from dataclasses import dataclass
import json
from pathlib import Path

import networkx as nx
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from .native_adapter import Source, load_frozen_engine, node_number
from .route_measure import NATIVE, key, prepare_weights

PUBLIC = {"yes", "designated", "permissive", "official"}
DENIED = {"no", "private", "customers", "destination", "delivery", "permit",
          "agricultural", "forestry", "restricted"}
FALSE = {None, "", "0", "no", "false"}
WALKWAYS = {"footway", "pedestrian", "path", "steps"}
REJECT = "REJECT_CONFLICT"
UNRESOLVED = "UNRESOLVED"
KEEP = "KEEP_NATIVE"
EPS = 1e-6


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def permission(tags):
    """Apply pedestrian-specific fields before general access."""
    if any(k.endswith(":conditional") and k.split(":", 1)[0] in {"foot", "access", "oneway"}
           for k in tags):
        return UNRESOLVED, "CONDITIONAL_PEDESTRIAN_PERMISSION"
    if tags.get("locked") == "yes":
        return REJECT, "LOCKED_ACCESS"
    foot = tags.get("foot")
    if foot is not None:
        if foot not in PUBLIC:
            return (REJECT if foot in DENIED else UNRESOLVED), "FOOT_NOT_PERMITTED"
        if tags.get("access") in DENIED:
            return KEEP, "FOOT_SPECIFIC_ALLOW_OVERRIDES_GENERAL_ACCESS"
        return KEEP, None
    if tags.get("access") in DENIED:
        return REJECT, "GENERAL_ACCESS_RESTRICTED"
    return KEEP, None


def obstacle_kind(obj):
    """Only grass coverage is treated as the background conflict in this revision."""
    if obj["kind"] != "AREA":
        return obj["kind"]
    tags = obj.get("tags", {})
    if (tags.get("natural") in {"water", "wetland"} or tags.get("water")
            or tags.get("waterway") == "riverbank" or tags.get("landuse") in {"reservoir", "basin"}):
        return "WATER"
    if (tags.get("landuse") in {"flowerbed", "flower_bed"} or tags.get("leisure") == "flowerbed"
            or tags.get("landcover") == "flowerbed" or tags.get("garden:type") == "flower_bed"
            or tags.get("barrier") in {"flower_bed", "planter"}):
        return "FLOWERBED"
    decision, _ = permission(tags)
    if decision != KEEP:
        return "RESTRICTED_AREA" if decision == REJECT else "UNKNOWN"
    if tags.get("landuse") == "grass" or tags.get("landcover") == "grass":
        return "BACKGROUND_GRASS"
    return "AREA"


def explicit_walkway(tags):
    return tags.get("highway") in WALKWAYS or tags.get("foot") in PUBLIC


def numeric_level(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def structure_conflict(tags):
    bridge, tunnel = (tags.get(k) not in FALSE for k in ("bridge", "tunnel"))
    layer = numeric_level(tags.get("layer"))
    return (bridge and tunnel or layer is not None and (
        bridge and layer < 0 or tunnel and layer > 0))


def known_separation(tags, obstacle_tags):
    """Only explicit distinct layers plus a mapped structure justify crossing a barrier."""
    layer_a = numeric_level(tags.get("layer"))
    layer_b = numeric_level(obstacle_tags.get("layer"))
    return (layer_a is not None and layer_b is not None and layer_a != layer_b
            and any(tags.get(k) not in FALSE for k in ("bridge", "tunnel")))


def has_shared_gate(intersection, obstacle, native_nodes):
    if intersection.geom_type != "Point":
        return False
    for gate in obstacle.get("gates", ()):
        gate_id = gate.get("id", "")
        if gate_id.startswith("node/") and node_number(gate_id) in native_nodes and gate.get("allowed"):
            if intersection.distance(Point(gate["xy"])) <= EPS:
                return True
    return False


def level_conflict(tags, endpoints):
    levels = [t.get("level") for t in endpoints]
    explicit = [set(str(level).split(";")) for level in levels if level is not None]
    own = tags.get("level")
    if own is not None:
        explicit.append(set(str(own).split(";")))
    stairs_or_ramp = tags.get("highway") in {"steps", "elevator"} or tags.get("ramp") not in FALSE
    return len(explicit) >= 2 and not set.intersection(*explicit) and not stairs_or_ramp


def segment_decision(line, tags, obstacles, mode, *, native_nodes=(), endpoint_tags=()):
    """Evaluate whole geometry; exception scope stays on positively mapped native lines."""
    if mode not in {"S0", "S1"}:
        raise ValueError("Expected S0 or S1")
    state, access_reason = permission(tags)
    reasons = [access_reason] if access_reason else []
    contacts = []
    if structure_conflict(tags) or level_conflict(tags, endpoint_tags):
        state = REJECT
        reasons.append("EXPLICIT_LEVEL_CONFLICT")
    for endpoint in endpoint_tags:
        endpoint_state, endpoint_reason = permission(endpoint)
        if endpoint_state != KEEP:
            if state != REJECT:
                state = endpoint_state
            reasons.append(endpoint_reason)
    for obj in obstacles:
        geometry = obj["geometry"]
        overlap = line.intersection(geometry)
        if overlap.is_empty:
            continue
        kind = obstacle_kind(obj)
        if kind != "BARRIER" and not (geometry.geom_type in {"Polygon", "MultiPolygon"}
                                     and not line.relate_pattern(geometry, "F********")):
            continue
        if kind == "BACKGROUND_GRASS" and mode == "S1" and explicit_walkway(tags) and state == KEEP:
            reason = "MAPPED_PATH_OVER_LANDCOVER"
        elif kind == "WATER" and any(tags.get(k) not in FALSE for k in ("bridge", "tunnel")) and not structure_conflict(tags):
            reason = "MAPPED_BRIDGE_OR_TUNNEL_OVER_WATER"
        elif kind == "BARRIER" and has_shared_gate(overlap, obj, native_nodes):
            reason = "SHARED_MAPPED_GATE_ALLOWED"
        elif kind in {"BARRIER", "BUILDING"} and known_separation(tags, obj.get("tags", {})) and not structure_conflict(tags):
            reason = "EXPLICIT_STRUCTURE_LAYER_SEPARATION"
        else:
            reason = {
                "BACKGROUND_GRASS": "BACKGROUND_GRASS_OVERLAP" if mode == "S0" else "NO_MAPPED_WALKWAY_OVER_GRASS",
                "UNKNOWN": "UNRESOLVED_OBSTACLE_GEOMETRY",
            }.get(kind, "MAPPED_" + kind + "_CONFLICT")
            if state != REJECT:
                state = UNRESOLVED if kind == "UNKNOWN" else REJECT
        contacts.append({"source_id": obj["id"], "kind": kind, "overlap_m": overlap.length,
                         "decision_reason": reason})
        reasons.append(reason)
    return {"status": state, "reasons": sorted(set(reasons)), "contacts": contacts}


@dataclass
class NativeBuild:
    source: Source
    graph: nx.MultiDiGraph
    obstacles: list
    segments: list
    audit: list
    raw_stats: dict
    obstacle_index: STRtree


def build_native(frozen_root, scene, mode="S1"):
    frozen_root = Path(frozen_root)
    raw = read(frozen_root / scene["osm_clip"])
    source = Source(raw)
    engine = load_frozen_engine(frozen_root)
    segments, endings, raw_stats = engine._segments(raw)
    native, _ = engine._build_graph(segments, endings, ())
    prepare_weights(native)
    obstacles, unlocated = source.obstacles([])
    if unlocated:
        raw_stats["unlocated_obstacles"] = unlocated
    tree = STRtree([obj["geometry"] for obj in obstacles])
    decisions = {}
    for seg in segments:
        line = LineString((source.projected[seg.a[0]], source.projected[seg.b[0]]))
        tags = source.ways[seg.way].get("tags", {})
        endpoint_tags = tuple(source.nodes[n].get("tags", {}) for n in (seg.a[0], seg.b[0]))
        examined = [obstacles[i] for i in tree.query(line, predicate="intersects")]
        result = segment_decision(line, tags, examined, mode, native_nodes=(seg.a[0], seg.b[0]),
                                  endpoint_tags=endpoint_tags)
        decisions[seg.key] = dict(result, scene_id=scene["scene_id"], mode=mode,
                                  way_id=seg.way, segment_index=seg.index, native_nodes=[seg.a[0], seg.b[0]],
                                  coordinates_wgs84=[list(seg.p), list(seg.q)], length_m=line.length,
                                  directions=list(seg.directions), tags=tags, layer_key=seg.a[1],
                                  level_key=seg.a[2], native_evidence=seg.evidence)
    remove = []
    for u, v, eid, edge in native.edges(keys=True, data=True):
        if edge["osm_way_id"] is None:
            edge["semantic_status"] = KEEP
            edge["semantic_reasons"] = ["NATIVE_SHARED_WAY_ENDPOINT"]
            continue
        result = decisions[(edge["osm_way_id"], edge["segment_index"])]
        edge["semantic_status"] = result["status"]
        edge["semantic_reasons"] = result["reasons"]
        if result["status"] != KEEP:
            remove.append((u, v, eid))
    native.remove_edges_from(remove)
    # Drop orphan nodes, except endpoints that retain a genuine shared-node transition.
    native.remove_nodes_from(list(nx.isolates(native)))
    audit = [result for result in decisions.values() if result["contacts"] or result["reasons"]]
    raw_stats.update(retained_directed_edges=native.number_of_edges(), removed_directed_edges=len(remove),
                     retained_native_nodes=native.number_of_nodes(), scene_id=scene["scene_id"], semantic_mode=mode)
    return NativeBuild(source, native, obstacles, segments, audit, raw_stats, tree)


def load_area_graph(rev1_root, scene_id, area_ids=None):
    """Read the exact frozen face-derived graph without regenerating its parameters."""
    graph = nx.MultiDiGraph()
    found = False
    path = Path(rev1_root) / "data/edge_evidence.jsonl"
    with path.open(encoding="utf-8") as handle:
        for row_text in handle:
            row = json.loads(row_text)
            if row["scene_id"] != scene_id:
                if found:
                    break  # frozen evidence is emitted in scene blocks
                continue
            found = True
            area_id = row["source_area_id"]
            if area_ids is not None and area_id not in area_ids:
                continue
            nodes = (key(row["u"]), key(row["v"]))
            for n, xy, ll in zip(nodes, row["coordinates_metric"], row["coordinates_wgs84"]):
                graph.add_node(n, xy=tuple(xy), coord=tuple(ll))
            attrs = {"kind": row["kind"], "route_weight_m": row["length_m"],
                     "edge_id": row["edge_id"], "source_area_id": area_id,
                     "native_port_id": row.get("native_port_id"), "semantic_status": "KEEP_DERIVED"}
            graph.add_edge(*nodes, **attrs)
            if row["direction"] == "BIDIRECTIONAL":
                graph.add_edge(nodes[1], nodes[0], **attrs)
    return graph
