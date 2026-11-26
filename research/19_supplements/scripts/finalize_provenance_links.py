from pathlib import Path
import json,hashlib,datetime
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q2-LOCAL-ENTRY-AUDIT-R1';p=D/'raw_results.jsonl';before=p.read_bytes();rows=[json.loads(z)for z in before.decode('utf-8').splitlines()if z.strip()];changed=[]
for r in rows:
 if r['run_id']=='Q2-SUPPLEMENTARY-AUDIT-CRS-A0-INVALIDATED'and r['output_file']=='../../audit/Q2_SUPPLEMENTARY_CRS_CORRECTION.json':
  changed.append({'run_id':r['run_id'],'before':r['output_file'],'after':'audit/Q2_SUPPLEMENTARY_CRS_CORRECTION.json','base':'ROOT'});r['output_file']='audit/Q2_SUPPLEMENTARY_CRS_CORRECTION.json'
if changed:
 backup=D/'attempts/A0_SUPPLEMENTARY_AUDIT_CRS_MISMATCH/raw_before_pointer_metadata_fix.jsonl';backup.write_bytes(before);tmp=p.with_suffix('.fixing');tmp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in rows),encoding='utf-8');tmp.replace(p)
 record={'timestamp':datetime.datetime.now().astimezone().isoformat(),'status':'PASS','changes':changed,'scientific_values_changed':False,'old_raw_bytes_retained':backup.relative_to(ROOT).as_posix(),'raw_sha256_before':hashlib.sha256(before).hexdigest(),'raw_sha256_after':hashlib.sha256(p.read_bytes()).hexdigest()};(ROOT/'audit/OUTPUT_POINTER_METADATA_FIX.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
correction=json.loads((ROOT/'audit/Q2_SUPPLEMENTARY_CRS_CORRECTION.json').read_text(encoding='utf-8'));mapping=[]
for old in correction['affected_old_new_run_ids']:
 replacement=old.replace('Q2-SOURCE-CONTEXT-','Q2-SOURCE-CONTEXT-A1-').replace('Q2-IDENTITY-RECHECK-','Q2-IDENTITY-RECHECK-A1-');r=next(r for r in rows if r['run_id']==old)
 mapping.append({'original_run_id':old,'original_status_kept':r['status'],'validity':'INVALIDATED_NEW_AUDIT_CRS_ERROR_NOT_MAP_FACT','replacement_run_id':replacement,'correction_record':'audit/Q2_SUPPLEMENTARY_CRS_CORRECTION.json','original_output':r['output_file']})
(ROOT/'audit/Q2_SUPERSESSION_MAP.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding='utf-8');print('METADATA_POINTER_AND_SUPERSESSION_RECORDED',len(mapping))
