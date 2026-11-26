"""Read-only final checks of the explicitly protected old dependencies."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    initial=read(ROOT/'audits/input_bindings.json');prior=read(ROOT/'audits/protection_midrun.json')
    git=[];env={**os.environ,'GIT_OPTIONAL_LOCKS':'0'}
    for old in initial['protected_git']:
        repo=Path(old['root'])
        cmd=subprocess.run(['git','status','--porcelain=v1','--untracked-files=no'],cwd=repo,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=True)
        row={'root':str(repo),'tracked_status_sha256':hashlib.sha256(cmd.stdout).hexdigest(),'HEAD_sha256':sha(repo/'.git/HEAD'),'index_sha256':sha(repo/'.git/index')}
        row['matches_initial']=all(row[k]==old[k]for k in('tracked_status_sha256','HEAD_sha256','index_sha256'));git.append(row)
    source=[]
    for old in prior['source12']:
        path=ROOT/old['path'];digest=sha(path);source.append({'path':old['path'],'sha256':digest,'matches':digest==old['sha256']})
    backend=[]
    for old in read(ROOT/'audits/backend_freeze_r2.json')['files']:
        digest=sha(ROOT/old['path']);backend.append({'path':old['path'],'sha256':digest,'matches':digest==old['sha256']})
    baseline={'path':initial['path'],'sha256':sha(Path(initial['path']))};baseline['matches']=baseline['sha256']==initial['sha256']
    receipt={'at':datetime.datetime.now().astimezone().isoformat(),'protected_git':git,'source12':source,'backend_freeze_r2':backend,'old_baseline':baseline,
        'all_match':all(r['matches_initial']for r in git)and all(r['matches']for r in source+backend)and baseline['matches'],
        'scope':'Tracked status/HEAD/index, bound12nativeinputs, new frozen backend and old exact baseline. New task files/storage are intentional changes; unrelated history not rescanned.'}
    (ROOT/'audits/protection_final.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'all_match':receipt['all_match'],'git':[r['matches_initial']for r in git],'sources':len(source),'backend':len(backend)},ensure_ascii=False))
    if not receipt['all_match']:raise SystemExit('PROTECTION_MISMATCH_SEE_RECEIPT')
if __name__=='__main__':main()
