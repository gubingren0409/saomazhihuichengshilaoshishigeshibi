"""Select only required benchmark files from the exact final baseline ZIP.

APP operation is self-contained and does not call this script. Regression is an
optional explicit dependency on one content-addressed baseline, not recursive
expansion of all historical projects. Existing destinations are never replaced.
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,io,json,re,stat,zipfile
ROOT=Path(__file__).resolve().parents[1]
EXPECTED='1d4110a76d0e5006f5c518366d82d6fb1aa98c8e46bac6956b2b0dbd91ccc77a'
FAILED={'W0caca58bc41_G_080','W902d9fe8127_G_080','W97b65e9a893_G_080','Wa273f228558_G_080'}

def sign(path):
    h=hashlib.sha256()
    with path.open('rb')as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def safe(name):
    name=name.replace('\\','/');p=PurePosixPath(name)
    if not name or p.is_absolute()or'..'in p.parts or re.match(r'^[A-Za-z]:',name):raise ValueError('UNSAFE_MEMBER '+name)
    return name

def main(args):
    baseline=args.baseline_zip.resolve();dest=args.destination.resolve()
    if sign(baseline)!=EXPECTED:raise ValueError('WRONG_BASELINE_FINAL_REPAIRED_SHA_REQUIRED')
    if dest.exists():raise FileExistsError('Choose a new empty destination, preserving earlier attempts: '+str(dest))
    dest.mkdir(parents=True);records=[]
    with zipfile.ZipFile(baseline)as z:
        seen=set()
        for info in z.infolist():
            name=safe(info.filename)
            if name.casefold()in seen or stat.S_ISLNK(info.external_attr>>16):raise ValueError('DUPLICATE_OR_SYMLINK '+name)
            seen.add(name.casefold())
        manifest=json.loads(z.read('MANIFEST.json'))['entries'];byname={e['path']:e for e in manifest}
        def get(name):
            data=z.read(name);e=byname[name]
            if digest(data)!=e['sha256']or len(data)!=e['bytes']:raise ValueError('MEMBER_HASH_MISMATCH '+name)
            return data
        def put(name,data,source_member,source_sha,role='EXACT_SELECTED_BASELINE_MEMBER'):
            p=dest/safe(name)
            if not p.resolve().is_relative_to(dest):raise ValueError('ESCAPED_DESTINATION')
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            records.append({'path':name,'bytes':len(data),'sha256':digest(data),'source_archive_sha256':EXPECTED,
                            'source_member':source_member,'source_member_sha256':source_sha,'role':role})
        inventory=json.loads(get('data/task_manifest.json'))
        rows=[r for r in inventory['instances']if r['panel']=='MAIN'or(args.include_natural and r.get('natural'))]
        inv={**inventory,'instances':rows,'staging_role':'EXACT_FIXED_ROWS_SELECTED_FROM_FINAL_BASELINE_NO_NEW_SAMPLE_SELECTION'}
        put('data/task_manifest.json',json.dumps(inv,ensure_ascii=False,indent=2).encode(),'data/task_manifest.json',byname['data/task_manifest.json']['sha256'],'DERIVED_MANIFEST_FIXED_ROW_SUBSET')
        members=set()
        for row in rows:
            ident=row['id'];members.update((row['observed'],row['query']))
            if row.get('reference'):members.add(row['reference'])
            for folder in ('common_guards_v2','common_guards_v3'):
                n=f'data/{folder}/{ident}.json'
                if n in byname:members.add(n)
            if row.get('natural'):members.update((row['route_graph'],f'data/classifier_cache/{ident}.json'))
            if ident in FAILED:
                members.update((f'data/constraints/{ident}.json',f'data/graphs/{ident}/F0.graph.json.gz'))
            for method in ('M1-C','F0','F1'):
                name=f'data/predictions/{ident}/{method}.json';data=get(name)
                if ident in FAILED and method=='F0':members.add(name);continue
                old=json.loads(data)
                comparison={'routes':old['routes'],'method':method,'input_id':ident,
                            'role':'ARCHIVED_ROUTE_COMPARISON_ONLY_NEVER_PREDICTOR_INPUT',
                            'original_prediction_sha256':digest(data),'original_archive_sha256':EXPECTED}
                put(name,json.dumps(comparison,ensure_ascii=False,separators=(',',':')).encode(),name,digest(data),'DERIVED_ARCHIVED_COMPARISON_FIELDS_ONLY')
        for name in sorted(members):
            data=get(name);put(name,data,name,digest(data))
        # One explicitly necessary nested member, never recursive archive expansion.
        nested='input_contract/frozen/R4_CONTEXT_OPEN_REVIEW.zip';container=get(nested)
        with zipfile.ZipFile(io.BytesIO(container))as inner:
            name='data/mask_dependency_ledger.jsonl';data=inner.read(name)
            put(name,data,nested+'!/'+name,digest(data),'EXACT_NESTED_MASK_LEDGER_TRUSTED_NEGATIVE_EXPORT_ONLY_NOT_WORKER_INPUT')
    receipt={'status':'SELECTIVE_CONTENT_ADDRESSED_STAGE_COMPLETE','baseline_sha256':EXPECTED,'files':records,
             'include_natural':args.include_natural,'old_routes_used_only_for_post_solve_comparison':True,
             'prediction_worker_inputs':'Observed, negative guards, config; query after surface freeze. No reference/raw map/old route payload.',
             'app_requires_this_stage':False,'nested_archive_expansion':'One named ledger file only'}
    (dest/'STAGING_MANIFEST.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':receipt['status'],'files':len(records),'bytes':sum(e['bytes']for e in records),'include_natural':args.include_natural,'destination':str(dest)},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline-zip',type=Path,required=True)
    p.add_argument('--destination',type=Path,default=ROOT/'runtime/regression_baseline')
    p.add_argument('--include-natural',action='store_true');main(p.parse_args())
