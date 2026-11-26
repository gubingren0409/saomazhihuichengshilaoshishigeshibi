"""Create a fixed review archive. Expanded historical files are not duplicated."""
import json,zipfile,hashlib,stat
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    keep=['README.md','SCOPE_AND_METHOD.md','RESULTS.md','USER_REVIEW_NOTES.md','CHECKPOINT.md','STATUS.json','PROCESS_RECORD.md','requirements.txt','config','src','scripts','tests','data','runs','visuals','audits','input_contract']
    files=[]
    for name in keep:
        p=ROOT/name
        files.extend([p] if p.is_file() else (x for x in p.rglob('*') if x.is_file()))
    files=sorted(p for p in files if '__pycache__' not in p.parts and p.suffix not in ('.pyc','.log') and p.name not in ('input_verification_second_attempt.json',))
    records=[]
    for p in files:
        rel=p.relative_to(ROOT).as_posix()
        assert not p.is_symlink() and not p.name.startswith('.env') and all(x not in rel.lower() for x in ('cookie','credential','security_code','browser_profile'))
        records.append(dict(path=rel,bytes=p.stat().st_size,sha256=sha(p)))
    manifest=ROOT/'MANIFEST.json';manifest.write_text(json.dumps({'entries':records,'role':'NEW_CODE_AND_RESULTS_PLUS_SINGLE_FROZEN_DEPENDENCY_ARCHIVE'},indent=2),encoding='utf8')
    out=ROOT/'delivery/OPEN_REVIEW.zip'
    if out.exists():raise FileExistsError('Archive is fixed; preserve prior archive before resealing')
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files+[manifest]:z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        for i in z.infolist():
            q=PurePosixPath(i.filename)
            assert '..' not in q.parts and not q.is_absolute() and ':' not in i.filename and not stat.S_ISLNK(i.external_attr>>16)
        assert len(z.namelist())==len(set(z.namelist()))
    receipt={'path':'delivery/OPEN_REVIEW.zip','sha256':sha(out),'bytes':out.stat().st_size,'members':len(files)+1,'crc':'PASS','paths':'PASS','sensitive_filename_check':'PASS','expanded_dependencies_included':False,'dependency':'input_contract/frozen/R4_CONTEXT_OPEN_REVIEW.zip staged by scripts/replay.py'}
    (ROOT/'delivery/archive_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt))
if __name__=='__main__':main()
