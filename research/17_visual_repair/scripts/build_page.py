"""Build an offline map-review page from frozen results and re-exported source context.

This program never imports a planner and never computes routes or graph topology.
"""
from pathlib import Path
import datetime
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    frozen=ROOT/'data/frozen'
    trial=read(frozen/'maps/trial_map_data.json')
    registry=[json.loads(l)for l in (frozen/'audit/experiment_registry.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    assert len(registry)==24
    contexts=[read(ROOT/'data/context'/f"{w['window_id']}.json")for w in trial['windows']]
    for w,c in zip(trial['windows'],contexts):
        assert c['window_id']==w['window_id'] and c['bounds_xy']==w['bounds_xy']
        assert c['source']['sha256']==w['source_sha256']
    inv=read(ROOT/'audit/source_to_figure_inventory.json')
    inventory=inv if isinstance(inv,list)else inv.get('rows',inv.get('inventory',[]))
    payload={'trial':trial,'contexts':contexts,'registry':registry,'inventory':inventory,
             'scope':'VISUAL_REPAIR_ONLY_NO_NEW_SOLVER','frozen_commit':'1ab7fd75704d98e85fe4e69a85dc828e7df2ffb5'}
    data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    template='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PG1 街区地图信息整改 · 冻结结果只读重绘</title><link rel="stylesheet" href="maps/viewer.css"></head><body>
<header><p class="eyebrow">SMART-CITY-WALKABILITY-FOUNDATION-PG1 / G1 VISUAL REPAIR</p><h1>先看完整街区，再看 R0 / R1 / R2</h1><p class="lead">三个旧锁定窗口、同一冻结 OSM 源、同一坐标范围与比例。建筑、道路、路名、步行线、过街、开放空间和限制对象作为独立底图保留；算法结果只作叠加。窗口名称标识原始裁片来源，<strong>不保证目标建筑本体在此320米窗口内</strong>；源POI“上海市历史博物馆”与目标“上海博物馆”不能混同。</p><div class="notice"><strong>本页仅重绘冻结结果，不触发求路。</strong> 已有24次尝试、22次实际求解保持原样，本轮新增求路/下载/API均为0。R0仍为默认，R1/R2未获升级。道路中心线线宽是制图符号；4米侧向偏移仍为SCHEMATIC，非实测人行道位置、道路宽度或净空。</div></header>
<main><p id="error" role="alert"></p><noscript>JavaScript未启用：交互地图不可用，请打开figures/中的PNG/SVG；不要把空白当成数据缺失。</noscript>
<div class="controls"><label class="control">固定窗口<select id="window"></select></label><label class="control">固定查询<select id="query"></select></label><label class="control">查看 / 导出面板<select id="variant"><option value="context">A 完整源上下文</option><option value="R0">R0</option><option value="R1">R1</option><option value="R2">R2</option></select></label><button id="full">完整街区全景</button><button id="detail">关键路侧局部</button><button id="export">导出查询与当前视野 JSON</button><button id="export-svg">导出当前面板 SVG</button></div>
<div id="layers" aria-label="原始地图与算法独立图层开关"></div><p id="source-note" class="counterline"></p><p id="source-status" class="source-status"></p><p id="view-note" class="muted"></p><p class="muted">滚轮缩放、拖动平移，四个视图联动。原始对象是否可画与是否进入路由图是两件事；点选查看源ID、标签、来源及准入身份。未取得的数据明确标注，不补画道路面。</p>
<div class="panel-grid"><section class="panel context"><h2>A · 完整街区上下文</h2><p class="summary">优先阅读原始地图。此视图不叠加 R0/R1/R2；不以路由准入过滤源对象。</p><svg class="map" id="map-context" aria-label="完整冻结源街区地图"></svg><p class="panel-note">原始源几何；线宽只表达道路等级，非实测路面。</p></section><section class="panel variant"><h2>R0 · 冻结道路轴表示</h2><p id="summary-R0" class="summary"></p><svg class="map" id="map-R0" aria-label="R0相同底图"></svg><p class="panel-note">相同底图和范围；显示修复后有效R0。共享轴不等于独立人行道。</p></section><section class="panel variant"><h2>R1 · 原生 / 侧别标签</h2><p id="summary-R1" class="summary"></p><svg class="map" id="map-R1" aria-label="R1相同底图"></svg><p class="panel-note">明确标签支持的侧向逻辑表示仍以SCHEMATIC虚线显示。</p></section><section class="panel variant"><h2>R2 · 增加条件侧道</h2><p id="summary-R2" class="summary"></p><svg class="map" id="map-R2" aria-label="R2相同底图"></svg><p class="panel-note">橙色虚线是CONDITIONAL假设；不将未知通行升级为地图事实。</p></section></div>
<div class="legend"><span><i style="border-color:#555b61"></i>源道路轴（等级分线宽）</span><span><i style="border-color:#5b9fbe"></i>原生步行线</span><span><i class="dash" style="border-color:#b97589"></i>源过街 / 信号</span><span><i class="dash" style="border-color:#8177a8"></i>标签派生 SCHEMATIC</span><span><i class="dash" style="border-color:#d49757"></i>条件侧道 CONDITIONAL</span><span><i style="border-color:#2d3238;border-top-width:4px"></i>已保存计算路线（示意 / 假设段仍虚线）</span></div>
<p class="muted">图中原生圆形道路、围合建筑或面来自原数据，不代表算法强制街区闭环。地图比例是源几何比例；无可靠道路宽度时，不能从图上量出车道或人行道净宽。全景范围沿用原320米窗口，并非新扩大数据或评分范围。</p>
<div class="evidence-grid"><section><h2>最终有效矩阵 · 当前固定查询</h2><div class="table-scroll"><table><thead><tr><th>方法</th><th>有效尝试</th><th>保存状态</th><th>路线段</th><th>假设段</th><th>示意段</th><th>F1代理代价</th></tr></thead><tbody id="result-body"></tbody></table></div><p class="muted">代理代价不是精确步程；零长度侧别别名不算合法跨路。无路线时保留状态，不补画连接。</p><h2>点选对象证据</h2><button id="export-evidence">导出所选对象证据</button><pre id="evidence"></pre></section><section><h2>当前查询身份与视野</h2><p class="muted">只读显示最终有效冻结记录；显示切换、缩放与导出不会调用算法。</p><pre id="request"></pre></section></div>
<section class="history"><h2>历史首跑与修复后身份分开</h2><p id="history-note"></p><label>历史查阅<select id="history"><option value="effective">仅显示最终有效结果</option><option value="original">查看被取代的原始R0记录（不替换主地图）</option></select></label><pre id="history-record"></pre></section>
<section><h2>源对象保留清单 · 当前窗口全景口径</h2><p>每个对象可以属于多个族，不能相加当唯一对象数。图计数仅表示源ID被原生边或派生边父对象引用，不代表原道路轴几何本身已准入，也不表示现实可通行真值。关图层或缩放局部不会删除源数据；下表是固定全景的导出/可渲染清单。</p><div class="table-scroll"><table><thead><tr><th>对象族</th><th>冻结源计数</th><th>本轮上下文导出</th><th>全景可渲染</th><th>冻结图源ID引用 R0/R1/R2</th><th>遗漏 / 不存在说明</th></tr></thead><tbody id="family-body"></tbody></table></div><p><a href="audit/source_to_figure_inventory.csv">机器清单 CSV</a> · <a href="audit/source_to_figure_inventory.json">完整清单 JSON</a> · <a href="VISUAL_REPAIR_REPORT.md">整改报告</a> · <a href="README_FIRST.md">运行与冻结边界</a></p></section>
<h2>完整街区与关键路侧静态图</h2><div class="thumbs">__FIGURES__</div>
</main><footer>© OpenStreetMap contributors · 冻结源矢量重绘，非在线瓦片、非实时导航。源EPSG:4326 → 工作EPSG:32651；建筑内环保留。绿化使用本轮制图类别色，P2页面框架保留，未修改长期Visual System。算法新增0，求路新增0，外部地图请求0；G1仍待GPT与用户视觉验收，父Goal未完成。</footer>
<script>window.MAP_REPAIR_INPUT=__DATA__;</script><script src="maps/viewer.js"></script></body></html>'''
    figures=[]
    for w in trial['windows']:
        ident=w['window_id']
        for name,label in [('context_full','完整街区源上下文'),('R0_R1_R2_same_extent','R0/R1/R2同底图'),('local_detail','关键路侧局部')]:
            p=f'figures/{ident}/{name}'
            figures.append(f'<figure><a href="{p}.png"><img loading="lazy" src="{p}.png" alt="{ident} {label}"></a><figcaption>{ident} · {label} · <a href="{p}.svg">SVG源图</a></figcaption></figure>')
    page=template.replace('__FIGURES__',''.join(figures)).replace('__DATA__',data)
    (ROOT/'index.html').write_text(page,encoding='utf-8')
    receipt={'built_at':datetime.datetime.now().astimezone().isoformat(),'role':'/root/visual_context_ui',
             'frozen_trial_sha256':hashlib.sha256((frozen/'maps/trial_map_data.json').read_bytes()).hexdigest(),
             'index_sha256':hashlib.sha256((ROOT/'index.html').read_bytes()).hexdigest(),
             'context_windows':[{ 'window_id':c['window_id'],'objects':len(c['features'])}for c in contexts],
             'registry_records_read':len(registry),'algorithm_runs_added':0,'solver_calls_added':0,
             'external_map_requests':0,'new_data_downloads':0,'frozen_results_modified':False,
             'browser_check':'PENDING_PARENT_AND_INDEPENDENT_BROWSER_REVIEW'}
    (ROOT/'reviews/ui_author_check.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))

if __name__=='__main__':main()
