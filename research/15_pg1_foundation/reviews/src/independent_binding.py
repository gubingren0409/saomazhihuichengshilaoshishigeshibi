"""Independent bundle, exact source snapshot and executed-base-code binding."""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,os,subprocess
ROOT=Path(__file__).resolve().parents[2]
REPO=Path(os.environ.get('PG1_REVIEW_LIVE_REPOSITORY',ROOT/'repository'))
def git(*args):
    r=subprocess.run(['git','--no-optional-locks',*args],cwd=REPO,capture_output=True,timeout=45);assert r.returncode==0,r.stderr.decode('utf8','replace');return r.stdout
binding=json.loads((ROOT/'audit/ROUND_BINDING.json').read_text(encoding='utf8'))
inventory=list(csv.DictReader((ROOT/'audit/PUBLIC_FILE_INVENTORY.csv').open(encoding='utf-8-sig',newline='')))
assert hashlib.sha256((ROOT/'audit/PUBLIC_FILE_INVENTORY.csv').read_bytes()).hexdigest()==binding['inventory_sha256']
assert git('rev-parse',binding['final_commit']+'^{tree}').decode().strip()==binding['tree_sha']
assert len(git('rev-list',binding['final_commit']).splitlines())==binding['reachable_commit_count']==3
assert {r['path']for r in inventory}==set(git('ls-tree','-r','--name-only',binding['final_commit']).decode('utf8').splitlines())
for row in inventory:
    body=(ROOT/'repository'/row['path']).read_bytes()
    assert body==git('show',binding['final_commit']+':'+row['path'])
    assert hashlib.sha256(body).hexdigest()==row['sha256']and len(body)==int(row['bytes'])
bundle=ROOT/'git/PG1_SOURCE.bundle';assert hashlib.sha256(bundle.read_bytes()).hexdigest()==binding['bundle_sha256']
verify=git('bundle','verify',str(bundle));heads=git('bundle','list-heads',str(bundle)).decode('utf8').splitlines()
assert len(heads)==2 and all(h.split()[0]==binding['final_commit']for h in heads)
mirrors=json.loads((ROOT/'audit/public_source_integration.json').read_text(encoding='utf8'))['rows']
for row in mirrors:
    a=(ROOT/row['source']).read_bytes();b=(ROOT/'repository'/row['public_path']).read_bytes()
    assert a==b and hashlib.sha256(a).hexdigest()==row['sha256']
protocol=json.loads((ROOT/'track_a/TA-PG1-01/protocol.json').read_text(encoding='utf8'))
for name,digest in protocol['code'].items():
    assert hashlib.sha256(git('show',binding['bootstrap_and_experiment_base_commit']+':'+name.replace('\\','/'))).hexdigest()==digest
out={'at_utc':datetime.now(timezone.utc).isoformat(),'status':'PASS_EXACT_SOURCE_COMMIT_BUNDLE_AND_EXECUTED_BASE_BINDING','final_commit':binding['final_commit'],'tree_sha':binding['tree_sha'],'source_file_count':len(inventory),'reachable_local_commits':3,'complete_git_bundle_sha256':binding['bundle_sha256'],'bundle_refs':heads,'public_private_source_mirrors':len(mirrors),'executed_track_a_base_commit':binding['bootstrap_and_experiment_base_commit'],'executed_code_hashes_verified':protocol['code'],'remote_pushes':'NONE_BY_REVIEWER; first push requires user approval'}
(ROOT/'reviews/independent_binding.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'files':len(inventory),'source_mirrors':len(mirrors),'final_commit':binding['final_commit'],'bundle':'PASS','executed_base_code':'PASS'}))
