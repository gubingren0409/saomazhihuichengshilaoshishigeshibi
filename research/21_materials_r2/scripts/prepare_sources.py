from pathlib import Path
import json,zipfile,hashlib,csv,io
R=Path(r'E:/智慧城市和位置服务/_task_runtime/PG1_MIDTERM_RESEARCH_MATERIALS_R2')
H=R.parent/'PG1_RESEARCH_MATERIALS_HANDOFF_R1'
zpath=H/'delivery/HANDOFF_PACKAGE.zip'
h=hashlib.file_digest(zpath.open('rb'),'sha256').hexdigest()
assert h=='1da065a47356057018246d2213812fc9ef7158471e15b2ecb2e216621c3f9444'
z=zipfile.ZipFile(zpath)
rows=list(csv.DictReader(io.StringIO(z.read('figures/FIGURE_CATALOG.csv').decode('utf-8-sig'))))
sel=[r for r in rows if r['round'] in ['PG1_MAP_CONTEXT_RECONSTRUCTION_R2','OSM_GEOAPIFY_R4_REV1','OSM_GEOAPIFY_R4','OSM_GEOAPIFY_R4_NORTH_ACCESS_R1','WALKABILITY-R2','PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED','PED-AREA-CONNECTIVITY-R2']]
print('Verified R1 SHA',h,'CRC',z.testzip(),'figures',len(sel))
(R/'working/figure_selection.json').write_text(json.dumps(sel,ensure_ascii=False,indent=2),encoding='utf8')
for r in sel:
 p=R/'working'/r['package_path'];p.parent.mkdir(parents=True,exist_ok=True);b=z.read(r['package_path']);assert hashlib.sha256(b).hexdigest()==r['sha256'];p.write_bytes(b)
print('\n'.join(n for n in z.namelist() if n.startswith('source_materials/') and any(k in n for k in ['R4_REV1','R4_NORTH','WALKABILITY-R2','SHORTEST','CONNECTIVITY-R2','OSM_GEOAPIFY_R4/'])))
(R/'STATUS.json').write_text(json.dumps({'task':'PG1_MIDTERM_RESEARCH_MATERIALS_R2','status':'IN_PROGRESS','new_experiments':False},indent=2),encoding='utf8')
