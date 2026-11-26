"""Local-only reviewed source commit and exact proposed first-public inventory."""
from pathlib import Path
import subprocess,hashlib,json,csv,datetime
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT/'repository';PERSONAL='https://github.com/gubingren0409/saomazhihuichengshilaoshishigeshibi.git'
def run(args,input=None):return subprocess.check_output(['git']+args,cwd=REPO,input=input)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert Path(run(['rev-parse','--show-toplevel']).decode().strip()).resolve()==REPO.resolve()
 assert run(['remote','get-url','origin']).decode().strip()==PERSONAL
 report=json.loads((ROOT/'audit/PUBLIC_RELEASE_AUDIT.json').read_text(encoding='utf-8'));assert not report['findings']
 paths=[r['path']for r in report['files']]
 for r in report['files']:assert sha(REPO/r['path'])==r['sha256']
 listpath=ROOT/'audit/public_stage_paths.txt';listpath.write_text('\n'.join(paths)+'\n',encoding='utf-8')
 run(['add','--pathspec-from-file='+str(listpath)])
 run(['add','--renormalize','--pathspec-from-file='+str(listpath)])
 staged=run(['diff','--cached','--stat']);(ROOT/'audit/staged_diff_stat.txt').write_bytes(staged)
 checkpoint=json.loads((ROOT/'audit/development_probe_source_history.json').read_text(encoding='utf-8'))['experiment_base_commit'];source=run(['show',checkpoint+':tools/run_development_probe.py']);protocol=json.loads((ROOT/'track_a/TA-PG1-01/protocol.json').read_text());assert hashlib.sha256(source).hexdigest()in protocol['code'].values()
 run(['-c','user.name=Codex Research Assistant','-c','user.email=codex-research@local.invalid','commit','-m','Complete PG1 foundation maps, bounded discovery and independently checked development evidence'])
 final=run(['rev-parse','HEAD']).decode().strip();tree=run(['rev-parse','HEAD^{tree}']).decode().strip();branch=run(['branch','--show-current']).decode().strip();entries=run(['ls-tree','-r','--full-tree','HEAD']).decode().splitlines();rows=[]
 for line in entries:
  header,path=line.split('\t',1);mode,kind,blob=header.split();assert kind=='blob';b=run(['cat-file','blob',blob]);working=(REPO/path).read_bytes();assert b==working,'SOURCE_FILTER_OR_DIVERGENCE:'+path
  rows.append({'path':path,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'git_blob_sha':blob,'category':'NEW_SOURCE_TEST_SCHEMA_OR_TEXT_ONLY','raw_map_or_private_coordinates':False,'license':'NEW_CODE_LICENSE_UNSPECIFIED_PENDING_USER','public_approval':'PENDING_EXPLICIT_USER_APPROVAL'})
 assert {r['path']for r in rows}==set(paths)
 with(ROOT/'audit/PUBLIC_FILE_INVENTORY.csv').open('w',encoding='utf-8-sig',newline='')as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 empty=run(['mktree'],b'').decode().strip();(ROOT/'audit/first_public_full_diff_stat.txt').write_bytes(run(['diff','--stat',empty,final]));(ROOT/'audit/round_diff_stat.txt').write_bytes(run(['diff','--stat',checkpoint,final]))
 bundle=ROOT/'git/PG1_SOURCE.bundle';bundle.parent.mkdir(exist_ok=True);run(['bundle','create',str(bundle),'--all']);run(['bundle','verify',str(bundle)])
 binding={'round_id':'PG1_FOUNDATION_G0_G1_G2_R1','at':datetime.datetime.now().astimezone().isoformat(),'repository':'gubingren0409/saomazhihuichengshilaoshishigeshibi','base_commit':None,'base_identity':'NONE_EMPTY_PERSONAL_REMOTE_NO_IMPORTED_HISTORY','bootstrap_and_experiment_base_commit':checkpoint,'final_commit':final,'tree_sha':tree,'branch':branch,'PR_URL':None,'remote_pushes':0,'remote_sync':'NOT_APPROVED_NOT_PERFORMED','first_public_target_proposal':'HEAD:refs/heads/main','reachable_commit_count':int(run(['rev-list','--count','HEAD'])),'first_public_file_count':len(rows),'inventory_sha256':sha(ROOT/'audit/PUBLIC_FILE_INVENTORY.csv'),'bundle_sha256':sha(bundle),'source_bytes_match_git_blobs':True,'public_scope':'ONLY_EXACT_SOURCE_TREE_PLUS_REACHABLE_LOCAL_HISTORY; private audit/coordinates/maps are outside repository','software_license':'UNSPECIFIED_PENDING_USER','whole_parent_status':'FOUNDATION_GATE_REVIEW_NOT_PASS'}
 (ROOT/'audit/ROUND_BINDING.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(binding,ensure_ascii=False))
if __name__=='__main__':main()
