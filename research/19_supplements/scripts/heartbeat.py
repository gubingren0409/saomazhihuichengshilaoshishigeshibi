"""Read-only process observation plus a small resumable task heartbeat."""
from pathlib import Path
import psutil,json,datetime,time
ROOT=Path(__file__).resolve().parents[1];now=time.time();processes=[]
for p in psutil.process_iter(['pid','name','cmdline','create_time','memory_info','cpu_times']):
 try:
  if p.info['name'].lower()not in('python.exe','pythonw.exe','python'):continue
  cmd=p.info['cmdline']or[]
  if not any('benchmark_joint_worker.py'in s or'run_joint_benchmark.py'in s for s in cmd):continue
  processes.append({'pid':p.pid,'script':[s for s in cmd if s.endswith('.py')],'elapsed_s':now-p.info['create_time'],'CPU_s':p.info['cpu_times'].user+p.info['cpu_times'].system,'RSS_bytes':p.info['memory_info'].rss})
 except(psutil.NoSuchProcess,psutil.AccessDenied):pass
progress=ROOT/'Q8-SCALE-LATENCY-BENCHMARK-R1/outputs/joint_progress.json';data={'timestamp':datetime.datetime.now().astimezone().isoformat(),'kind':'PROCESS_OBSERVATION_NOT_SCIENTIFIC_RESULT','processes':processes,'joint_worker_progress':json.loads(progress.read_text())if progress.exists()else None}
(ROOT/'audit/HEARTBEAT_CURRENT.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
with(ROOT/'audit/HEARTBEATS.jsonl').open('a',encoding='utf-8')as f:f.write(json.dumps(data,ensure_ascii=False)+'\n')
print(json.dumps(data,ensure_ascii=False))
