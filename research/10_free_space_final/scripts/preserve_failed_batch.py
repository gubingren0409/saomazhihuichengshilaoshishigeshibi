"""Move only our stopped, derived outputs into a versioned failure record."""
import json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
dst=ROOT/'runs/superseded'/(sys.argv[1] if len(sys.argv)>1 else 'R1_partition_defect')
assert not dst.exists()
dst.mkdir(parents=True)
for p in sorted((ROOT/'runs/executions').glob('*.json')):
    ident=p.stem
    for rel in [f'data/predictions/{ident}',f'data/graphs/{ident}',f'data/calibration/{ident}.json',f'data/constraints/{ident}.json',f'runs/executions/{ident}.json']:
        src=ROOT/rel;target=dst/rel
        assert src.resolve().is_relative_to(ROOT) and target.resolve().is_relative_to(ROOT)
        if src.exists():target.parent.mkdir(parents=True,exist_ok=True);src.rename(target)
for p in (ROOT/'runtime/workers').iterdir():
    target=dst/'interrupted_workers'/p.name
    assert p.resolve().is_relative_to(ROOT) and target.resolve().is_relative_to(ROOT)
    target.parent.mkdir(exist_ok=True);p.rename(target)
    # Upper-bound all four in-memory regions for an interrupted worker.
    receipt=dst/'runs/executions'/f'{p.name}_INTERRUPTED.json';receipt.parent.mkdir(parents=True,exist_ok=True)
    receipt.write_text(json.dumps({'input_id':p.name,'region_builds':4,'wall_s':0,'status':'INTERRUPTED_UPPER_BOUND','elapsed_wall_not_recoverable':'Counted conservatively in total wall from start'}),encoding='utf8')
for name in ['free_surface.py','free_routing.py','predict_free.py']:
    target=dst/'code'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(ROOT/'src'/name,target)
print('Preserved',dst)
