import json,sys
from pathlib import Path
from shapely.geometry import shape,box,mapping
from shapely import make_valid,normalize,set_precision
from shapely.ops import unary_union
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.free_surface import partition_roads
ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads(p.read_text(encoding='utf8'))
out=[]
for ident in ['W0440b97497a_N_080','W87f642a7b21_N_080']:
    pred=load(ROOT/'data/predictions'/ident/'F0.json');contract=load(ROOT/'data/constraints'/f'{ident}.json')
    base=load(ROOT/'data/calibration'/f'{ident}.json')['M1'];native=unary_union([shape(c['geometry']) for c in base['cells'] if c['walkability_state']=='NATIVE_WALKABLE'])
    valid=make_valid(shape(contract['valid_geometry'])).intersection(shape(base['domain']))
    blocked=make_valid(shape(contract['blocked_geometry'])).intersection(valid)
    native=native.intersection(valid).difference(blocked)
    allowed=valid.difference(blocked).difference(native)
    rows=[c for c in pred['surface']['cells'] if c['walkability_state']=='INFERRED_WALKABLE']
    bad=[c for c in rows if shape(c['geometry']).difference(allowed).area>1e-8]
    cases=[]
    for c in bad:
        i,j=c['ij'];g=box(i,j,i+1,j+1).intersection(allowed)
        pieces=partition_roads(g,contract['road_centerlines'])
        first=unary_union(pieces)
        clipped=unary_union([p.intersection(g) for p in pieces])
        cases.append(dict(cell=c['region_id'],original_tile=mapping(g),source_allowed_valid=allowed.is_valid,tile_area=g.area,raw_mask_diff=allowed.symmetric_difference(shape(contract['valid_geometry']).difference(shape(contract['blocked_geometry'])).difference(native)).area,split_symdiff_m2=first.symmetric_difference(g).area,clipped_symdiff_m2=clipped.symmetric_difference(g).area,original_wrong_m2=shape(c['geometry']).difference(allowed).area,actual_final_clip=shape(c['geometry']).intersection(allowed).area,precision1e8=mapping(set_precision(g,1e-8))))
    out.append(dict(id=ident,cases=cases))
print(json.dumps(out,indent=2))
(ROOT/'audits/partition_reproduction.json').write_text(json.dumps(out,indent=2),encoding='utf8')
