"""Seal new diagnosis artifacts only. The referenced R1 archive is never copied."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,zipfile,datetime
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def permitted(p):
    rel=p.relative_to(ROOT)
    if any(x in rel.parts for x in('delivery','runtime','scratch','__pycache__','.git','node_modules','.pytest_cache')):return False
    if p.suffix in('.pyc','.tmp','.log')or p.name.startswith('.env')or p.name in('service.json','map_service.json','MANIFEST_SHA256.json'):return False
    return True
def main():
    a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    output=args.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise ValueError('REFUSE_OVERWRITE_FIXED_ARCHIVE')
    paths=[p for p in sorted(ROOT.rglob('*'))if p.is_file()and permitted(p)]
    names={p.relative_to(ROOT).as_posix()for p in paths}
    required={'README.md','ROUTE_DIAGNOSIS.md','BUSINESS_ROUTE_OPPORTUNITY.md','COMPONENT_LINEAGE.md','INTERFACE_USAGE_AUDIT.csv','NEW_FACE_ROUTE_RELEVANCE.csv','ALTERNATIVE_ROUTES.csv','visuals/index.html','audits/INDEPENDENT_REVIEW.md','STATUS.json'}
    if required-names:raise ValueError('MISSING_REQUIRED:'+str(sorted(required-names)))
    manifest={'sealed_at':datetime.datetime.now().astimezone().isoformat(),'files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}for p in paths],
        'historical_R1_SHA256':'d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed','dependency_note':'R1 authority is separately referenced; reproducibility scope is stated in README. No old archive/model duplicated.'}
    mp=ROOT/'MANIFEST_SHA256.json';mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
        for p in paths+[mp]:
            name=p.relative_to(ROOT).as_posix()
            if PurePosixPath(name).is_absolute()or'..'in PurePosixPath(name).parts:raise ValueError('UNSAFE_MEMBER')
            z.write(p,name)
    with zipfile.ZipFile(output)as z:
        if z.testzip():raise ValueError('CRC_FAILED')
        for row in manifest['files']:
            h=hashlib.sha256();size=0
            with z.open(row['path'])as f:
                for b in iter(lambda:f.read(1048576),b''):h.update(b);size+=len(b)
            if size!=row['bytes']or h.hexdigest()!=row['sha256']:raise ValueError('CONTENT_CHANGED:'+row['path'])
    receipt={'archive':str(output),'bytes':output.stat().st_size,'sha256':sha(output),'members':len(paths)+1,'CRC':'PASS','all_content_SHA':'PASS','postseal_independent_receipt':'PENDING_OUTSIDE_ARCHIVE'}
    output.with_suffix('.build_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()
