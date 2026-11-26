"""Independent exact Git-tree inventory/bytes and secret/data-boundary review.

Reports only file/line/rule, never suspected credential text.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,subprocess,csv
ROOT=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser();ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--commit',required=True);args=ap.parse_args();repo=ROOT/'repository'
def git(*argv):
    r=subprocess.run(['git','--no-optional-locks',*argv],cwd=repo,capture_output=True,timeout=30)
    assert r.returncode==0
    return r.stdout
records=list(csv.DictReader(args.inventory.open(encoding='utf-8-sig',newline='')))if args.inventory.suffix.lower()=='.csv'else json.loads(args.inventory.read_text(encoding='utf-8-sig'))
records=records['files']if isinstance(records,dict)else records
listed={r['path'].replace('\\','/'):r for r in records}
names=git('ls-tree','-r','--name-only',args.commit).decode('utf8').splitlines()
assert set(listed)==set(names)
patterns={
 'credential_prefix':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}|AKIA[0-9A-Z]{16})\b'),
 'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'credential_assignment':re.compile(r'''(?i)\b(?:api[_-]?key|access[_-]?token|password|secret)\b\s*[:=]\s*["']([^"'\s]{12,})'''),
 'private_absolute_path':re.compile(r'(?i)\b[A-Z]:[\\/](?:Users|智慧城市)'),
 'frozen_latlon':re.compile(r'\b(?:121\.\d{4,}|31\.2\d{4,}|24\.9\d{4,}|60\.1\d{4,}|-73\.9\d{4,}|40\.7\d{4,})\b'),
}
findings=[];checked=[]
for name in names:
    p=repo/name;working=p.read_bytes();blob=git('show',args.commit+':'+name);digest=hashlib.sha256(blob).hexdigest()
    assert working==blob and digest==listed[name]['sha256']and len(blob)==int(listed[name]['bytes'])
    if p.is_symlink()or any(part in {'data','samples','runs','cache','delivery','.git','__pycache__'}for part in Path(name).parts):findings.append({'path':name,'rule':'restricted_path_family'})
    if p.suffix.lower()in{'.osm','.gz','.zip','.npz','.pkl','.png','.jpg','.pdf','.exe','.dll'}:findings.append({'path':name,'rule':'restricted_binary_or_data_suffix'})
    if len(blob)>5_000_000:findings.append({'path':name,'rule':'large_file'})
    try:text=blob.decode('utf8')
    except UnicodeDecodeError:findings.append({'path':name,'rule':'non_utf8_public_file'});continue
    for lineno,line in enumerate(text.splitlines(),1):
        for rule,pattern in patterns.items():
            if pattern.search(line):findings.append({'path':name,'line':lineno,'rule':rule})
    checked.append({'path':name,'bytes':len(blob),'sha256':digest})
historical_blobs=0
for record in git('rev-list','--objects',args.commit).decode('utf8').splitlines():
    objectid,_,name=record.partition(' ')
    if git('cat-file','-t',objectid).strip()!=b'blob':continue
    historical_blobs+=1;blob=git('cat-file','blob',objectid)
    try:text=blob.decode('utf8')
    except UnicodeDecodeError:findings.append({'path':name,'object':objectid,'rule':'historical_non_utf8_blob'});continue
    for lineno,line in enumerate(text.splitlines(),1):
        for rule,pattern in patterns.items():
            if pattern.search(line):findings.append({'path':name,'object':objectid,'line':lineno,'rule':'reachable_history_'+rule})
status=git('status','--porcelain=v1').decode('utf8')
remotes=git('remote','get-url','origin').decode('utf8').strip()
assert remotes=='https://github.com/gubingren0409/saomazhihuichengshilaoshishigeshibi.git'
assert not status
out={'at_utc':datetime.now(timezone.utc).isoformat(),'commit':args.commit,'repository':'gubingren0409/saomazhihuichengshilaoshishigeshibi','tree_file_count':len(names),'reachable_historical_blobs_scanned':historical_blobs,'reachable_commit_count':len(git('rev-list',args.commit).splitlines()),'inventory_sha256':hashlib.sha256(args.inventory.read_bytes()).hexdigest(),'all_git_blob_worktree_inventory_bytes_equal':True,'working_tree_clean':not status,'findings':findings,'checked_files':checked,'first_public_push':'NOT_APPROVED_NOT_PERFORMED_BY_REVIEWER','license':'New-source copyright/license choice remains user decision; raw and derived map database excluded. Public visibility is not an open-source license.','scope_limit':'Independent regex/content boundary review is not a legal rights opinion or proof of absence of all secrets.'}
(ROOT/'reviews/independent_public_release.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'tree_files':len(names),'findings':len(findings),'commit':args.commit,'clean':not status}))
assert not findings
