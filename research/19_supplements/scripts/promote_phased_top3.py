"""Run only after other writers stop; retain A1 and collect declared A2."""
from pathlib import Path
import json,hashlib,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q8-SCALE-LATENCY-BENCHMARK-R1'
assert json.loads((D/'outputs/replan_progress.json').read_text(encoding='utf-8'))['completed_workers']==11
p=D/'raw_results.jsonl';rows=[json.loads(x)for x in p.read_text(encoding='utf-8').splitlines()if x.strip()];old=[r for r in rows if r.get('query_type')=='TOP3_EXPERIMENTAL_ADAPTER'and r['run_id'].startswith('Q8-TOP3-ADAPTER-')]
assert len(old)==43,'No repeat promotion; old first measurement must be present exactly once'
secondary=D/'secondary_results';secondary.mkdir(exist_ok=True);out=secondary/'top3_A1_uninstrumented_raw_results.jsonl';assert not out.exists()
out.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in old),encoding='utf-8');(secondary/'primary_raw_before_A2_promotion.jsonl').write_bytes(p.read_bytes());keep=[r for r in rows if r not in old];temp=p.with_suffix('.tmp');temp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in keep),encoding='utf-8');temp.replace(p)
(secondary/'README.md').write_text('43次A1记录（3热身、30热、10冷）整体计时及路线仍有效；因未细分读取/索引，保留为补充版本，不与A2主统计混池。不属于失败路线或被按速度剔除。原输出和TOP3_*日志仍在原位置；执行源码在audit/EXECUTED_TOP3_WORKER_A1.py。',encoding='utf-8')
print('SECONDARY_A1_PRESERVED',hashlib.sha256(out.read_bytes()).hexdigest(),flush=True)
r=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'scripts/run_topk_phased_benchmark.py')],timeout=6600);raise SystemExit(r.returncode)
