from pathlib import Path
import csv,json,zipfile,hashlib,datetime,shutil,collections
from shapely.geometry import LineString
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q6-LOCAL-MAP-CONSISTENCY-R1';backup=D/'attempts/A2_AGGREGATE_SCHEMA_FALSE_FLAGS';backup.mkdir(parents=True,exist_ok=False)
for n in ['replay_comparison.csv','route_constraint_audit.csv','summary.json','outputs/route_constraint_details.json']:
 p=D/n;q=backup/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
def rows(name):return list(csv.DictReader((D/name).open(encoding='utf-8-sig')))
def csvout(name,data):
 fields=list(dict.fromkeys(k for row in data for k in row))
 with(D/name).open('w',encoding='utf-8-sig',newline='')as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
replay=rows('replay_comparison.csv');constraints=rows('route_constraint_audit.csv');details=json.loads((D/'outputs/route_constraint_details.json').read_text(encoding='utf-8'));byid={r['run_id']:r for r in details};checks=[]
zp=ROOT.parent/'PED_AREA_CONNECTIVITY_R2_ROUTE_DIAGNOSIS/delivery/OPEN_REVIEW.zip';assert hashlib.sha256(zp.read_bytes()).hexdigest()=='3988e9fba95da70dc03b8191a177740a3ccd13602019afe3765e566648b55711'
with zipfile.ZipFile(zp)as z:
 for row in replay:
  if row['stage']!='PED-AREA-CONNECTIVITY-R2':continue
  b=z.read(row['source_file']);doc=json.loads(b);segments=doc['minimum']['segments'];assert all('hypothesis_m'in s for s in segments)
  measured=sum(LineString(s['xy']).length for s in segments);assumed=sum(s['hypothesis_m']for s in segments);detail=byid[row['run_id']]
  assert abs(measured-float(row['recomputed_length_m']))<=1e-6 and abs(assumed-doc['minimum']['hypothesis_m'])<=1e-6
  assert not detail['raw_source_2D_conflicts']
  previous=row['status'];row.update(status='INCONCLUSIVE',native_m='',derived_m='',assumption_m=assumed,source_composition_status='AGGREGATED_NATIVE_DERIVED_UNSPLIT',audit_revision_run_id='Q6-AUDITOR-A3-AGGREGATE-SCHEMA-RECHECK')
  detail.update(status='INCONCLUSIVE',assumption_label_missing=0,explicit_assumption_length_m=assumed,source_composition_status='AGGREGATED_NATIVE_DERIVED_UNSPLIT',reason='Explicit hypothesis_m exists; native/derived constituent records are not exported in this aggregated minimum; not an undeclared assumption')
  checks.append({'source_file':row['source_file'],'source_sha256':hashlib.sha256(b).hexdigest(),'before_status':previous,'after_status':row['status'],'recomputed_length_m':measured,'declared_assumption_m':assumed,'historical_file_modified':False})
for row in constraints:
 if row['stage']=='PED-AREA-CONNECTIVITY-R2':
  detail=byid[row['run_id']];row.update(status='INCONCLUSIVE',assumption_label_missing=0,source_composition_status='AGGREGATED_NATIVE_DERIVED_UNSPLIT',explicit_assumption_length_m=detail['explicit_assumption_length_m'])
csvout('replay_comparison.csv',replay);csvout('route_constraint_audit.csv',constraints)
(D/'outputs/route_constraint_details.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf-8')
summary=json.loads((D/'summary.json').read_text(encoding='utf-8'));summary.update(route_audit_status_counts=dict(collections.Counter(r['status']for r in replay)),latest_schema_revision='Q6-AUDITOR-A3-AGGREGATE-SCHEMA-RECHECK',original_8_FAIL_flags='Superseded new-auditor schema false positives, not old algorithm violations; old table retained in attempts/A2_AGGREGATE_SCHEMA_FALSE_FLAGS',aggregate_native_derived_breakdown='NOT_EXPORTED_NOT_GUESSED')
(D/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');(D/'logs/aggregate_schema_recheck.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
raw={'experiment_id':D.name,'run_id':'Q6-AUDITOR-A3-AGGREGATE-SCHEMA-RECHECK','scene_id':'sh-huangpu-01_and_sh-library','building_id':'MULTIPLE','entrance_id':'REGISTERED_DOORS_AND_EXIT','method':'SAVED_SCHEMA_AND_LENGTH_RECHECK','input_version':'3988e9fba95da70dc03b8191a177740a3ccd13602019afe3765e566648b55711','status':'INCONCLUSIVE','result':{'rows':checks,'native_derived_split':'NOT_EXPORTED'},'failure_reason':'No missing assumption declaration; aggregated native/derived split remains unknown','route_length_m':None,'assumption_length_m':None,'runtime_ms':None,'source_edge_count':None,'derived_edge_count':None,'assumption_edge_count':None,'output_file':'logs/aggregate_schema_recheck.json'}
with(D/'raw_results.jsonl').open('a',encoding='utf-8')as f:f.write(json.dumps(raw,ensure_ascii=False)+'\n')
print(json.dumps({'rows_rechecked':len(checks),'current_status_counts':summary['route_audit_status_counts'],'historical_input_drift':0},ensure_ascii=False))
