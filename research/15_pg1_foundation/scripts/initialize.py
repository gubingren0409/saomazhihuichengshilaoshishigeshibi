"""Read-only handover snapshot and verified input extraction; never alters historical Git."""
from pathlib import Path,PurePosixPath
import datetime,hashlib,json,os,subprocess,zipfile,shutil
import psutil
ROOT=Path(__file__).resolve().parents[1]
INPUT=Path(r'C:/Users/28489/Downloads/SMART_CITY_WALKABILITY_FOUNDATION_PG1_CODEX_INPUTS (1).zip')
OLD=Path(r'E:/智慧城市和位置服务/project/Smart_Cities_and_Location_Services')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(name,x):
 p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 if(ROOT/'STATUS.json').exists():raise SystemExit('ALREADY_INITIALIZED_DO_NOT_RESET')
 at=json.loads((ROOT/'audit/input_verification.json').read_text(encoding='utf-8'))['at']if(ROOT/'audit/input_verification.json').exists()else datetime.datetime.now().astimezone().isoformat();checks=[]
 with zipfile.ZipFile(INPUT)as z:
  assert z.testzip()is None
  manifest=json.loads(z.read('SMART_CITY_WALKABILITY_FOUNDATION_PG1/MANIFEST_SHA256.json'))
  assert set(z.namelist())=={'SMART_CITY_WALKABILITY_FOUNDATION_PG1/'+r['path']for r in manifest}|{'SMART_CITY_WALKABILITY_FOUNDATION_PG1/MANIFEST_SHA256.json'}
  for r in manifest:
   b=z.read('SMART_CITY_WALKABILITY_FOUNDATION_PG1/'+r['path']);assert len(b)==r['bytes']and hashlib.sha256(b).hexdigest()==r['sha256'];checks.append(r)
  for i in z.infolist():
   p=PurePosixPath(i.filename);assert not p.is_absolute()and'..'not in p.parts and ':'not in i.filename
   target=ROOT/'inputs'/Path(*p.parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(i))
 write('audit/input_verification.json',{'at':at,'input':str(INPUT),'sha256':sha(INPUT),'CRC':'PASS','members':4,'content_checks':checks})
 rules=[OLD/'AGENTS.md',OLD/'docs/research/SMART_CITIES_RESEARCH_PROTOCOL.md',OLD/'docs/design-system/SMART_CITIES_VISUAL_SYSTEM.md',OLD/'docs/report-writing/SMART_CITIES_REPORT_WRITING_GUIDE.md',OLD/'docs/process-report/WORKFLOW_INTERACTION_EVIDENCE_PROTOCOL.md']
 write('audit/authoritative_rules.json',{'rules':[{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}for p in rules],'conflicts':[{'legacy':'woobowen repository, default push/full-project mirror','resolution':'Current PG1 selects personal repository and requires explicit first-push approval; legacy repository and substantive-data-publication clauses are overridden for this task. Long-term originals unchanged.'}]})
 env=dict(os.environ,GIT_OPTIONAL_LOCKS='0',GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never');snap=json.loads((ROOT/'audit/protected_git_initial.json').read_text(encoding='utf-8'))['roots']if(ROOT/'audit/protected_git_initial.json').exists()else[]
 for i,p in enumerate([]if snap else[Path(r'E:/智慧城市和位置服务'),OLD,Path(r'C:/Users/28489/.codex/visualizations/2026/10/10/01a12554-d978-7d60-bdf2-97caf96e0581')]):
  if not(p/'.git').exists():continue
  row={'root':str(p),'commands':{}}
  for name,args in [('tracked_status',['status','--porcelain=v1','--untracked-files=no']),('status',['status','--porcelain=v1']),('HEAD',['rev-parse','HEAD']),('branch',['branch','--show-current']),('remotes',['remote','-v']),('git_dir',['rev-parse','--absolute-git-dir'])]:
   r=subprocess.run(['git']+args,cwd=p,env=env,capture_output=True,timeout=30);target=ROOT/f'audit/git_{i}_{name}.txt';target.write_bytes(r.stdout)
   row['commands'][name]={'exit':r.returncode,'sha256':hashlib.sha256(r.stdout).hexdigest(),'bytes':len(r.stdout),'lines':len(r.stdout.splitlines()),'evidence':str(target.relative_to(ROOT))}
   if name in('HEAD','branch','git_dir'):row[name]=r.stdout.decode('utf-8','replace').strip()
  gd=Path(row['git_dir']);row['index_sha256']=sha(gd/'index')if(gd/'index').exists()else None;row['HEAD_file_sha256']=sha(gd/'HEAD');snap.append(row)
 write('audit/protected_git_initial.json',{'at':at,'roots':snap,'scope':'Full existing status recorded privately; closure compares tracked status, HEAD/index and preexisting untracked resources. New isolated files may be untracked in ancestor; no old staging touched.'})
 try:ports=[x.laddr.port for x in psutil.net_connections(kind='tcp')if x.status=='LISTEN'and x.laddr and x.laddr.port in(53421,53431,53441,53451)]
 except RuntimeError:ports='NOT_VERIFIED_SANDBOX_TCP_TABLE'
 write('audit/environment_initial.json',{'at':at,'cwd':str(Path.cwd()),'python':os.sys.executable,'RAM_available_bytes':psutil.virtual_memory().available,'disk_free_bytes':shutil.disk_usage(ROOT).free,'existing_listening_ports':ports})
 write('STATUS.json',{'parent_goal':'SMART-CITY-WALKABILITY-FOUNDATION-PG1','status':'FOUNDATION','started_at':'2026-11-12T15:21:50+08:00','initialized_at':at,'repository':'gubingren0409/saomazhihuichengshilaoshishigeshibi','first_public_push':'NOT_APPROVED_NOT_PERFORMED','G0':'IN_PROGRESS','G1':'IN_PROGRESS','G2':'IN_PROGRESS','blind_test':'NOT_FROZEN_NOT_USED','next_phases':'WAIT_G0_G1_G2','track_A':'BOUNDED_DEVELOPMENT_ONLY'})
 (ROOT/'CHECKPOINT.md').write_text('# PG1检查点\n\n原输入已CRC/manifest核验，旧Git状态私有快照已保存。Phase0/地图Phase1/发现Phase2并行；首次Push、Blind冻结与后续阶段须用户批准。新工作仅本目录及独立repository子目录。不要启动旧Southampton任务或修改长期规范。\n',encoding='utf-8')
 print(json.dumps({'initialized':str(ROOT),'verified_input_files':len(checks),'git_roots_snapshotted':len(snap),'at':at},ensure_ascii=False))
if __name__=='__main__':main()
