"""Explicitly synthetic S contrast. It carries no real benchmark observations."""
import argparse
from pathlib import Path

from shapely.geometry import box, mapping

from build_observed import ROOT, module, read, write, sign


def main(r3, output):
    m0 = module("context_r4_frozen_synthetic_m0",r3/"src/region.py")
    config_path = r3/"config/region.json"
    cfg = read(config_path)
    # The neutral shape and known obstacle are declared before evaluating.
    outline = box(-4,-4,4,4)
    hard = box(-1,-4,1,4)
    observed = {"task_id":"SYNTHETIC_NEUTRAL_GEOMETRY_CONTRACT","crs":"EPSG:32651",
                "domain":{"anchor_xy":[0,0],"anchor_role":"SYNTHETIC_FIXTURE"},
                "registered_entrance":None,"nodes":[],"edges":[],
                "context":{"hard":[{"id":"fixture/barrier","kind":"BUILDING","geometry":mapping(hard),
                                    "tags":{"building":"yes"}}],"background":[],
                           "support":[{"id":"fixture/shape","kind":"NEUTRAL_OUTLINE","geometry":mapping(outline),
                                       "tags":{"area":"yes"}}]}}
    result = m0.build_surface(observed,cfg)
    # The scoring reference is separate from the observation; synthetic by construction.
    reference = outline.difference(hard)
    assert result.masks[m0.NATIVE].area == 0
    assert result.masks[m0.UNKNOWN].covers(reference.representative_point())
    assert abs(result.masks[m0.RESTRICTED].intersection(hard).area-hard.area) < 1e-8
    write(output,{"status":"SYNTHETIC_MECHANISM_ONLY","in_real_denominator":False,
                  "observed":observed,"synthetic_reference":{"geometry":mapping(reference),"area_m2":reference.area},
                  "m0_source_sha256":sign(r3/"src/region.py"),"m0_config_sha256":sign(config_path),
                  "comparisons":[
                    {"method":"FROZEN_M0","native_area_m2":result.masks[m0.NATIVE].area,
                     "reference_covered_m2":result.masks[m0.INFERRED].intersection(reference).area,
                     "hard_overlap_m2":result.masks[m0.INFERRED].intersection(hard).area},
                    {"method":"FILL_ENTIRE_NEUTRAL_SHAPE_DIAGNOSTIC","native_area_m2":None,
                     "reference_covered_m2":outline.intersection(reference).area,
                     "hard_overlap_m2":outline.intersection(hard).area}],
                  "interpretation":"The visible neutral shape is a specified synthetic input; full-shape coverage is by construction and crosses a known restriction. It is not evidence of real-area reconstruction or a routing method."})
    print("Synthetic S contract: frozen M0 NATIVE=0; full neutral fill overlaps 16m² known hazard.")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--r3",type=Path,default=ROOT/"frozen_r3")
    p.add_argument("--output",type=Path,default=ROOT/"audits/semantic_contract_fixture.json")
    a=p.parse_args()
    main(a.r3,a.output)
