"""Noninteractive read-only checks. Credential bytes never enter logs or artifacts."""
from pathlib import Path
import subprocess,os,json,datetime,urllib.request,urllib.error
ROOT=Path(__file__).resolve().parents[1];REPO='gubingren0409/saomazhihuichengshilaoshishigeshibi'
env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never',GIT_OPTIONAL_LOCKS='0')
result={'at':datetime.datetime.now().astimezone().isoformat(),'repo':REPO,'first_push_approved':False,'writes_to_remote':0,'actual_GET_requests':0}
try:
 r=subprocess.run(['git','ls-remote','https://github.com/'+REPO+'.git'],env=env,capture_output=True,timeout=30)
 result['ls_remote']={'exit_code':r.returncode,'advertised_ref_count':len(r.stdout.splitlines()),'empty_refs':r.returncode==0 and not r.stdout.strip()}
except subprocess.TimeoutExpired:result['ls_remote']={'status':'TIMEOUT_30_SECONDS'}
try:
 r=subprocess.run(['git','-c','credential.interactive=never','credential','fill'],input=b'protocol=https\nhost=github.com\n\n',env=env,capture_output=True,timeout=20)
 pairs=dict(line.split(b'=',1)for line in r.stdout.splitlines()if b'='in line);token=pairs.get(b'password',b'').decode('utf-8','replace')
 result['credential_available']=bool(token);result['credential_fill_exit']=r.returncode
 if token:
  headers={'Authorization':'Bearer '+token,'User-Agent':'SmartCity-PG1-ReadOnly-Audit','Accept':'application/vnd.github+json'}
  for name,url in [('local_authenticated_identity','https://api.github.com/user'),('repository_permissions','https://api.github.com/repos/'+REPO)]:
   try:
    result['actual_GET_requests']+=1
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=20)as f:obj=json.load(f)
    result[name]={'login':obj.get('login')}if name=='local_authenticated_identity'else{'full_name':obj.get('full_name'),'visibility':obj.get('visibility'),'size':obj.get('size'),'default_branch':obj.get('default_branch'),'permissions':obj.get('permissions')}
   except urllib.error.HTTPError as e:result[name]={'HTTP_status':e.code}
   except Exception as e:result[name]={'error_class':type(e).__name__}
  token='';pairs.clear()
except subprocess.TimeoutExpired:result['credential_available']='NOT_VERIFIED_TIMEOUT_20_SECONDS'
except Exception as e:result['credential_check_error']=type(e).__name__
result['push_status']='PERMISSION_ADVERTISED_NO_PUSH_ATTEMPT'if result.get('repository_permissions',{}).get('permissions',{}).get('push')else'NOT_CONFIRMED_OR_NO_PERMISSION'
result['note']='Read-only credential/metadata check; no secret output, no remote write. A public ls-remote alone does not prove push rights. Dry-run push may be checked only from the isolated prepared local commit.'
(ROOT/'audit/local_repository_access.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
