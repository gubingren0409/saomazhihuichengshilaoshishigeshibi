"""Copy selected frozen material bytes; never execute imported research code."""
from pathlib import Path
import csv,hashlib,json,shutil,zipfile,io
R=Path(__file__).resolve().parents[1];P=R/'package'
C=Path('C:/Users/28489/.codex/visualizations/2026/10/10/01a12554-d978-7d60-bdf2-97caf96e0581')
def sh(b):return hashlib.sha256(b).hexdigest()
def write(p,b):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
def table(p,rows):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
sources=[];archives=[]
def archive(path,label,expected):
 b=path.read_bytes();h=sh(b);assert h==expected,(label,h);z=zipfile.ZipFile(io.BytesIO(b));assert z.testzip() is None
 archives.append({'stage':label,'path':str(path),'sha256':h,'bytes':len(b)})
 return z,h
def take(z,h,label,n,dest=None):
 b=z.read(n);p=P/(dest or ('sources/'+label+'/'+n));write(p,b)
 sources.append({'source_id':label+'::'+n,'experiment':label,'version':'FROZEN_FINAL','package_file':p.relative_to(P).as_posix(),'archive_sha256':h,'archive_member':n,'sha256':sh(b),'bytes':len(b),'identity':'FROZEN_MEMBER_UNCHANGED'})
 return p
r2path=R.parent/'PG1_MIDTERM_RESEARCH_MATERIALS_R2/delivery/PG1_MIDTERM_RESEARCH_MATERIALS_R2.zip'
r2,h=archive(r2path,'MATERIALS_R2','5fecb3c0f3f65dbf371967deaf6d7d3aa3885b09a3d160bf07b00813a3e682da')
write(P/'prior/PG1_MIDTERM_RESEARCH_MATERIALS_R2.zip',r2path.read_bytes())
for n in r2.namelist():
 if n.endswith(('.png','.svg')) and len(n.split('/'))==2 or n.startswith('sources/'):
  take(r2,h,'MATERIALS_R2',n,'prior/R2_selected/'+n)
for n in ['FIGURE_MANIFEST.csv','SOURCE_MANIFEST.csv','MASTER_NUMBERS_TABLE.csv']:
 take(r2,h,'MATERIALS_R2',n,'prior/R2_selected/'+n)
# Correct map reconstruction context includes original coordinates and raw features, no algorithms invoked.

st,hs=archive(R.parent/'PG1_RESUME_STREET_SIDE_R1/delivery/PG1_RESUME_STREET_SIDE_R1_REVIEW_FIXED.zip','STREET_SIDE_R1','6b2db66e8347603c2aa346810846f4d6c5cf39e2e830f12a162b0e6c6e9485ab')
for n in st.namelist():
 if n.startswith(('figures/','results/','reviews/','contracts/')) or n in ['EXPERIMENT_BRIEF.md','README.md','PROCESS_RECORD.md','STATUS.json','audit/execution_counts.json','audit/experiment_registry.jsonl','audit/window_lock.json','maps/trial_map_data.json']:
  if not n.endswith('/') and not n.endswith(('.py','.zip')):take(st,hs,'STREET_SIDE_R1',n)

app,ha=archive(C/'OSM_GEOAPIFY_PEDESTRIAN_AREA_SHORTEST_R1/input_contract/baseline/OPEN_REVIEW_R1_FIXED.zip','KNOWN_ENTRANCE_E2E_R1_FIXED','4fc46d467a25aa19db46a8d721f523b1f3a5aed43ae7645d107a52a08682e6da')
selected=['README.md','RESULTS.md','SCOPE_AND_METHOD.md','AUDIT/performance_final.json','AUDIT/independent_io_fix_regression_check.json','AUDIT/regression_counter_clarification.json','AUDIT/independent_browser_compute.png','AUDIT/independent_browser_exports.computed-full.png','AUDIT/independent_browser_exports.computed-door.png','AUDIT/independent_browser_inspect.png','AUDIT/browser/F0-full.png','AUDIT/browser/F1-full.png','src/planner.py','scripts/plan.py','scripts/serve_app.py','app/app.js','runs/acceptance/app_acceptance.csv','runs/acceptance/summary.json','runs/acceptance/fixed_requests.json','runs/acceptance/cli_final_request.json','runs/acceptance/cli_final_response.json','runs/acceptance/APP-01.response.json','runs/acceptance/APP-02.response.json','runs/acceptance/APP-03.response.json','runs/acceptance/APP-09.response.json','runs/acceptance/APP-13.response.json']
for n in selected:
 if n in app.namelist():take(app,ha,'KNOWN_ENTRANCE_E2E_R1_FIXED',n)

sup,hu=archive(R.parent/'PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115/delivery/PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115_REVIEW.zip','SUPPLEMENTARY_20261115','bebdd6cb52c3afc156fc62a3b373ea29a2f4f38d68b28976ef771c5df6728103')
for n in sup.namelist():
 q7=n.startswith('Q7-DYNAMIC-CLOSURE-SIMULATION-R1/') and (n.count('/')==1 and n.endswith(('.csv','.json','.jsonl','.md')) or '/figures/' in n and n.endswith(('.png','.svg')) or n.endswith('primary_result_ids.json'))
 q8=n.startswith('Q8-SCALE-LATENCY-BENCHMARK-R1/') and (Path(n).name in ['README.md','summary.json','summary.csv','latency_distribution.csv','observations_normalized.csv','capacity_inventory.csv','top3_measurement_versions.csv','worker_process_outcomes.csv'] or '/figures/' in n and n.endswith(('.png','.svg')))
 if q7 or q8 or n in ['RESEARCH_REVIEW.md','DATA_VERSION_NOTES.md','INDEPENDENCE_SCOPE.md','CLAIM_EVIDENCE_MAP.csv']:
  take(sup,hu,'SUPPLEMENTARY_20261115',n)

# Previous positive-evidence phases are retained with their own contracts and task difficulty.
old,ho=archive(R.parent/'PG1_RESEARCH_MATERIALS_HANDOFF_R1/delivery/HANDOFF_PACKAGE.zip','HANDOFF_R1','1da065a47356057018246d2213812fc9ef7158471e15b2ecb2e216621c3f9444')
for n in old.namelist():
 if n.startswith('source_materials/') and any('/'+k+'/' in n for k in ['WALKABILITY-R3','WALKABILITY-R4-CONTEXT']) and not n.endswith(('.gz','.zip')):take(old,ho,'HANDOFF_R1',n)
 if (n.startswith('figures/') and any('/'+k+'/' in n for k in ['WALKABILITY-R3','WALKABILITY-R4-CONTEXT'])):take(old,ho,'HANDOFF_R1',n)
for n in ['evidence/SOURCE_INDEX.csv','figures/FIGURE_CATALOG.csv']:take(old,ho,'HANDOFF_R1',n)
table(P/'evidence/SOURCE_INDEX.csv',sources)
write(R/'audit/ROOT_ARCHIVE_INVENTORY.json',json.dumps(archives,ensure_ascii=False,indent=2).encode('utf8'))
print(json.dumps({'source_files':len(sources),'archives':len(archives)},ensure_ascii=False))
