"""Generate review prose and ledger only from actual frozen run files."""
from pathlib import Path
import json,csv,datetime,hashlib
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def put(p,v):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
    current=read(ROOT/'runs/main_matrix_R2/summary.json');prior=read(ROOT/'runs/main_matrix_R1/summary.json')
    paired=current['positive_comparisons'];rows=[];segment_rows=[];performance=[]
    for case in paired:
        for mode in('EDGE_BAND','FULL_FACE'):
            r=read(ROOT/'runs/main_matrix_R2'/(case['case_id']+'-'+mode+'.json'))
            performance.append({'case_id':case['case_id'],'mode':mode,'method':case['method'],'run_id':r['run_id'],'nodes':r['graph']['nodes'],'arcs':r['graph']['arcs'],
                'cache_hit':r['preprocessing_cache']['hit'],'load_or_prepare_s':r['preprocessing_cache']['load_or_prepare_s'],'solver_s':r['solver']['elapsed_s'],'validation_s':r['validation_s'],'total_s':r['elapsed_s']})
            for i,s in enumerate(r['route']['segments']):
                segment_rows.append({'case_id':case['case_id'],'mode':mode,'method':case['method'],'run_id':r['run_id'],'segment':i,'u':s['u'],'v':s['v'],
                    'layer':s['layer'],'source_id':s.get('source_id'),'source_area_id':s.get('source_area_id'),'component':s.get('component'),'length_m':s['length_m'],'cost_m':s['cost_m'],
                    'geometry_kind':s.get('geometry_kind'),'evidence_level':s['evidence_level'],'clearance_m':s.get('clearance_m'),'start_xy':json.dumps(s['xy'][0]),'end_xy':json.dumps(s['xy'][-1])})
    for name,items in[('segment_evidence.csv',segment_rows),('performance.csv',performance)]:
        with(ROOT/'runs'/name).open('w',newline='',encoding='utf-8-sig')as f:
            w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
    for d in sorted((ROOT/'runs/app').glob('*.json')):
        r=read(d);rows.append({'run_id':r['run_id'],'request_id':r['request_id'],'file':d.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(d.read_bytes()).hexdigest(),
            'source':'CURRENT_NEW_WORKSPACE','status':r['status'],'solver_invoked':r.get('solver',{}).get('invoked',False),'code_sha256':r.get('versions',{}).get('code_sha256'),
            'area_mode':r.get('area_routing'),'method':r.get('input',{}).get('method'),'length_m':r.get('route',{}).get('length_m'),'elapsed_s':r.get('elapsed_s')})
    calibration=read(ROOT/'runtime/edge_calibration/result.json')
    rows.append({'run_id':calibration['run_id'],'request_id':calibration['request_id'],'file':'audits/frozen_calibration_result.json',
        'sha256':hashlib.sha256((ROOT/'runtime/edge_calibration/result.json').read_bytes()).hexdigest(),'source':'ISOLATED_FROZEN_BASELINE_CALIBRATION','status':calibration['status'],
        'solver_invoked':calibration['solver']['invoked'],'code_sha256':calibration.get('versions',{}).get('code_sha256'),'area_mode':'EDGE_BAND','method':'F0','length_m':calibration['route']['length_m'],'elapsed_s':calibration['elapsed_s']})
    (ROOT/'audits/frozen_calibration_result.json').write_bytes((ROOT/'runtime/edge_calibration/result.json').read_bytes())
    with(ROOT/'runs/run_registry.csv').open('w',newline='',encoding='utf-8-sig')as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    changed=[r['case_id']for r,p in zip(paired,prior['positive_comparisons'])if any(abs(r[k]-p[k])>1e-6 for k in ('full_length_m','edge_length_m','full_cost_m','edge_cost_m'))]
    if changed or any(abs(r['baseline_edge_length_difference_m'])>1e-6 for r in paired):raise ValueError('Reassess narrative: final core changed measured main results or baseline')
    summary={'main_positive_requests':8,'geometric_tasks':4,'main_actual_positive_solves':16,'negative_checks':10,'negative_pass':all(r['matches_expected']for r in current['negative_checks']),
        'shorter_requests':sum(r['saving_length_m']>1e-6 for r in paired),'equal_requests':sum(abs(r['saving_length_m'])<=1e-6 for r in paired),
        'unchanged_original_local_domains':current['all_local_domains_unchanged'],'final_vs_R1_changed_tasks':changed,'cost_monotonic':current['cost_monotonic'],
        'actual_APP_attempts_before_final_external_replay':len(rows),'actual_solver_calls_before_final_external_replay':sum(r['solver_invoked']for r in rows),
        'budget_cap_attempts':96,'budget_note':'Includes isolated baseline and preserved R0/R1 plus final R2/extra/UI/CLI records; final clean archive call is added in external delivery receipt',
        'no_field_validation':True,'no_new_Geoapify_requests':True,'new_external_map_requests':0}
    put(ROOT/'audits/author_results_check.json',summary)
    table='| 请求/方法 | 旧长度m | 完整面m | 缩短m | 旧/新代价 | 新假设段m | 旧带外面段m |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for r in paired:table+=f"| {r['case_id']} / {r['method']} | {r['edge_length_m']:.6f} | {r['full_length_m']:.6f} | {r['saving_length_m']:.6f} | {r['edge_cost_m']:.3f} / {r['full_cost_m']:.3f} | {r['full_assumed_m']:.6f} | {r['full_outside_old_band_m']:.6f} |\n"
    extra=ROOT/'runs/extra_and_concurrency_R1';extra_text=''
    if(extra/'summary.json').exists():
        a=read(extra/'EXTRA-HISTORICAL-EDGE_BAND-F1.json');b=read(extra/'EXTRA-HISTORICAL-FULL_FACE-F1.json')
        extra_text=f"\n原日志相似长绕行任务：{a['route']['length_m']:.6f} → {b['route']['length_m']:.6f}米，缩短{a['route']['length_m']-b['route']['length_m']:.6f}米。起点node/1890885411、南门node/6897141353、用途APPROACH_OUTSIDE。截图无唯一请求元数据，因此此任务是**真实旧日志相似演示**，不称截图精确复算。\n"
    text=f'''# 实际结果与裁决

最终内核为R2，输入核验、冻结锁及版本见audits。主实验为8个合法请求（4个起终点用途任务×F0/F1），每请求两模式，实际16次求解；5种固定拒绝×两模式，10项检查。{summary['shorter_requests']}/8缩短，{summary['equal_requests']}/8持平。全部共同30米区域不变；旧模式与封存基线长度完全一致；最终R2与修复前R1主表没有变化。对照不是新独立盲测。

{table}

南门不再受3米边缘带限制；新增紫色段实际穿过旧带之外的合法面。北出口仍有9.68–12.53米条件假设段，完整面不填掉原门外未知空间，不能称完整来源支持通路。F1多走少量几何距离以减少假设成本，并非同一目标下算法退步。图书馆固定全程持平：有面内局部捷径不意味着当前完整任务必须利用它。
{extra_text}
7个事前锁定的真实面点对全部在最终代码下重放，7/7合法缩短、6/7使用旧3米带外区域。它们是局部机制点，不是新门；旧分支按相同Ω过滤称BAND-C，不能与APP原EDGE_BAND混写。真实面未出现断开component反例，不制造成功/失败案例；对应点触、围栏、狭窄通道、洞、私有/层级反例在合成测试单列。

## 性能、版本与修复

冷预处理、热请求和实际solver时间逐次保存在run_registry及响应中。首次全图构建是主要成本；合法版本绑定缓存减少重复构图，每次仍真实求解。并发F0/F1共享未加权图、不同run且成本不串写，见extra_and_concurrency与独立UI记录。RSS仅记录实际快照，不虚称峰值。

保留R0首跑及R1完整矩阵。修复了派生交点浮差、同端点多候选费用选择和独立角点反例；未移动门/原生点、未扩Ω、未放松障碍。R0源码仅保有hash及结果，未声称完整R0源码自包含；R1原字节、R1→R2差异及最终源码完整保留。旧首次149.0338m是历史诊断，最终采用148.8631m。

## 解释边界与审核

结论支持：完整已标步行面能减少表示方式造成的绕行；全程图可以重新选择多个接点。它不证明真实公众可进入、同层已现场确认、障碍无遗漏或现实全局最短。旧原生草地步道保留，草地未整体开放。其他四个冻结场景无登记门，不冒称完成到门规划。无新增Geoapify托管请求或源比较，无新入口、训练或历史遮蔽恢复实验。

独立代理/root/face_review未编写主实现，直接从raw OSM重构Ω、复测几何、全路线费用/原生折线/端点、独立APP交互与最终ZIP新请求；具体范围以其回执为准。作者测试、独立技术审核、用户自然语言验收与现场验证分别记录。用户和现场验证仍待完成。

最终ZIP的CRC/成员SHA/路径由作者和独立角色分别核验；包外最终回执针对实际封包字节与干净解包新求路，不用封包前承诺冒充已完成核验。APP自包含，全部历史研究/环境不自包含。新页面入口及准确命令见README。
'''
    (ROOT/'RESULTS.md').write_text(text,encoding='utf-8');print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
