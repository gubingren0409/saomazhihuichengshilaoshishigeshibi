"""Search frozen OSM for lawful independent neutral geometry for semantic-only controls."""
import argparse
from collections import defaultdict
from pathlib import Path
import sys

from shapely.geometry import box, shape

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.context_audit_common import ROOT, RawClip, read, write

SEMANTIC_KEYS = {"highway","foot","access","public_transport","footway","barrier","building","building:part",
                 "natural","water","waterway","entrance","indoor","layer","level","amenity","tourism","leisure"}


def named_or_classified(tags):
    return sorted(key for key in tags if key in SEMANTIC_KEYS or key.startswith(("name","foot:","access:")))


def memberships(raw):
    direct, reverse = defaultdict(set), defaultdict(set)
    for ident,row in raw.objects.items():
        if row["type"]!="relation":
            continue
        for member in row.get("members",[]):
            child=f"{member['type']}/{member['ref']}"
            direct[ident].add(child)
            reverse[child].add(ident)
    return direct,reverse


def raw_polygon_candidates(raw, extent):
    for ident,obj in raw.objects.items():
        if obj["type"]=="way":
            nodes=obj.get("nodes",[])
            if len(nodes)<4 or nodes[0]!=nodes[-1]:
                continue
        elif obj["type"]=="relation" and obj.get("tags",{}).get("type") in {"multipolygon","boundary"}:
            nodes=[n for member in obj.get("members",[]) if member["type"]=="way"
                   for n in raw.objects.get(f"way/{member['ref']}",{}).get("nodes",[])]
        else:
            continue
        points=[raw.xy[n] for n in nodes if n in raw.xy]
        if not points:
            continue
        xs,ys=zip(*points)
        if not extent.intersects(box(min(xs),min(ys),max(xs),max(ys))):
            continue
        try:
            geometry=raw.area(ident)
        except (ValueError,KeyError):
            continue
        if geometry is not None:
            yield ident,obj,geometry


def raw_line_candidates(raw, extent):
    for ident,row in raw.objects.items():
        if row["type"]!="way":
            continue
        coords=[raw.xy[n] for n in row.get("nodes",[]) if n in raw.xy]
        if len(coords)<2:
            continue
        xs,ys=zip(*coords)
        x0,y0,x1,y1=extent.bounds
        if not (min(xs)<=x1 and max(xs)>=x0 and min(ys)<=y1 and max(ys)>=y0):
            continue
        try:
            geometry=raw.line(ident)
        except (KeyError,ValueError):
            continue
        if geometry.length>0:
            yield ident,row,geometry


def review(ref,raw):
    original=set(ref["source_ids"])
    direct,reverse=memberships(raw)
    linked=original|{v for ident in original for v in direct[ident]|reverse[ident]}
    bounds=shape(ref["domain_geometry"])
    area_case=ref["kind"].startswith("AREA_")
    if area_case:
        target=raw.area(ref["source_ids"][0])
        choices=raw_polygon_candidates(raw,target.envelope)
        amount=target.area
    else:
        target=shape(ref["geometry"])
        choices=raw_line_candidates(raw,target.buffer(.05).envelope)
        amount=target.length
    rows=[]
    for ident,obj,g in choices:
        if ident in original:
            continue
        if area_case:
            intersection=target.intersection(g).area
            if intersection<.1*amount:
                continue
            a,b=intersection/amount,intersection/g.area
        else:
            a=target.intersection(g.buffer(.05)).length/amount
            if a<.1:
                continue
            b=g.intersection(target.buffer(.05)).length/g.length
        direct_dependency=ident in linked or bool(direct[ident]&linked)
        fields=named_or_classified(obj.get("tags",{}))
        relation_fields=sorted({key for p in reverse[ident] for key in named_or_classified(raw.objects[p].get("tags",{}))})
        same=a>=.99 and b>=.99
        rows.append(dict(source_id=ident,target_coverage=a,geometry_fraction_in_target=b,
                         equivalent_footprint_or_trace=same,dependent_on_source_target=direct_dependency,
                         identity_fields=fields,related_identity_fields=relation_fields,
                         eligible_independent_neutral=same and not (direct_dependency or fields or relation_fields),
                         tags=obj.get("tags",{})))
    return {"parent_task_id":ref["task_id"],"reference_kind":ref["kind"],"target_ids":sorted(original),
            "evaluation_window_area_m2":bounds.area,"near_overlap_candidates":len(rows),
            "near_exact_candidates":[r for r in rows if r["equivalent_footprint_or_trace"]],
            "best_overlap_examples":sorted(rows,key=lambda a:(-a["target_coverage"],-a["geometry_fraction_in_target"],
                                                              a["source_id"]))[:5],
            "eligible_count":sum(r["eligible_independent_neutral"] for r in rows)}


def main(args):
    root=args.root.resolve()
    source=root/"frozen_r3/inputs/rev1/frozen_r4/data/source"
    clips={}
    reports=[]
    for path in sorted((root/"data/reference").glob("*.json")):
        ref=read(path)
        if ref["label"]!="POSITIVE":
            continue
        name=ref["source_clip"]
        if name not in clips:
            clips[name]=RawClip(source/name)
        reports.append(review(ref,clips[name]))
    total=sum(r["eligible_count"] for r in reports)
    write(args.out or root/"audits/neutral_shape_audit.json",{
        "status":"INDEPENDENT_NATIVE_NEUTRAL_GEOMETRY_SCAN","scope":"EXISTING_FROZEN_OBJECTS_ONLY",
        "same_geometry_min_mutual_coverage":.99,"line_alias_buffer_m":.05,
        "native_polygon_cases":sum(r["reference_kind"].startswith("AREA_") for r in reports),
        "native_line_cases":sum(r["reference_kind"].startswith("LINE_") for r in reports),
        "eligible_neutral_geometry":total,"cases":reports,
        "interpretation":"Synthetic neutral diagnostics are separate. This check requires an existing independent shape, not a polygon manufactured from the withheld reference."})
    print(f"Native neutral-shape candidates: {total} across {len(reports)} frozen positives",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--out",type=Path)
    main(parser.parse_args())
