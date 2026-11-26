from pathlib import Path
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q8-SCALE-LATENCY-BENCHMARK-R1'
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'svg.fonttype':'none','font.size':10})
rows=list(csv.DictReader((D/'latency_distribution.csv').open(encoding='utf-8-sig')));quality=list(csv.DictReader((D/'route_quality_comparison.csv').open(encoding='utf-8-sig')))
def save(fig,name):
 (D/'figures').mkdir(exist_ok=True);fig.savefig(D/f'figures/{name}.png',dpi=170,bbox_inches='tight');fig.savefig(D/f'figures/{name}.svg',bbox_inches='tight');plt.close(fig)
select=lambda **kw:[r for r in rows if all(r[k]==v for k,v in kw.items())]
fig,axs=plt.subplots(1,2,figsize=(13,5));sel=select(query_type='SINGLE_SHORTEST_PATH',method='F1',mode='FULL_FACE')
for ax,temp,metric,title in zip(axs,['HOT_PROCESS','COLD_PROCESS'],['end_to_end_worker_ms','cold_process_end_to_end_ms'],['热进程核心请求','冷进程端到端']):
 points=[]
 for r in sel:
  if r['temperature']!=temp or r['timing_scope']!=metric:continue
  q=next(q for q in quality if all(q[k]==r[k]for k in('scale','query_type','mode','method','temperature')));nodes=__import__('json').loads(q['graph_nodes'])[0];points.append((nodes,float(r['p95_ms']),float(r['max_ms']),'小裁片'if r['scale'].startswith('SMALL')else'两裁片合并'))
 points.sort()
 for x,y,m,label in points:ax.scatter(x,y,s=65);ax.scatter(x,m,marker='x',s=65);ax.annotate(f'{label}\np95={y:.1f}\nmax={m:.1f}',(x,y),xytext=(8,10),textcoords='offset points',fontsize=9)
 ax.axhline(1000,c='#b33131',ls='--',label='1000 ms');ax.set_title(title+'：FULL_FACE / F1 / 单入口');ax.set_xlabel('实际求路图节点数');ax.set_ylabel('毫秒');ax.set_ylim(bottom=0);ax.margins(x=.25,y=.3)
fig.suptitle('规模—耗时：仅两个已暴露、重叠输入规模；未测城市级，不外推复杂度');save(fig,'scale_latency')
fig,ax=plt.subplots(figsize=(9,5))
for scope,temp,col in [('solver_ms','HOT_PROCESS','#246e83'),('end_to_end_worker_ms','HOT_PROCESS','#d18a2f'),('cold_process_end_to_end_ms','COLD_PROCESS','#923d62')]:
 candidates=select(scale='SMALL_FROZEN_LIBRARY_ONLY',query_type='SINGLE_SHORTEST_PATH',mode='FULL_FACE',method='F1',temperature=temp,timing_scope=scope)
 if candidates:ax.scatter(1,float(candidates[0]['p95_ms']),s=60,c=col,label=scope)
for scope,temp,col in [('solver_ms','HOT_PROCESS','#246e83'),('end_to_end_worker_ms','HOT_PROCESS','#d18a2f'),('cold_process_end_to_end_ms','COLD_PROCESS','#923d62')]:
 candidates=select(scale='SMALL_FROZEN_MUSEUM_TWO_DOORS',query_type='MULTI_ENTRANCE_K2_SEQUENTIAL_COST_SELECTION_ADAPTER',mode='FULL_FACE',method='F1',temperature=temp,timing_scope=scope)
 if candidates:ax.scatter(2,float(candidates[0]['p95_ms']),s=65,c=col,marker='^',label='K2不同场地 / '+scope)
ax.set_yscale('log');ax.set_xscale('log');ax.set_xticks([1,2,10,100],['1','2','10','100']);ax.set_xlim(.75,140);ax.text(10,100,'K10缺合格入口',rotation=45);ax.text(72,100,'K100缺合格入口',rotation=45);ax.set_xlabel('真实候选入口数量；K1/K2不同输入，不能据此拟合候选复杂度');ax.set_ylabel('p95 毫秒（对数轴）');ax.axhline(1000,c='#b33131',ls='--');ax.legend(fontsize=7);ax.set_title('候选数—耗时：仅真实观测点，不补造K10/100或连线作因果推断');save(fig,'candidate_count_latency')
fig,ax=plt.subplots(figsize=(14,6));configs=[]
for scale in('SMALL_FROZEN_LIBRARY_ONLY','MEDIUM_TWO_OVERLAPPING_FROZEN_CROPS'):
 for mode in('EDGE_BAND','FULL_FACE'):
  for method in('F0','F1'):
   hot=select(scale=scale,query_type='SINGLE_SHORTEST_PATH',mode=mode,method=method,temperature='HOT_PROCESS',timing_scope='end_to_end_worker_ms');cold=select(scale=scale,query_type='SINGLE_SHORTEST_PATH',mode=mode,method=method,temperature='COLD_PROCESS',timing_scope='cold_process_end_to_end_ms')
   if hot and cold:configs.append((('小图'if scale.startswith('SMALL')else'合并图')+'\n'+mode+'\n'+method,float(hot[0]['p95_ms']),float(cold[0]['p95_ms'])))
x=np.arange(len(configs));ax.bar(x-.18,[z[1]for z in configs],.36,label='热core p95（不含后续落盘）');ax.bar(x+.18,[z[2]for z in configs],.36,label='冷进程端到端p95');ax.set_xticks(x,[z[0]for z in configs],fontsize=8);ax.set_yscale('log');ax.axhline(1000,c='#b33131',ls='--');ax.set_ylabel('毫秒（对数轴）');ax.legend();ax.set_title('冷/热计时口径不能互换；每配置热30次、冷10次，warm-up另排除');save(fig,'cold_hot_comparison')
print('PERFORMANCE_PLOTS_COMPLETE')
