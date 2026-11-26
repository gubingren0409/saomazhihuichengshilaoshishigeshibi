"""Seal local PG1 evidence bound to the exact independently reviewed source commit."""
from pathlib import Path,PurePosixPath
import argparse,datetime,hashlib,json,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def include(p):
 rel=p.relative_to(ROOT)
 if any(k in rel.parts for k in('.git','__pycache__','.pytest_cache','runtime','delivery','node_modules')):return False
 if p.suffix in('.pyc','.tmp','.log')or p.name.startswith('.env')or p.name=='MANIFEST_SHA256.json'and len(rel.parts)==1:return False
 return True
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True);args=a.parse_args();target=args.output.resolve();assert not target.exists(),'REFUSE_OVERWRITE_FIXED_ZIP'
 binding=json.loads((ROOT/'audit/ROUND_BINDING.json').read_text(encoding='utf-8'));current=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'repository',text=True).strip();assert current==binding['final_commit'];assert sha(ROOT/'git/PG1_SOURCE.bundle')==binding['bundle_sha256']
 assert not subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=ROOT/'repository').strip(),'SOURCE_TREE_NOT_FROZEN'
 required=['index.html','FOUNDATION_REVIEW.md','reviews/INDEPENDENT_REVIEW.md','audit/PUBLIC_FILE_INVENTORY.csv','audit/PUBLIC_RELEASE_AUDIT.json','phase1/index.html','phase2/index.html','track_a/TA-PG1-01/registry.json','git/PG1_SOURCE.bundle']
 for name in required:assert(ROOT/name).is_file(),name
 files=[]
 for p in sorted(ROOT.rglob('*')):
  if not p.is_file()or not include(p):continue
  assert not p.is_symlink(),'UNEXPECTED_SYMLINK';rel=p.relative_to(ROOT).as_posix();pp=PurePosixPath(rel);assert not pp.is_absolute()and'..'not in pp.parts and ':'not in rel
  files.append((p,{'path':rel,'bytes':p.stat().st_size,'sha256':sha(p)}))
 size=sum(r['bytes']for _,r in files);assert size<768*1024*1024,'BOUNDED_REVIEW_PACKAGE_EXCEEDED'
 manifest={'sealed_at':datetime.datetime.now().astimezone().isoformat(),'round_id':binding['round_id'],'repository':binding['repository'],'base_commit':binding['base_commit'],'final_commit':binding['final_commit'],'git_tree':binding['tree_sha'],'public_upload_approved':False,'scope':'LOCAL PRIVATE REVIEW: NOT THE PUBLIC PUSH FILE SET','external_dependencies':[{'artifact':'R1','sha256':'d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed'},{'artifact':'R2','sha256':'3988e9fba95da70dc03b8191a177740a3ccd13602019afe3765e566648b55711'}],'files':[r for _,r in files]}
 mp=ROOT/'MANIFEST_SHA256.json';mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');target.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
  for p,r in files:z.write(p,r['path'])
  z.write(mp,'MANIFEST_SHA256.json')
 with zipfile.ZipFile(target)as z:
  assert z.testzip()is None
  for r in manifest['files']:
   h=hashlib.sha256();n=0
   with z.open(r['path'])as f:
    for b in iter(lambda:f.read(1048576),b''):h.update(b);n+=len(b)
   assert n==r['bytes']and h.hexdigest()==r['sha256'],r['path']
 receipt={'archive':str(target),'bytes':target.stat().st_size,'sha256':sha(target),'members':len(files)+1,'uncompressed_bytes':size+mp.stat().st_size,'CRC':'PASS','all_content_SHA256':'PASS','final_commit':binding['final_commit'],'independent_postseal_replay':'PENDING_OUTSIDE_ARCHIVE','first_public_push':'NOT_APPROVED_NOT_PERFORMED'}
 target.with_suffix('.build_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()
