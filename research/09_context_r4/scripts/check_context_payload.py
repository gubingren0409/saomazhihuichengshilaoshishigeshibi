"""Check plotted observed roads and G continuations against the recorded machine inputs."""
import argparse
import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re

from shapely.geometry import LineString, Point, shape

ROOT=Path(__file__).resolve().parents[1]
PATH_POINT=re.compile(r"[ML](-?[\d.]+(?:e[+-]?\d+)?),(-?[\d.]+(?:e[+-]?\d+)?)",re.I)


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def decoded(path):
    html=path.read_text(encoding="utf-8")
    match=re.search(r'<script type="text/plain" id="payload">([^<]+)</script>',html)
    if not match:
        raise ValueError("No embedded offline dataset")
    return json.loads(gzip.decompress(base64.b64decode(match[1])))


def plotted_points(feature, anchor):
    for piece in feature["shape"]:
        for x,y in PATH_POINT.findall(piece.get("d","")):
            yield Point(anchor[0]+float(x),anchor[1]-float(y))


def main(args):
    r=args.root
    manifest=load(args.manifest or r/"data/task_manifest.json")
    instances={x["id"]:x for x in manifest["instances"]}
    inv_path=(args.manifest.parent if args.manifest else r/"data")/"context_inventory.jsonl"
    inventory={x["id"]:x for x in map(json.loads,inv_path.read_text(encoding="utf-8-sig").splitlines())} if inv_path.is_file() else {}
    data=decoded(args.html)
    errors=[]
    worst=0.0
    counts={"cases":0,"observations":0,"observed_road_paths":0,"restored_paths":0,"reference_paths":0}
    for case in data["cases"].values():
        counts["cases"]+=1
        anchor=case["anchor"]
        first=None
        for entries in case["inputs"].values():
            for view in entries.values():
                ident=view["id"]
                info=instances.get(ident)
                if info:
                    path=r/info["observed"]
                    first=first or info
                elif ident.startswith("NORTH"):
                    path=next(p for p in (r/"data/e5/observed"/f"{ident}.json",r/"data/observed"/f"{ident}.json") if p.is_file())
                else:
                    errors.append(f"No frozen observation for displayed {ident}")
                    continue
                raw=load(path)
                if digest(path)!=view["observed_sha256"] or list(raw["domain"]["anchor_xy"])!=anchor:
                    errors.append(f"Observation hash or center mismatch {ident}")
                counts["observations"]+=1
                nodes={n["id"]:n["xy"] for n in raw["nodes"]}
                edges={e["id"]:e for e in raw["edges"]}
                for feature in view["visible"]:
                    if feature["layer"]=="reference" or feature["props"].get("observation")=="EVALUATION_ONLY":
                        errors.append(f"Reference in default observation layer {ident}")
                    if feature["layer"]!="way":
                        continue
                    eid=feature["props"]["id"]
                    if eid not in edges:
                        errors.append(f"Displayed road is not from {ident}: {eid}")
                        continue
                    edge=edges[eid]
                    original=LineString([nodes[edge["u"]],nodes[edge["v"]]])
                    diff=max((original.distance(p) for p in plotted_points(feature,anchor)),default=float("inf"))
                    worst=max(worst,diff)
                    counts["observed_road_paths"]+=1
                if ident in inventory:
                    originals={f["fragment_id"]:shape(f["geometry"]) for f in inventory[ident].get("restored_source_fragments",[])}
                    actual={f["props"].get("fragment_id"):f for f in view.get("restored",[])}
                    if set(actual)!=set(originals):
                        errors.append(f"Restored-fragment set mismatch {ident}")
                    for key,feature in actual.items():
                        if key not in originals:
                            continue
                        diff=max((originals[key].distance(p) for p in plotted_points(feature,anchor)),default=float("inf"))
                        worst=max(worst,diff)
                        counts["restored_paths"]+=1
        if case.get("reference") and first:
            ref_path=r/first["reference"]
            ref=shape(load(ref_path)["geometry"])
            carrier=ref.boundary if ref.area else ref
            diff=max((carrier.distance(p) for p in plotted_points(case["reference"],anchor)),default=float("inf"))
            worst=max(worst,diff)
            counts["reference_paths"]+=1
    if errors or worst>.00075:
        raise ValueError(f"Payload geometry validation failed, max {worst}: {errors[:20]}")
    value={"status":"PASS","scope":"VISUAL_AUTHOR_PROVENANCE_AND_COORDINATE_CHECK","page_sha256":digest(args.html),
           **counts,"max_plot_rounding_m":worst}
    if args.receipt:
        args.receipt.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(value,ensure_ascii=False))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--manifest",type=Path)
    p.add_argument("--html",type=Path)
    p.add_argument("--receipt",type=Path)
    args=p.parse_args()
    args.html=args.html or args.root/"visuals/index.html"
    main(args)
