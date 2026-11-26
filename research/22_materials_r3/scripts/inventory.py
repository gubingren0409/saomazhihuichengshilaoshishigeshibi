from pathlib import Path
import zipfile,hashlib,json
R=Path(r'E:/智慧城市和位置服务/_task_runtime/PG1_MIDTERM_RESEARCH_MATERIALS_R3')
C=Path(r'C:/Users/28489/.codex/visualizations/2026/10/10/01a12554-d978-7d60-bdf2-97caf96e0581')
paths=[R.parent/'PG1_MIDTERM_RESEARCH_MATERIALS_R2/delivery/PG1_MIDTERM_RESEARCH_MATERIALS_R2.zip',R.parent/'PG1_RESUME_STREET_SIDE_R1/delivery/PG1_RESUME_STREET_SIDE_R1_REVIEW_FIXED.zip',C/'OSM_GEOAPIFY_PEDESTRIAN_AREA_SHORTEST_R1/input_contract/baseline/OPEN_REVIEW_R1_FIXED.zip']
records=[]
for p in paths:
 h=hashlib.file_digest(p.open('rb'),'sha256').hexdigest();z=zipfile.ZipFile(p)
 records.append({'path':str(p),'sha256':h,'bytes':p.stat().st_size,'crc':z.testzip()})
 print(p.name,h,len(z.namelist()))
 if p==paths[1]:print('STREET MEMBERS\n'+'\n'.join(n for n in z.namelist() if any(t in n for t in ['summary','figures','maps','review','attempt','count']) and not n.endswith('.zip'))[:5500])
 if p==paths[2]:print('APP MEMBERS\n'+'\n'.join(n for n in z.namelist() if any(t in n for t in ['README','RESULT','summary','performance','png','independent_ui','regression']) and not n.endswith('.zip'))[:4500])
(R/'audit/input_inventory.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
(R/'STATUS.json').write_text(json.dumps({'task':'PG1-MIDTERM-RESEARCH-MATERIALS-R3','status':'IN_PROGRESS','route_calls':0,'new_experiments':0},indent=2),encoding='utf8')
