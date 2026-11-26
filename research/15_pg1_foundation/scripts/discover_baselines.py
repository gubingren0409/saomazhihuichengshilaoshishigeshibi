"""Bounded discovery in named historical roots, without copying or executing artifacts."""
from pathlib import Path
import json,zipfile
ROOT=Path(__file__).resolve().parents[1]
C=Path(r'C:/Users/28489/.codex/visualizations/2026/10/10/01a12554-d978-7d60-bdf2-97caf96e0581')
NAMES=['NAV_END_V1','NAV_END_V2','OSM_GEOAPIFY_PILOT_R1','OSM_GEOAPIFY_PILOT_R2','OSM_GEOAPIFY_PILOT_R3','OSM_GEOAPIFY_R4_REV1','OSM_GEOAPIFY_R4_NORTH_ACCESS_R1','OSM_GEOAPIFY_R4_WALKABILITY_R2','OSM_GEOAPIFY_R4_WALKABILITY_R3','OSM_GEOAPIFY_R4_WALKABILITY_R4_CONTEXT','OSM_GEOAPIFY_R4_FREE_SPACE_R1','OSM_GEOAPIFY_KNOWN_ENTRANCE_E2E_R1','OSM_GEOAPIFY_PEDESTRIAN_AREA_SHORTEST_R1','OSM_GEOAPIFY_PED_AREA_CONNECTIVITY_R1']
roots=[C/n for n in NAMES]+[ROOT.parent/'PED_AREA_CONNECTIVITY_R1',ROOT.parent/'PED_AREA_CONNECTIVITY_R2_ROUTE_DIAGNOSIS']
rows=[]
for base in roots:
 row={'root':str(base),'exists':base.exists(),'archives':[],'status_evidence':[]}
 if base.exists():
  for d in [base,base/'delivery',base/'deliveries',base/'releases',base/'reviews',base/'audit']:
   if not d.is_dir():continue
   for p in sorted(d.iterdir()):
    if not p.is_file():continue
    if p.suffix.lower()=='.zip':row['archives'].append({'path':str(p),'bytes':p.stat().st_size})
    if p.suffix.lower()=='.json'and any(x in p.name.lower()for x in('status','receipt','final','deliver','independent','manifest'))and p.stat().st_size<120000:
     try:
      obj=json.loads(p.read_text(encoding='utf-8-sig'))
      if isinstance(obj,dict):
       keys={k:v for k,v in obj.items()if isinstance(v,(str,int,bool,type(None)))and any(x in k.lower()for x in('status','sha','archive','zip','byte','path','final','package'))}
       row['status_evidence'].append({'path':str(p),'fields':keys})
     except (ValueError,OSError):pass
 rows.append(row)
(ROOT/'audit/baseline_discovery.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
for r in rows:print(json.dumps({'root':r['root'],'archives':r['archives'],'status_evidence':r['status_evidence'][:7]},ensure_ascii=False))
