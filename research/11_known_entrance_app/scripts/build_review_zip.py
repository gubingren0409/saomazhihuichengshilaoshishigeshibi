"""Build a fixed, selective review snapshot; --plan never creates an archive.

Existing archives/receipts are never replaced. Runtime caches, live service state,
and repeated historical workers are excluded. APP data and main25 replay inputs
are included; NORTH's large historical dependencies are content-addressed outside.
"""
from pathlib import Path,PurePosixPath
from collections import Counter,defaultdict
from datetime import datetime
import argparse,hashlib,json,os,re,shutil,stat,zipfile,zlib

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES={'README.md','SCOPE_AND_VERSION.md','RESULTS.md','INPUT_OUTPUT_CONTRACT.md',
            'USER_REVIEW_NOTES.md','STATUS.json','CHECKPOINT.md','FAILURE_DIAGNOSIS.csv',
            'EXPERIMENT_BRIEF.md','PROCESS_RECORD.md','requirements.txt','LICENSE','NOTICE'}
REQUIRED_ROOT={'README.md','SCOPE_AND_VERSION.md','RESULTS.md','INPUT_OUTPUT_CONTRACT.md',
               'USER_REVIEW_NOTES.md','STATUS.json','CHECKPOINT.md','FAILURE_DIAGNOSIS.csv'}
TREES={'src','app','scripts','config','tests','data','visuals','AUDIT','runs'}
SKIP_DIRS={'__pycache__','runtime','logs','.git','.pytest_cache','.mypy_cache','node_modules','delivery'}
NORTH_BIG={'observed.json','route_graph.json','classifier_cache.json'}
R2_FILES={'observed.json','query.json','guards.json','config.json','methods.json','version.json',
          'input_bindings.json','freeze.json','result.json','graphs.json.gz','surfaces.json.gz','execution.json'}

def safe(name):
    p=PurePosixPath(name)
    if not name or'\\'in name or p.is_absolute()or'..'in p.parts or re.match(r'^[A-Za-z]:',name):
        raise ValueError('UNSAFE_ARCHIVE_PATH: '+name)
    return name

def reparse(path):
    s=path.lstat()
    return stat.S_ISLNK(s.st_mode)or bool(getattr(s,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400))

def selected(rel):
    p=PurePosixPath(rel);parts=p.parts;name=p.name;lower=name.lower()
    if len(parts)==1:return name in ROOT_FILES
    if parts[0]not in TREES:return False
    if any(s.lower()in SKIP_DIRS for s in parts):return False
    if lower.startswith('.env')or p.suffix.lower()in {'.zip','.log','.pyc','.pyo','.pem','.key','.pfx','.p12'}:return False
    if 'stderr'in lower or'stdout'in lower:return False
    if parts[0]!='runs':return True
    if len(parts)==2:return False  # live service.json, PID, stdout/stderr
    branch=parts[1]
    if branch in {'progress','logs'}:return False
    if branch in {'app','preprocessing','acceptance','performance'}:
        return name!='progress.json'
    if branch!='benchmark'or len(parts)<4:return False
    suite=parts[2]
    if suite=='R2_unified':
        return name in ({'summary.json','query_comparison.csv'}if len(parts)==4 else R2_FILES)
    if suite=='NORTH_regression':return name not in NORTH_BIG
    if suite=='R1_cold':return len(parts)==4 and name in {'summary.json','query_comparison.csv'}
    if suite=='R3_staging_smoke':
        return name in ({'summary.json','query_comparison.csv'}if len(parts)==4 else {'result.json','execution.json','version.json','freeze.json','input_bindings.json'})
    if suite=='SOUTH_source_R1':return len(parts)==4 and name=='result.json'
    return False

def files():
    result=[]
    for p in sorted(ROOT.iterdir()):
        if p.is_file()and selected(p.name):
            if reparse(p):raise ValueError('REPARSE_SOURCE: '+p.name)
            result.append(p)
    for name in sorted(TREES):
        start=ROOT/name
        if not start.exists():continue
        if reparse(start):raise ValueError('REPARSE_SOURCE: '+name)
        for folder,dirs,names in os.walk(start,followlinks=False):
            current=Path(folder)
            dirs[:]=sorted(d for d in dirs if d.lower()not in SKIP_DIRS)
            for d in dirs:
                if reparse(current/d):raise ValueError('REPARSE_DIRECTORY: '+str((current/d).relative_to(ROOT)))
            for filename in sorted(names):
                path=current/filename;rel=path.relative_to(ROOT).as_posix()
                if not selected(rel):continue
                if reparse(path)or not path.is_file()or not path.resolve().is_relative_to(ROOT.resolve()):
                    raise ValueError('UNSAFE_SOURCE: '+rel)
                result.append(path)
    return sorted(result,key=lambda p:p.relative_to(ROOT).as_posix())

def sha(path):
    h=hashlib.sha256()
    with path.open('rb')as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def plan(estimate=False):
    paths=files();groups=defaultdict(lambda:{'files':0,'bytes':0});compressed=0
    for path in paths:
        rel=path.relative_to(ROOT).as_posix();safe(rel)
        g=groups[rel.split('/')[0]if'/'in rel else'ROOT'];g['files']+=1;g['bytes']+=path.stat().st_size
        if estimate:
            compressor=zlib.compressobj(6,zlib.DEFLATED,-15)
            with path.open('rb')as f:
                for block in iter(lambda:f.read(1024*1024),b''):compressed+=len(compressor.compress(block))
            compressed+=len(compressor.flush())+len(rel.encode('utf-8'))*2+100
    return paths,{'role':'PROPOSED_MEMBERS_NOT_SEALED_ARCHIVE','files':len(paths),'uncompressed_bytes':sum(p.stat().st_size for p in paths),
                  'estimated_zip_bytes':compressed+len(paths)*200 if estimate else None,'groups':dict(groups),
                  'exclusions':['runtime and caches','logs/PID/service state/stdout/stderr','all nested ZIPs and delivery','NORTH three large dependencies','duplicate cold/diagnostic worker inputs'],
                  'north_dependency_index':'AUDIT/review_external_dependencies.json','app_inputs_included':True,'main25_selected_baseline_included':True,
                  'missing_required_root_files':sorted(n for n in REQUIRED_ROOT if not(ROOT/n).is_file())}

def verify(path):
    seen=set()
    with zipfile.ZipFile(path)as z:
        for info in z.infolist():
            name=safe(info.filename)
            if info.is_dir()or name.casefold()in seen or stat.S_ISLNK(info.external_attr>>16):raise ValueError('UNSAFE_OR_DUPLICATE_ZIP_MEMBER: '+name)
            seen.add(name.casefold())
        bad=z.testzip()
        if bad:raise ValueError('CRC_FAILED: '+bad)
        manifest_bytes=z.read('MANIFEST.json');manifest=json.loads(manifest_bytes);entries=manifest['entries'];listed=set()
        for row in entries:
            name=safe(row['path'])
            if name in listed or name=='MANIFEST.json':raise ValueError('DUPLICATE_OR_SELF_HASHED_MANIFEST_MEMBER')
            listed.add(name);data=z.read(name)
            if len(data)!=row['bytes']or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('MEMBER_HASH_FAILED: '+name)
        if set(z.namelist())!=listed|{'MANIFEST.json'}:raise ValueError('ZIP_MANIFEST_SET_DIFFERS')
    return {'status':'PASS_ARCHIVE_INTEGRITY_NOT_APP_REPLAY','archive':str(path.resolve()),'bytes':path.stat().st_size,'sha256':sha(path),
            'members':len(entries)+1,'manifest_entries':len(entries),'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
            'crc':'PASS','member_hashes':'PASS','member_set':'EXACT_MANIFEST_PLUS_SELF','path_safety':'PASS','symlinks':'NONE',
            'limitations':['Archive integrity is not independent algorithm review','Clean-unpack server/new-query replay requires a separate receipt','No source selection or field-truth claim']}

def build(output):
    output=output.resolve();delivery=(ROOT/'delivery').resolve()
    if not output.is_relative_to(delivery)or output.suffix.lower()!='.zip':raise ValueError('--output must be a ZIP under this new task delivery directory')
    receipt=output.parent/(output.stem+'_VERIFICATION.json');partial=output.with_suffix(output.suffix+'.partial')
    if output.exists()or partial.exists()or receipt.exists():raise FileExistsError('Refusing to replace archive, partial archive or receipt')
    output.parent.mkdir(parents=True,exist_ok=True)
    paths,proposal=plan();entries=[]
    if proposal['missing_required_root_files']:raise ValueError('MISSING_FINAL_DOCUMENTS: '+','.join(proposal['missing_required_root_files']))
    with partial.open('xb')as handle:
        with zipfile.ZipFile(handle,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
            for path in paths:
                rel=safe(path.relative_to(ROOT).as_posix());data=path.read_bytes()
                entries.append({'path':rel,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
                z.writestr(rel,data)
            manifest={'task':ROOT.name,'created_at':datetime.now().astimezone().isoformat(),'policy':'SELECTIVE_KNOWN_ENTRANCE_E2E_R1_REVIEW_V1',
                      'manifest_self_hash_excluded':True,'proposal':proposal,'external_dependencies':'AUDIT/review_external_dependencies.json','entries':entries}
            z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    if [p.relative_to(ROOT).as_posix()for p in files()]!=[e['path']for e in entries]:raise ValueError('SELECTED_SOURCE_SET_CHANGED_DURING_PACKAGING; partial preserved')
    for row in entries:
        path=ROOT/row['path']
        if path.stat().st_size!=row['bytes']or sha(path)!=row['sha256']:raise ValueError('SOURCE_CHANGED_DURING_PACKAGING: '+row['path'])
    verify(partial)
    # Exclusive creation is portable and cannot overwrite an existing fixed ZIP.
    with partial.open('rb')as src,output.open('xb')as dst:shutil.copyfileobj(src,dst,1024*1024)
    result=verify(output);result['source_snapshot_stable']=True;result['external_dependency_index']='AUDIT/review_external_dependencies.json'
    with receipt.open('x',encoding='utf-8')as f:json.dump(result,f,ensure_ascii=False,indent=2)
    if partial.resolve().parent!=delivery and not partial.resolve().is_relative_to(delivery):raise ValueError('UNEXPECTED_PARTIAL_PATH')
    partial.unlink()  # only this successfully verified, newly created temporary file
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'delivery/OPEN_REVIEW.zip')
    p.add_argument('--plan',action='store_true');p.add_argument('--estimate-compression',action='store_true');p.add_argument('--verify-only',action='store_true');args=p.parse_args()
    if args.plan:_,result=plan(args.estimate_compression)
    elif args.verify_only:result=verify(args.output)
    else:result=build(args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))
