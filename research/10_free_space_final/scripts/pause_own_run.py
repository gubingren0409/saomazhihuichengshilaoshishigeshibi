import psutil,os,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
stopped=[]
for p in psutil.process_iter(['cmdline']):
    try:
        if p.pid==os.getpid() or not any('scripts/run_free.py' in x for x in (p.info['cmdline'] or [])):continue
        if Path(p.cwd()).resolve()!=ROOT:continue
        children=p.children(recursive=True)
        stopped.append(dict(pid=p.pid,children=[c.pid for c in children]))
        for c in children:c.terminate()
        p.terminate()
    except (psutil.Error,OSError):pass
record={'reason':'independent geometry partition overlap defect; stop own batch before source edit','stopped':stopped,'completed':[p.stem for p in (ROOT/'runs/executions').glob('*.json')], 'active_workers':[str(p.relative_to(ROOT)) for p in (ROOT/'runtime/workers').iterdir()]}
(ROOT/'audits/pause_partition_fix.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print(record)
