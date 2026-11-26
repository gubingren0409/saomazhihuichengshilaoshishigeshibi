"""Run the paired contract serially with resumable per-input outputs and explicit budget."""
import argparse,json,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return sha256(p.read_bytes()).hexdigest()
def combined(paths):return sha256(''.join(sha(p) for p in paths).encode()).hexdigest()
def run_one(row,sensitivity=True,timeout=480):
    ident=row['id'];out=ROOT/'data/predictions'/ident
    receipt=ROOT/'runs/executions'/f'{ident}.json'
    if receipt.exists():return read(receipt)
    if any(out.glob('*.json')):raise RuntimeError(f'Partial output exists, preserve as failed run before resume {ident}')
    code=combined(sorted((ROOT/'src').glob('*.py')))
    conf=combined([ROOT/'config/frozen_region.json',ROOT/'config/historical_methods.json',ROOT/'config/contract.json'])
    workers=ROOT/'runtime/workers';workers.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=ident+'_',dir=workers) as tmp:
        work=Path(tmp)
        inputs={'observed.json':ROOT/row['observed'],'query.json':ROOT/row['query'],
                'guards.json':ROOT/'data/common_guards_v2'/f'{ident}.json',
                'config.json':ROOT/'config/frozen_region.json','historical_methods.json':ROOT/'config/historical_methods.json'}
        if row.get('natural'):inputs['route_graph.json']=ROOT/row['route_graph']
        for dst,src in inputs.items():
            field={'observed.json':'observed','query.json':'query','route_graph.json':'route_graph'}.get(dst)
            if field and sha(src)!=row[field+'_sha256']:raise ValueError(f'Input identity mismatch {ident} {field}')
            shutil.copyfile(src,work/dst)
        cmd=[sys.executable,'-X','utf8','-B',str(ROOT/'src/predict_free.py'),'--input-id',ident,'--radius',str(row['context_radius_m']),'--code-sha',code,'--config-sha',conf]
        if row.get('natural'):cmd.append('--natural')
        if sensitivity:cmd.append('--sensitivity')
        start=time.perf_counter()
        done=subprocess.run(cmd,cwd=work,encoding='utf8',capture_output=True,timeout=timeout)
        if done.returncode:
            failure=ROOT/'runs/failures';failure.mkdir(exist_ok=True)
            p=failure/f'{ident}_{time.time_ns()}.json'
            p.write_text(json.dumps({'command':cmd,'stderr':done.stderr,'stdout':done.stdout,'code_sha256':code,'elapsed_s':time.perf_counter()-start},indent=2),encoding='utf8')
            raise RuntimeError(done.stderr)
        out.mkdir(parents=True,exist_ok=True)
        for p in work.glob('*.prediction.json'):shutil.copyfile(p,out/p.name.replace('.prediction',''))
        graphs=ROOT/'data/graphs'/ident;graphs.mkdir(parents=True,exist_ok=True)
        for p in work.glob('*.graph.json.gz'):shutil.copyfile(p,graphs/p.name)
        for name,folder in [('constraints.json','data/constraints'),('history.json','data/calibration')]:
            dst=ROOT/folder/f'{ident}.json';dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(work/name,dst)
        record=read(work/'execution.json')
        record.update(code_sha256=code,config_sha256=conf,wall_s=time.perf_counter()-start,
            region_builds=4,outputs={p.name:sha(p) for p in sorted(out.glob('*.json'))},panel=row['panel'])
        receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(json.dumps(record,indent=2),encoding='utf8')
        print(ident,len(record['runs']),round(record['wall_s'],2),'s',flush=True)
        return record
def main(args):
    rows=read(ROOT/'data/task_manifest.json')['instances']
    rows=[r for r in rows if (not args.ids or r['id'] in args.ids) and (not args.panel or r['panel'] in args.panel)]
    old=list((ROOT/'runs').glob('**/executions/*.json'))
    used=sum(read(p)['region_builds'] for p in old)+read(ROOT/'config/contract.json').get('synthetic_region_builds_before_replay',0)
    active=sum(read(p).get('wall_s',0) for p in old)
    for row in rows:
        existing=(ROOT/'runs/executions'/f"{row['id']}.json").exists()
        if not existing and (used+4>200 or active>=14400):
            print('BUDGET_STOP',row['id'],used,active);break
        rec=run_one(row,sensitivity=row.get('split') in ('development','selection') or row.get('natural',False))
        if not existing:used+=4;active+=rec['wall_s']
        status=read(ROOT/'STATUS.json');status.update(phase='paired_experiments',completed_inputs=len(list((ROOT/'runs/executions').glob('*.json'))),region_builds=used,active_worker_wall_s=active)
        (ROOT/'STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ids',nargs='+');p.add_argument('--panel',nargs='+');main(p.parse_args())
