"""Fixed lightweight archive: explicit allowlist, CRC and content hashes.

The final independent replay receipt is deliberately outside the ZIP and binds
its final SHA. Never include live service/latest-progress files or temp copies.
"""
from pathlib import Path,PurePosixPath
import json,hashlib,zipfile,argparse,datetime
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def permitted(p):
    rel=p.relative_to(ROOT);parts=rel.parts
    if p.is_symlink()or any(x in parts for x in('__pycache__','.git','node_modules','runtime','delivery','.pytest_cache')):return False
    if p.suffix in('.pyc','.log','.tmp')or p.name.startswith('.env'):return False
    if parts[0]=='runs':
        return len(parts)>2 and parts[1]in('app','mechanisms','preprocessing')and p.suffix=='.json'
    if parts[0]=='figures':return False # figures duplicate visuals; one physical copy only
    if parts[0]=='visuals':return p.suffix in('.png','.svg','.json','.pdf','.md')
    if parts[0]in('app','src','scripts','tests','config','data','results','audits','input_contract','reviews','manifests'):return True
    return len(parts)==1 and p.suffix in('.md','.html','.json','.txt')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    archive=a.output.resolve();archive.parent.mkdir(parents=True,exist_ok=True)
    if archive.exists():raise SystemExit('REFUSE_OVERWRITE_FIXED_ARCHIVE')
    paths=[p for p in sorted(ROOT.rglob('*'))if p.is_file()and permitted(p)and p.name!='MANIFEST_SHA256.json']
    names={p.relative_to(ROOT).as_posix()for p in paths}
    required={'app/index.html','app/app.js','app/app.css','app/diagnosis.html','app/diagnosis.js',
        'src/planner.py','src/connectivity.py','scripts/serve_app.py','scripts/plan.py','requirements.txt',
        'README.md','METHOD.md','RESULTS.md','DECISION_BRIEF.md','EXPERIMENT_BRIEF.md','index.html',
        'results/summary.json','results/sample_results.csv','results/segment_evidence.csv',
        'results/interface_evidence.csv','results/component_statistics.csv','results/interface_component_membership.csv',
        'results/component_analysis_receipt.json','audits/independent_review.md'}
    missing=sorted(required-names)
    if missing:raise ValueError('DELIVERY_REQUIRED_MEMBERS_MISSING:'+json.dumps(missing))
    for scene in json.loads((ROOT/'data/scene_manifest.json').read_text(encoding='utf-8-sig'))['scenes']:
        for key in('source_path','mapped_edges_path'):
            if scene[key]not in names:raise ValueError('BOUND_SOURCE_NOT_PACKED:'+scene[key])
    manifest={'schema':'RELATIVE_MEMBER_SHA256_V1','task':'OSM-GEOAPIFY-PED-AREA-CONNECTIVITY-R1','sealed_at':datetime.datetime.now().astimezone().isoformat(),
        'files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}for p in paths],
        'excluded':'runtime copies, caches, current service/latest progress, logs, duplicate figures, old full archives and models; independent postseal receipt outside ZIP',
        'self_containment':'New solver/source sixclips/queries/code/figures included. Historical baseline authority remains SHA-referenced; no field passability truth included.'}
    mp=ROOT/'MANIFEST_SHA256.json';mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
        for p in paths+[mp]:
            name=p.relative_to(ROOT).as_posix()
            if PurePosixPath(name).is_absolute()or'..'in PurePosixPath(name).parts:raise ValueError('UNSAFE_MEMBER')
            z.write(p,name)
    with zipfile.ZipFile(archive)as z:
        bad=z.testzip()
        if bad:raise ValueError('CRC_FAILED:'+bad)
        for row in manifest['files']:
            data=z.read(row['path'])
            if len(data)!=row['bytes']or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('MEMBER_CHANGED:'+row['path'])
    receipt={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive),'members':len(paths)+1,'content_manifest_entries':len(paths),'CRC':'PASS','all_member_SHA256':'PASS',
        'independent_clean_replay':'PENDING_EXTERNAL_RECEIPT','manifest_sha256':sha(mp)}
    out=archive.with_suffix('.build_receipt.json');out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()
