"""Copy only explicitly selected new source bytes; no data or old code enters repo."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT/'repository'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
manifest=json.loads((ROOT/'phase1/public_source_candidates.json').read_text(encoding='utf-8'))
for row in manifest['files']:
 rel=row['path'].replace(chr(92),'/');p=ROOT/rel;assert sha(p)==row['sha256'];target=REPO/'tools'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes());rows.append({'source':rel,'public_path':target.relative_to(REPO).as_posix(),'sha256':sha(target),'reason':'new generic source/template; no raw data copied'})
for name in['build_atlas.py','spatial_groups.py','summarize_audit.py','verify_atlas.py','fetch_bounded.py']:
 p=ROOT/'phase2/src'/name;target=REPO/'tools/phase2/src'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes());rows.append({'source':p.relative_to(ROOT).as_posix(),'public_path':target.relative_to(REPO).as_posix(),'sha256':sha(target),'reason':'new generic CLI; private scene acquisition configuration excluded'})
(ROOT/'audit/public_source_integration.json').write_text(json.dumps({'source_mirrors_byte_identical':True,'rows':rows,'data_copied':0,'legacy_planner_copied':0},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'integrated_files':len(rows),'data_files':0}))
