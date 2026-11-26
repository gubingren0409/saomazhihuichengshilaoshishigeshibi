"""Inventory legally independent neutral geometry in the frozen source."""
import argparse
from pathlib import Path

from shapely.geometry import LineString, shape

from build_observed import ROOT, SHADOW, module, read, write, sign

WALK = {"footway", "path", "pedestrian", "steps", "corridor", "living_street", "bridleway"}


def neutral(tags):
    return (tags.get("highway") not in WALK and "foot" not in tags and "footway" not in tags
            and not any(k.startswith(("foot:", "sidewalk:")) for k in tags)
            and tags.get("area:highway") not in WALK
            and tags.get("barrier") is None and tags.get("entrance") is None)


def dependent_members(src, hidden):
    ids = set(hidden)
    repeat = True
    while repeat:
        repeat = False
        for number, obj in src.relations.items():
            ident = f"relation/{number}"
            members = {f"{m['type']}/{m['ref']}" for m in obj["members"]}
            if ident in ids:
                new = members - ids
            elif members & ids:
                new = {ident}
            else:
                new = set()
            ids.update(new)
            repeat |= bool(new)
    return ids


def matching(ref, src):
    area = ref["kind"].startswith("AREA_")
    target = src.area(ref["source_ids"][0]) if area else shape(ref["geometry"])
    hidden = dependent_members(src, set(ref["source_id_hidden"]) | set(ref["source_ids"]))
    window = target.buffer(SHADOW, cap_style="flat")
    points = src.projected
    minx,miny,maxx,maxy = window.bounds
    rows = []
    for kind, objects in (("way",src.ways),("relation",src.relations)):
        if kind=="relation" and not area:
            continue
        for number, obj in objects.items():
            ident = f"{kind}/{number}"
            tags = obj.get("tags", {})
            if ident in hidden or not neutral(tags):
                continue
            if kind=="way" and area and (len(obj["nodes"])<4 or obj["nodes"][0]!=obj["nodes"][-1]):
                continue
            if kind=="relation" and tags.get("type")!="multipolygon":
                continue
            coords = src.known_coords(obj)
            if len(coords)<2:
                continue
            xs,ys=zip(*coords)
            if max(xs)<minx or min(xs)>maxx or max(ys)<miny or min(ys)>maxy:
                continue
            if area:
                geometry=src.area(ident)
                if geometry is None:
                    continue
                overlap=target.intersection(geometry).area
                a,b=overlap/target.area,overlap/geometry.area
            else:
                geometry=LineString(coords)
                if geometry.length<1e-6 or not geometry.intersects(window):
                    continue
                a=target.intersection(geometry.buffer(SHADOW,cap_style="flat")).length/target.length
                b=geometry.intersection(window).length/geometry.length
            if a>=.25 and b>=.25:
                rows.append({"id":ident,"target_covered":a,"candidate_covered":b,"tags":tags,
                             "independently_coincident":a>=.98 and b>=.98})
    rows.sort(key=lambda r:(-min(r["target_covered"],r["candidate_covered"]),r["id"]))
    return {"parent_task_id":ref["task_id"],"kind":ref["kind"],"source_clip_sha256":ref["source_clip_sha256"],
            "eligible_independent_neutral_geometry":any(r["independently_coincident"] for r in rows),
            "candidate_shapes":rows}


def main(r3,out):
    rev1=r3/"inputs/rev1"
    adapter=module("context_r4_neutral_adapter",rev1/"src/native_adapter.py")
    raw=rev1/"frozen_r4/data/source"
    src=None
    active=None
    refs=sorted((read(p) for p in (r3/"data/benchmark/reference").glob("*.json")),key=lambda r:r["source_clip"])
    rows=[]
    for ref in refs:
        if ref["label"]!="POSITIVE":
            continue
        if ref["source_clip"]!=active:
            p=raw/ref["source_clip"]
            assert sign(p)==ref["source_clip_sha256"]
            src=adapter.Source(read(p))
            active=ref["source_clip"]
        rows.append(matching(ref,src))
    write(out,{"status":"OBSERVED_SOURCE_INVENTORY","positive_parent_count":len(rows),
               "eligible_count":sum(row["eligible_independent_neutral_geometry"] for row in rows),
               "criterion":"source provenance disjoint from withheld relation closure and >=98% two-way overlap; no walking tags",
               "rows":rows})
    print("Neutral independent candidates",sum(row["eligible_independent_neutral_geometry"] for row in rows),"/",len(rows))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--r3",type=Path,default=ROOT/"frozen_r3")
    p.add_argument("--output",type=Path,default=ROOT/"audits/neutral_geometry_inventory.json")
    a=p.parse_args()
    main(a.r3,a.output)
