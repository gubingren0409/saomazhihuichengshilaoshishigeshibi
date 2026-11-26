"""Verify selected historical archives and register alternatives; no historical execution."""
from pathlib import Path
import csv,hashlib,json,zipfile,datetime
ROOT=Path(__file__).resolve().parents[1]
C=Path(r'C:/Users/28489/.codex/visualizations/2026/10/10/01a12554-d978-7d60-bdf2-97caf96e0581')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
selected=[('NAV_END_V1',C/'NAV_END_V1_OPEN_REVIEW.zip','HISTORICAL_SCREENSHOT_REFERENCE'),('NAV_END_V2',C/'NAV_END_V2_OPEN_REVIEW.zip','HISTORICAL_SCREENSHOT_REFERENCE'),('PILOT_R1_AB',C/'OSM_GEOAPIFY_PILOT_R1/delivery/OPEN_REVIEW_AB_COMPLETION.zip','HISTORICAL_DUAL_PATH'),('PILOT_R2',C/'OSM_GEOAPIFY_PILOT_R2/delivery/OPEN_REVIEW.zip','HISTORICAL_DIAGNOSIS'),('PILOT_R3',C/'OSM_GEOAPIFY_PILOT_R3/delivery/OPEN_REVIEW.zip','DEVELOPMENT_SOURCE_SIX_SCENES'),('R4_REV1',C/'OSM_GEOAPIFY_R4_REV1/delivery/OPEN_REVIEW.zip','HISTORICAL_FACE_METHOD'),('NORTH_ACCESS_R1',C/'OSM_GEOAPIFY_R4_NORTH_ACCESS_R1/delivery/OPEN_REVIEW.zip','HISTORICAL_EXIT_HYPOTHESIS'),('WALKABILITY_R1',C/'OSM_GEOAPIFY_R4_WALKABILITY_R1/delivery/OPEN_REVIEW.zip','NOT_FOUND_NO_RECONSTRUCTION'),('WALKABILITY_R2',C/'OSM_GEOAPIFY_R4_WALKABILITY_R2/delivery/OPEN_REVIEW.zip','HISTORICAL_LINE_INFERENCE'),('WALKABILITY_R3',C/'OSM_GEOAPIFY_R4_WALKABILITY_R3/delivery/OPEN_REVIEW.zip','HISTORICAL_REGION_RECOVERY'),('WALKABILITY_R4_CONTEXT',C/'OSM_GEOAPIFY_R4_WALKABILITY_R4_CONTEXT/delivery/OPEN_REVIEW.zip','HISTORICAL_CONTEXT_DIAGNOSIS'),('FREE_SPACE_R1_FINAL',C/'OSM_GEOAPIFY_R4_FREE_SPACE_R1/delivery/OPEN_REVIEW.zip','CURRENT_FREE_SPACE_DEFINITION'),('KNOWN_ENTRANCE_E2E_R1_FIXED',C/'OSM_GEOAPIFY_KNOWN_ENTRANCE_E2E_R1/delivery/OPEN_REVIEW_R1_FIXED.zip','CURRENT_KNOWN_DOOR_PROTOTYPE'),('PED_AREA_SHORTEST_R1_FIXED',C/'OSM_GEOAPIFY_PEDESTRIAN_AREA_SHORTEST_R1/delivery/OPEN_REVIEW_R1_FINAL_FIXED.zip','CURRENT_FULL_FACE_BASELINE'),('PED_AREA_CONNECTIVITY_R1',ROOT.parent/'PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip','CURRENT_SOURCE_TOPOLOGY_BASELINE'),('PED_AREA_CONNECTIVITY_R2',ROOT.parent/'PED_AREA_CONNECTIVITY_R2_ROUTE_DIAGNOSIS/delivery/OPEN_REVIEW.zip','LATEST_ROUTE_DIAGNOSIS')]
anchors=[]
def visit(v,path):
 if isinstance(v,dict):
  for k,x in v.items():
   if isinstance(x,str)and len(x)==64 and all(c in '0123456789abcdef'for c in x.lower()):anchors.append((x.lower(),str(path),k))
   elif isinstance(x,(dict,list)):visit(x,path)
 elif isinstance(v,list):
  for x in v:visit(x,path)
for _,p,_ in selected:
 for d in[p.parent,p.parent.parent]:
  if not d.exists():continue
  for a in d.glob('*.json'):
   if a.stat().st_size>150000:continue
   try:visit(json.loads(a.read_text(encoding='utf-8-sig')),a)
   except (ValueError,OSError):pass
rows=[]
for ident,p,role in selected:
 row={'artifact_id':ident,'canonical_path':str(p),'role':role,'exists':p.is_file(),'source_commit':'NOT_RECORDED_IN_HISTORICAL_PACKAGE','public_release':'NOT_AUTOMATICALLY_APPROVED','user_acceptance':'NOT_INFERRED_FROM_INTERNAL_PASS'}
 if p.is_file():
  digest=sha(p);matched=[{'path':a,'field':k}for h,a,k in anchors if h==digest];row.update(bytes=p.stat().st_size,sha256=digest,matching_receipt_anchors=matched)
  with zipfile.ZipFile(p)as z:
   assert z.testzip()is None;names=z.namelist();assert len(names)==len(set(names));row.update(CRC='PASS',members=len(names),source_members=sum('/src/'in'/'+n or n.startswith('src/')for n in names),data_members=sum(any(k in n.lower()for k in('source','data/','geojson','osm'))for n in names),review_evidence_members=[n for n in names if any(s in n.lower()for s in('independent_review','independent_package','replay_receipt'))][:12])
  row['verification']='HASH_MATCHES_HISTORICAL_RECEIPT_CRC_PASS'if matched else'MEASURED_SHA_CRC_PASS_NO_SEPARATE_HASH_ANCHOR'
 else:row.update(verification='NOT_FOUND',bytes=0,sha256='',CRC='NOT_RUN',limitation='No unambiguous separately named WALKABILITY_R1 package found; NORTH_ACCESS_R1 is a different task, not silently renamed.')
 rows.append(row);print(json.dumps({'artifact':ident,'verification':row['verification'],'sha256':row['sha256']},ensure_ascii=False),flush=True)
(ROOT/'audit/baseline_registry_private.json').write_text(json.dumps({'at':datetime.datetime.now().astimezone().isoformat(),'artifacts':rows,'note':'CRC/source membership are engineering evidence, not scientific acceptance; no old code rerun.'},ensure_ascii=False,indent=2),encoding='utf-8')
fields=['artifact_id','canonical_path','bytes','sha256','verification','CRC','role','source_commit','public_release','user_acceptance']
with (ROOT/'audit/baseline_registry_private.csv').open('w',encoding='utf-8-sig',newline='')as f:
 w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
