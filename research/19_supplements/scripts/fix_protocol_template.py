"""Metadata-only correction after the primary manager has stopped."""
from pathlib import Path
import hashlib,json,datetime
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'scripts/run_benchmark.py';before=p.read_bytes();target=ROOT/'audit/RUN_BENCHMARK_SOURCE_EXECUTED_A1.py'
if not target.exists():target.write_bytes(before)
s=before.decode('utf-8');s=s.replace('Lexicographically first native registered-door ID across 3 eligible frozen records; library. No library latency observed before lock. Not representative of all six scenes.','Lexicographic native registered-door ID selection was declared earlier. Library pilot latency was observed before the execution lock; this is unblinded engineering timing, not representative of all six scenes.')
p.write_text(s,encoding='utf-8');record={'timestamp':datetime.datetime.now().astimezone().isoformat(),'change':'Correct protocol generator chronology wording only, after main benchmark exit; no data, repeats, core or measured outputs changed','executed_source_sha256':hashlib.sha256(before).hexdigest(),'current_source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'executed_source_copy':'audit/RUN_BENCHMARK_SOURCE_EXECUTED_A1.py'};(ROOT/'audit/PROTOCOL_TEMPLATE_CORRECTION.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(record)
