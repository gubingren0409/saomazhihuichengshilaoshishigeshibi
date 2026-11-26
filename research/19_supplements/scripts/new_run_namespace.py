"""Copy inputs/code to a new empty namespace, never copy old measured result rows."""
from pathlib import Path
import argparse,shutil,json,datetime,platform,uuid,sys
ROOT=Path(__file__).resolve().parents[1];ap=argparse.ArgumentParser();ap.add_argument('--destination',required=True);args=ap.parse_args();dest=Path(args.destination).resolve()
if dest.exists():raise SystemExit('DESTINATION_EXISTS: choose a new empty directory; no deletion is performed')
dest.mkdir(parents=True);shutil.copytree(ROOT/'scripts',dest/'scripts')
manifest=json.loads((ROOT/'audit/FROZEN_RUNTIME_MANIFEST.json').read_text(encoding='utf-8'))
for member in manifest['members']:
 target=dest/'frozen_runtime'/member['member'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/'frozen_runtime'/member['member'],target)
for p in(ROOT/'medium_runtime').rglob('*'):
 if not p.is_file()or'runs'in p.relative_to(ROOT/'medium_runtime').parts or'derived_graphs'in p.parts or'__pycache__'in p.parts:continue
 target=dest/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
(dest/'audit').mkdir();(dest/'figures').mkdir()
for name in('FROZEN_RUNTIME_MANIFEST.json','PRIMARY_PROTOCOL_AMENDMENT.json','USER_EXPERIMENT_PROTOCOL.md'):
 shutil.copy2(ROOT/'audit'/name,dest/'audit'/name)
env={'timestamp':datetime.datetime.now().astimezone().isoformat(),'python':sys.version,'platform':platform.platform(),'source':'Reproduction machine, not claimed identical to original benchmark hardware','reproduction_of_root':str(ROOT),'namespace_id':uuid.uuid4().hex,'network_calls':0,'API_calls':0,'route_answer_cache':False}
(dest/'audit/environment.json').write_text(json.dumps(env,ensure_ascii=False,indent=2),encoding='utf-8')
for p in ROOT.glob('Q*'):
 if not p.is_dir():continue
 q=dest/p.name;q.mkdir()
 for name in('logs','figures','outputs'):(q/name).mkdir()
 if(p/'protocol.json').exists():
  protocol=json.loads((p/'protocol.json').read_text(encoding='utf-8'));protocol.update(reproduction_inherited_protocol=True,reproduction_started_at=env['timestamp']);(q/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
 (q/'environment.json').write_text(json.dumps(env,ensure_ascii=False,indent=2),encoding='utf-8');(q/'raw_results.jsonl').write_text('',encoding='utf-8')
(dest/'STATUS.json').write_text(json.dumps({'status':'INCONCLUSIVE','started_at':env['timestamp'],'namespace_id':env['namespace_id'],'note':'New reproduction namespace; historical external archive dependencies still required for source audit.'},ensure_ascii=False,indent=2),encoding='utf-8')
print(dest)
