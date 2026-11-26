"""New-task-only allowlisted archive; fixed bytes, safe paths, exact manifest."""
from pathlib import Path,PurePosixPath
from datetime import datetime
import argparse,hashlib,json,os,stat,zipfile
ROOT=Path(__file__).resolve().parents[1]
FOLDERS={'src','config','app','tests','scripts','data','audits','visuals','runs','input_contract'}
ROOT_FILES={'README.md','SCOPE_AND_METHOD.md','RESULTS.md','STATUS.json','CHECKPOINT.md','PROCESS_RECORD.md','index.html','NOTICE','requirements.txt'}
SKIP={'__pycache__','.git','.env','runtime','baseline','delivery','logs','progress'}
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def members():
    for folder,dirs,names in os.walk(ROOT,followlinks=False):
        current=Path(folder);rel=current.relative_to(ROOT)
        dirs[:]=sorted(d for d in dirs if d not in SKIP and(current!=ROOT or d in FOLDERS))
        for d in dirs:
            if(current/d).is_symlink()or(current/d).lstat().st_file_attributes&stat.FILE_ATTRIBUTE_REPARSE_POINT:raise ValueError('REPARSE:'+str(current/d))
        for name in sorted(names):
            p=current/name;r=p.relative_to(ROOT);s=r.as_posix()
            if current==ROOT and name not in ROOT_FILES:continue
            if any(part in SKIP for part in r.parts):continue
            if p.suffix.lower()in('.zip','.log','.pyc','.pyo','.pem','.key','.tmp')or name.startswith('.env'):continue
            if name=='build_review_zip.py'or name in('service.json','server_error.json')or 'stdout'in name or'stderr'in name:continue
            if r.parts[0]=='runs'and len(r.parts)<3 and name not in('run_registry.csv','segment_evidence.csv','performance.csv'):continue
            if name=='progress.json'or name.endswith('_progress.json'):continue
            if name=='independent_clean_replay.json':continue # final bytes are reviewed later; receipt stays outside
            if p.is_symlink()or p.lstat().st_file_attributes&stat.FILE_ATTRIBUTE_REPARSE_POINT:raise ValueError('REPARSE_FILE:'+s)
            q=PurePosixPath(s)
            if q.is_absolute()or'..'in q.parts or'\\'in s:raise ValueError('UNSAFE_PATH:'+s)
            yield p
def main(output):
    output=output.resolve()
    if not output.is_relative_to((ROOT/'delivery').resolve())or output.exists():raise ValueError('NEW_FIXED_ZIP_UNDER_DELIVERY_REQUIRED')
    files=sorted(members());entries=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}for p in files]
    manifest={'task':'PEDESTRIAN_AREA_SHORTEST_R1','created_at':datetime.now().astimezone().isoformat(),'entries':entries,
        'baseline_sha256':'4fc46d467a25aa19db46a8d721f523b1f3a5aed43ae7645d107a52a08682e6da',
        'offline_self_containment':'Current APP and new legal request inputs included; not all historical experiments or external baseline ZIP',
        'external_archive_replay_receipt':'independent_clean_replay.json is delivered next to this final archive; not a self-circular preclaimed check',
        'exclusions':['Nested archives, runtime/environment, transient service/progress/stdout, duplicate old whole project, final external replay receipt']}
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True)as z:
        for p in files:z.write(p,p.relative_to(ROOT).as_posix())
        z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(output)as z:
        assert z.testzip()is None
        assert set(z.namelist())=={r['path']for r in entries}|{'MANIFEST.json'}
        for r in entries:assert hashlib.sha256(z.read(r['path'])).hexdigest()==r['sha256']
    result={'status':'PASS_INTEGRITY_AWAITING_INDEPENDENT_CLEAN_REQUEST','archive':str(output),'bytes':output.stat().st_size,'sha256':sha(output),'members':len(entries)+1,'CRC':'PASS','member_SHA':'PASS','exact_manifest':'PASS'}
    output.with_suffix('.integrity.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'delivery/OPEN_REVIEW_R1_FINAL.zip');main(p.parse_args().output)
