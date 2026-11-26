"""Make a LOCAL source-only commit in the new clone; never push or choose a license."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT/'repository'
PREFIX=Path('rounds/PG1_RESUME_STREET_SIDE_R1')

def git(*args):
    r=subprocess.run(['git','-C',str(REPO),*args],capture_output=True,text=True,encoding='utf-8')
    if r.returncode:raise RuntimeError(r.stderr)
    return r.stdout.strip()

def main():
    target=ROOT/'audit/ROUND_BINDING.json'
    if target.exists():raise RuntimeError('Already frozen: inspect existing binding; do not silently recommit')
    assert git('rev-parse','HEAD')=='3134c0ea68e00871ed6dc86ca7bc905071449dae'
    assert not git('status','--porcelain')
    files=sorted(ROOT.glob('scripts/*.py'))+[ROOT/'maps/viewer.js',ROOT/'maps/viewer.css',ROOT/'README.md',ROOT/'DEPENDENCIES_AND_RIGHTS.md']
    patterns=[r'\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}',
              r'\bAKIA[0-9A-Z]{16}\b',r'\bAIza[0-9A-Za-z_-]{30,}',
              r'\bsk-(?:proj-)?[A-Za-z0-9_-]{25,}']
    records=[]
    for p in files:
        b=p.read_bytes();txt=b.decode('utf-8-sig')
        assert not any(re.search(pattern,txt)for pattern in patterns),p
        rel=p.relative_to(ROOT);dst=REPO/PREFIX/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dst)
        assert dst.read_bytes()==b
        records.append({'execution_copy':rel.as_posix(),'repository_path':(PREFIX/rel).as_posix(),
                        'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
    git('remote','set-url','origin','https://github.com/gubingren0409/saomazhihuichengshilaoshishigeshibi')
    git('add','--',PREFIX.as_posix())
    staged=git('diff','--cached','--name-only').splitlines()
    assert set(staged)=={r['repository_path']for r in records}
    git('-c','user.name=Codex Local Experiment','-c','user.email=codex-local@localhost',
        'commit','-m','Add bounded PG1 street-side trial source and local review tooling')
    sha=git('rev-parse','HEAD')
    for r in records:
        # Binary Git blob check prevents worktree filter mismatches.
        b=subprocess.run(['git','-C',str(REPO),'show',sha+':'+r['repository_path']],capture_output=True,check=True).stdout
        assert hashlib.sha256(b).hexdigest()==r['sha256']
    out={'round_id':'PG1-RESUME-STREET-SIDE-R1','bound_at':datetime.datetime.now().astimezone().isoformat(),
         'base_commit':'3134c0ea68e00871ed6dc86ca7bc905071449dae','final_local_commit':sha,
         'branch':git('branch','--show-current'),'repository':'gubingren0409/saomazhihuichengshilaoshishigeshibi',
         'source_prepared':True,'local_committed':True,'pushed':False,'GPT_remote_readback':False,
         'current_remote_state':'NOT_QUERIED_THIS_RESUME','first_public_push':'NOT_APPROVED_NOT_PERFORMED',
         'new_source_file_count':len(records),'source_files':records,'secret_scan':{'scope':'Only selected new text/source files; known token-prefix patterns; not a proof of universal secret absence','findings':0},
         'publication_boundary':'Old38 candidate list frozen. New private local source commit not added to approved public list; raw maps/results/coordinates excluded from this source commit; license not selected.'}
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'commit':sha,'source_files':len(records),'pushes':0}))

if __name__=='__main__':main()
