import json, zipfile, hashlib, sys
from pathlib import Path, PurePosixPath
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
now=datetime.now().astimezone().isoformat()
for name in ('src','tests','config','data','runs','visuals','audits','delivery'):
    (ROOT/name).mkdir(exist_ok=True)
status={'task':'OSM-GEOAPIFY-R4-FREE-SPACE-R1','started_at':'2026-11-11T13:39:29+08:00','updated_at':now,'status':'RUNNING','phase':'implementation','active_compute_budget_s':14400,'max_region_builds':200,'external_requests':0,'training_runs':0,'entrance_generation':'DEFERRED_PENDING_USER_DESIGN','pending':['common guards','calibration','full paired matrix','north regression','sensitivity','independent review','map rendering','ZIP replay']}
if not (ROOT/'STATUS.json').exists(): (ROOT/'STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
if not (ROOT/'CHECKPOINT.md').exists(): (ROOT/'CHECKPOINT.md').write_text('# 检查点\n\n2026-11-11 13:39启动。完整阅读四文档，输入校验PASS（audits/input_verification.json）。正在建立共同约束与公平路由。尚无新实验结论。历史工程不变。\n',encoding='utf-8')
if not (ROOT/'RESULTS.md').exists(): (ROOT/'RESULTS.md').write_text('# 当前结果\n\n尚未验证。固定25任务41查询，主M1-C/F0/F1，30米域与1米格网不变。\n',encoding='utf-8')
archive=ROOT/'input_contract/frozen/R4_CONTEXT_OPEN_REVIEW.zip'
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='40f8e18d76d04819d66a3bd526ecb2b74fc83201b3b58452881a6576b6651cbf'
out=ROOT/'frozen_context'
if not out.exists():
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for x in z.infolist():
            p=PurePosixPath(x.filename)
            assert not p.is_absolute() and '..' not in p.parts and ':' not in str(p)
        z.extractall(out)
for rel in ['src/region.py','src/context_policy.py','src/region_routing.py','config/frozen_region.json']:
    dst=ROOT/('src/legacy_'+Path(rel).name if rel.startswith('src/') else rel)
    if not dst.exists(): dst.write_bytes((out/rel).read_bytes())
(ROOT/'src/__init__.py').touch(exist_ok=True)
print('STAGED',len(list(out.iterdir())), 'verification',json.loads((ROOT/'audits/input_verification.json').read_text(encoding='utf8'))['status'])
