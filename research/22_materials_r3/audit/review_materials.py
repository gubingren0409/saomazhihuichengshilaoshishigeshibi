from pathlib import Path
import json,csv,zipfile,hashlib,re
B=Path(r'E:/智慧城市和位置服务/_task_runtime');C=Path(r'C:/Users/28489/.codex/visualizations/2026/10/10/01a12554-d978-7d60-bdf2-97caf96e0581');R=B/'PG1_MIDTERM_RESEARCH_MATERIALS_R3';P=R/'package';O=R/'working/independent'
paths={
'5fecb3c0f3f65dbf371967deaf6d7d3aa3885b09a3d160bf07b00813a3e682da':B/'PG1_MIDTERM_RESEARCH_MATERIALS_R2/delivery/PG1_MIDTERM_RESEARCH_MATERIALS_R2.zip',
'1da065a47356057018246d2213812fc9ef7158471e15b2ecb2e216621c3f9444':B/'PG1_RESEARCH_MATERIALS_HANDOFF_R1/delivery/HANDOFF_PACKAGE.zip',
'6b2db66e8347603c2aa346810846f4d6c5cf39e2e830f12a162b0e6c6e9485ab':B/'PG1_RESUME_STREET_SIDE_R1/delivery/PG1_RESUME_STREET_SIDE_R1_REVIEW_FIXED.zip',
'bebdd6cb52c3afc156fc62a3b373ea29a2f4f38d68b28976ef771c5df6728103':B/'PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115/delivery/PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115_REVIEW.zip',
'1d4110a76d0e5006f5c518366d82d6fb1aa98c8e46bac6956b2b0dbd91ccc77a':C/'OSM_GEOAPIFY_R4_FREE_SPACE_R1/delivery/OPEN_REVIEW.zip',
'36d83fb2d792b33457968f1c649099380cc5cffa1e7b561c1dd6463fd82ce2f3':C/'R4_REV1_INPUT_c3s9957s/OSM_GEOAPIFY_R4_REV1_CODEX_INPUTS/references/frozen/OSM_GEOAPIFY_R4_OPEN_REVIEW.zip',
'f2de5326ffbffe1e62c0fa5d622cec6645582342824ea1ae13716789d5af5ee0':R/'working/history/R4_REV1_OPEN_REVIEW.zip',
'4fc46d467a25aa19db46a8d721f523b1f3a5aed43ae7645d107a52a08682e6da':C/'OSM_GEOAPIFY_PEDESTRIAN_AREA_SHORTEST_R1/input_contract/baseline/OPEN_REVIEW_R1_FIXED.zip'}
def sha(b):return hashlib.sha256(b).hexdigest()
zips={}
for h,p in paths.items():assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==h,p;zips[h]=zipfile.ZipFile(p)
rows=list(csv.DictReader((P/'evidence/SOURCE_INDEX.csv').open(encoding='utf-8-sig')));checks=[];errors=[]
for r in rows:
 p=P/r['package_file'];actual=sha(p.read_bytes())
 if actual!=r['sha256']:errors.append({'type':'source_hash','file':r['package_file']})
 if r['identity']=='EXTERNAL_POSTSEAL_RECEIPT':
  original=C/'OSM_GEOAPIFY_R4_FREE_SPACE_R1'/r['archive_member'];assert actual==sha(original.read_bytes());checks.append({'file':r['package_file'],'identity':'EXTERNAL_POSTSEAL_RECEIPT_MATCH','sha256':actual});continue
 if r['identity']=='DERIVED_TABLE_FROM_FROZEN_RESULTS_NO_SOLVER':
  checks.append({'file':r['package_file'],'identity':'DERIVED_TABLE_NOT_EXPECTED_IN_ORIGINAL_ZIP','sha256':actual});continue
 z=zips[r['archive_sha256']]
 if r['archive_member'] not in z.namelist():errors.append({'type':'archive_member_missing','file':r['package_file'],'member':r['archive_member']});continue
 if actual!=sha(z.read(r['archive_member'])):errors.append({'type':'archive_bytes_mismatch','file':r['package_file']})
 checks.append({'file':r['package_file'],'identity':'EXACT_FROZEN_ARCHIVE_MEMBER_MATCH','sha256':actual})
nums=list(csv.DictReader((P/'04_MASTER_NUMBERS_TABLE.csv').open(encoding='utf-8-sig')));nchecks=[]
for r in nums:
 p=P/r['source_file'];actual=sha(p.read_bytes());assert actual==r['source_sha256'],r
 field=r['source_field'];status='TEXT_OR_CSV_SOURCE_MANUALLY_CHECKED'
 if p.suffix=='.json' and re.fullmatch(r'[\w.\-\[\]]+',field):
  d=json.loads(p.read_text(encoding='utf-8-sig'))
  for tok in re.findall(r'[^.\[\]]+',field):d=d[int(tok)]if isinstance(d,list)else d[tok]
  if isinstance(d,list):d=len(d);status='JSON_LIST_LENGTH_RECALCULATED'
  else:status='JSON_SCALAR_RECHECKED'
  if abs(float(d)-float(r['value']))>1e-8:errors.append({'type':'number_mismatch','metric':r['metric'],'saved':r['value'],'actual':d})
 nchecks.append({'event_id':r['event_id'],'metric':r['metric'],'value':r['value'],'status':status,'source_sha256':actual})
result={'reviewer':'/root/r3_independent','original_archives_checked':len(zips),'source_records':len(rows),'exact_original_member_matches':sum(x['identity']=='EXACT_FROZEN_ARCHIVE_MEMBER_MATCH'for x in checks),'derived_tables_separately_identified':sum(x['identity']=='DERIVED_TABLE_NOT_EXPECTED_IN_ORIGINAL_ZIP'for x in checks),'number_records':len(nums),'numeric_json_rechecks':sum(x['status']!='TEXT_OR_CSV_SOURCE_MANUALLY_CHECKED'for x in nchecks),'errors':errors,'source_checks':checks,'number_checks':nchecks,'new_solver_calls':0}
(O/'R3_SOURCE_AND_NUMBER_REVIEW.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print({k:v for k,v in result.items()if k not in ['source_checks','number_checks']})


