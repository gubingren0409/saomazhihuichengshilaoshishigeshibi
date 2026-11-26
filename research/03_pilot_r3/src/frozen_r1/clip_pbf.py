"""Convert a bounded Geofabrik extract to ODbL native-ID JSON for the pilot."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://download.geofabrik.de/asia/china/shanghai-261108.osm.pbf"
FIELDS = {"building", "highway", "landuse", "leisure", "natural", "waterway",
          "amenity", "tourism", "barrier", "railway", "public_transport", "entrance", "area:highway"}


def extract(pbf, bounds):
    import osmium
    w, s, e, n = bounds
    ways, local_nodes, relations = {}, {}, {}
    with osmium.io.Reader(str(pbf)) as reader:
        header = reader.header()
        timestamp = header.get("osmosis_replication_timestamp")
        sequence = header.get("osmosis_replication_sequence_number")
    for obj in osmium.FileProcessor(str(pbf)).with_locations():
        if obj.is_node():
            point = obj.lon, obj.lat
            if w <= point[0] <= e and s <= point[1] <= n:
                local_nodes[obj.id] = {"type": "node", "id": obj.id, "lon": point[0], "lat": point[1],
                                       "tags": dict(obj.tags), "version": obj.version}
        elif obj.is_way():
            tags = dict(obj.tags)
            if tags and not FIELDS.intersection(tags):
                continue
            coords = [(ref.ref, ref.lon, ref.lat) for ref in obj.nodes if ref.location.valid()]
            if len(coords) != len(obj.nodes) or len(coords) < 2:
                continue
            xs, ys = [c[1] for c in coords], [c[2] for c in coords]
            if max(xs) < w or min(xs) > e or max(ys) < s or min(ys) > n:
                continue
            ways[obj.id] = {"type": "way", "id": obj.id, "nodes": [c[0] for c in coords],
                            "tags": tags, "version": obj.version, "_coords": coords}
        elif obj.is_relation() and obj.tags.get("type") == "multipolygon":
            tags = dict(obj.tags)
            if FIELDS.intersection(tags):
                members = [{"type": "way", "ref": member.ref, "role": member.role}
                           for member in obj.members if member.type == "w"]
                if any(member["ref"] in ways for member in members):
                    relations[obj.id] = {"type": "relation", "id": obj.id, "members": members,
                                         "tags": tags, "version": obj.version}
    missing = {m["ref"] for r in relations.values() for m in r["members"]} - ways.keys()
    if missing:
        for obj in osmium.FileProcessor(str(pbf)).with_locations():
            if not obj.is_way() or obj.id not in missing:
                continue
            coords = [(ref.ref, ref.lon, ref.lat) for ref in obj.nodes if ref.location.valid()]
            if len(coords) == len(obj.nodes) and len(coords) >= 2:
                ways[obj.id] = {"type": "way", "id": obj.id, "nodes": [c[0] for c in coords],
                                "tags": dict(obj.tags), "version": obj.version, "_coords": coords}
    needed_nodes = {}
    relation_members = {m["ref"] for r in relations.values() for m in r["members"]}
    for way_id in sorted(ways):
        way = ways[way_id]
        if not way["tags"] and way_id not in relation_members:
            continue
        for ref, lon, lat in way.pop("_coords"):
            needed_nodes.setdefault(ref, local_nodes.get(ref) or
                                    {"type": "node", "id": ref, "lon": lon, "lat": lat})
    for key, node in local_nodes.items():
        if node["tags"] and (FIELDS.intersection(node["tags"]) or "name" in node["tags"]):
            needed_nodes.setdefault(key, node)
    good_ways = [ways[i] for i in sorted(ways) if "_coords" not in ways[i]]
    return {
        "generator": "Geofabrik PBF + pyosmium 4.3.2 pilot clip",
        "osm3s": {"timestamp_osm_base": timestamp, "replication_sequence_number": sequence},
        "bounds_wsen": bounds, "source": SOURCE, "license": "ODbL-1.0",
        "elements": [needed_nodes[i] for i in sorted(needed_nodes)] + good_ways +
                    [relations[i] for i in sorted(relations)],
        "missing_relation_way_count": len(missing - ways.keys()),
    }


def main(root=ROOT):
    plan = json.loads((root / "runs/pilot_plan.json").read_text(encoding="utf-8"))
    pbf = root / "runtime/shanghai-261108.osm.pbf"
    bounds = plan["scene"]["snapshot_query_bbox_wsen"]
    if pbf.stat().st_size != 26079230:
        raise ValueError("GEOFABRIK_TRANSFER_LENGTH_MISMATCH")
    payload = extract(pbf, bounds)
    if not payload["elements"]:
        raise ValueError("EMPTY_OSM_CLIP")
    path = root / "data/sh-huangpu-01.osm.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
    with pbf.open("rb") as stream:
        pbf_hash = __import__("hashlib").file_digest(stream, "sha256").hexdigest()
    receipt = {"status": "LIVE_SNAPSHOT_OFFLINE_CLIP", "source": SOURCE,
               "source_bytes": pbf.stat().st_size, "source_sha256": pbf_hash,
               "bounds_wsen": bounds, "license": "ODbL-1.0",
               "snapshot_timestamp": payload["osm3s"]["timestamp_osm_base"],
               "clip_utc": datetime.now(timezone.utc).isoformat(),
               "clip_bytes": path.stat().st_size, "clip_sha256": sha256(path.read_bytes()).hexdigest(),
               "element_count": len(payload["elements"]),
               "missing_relation_way_count": payload["missing_relation_way_count"],
               "first_transfer": {"http_status": 200, "bytes": 17038870, "status": "TIMEOUT"},
               "resume_transfer": {"http_status": 206, "bytes": 9040360, "status": "COMPLETE"}}
    (root / "runs/geofabrik_acquisition.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=True))


if __name__ == "__main__":
    main()
