"""Read-only bounded closure: two Git indices, three old pages and frozen R1 ZIP."""
from pathlib import Path
import datetime, hashlib, json, os, subprocess, urllib.request
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 old=json.loads((ROOT/'audit/protection_initial.json').read_text(encoding='utf-8'))
 env=dict(os.environ,GIT_OPTIONAL_LOCKS='0');checks=[]
 for item in old['git']:
  repo=Path(item['root']);out=subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=no'],cwd=repo,env=env)
  gd=subprocess.check_output(['git','rev-parse','--absolute-git-dir'],cwd=repo,env=env).decode().strip()
  current={'tracked_status_sha256':hashlib.sha256(out).hexdigest(),'HEAD_sha256':sha(Path(gd)/'HEAD'),'index_sha256':sha(Path(gd)/'index')}
  checks.append({'kind':'git_tracked_and_index','root':str(repo),'current':current,'unchanged':all(current[k]==item[k]for k in current)})
 for item in old['old_services']:
  try:
   with urllib.request.urlopen(f"http://127.0.0.1:{item['port']}/",timeout=10)as f:b=f.read()
   got=hashlib.sha256(b).hexdigest();checks.append({'kind':'old_service_homepage','port':item['port'],'sha256':got,'unchanged':got==item['homepage_sha256']})
  except Exception as e:checks.append({'kind':'old_service_homepage','port':item['port'],'unchanged':False,'error':type(e).__name__})
 state=json.loads((ROOT/'STATUS.json').read_text(encoding='utf-8'));p=Path(state['source_archive']);got=sha(p)
 checks.append({'kind':'frozen_R1_archive','path':str(p),'sha256':got,'unchanged':got==state['source_archive_sha256']})
 result={'at':datetime.datetime.now().astimezone().isoformat(),'checks':checks,'status':'PASS'if all(x['unchanged']for x in checks)else'FAIL','scope':'Protected indices/tracked status, frozen archive content, old service page bytes. No whole-history filesystem scan or field verification.'}
 (ROOT/'audit/protection_final.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
 if result['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
