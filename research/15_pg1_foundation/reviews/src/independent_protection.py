"""Read-only old Git snapshot and old-service availability checks."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,urllib.request
ROOT=Path(__file__).resolve().parents[2]
initial=json.loads((ROOT/'audit/protected_git_initial.json').read_text(encoding='utf8'))
env=dict(os.environ,GIT_OPTIONAL_LOCKS='0',GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never')
out={'at_utc':datetime.now(timezone.utc).isoformat(),'old_git':[],'old_services':[],'operations':'Git optional locks disabled; GET health only; no process termination/config/old-data mutation'}
for old in initial['roots']:
    row={'root':old['root'],'checks':{}}
    for label,relative,key in [('index','index','index_sha256'),('HEAD_file','HEAD','HEAD_file_sha256')]:
        try:
            digest=hashlib.sha256((Path(old['git_dir'])/relative).read_bytes()).hexdigest();row['checks'][label]={'sha256':digest,'initial_match':digest==old[key]}
        except OSError as e:row['checks'][label]={'status':'NOT_VERIFIED','reason':type(e).__name__}
    for label,args in [('tracked_status',['status','--porcelain=v1','--untracked-files=no']),('HEAD',['rev-parse','HEAD']),('branch',['branch','--show-current']),('remotes',['remote','-v'])]:
        r=subprocess.run(['git','--no-optional-locks',*args],cwd=old['root'],env=env,capture_output=True,timeout=30)
        digest=hashlib.sha256(r.stdout).hexdigest();row['checks'][label]={'exit':r.returncode,'sha256':digest,'initial_match':r.returncode==0 and digest==old['commands'][label]['sha256']}
    out['old_git'].append(row)
for port in [53421,53431,53441,53451]:
    row={'port':port,'method':'GET','path':'/api/health'}
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f'http://127.0.0.1:{port}/api/health',timeout=3)as response:
            body=response.read(65536);row['http_status']=response.status;row['body_sha256']=hashlib.sha256(body).hexdigest()
            try:
                payload=json.loads(body);row['identity']={k:v for k,v in payload.items()if k in ['service','service_identity','pid','read_only','solver_endpoint','status']}
            except (ValueError,AttributeError):row['identity']='NON_JSON_NOT_INSPECTED'
    except OSError as e:row['status']='NOT_VERIFIED';row['reason']=type(e).__name__;row['underlying_reason']=type(getattr(e,'reason',e)).__name__;row['errno']=getattr(getattr(e,'reason',e),'errno',None)
    out['old_services'].append(row)
(ROOT/'reviews/independent_protection.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
assert all(v.get('initial_match')for r in out['old_git']for v in r['checks'].values())
print(json.dumps({'old_git_roots_unchanged':len(out['old_git']),'old_service_http_statuses':[r.get('http_status',r.get('status'))for r in out['old_services']]}))
