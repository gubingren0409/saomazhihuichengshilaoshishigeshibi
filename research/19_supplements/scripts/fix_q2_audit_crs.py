from pathlib import Path
import json,hashlib,datetime,shutil,sys
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q2-LOCAL-ENTRY-AUDIT-R1';A=D/'attempts/A0_SUPPLEMENTARY_AUDIT_CRS_MISMATCH';A.mkdir(parents=True,exist_ok=True);changes=[]
for name in('complete_entry_context.py','recheck_entry_identity.py'):
 p=ROOT/'scripts'/name;before=p.read_bytes();backup=ROOT/'audit'/('EXECUTED_'+p.stem.upper()+'_A0.py')
 if not backup.exists():backup.write_bytes(before)
 s=before.decode('utf-8')
 if name=='complete_entry_context.py':
  s=s.replace("Point(source.coord(r['entrance_id']))","Point(source.projected[int(r['entrance_id'].split('/')[1])])")
  s=s.replace('Q2-SOURCE-CONTEXT-','Q2-SOURCE-CONTEXT-A1-').replace('entry_constraint_context.csv','entry_constraint_context_A1.csv').replace('outputs/entry_constraint_context.json','outputs/entry_constraint_context_A1.json')
 else:
  s=s.replace("Point(source.coord(old['entrance_id']))","Point(source.projected[nid])")
  s=s.replace('Q2-IDENTITY-RECHECK-','Q2-IDENTITY-RECHECK-A1-').replace('outputs/identity_recheck.json','outputs/identity_recheck_A1.json')
 p.write_text(s,encoding='utf-8');changes.append({'script':name,'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'original_source_copy':backup.relative_to(ROOT).as_posix()})
for rel in('entry_constraint_context.csv','outputs/entry_constraint_context.json','outputs/identity_recheck.json'):
 p=D/rel;target=A/p.name
 if not target.exists():shutil.copy2(p,target)
record={'timestamp':datetime.datetime.now().astimezone().isoformat(),'status':'RUNTIME_ERROR','reason':'New supplemental audit used Source.coord (WGS84 degrees) with Source.area/obstacles (EPSG32651 metres). Corrected to Source.projected, without changing old core or source.','affected_old_new_run_ids':['Q2-SOURCE-CONTEXT-node-6897141353','Q2-SOURCE-CONTEXT-node-6897145227','Q2-SOURCE-CONTEXT-node-11300000483','Q2-IDENTITY-RECHECK-node-6897141353','Q2-IDENTITY-RECHECK-node-6897145227','Q2-IDENTITY-RECHECK-node-11300000483'],'old_outputs_kept_unmodified':True,'corrected_outputs':'Q2/entry_constraint_context_A1.csv and outputs/identity_recheck_A1.json','main_9_target_route_runs_affected':False,'main_entry_identity_audit_affected':False,'historical_inputs_or_core_changed':False,'other_coord_callsite':'audit_sources.py compares Source.coord only to coordinates_wgs84; correct units, not changed','changes':changes}
(ROOT/'audit/Q2_SUPPLEMENTARY_CRS_CORRECTION.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
sys.path.insert(0,str(ROOT/'scripts'));from experiment_core import base_row,append
row=base_row(D.name,'Q2-SUPPLEMENTARY-AUDIT-CRS-A0-INVALIDATED','MULTI_FROZEN_SCENES','','AUDIT_HARNESS_CORRECTION','RUNTIME_ERROR');row.update(result=record,failure_reason=record['reason'],output_file='../../audit/Q2_SUPPLEMENTARY_CRS_CORRECTION.json');append(D.name,row);print(record)
