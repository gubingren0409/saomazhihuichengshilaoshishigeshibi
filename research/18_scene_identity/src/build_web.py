"""Build the target-anchored offline viewer from verified source and frozen overlays."""
from pathlib import Path
import datetime
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    scene=read(ROOT/'data/scene.json')
    trial=read(ROOT/'data/frozen/maps/trial_map_data.json')
    registry=[json.loads(s)for s in (ROOT/'data/frozen/audit/experiment_registry.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    assert len(registry)==24
    assert scene['target']['status']=='TARGET_SOURCE_IDENTITY_VERIFIED'
    assert scene['target']['building_id']=='way/161090899'
    assert scene['target']['target']['tags']['name']=='上海博物馆'
    assert 'way/478271881' not in scene['road']['road_way_ids']
    assert {d['source_id']for d in scene['target']['doors']}=={'node/6897141353','node/6897145227'}
    overview=next(v for v in scene['views']if v['id']=='target_overview')
    target_coords=scene['target']['geometry']['coordinates'][0]
    assert all(overview['bounds_xy'][0]<=p[0]<=overview['bounds_xy'][2]and overview['bounds_xy'][1]<=p[1]<=overview['bounds_xy'][3]for p in target_coords)
    payload={'scene':scene,'trial':trial,'registry':registry,
        'base_map_sha256':hashlib.sha256(json.dumps(scene['features'],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
        'frozen_trial_sha256':sha(ROOT/'data/frozen/maps/trial_map_data.json'),
        'frozen_commit':'1ab7fd75704d98e85fe4e69a85dc828e7df2ffb5',
        'scope':'TARGET_CONTEXT_RECONSTRUCTION_ONLY_NO_SOLVER'}
    data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>上海博物馆人民广场馆 · 目标锚定地图</title><link rel="stylesheet" href="viewer.css"></head><body>
<header><p class="eyebrow">SMART-CITY-WALKABILITY-FOUNDATION-PG1 / TARGET CONTEXT RECONSTRUCTION R2</p><h1>上海博物馆人民广场馆：建筑、原门与黄陂北路</h1><p class="lead">地图由实际目标建筑 <strong>way/161090899</strong>、南门和北侧出口及黄陂北路确定范围，不再以附近步道中点定窗。上海市历史博物馆、上海大剧院不是目标建筑。</p><div class="notice"><strong>只重建场景与地图，不触发求路。</strong> 旧24次尝试、22次实际求解及坐标保持不变。R0/R1/R2叠加仍是原西北侧步道诊断，<strong>不是本轮上海博物馆到门路线</strong>；门前视野没有旧诊断边时如实显示OUTSIDE_VIEW，不补线。</div><p class="reference-warning">REAL_WORLD_GEOMETRY_UNVERIFIED：目标身份和坐标已与冻结源绑定；没有在本轮获得适合米制比较的独立现实参照，不能把源一致性称为现场精度验证。</p></header>
<main><p id="error" role="alert"></p><noscript>JavaScript未启用，请查看figures中的源数据PNG/SVG。</noscript>
<nav class="scene-nav"><a href="#overview">目标建筑与接近概览</a><a href="#block-context">完整街区</a><a href="#huangpi-north-road">黄陂北路</a><a href="#south-entrance">南门</a><a href="#north-exit">北侧出口</a><a href="#r0-r1-r2">原诊断同底图</a><a href="#source-lineage">对象来源</a></nav>
<div class="controls"><label class="control">目标锚定视野<select id="view"></select></label><label class="control">旧诊断查询（无门身份）<select id="query"></select></label><label class="control">查看 / 导出面板<select id="variant"><option value="context">A 原始源地图</option><option value="R0">R0</option><option value="R1">R1</option><option value="R2">R2</option></select></label><button id="reset">恢复当前锚定范围</button><button id="layer-controls-toggle">图层 / 来源</button><button id="export">导出视野与身份 JSON</button><button id="export-svg">导出当前面板 SVG</button></div>
<p class="map-summary">目标 way/161090899 · 南门 main / 北侧 exit（仅门外） · 原门未移动 · 道路中心线符号不代表路宽</p>
<div class="panel-grid"><section class="panel context"><h2>A · 目标街区原始上下文</h2><p class="summary">上海博物馆玫瑰色边界、原南门与北出口、黄陂北路金色实线均来自原生源对象。</p><svg class="map" id="map-context" aria-label="实际上海博物馆目标地图"></svg><p class="panel-note">目标图形与门点按原始坐标显示；原生地物不按路由准入过滤。</p></section><section class="panel variant"><h2>R0 · 原道路轴诊断</h2><p id="summary-R0" class="summary"></p><svg class="map" id="map-R0"></svg><p class="panel-note">旧西北步道诊断的原始位置，不改称博物馆门前路线。</p></section><section class="panel variant"><h2>R1 · 原生/侧别标签诊断</h2><p id="summary-R1" class="summary"></p><svg class="map" id="map-R1"></svg><p class="panel-note">标签侧向表示仍为SCHEMATIC虚线。</p></section><section class="panel variant"><h2>R2 · 条件侧道诊断</h2><p id="summary-R2" class="summary"></p><svg class="map" id="map-R2"></svg><p class="panel-note">金色虚线为条件假设；黄陂北路原生中心线是金色实线，两者身份不同。</p></section></div>
<div class="legend"><span><i style="border-color:#b97589"></i>目标博物馆原始轮廓</span><span><i style="border-color:#d49757"></i>黄陂北路原生中心线</span><span><i style="border-color:#555b61"></i>其他道路中心线</span><span><i style="border-color:#5b9fbe"></i>原生步行线</span><span><i class="dash" style="border-color:#b97589"></i>源过街/交通设施</span><span><i class="dash" style="border-color:#8177a8"></i>标签侧向SCHEMATIC</span><span><i class="dash" style="border-color:#d49757"></i>条件侧道HYPOTHESIS</span><span><i style="border-color:#2d3238;border-top-width:4px"></i>旧保存诊断路线（假设段虚线）</span></div>
<details class="inspection-details" id="layer-controls"><summary id="layer-controls-summary">展开图层、源数据与当前尺度</summary><div id="layers" aria-label="原始地图和冻结诊断叠加独立图层"></div><p id="source-note" class="counterline"></p><p id="source-status"></p><p id="view-note" class="muted"></p><p class="muted">滚轮缩放、拖动平移，四视图联动。线宽只是道路等级制图符号，不是实测道路宽度；sidewalk/cycleway标签不自动生成路缘或独立车道几何。</p>
</details>
<details class="inspection-details" id="identity-details"><summary id="identity-details-summary">展开目标原生身份、门坐标及审计来源</summary><section class="identity-panel"><h2>实际目标身份</h2><p><strong>上海博物馆</strong> · way/161090899 · 原地址标签：人民大道201号。南门 node/6897141353：entrance=main；北侧 node/6897145227：entrance=exit，<strong>仅门外接近，不当作入馆入口</strong>。</p><p id="identity-note"></p><p><a href="../audit/TARGET_IDENTITY_AUDIT.md">目标身份审计</a> · <a href="../audit/huangpi_north_road_objects.json">黄陂北路七段道路证据</a> · <a href="../audit/REAL_SCENE_VALIDATION.md">现实参照边界</a></p></section>
</details>
<div class="evidence-grid" id="source-lineage"><section><h2>点选对象，核对原生身份</h2><button id="export-evidence">导出所选对象证据</button><pre id="evidence"></pre><h2>黄陂北路身份</h2><p id="road-note"></p></section><section><h2>当前场景、视野与旧诊断绑定</h2><pre id="request"></pre></section></div>
<section><h2>旧诊断有效记录：不等于目标门路线</h2><table><thead><tr><th>变体</th><th>原尝试</th><th>原状态</th><th>当前视野诊断边</th><th>旧F1代理代价</th></tr></thead><tbody id="result-body"></tbody></table><p class="muted">保存结果属于原way/39764359步道诊断，端点不是本任务的南门或北出口。图面范围重建没有迁移、重算或替换旧查询。</p></section>
<section class="history"><h2>原首跑与最终有效R0</h2><label>查阅历史<select id="history"><option value="effective">当前有效矩阵</option><option value="original">原始R0记录（不替换主图）</option></select></label><pre id="history-record"></pre></section>
<section><h2>实际源对象清单</h2><table><thead><tr><th>源族</th><th>街区导出数</th><th>当前视野绘制数</th><th>源身份/缺失</th></tr></thead><tbody id="family-body"></tbody></table><p><a href="../audit/source_to_render_inventory.csv">原始对象到图件清单</a> · <a href="../audit/window_definition.json">目标锚定窗口定义</a> · <a href="../TARGET_SCENE_CORRECTION.md">纠正说明</a> · <a href="../README.md">运行与停止</a></p></section>
<h2>目标锚定静态图册</h2><div class="thumbs">__FIGURES__</div>
</main><footer>© OpenStreetMap contributors · 冻结原始矢量重建，非在线瓦片，非实时导航。EPSG:4326→EPSG:32651。原门坐标与exit身份未改；本轮算法/求路/下载/API新增均0。R0仍默认；G1用户视觉验收和整个Parent Goal未完成。</footer><script>window.RECON_MAP_INPUT=__DATA__;</script><script src="viewer.js"></script></body></html>'''
    figures=[]
    for name,label in [('target_context_full','上海博物馆完整街区'),('target_approach_overview','目标建筑与原门'),('huangpi_north_road_detail','黄陂北路及周边'),('south_entrance_detail','南门原坐标局部'),('north_exit_detail','北出口原坐标局部'),('R0_R1_R2_same_extent','冻结R0/R1/R2同底图'),('source_vs_algorithm','源地图与旧算法分层'),('object_provenance_inspection','目标对象来源检查')]:
        figures.append(f'<figure><a href="../figures/{name}.png"><img loading="lazy" src="../figures/{name}.png" alt="{label}"></a><figcaption>{label} · <a href="../figures/{name}.svg">SVG</a></figcaption></figure>')
    (ROOT/'web/index.html').write_text(page.replace('__DATA__',data).replace('__FIGURES__',''.join(figures)),encoding='utf-8')
    receipt={'built_at':datetime.datetime.now().astimezone().isoformat(),'author':'/root/recon_map_ui',
        'index_sha256':sha(ROOT/'web/index.html'),'frozen_trial_sha256':payload['frozen_trial_sha256'],
        'source_features':len(scene['features']),'target_building':'way/161090899',
        'doors':['node/6897141353','node/6897145227'],'default_view':'target_overview',
        'algorithm_runs_added':0,'solver_calls_added':0,'external_map_requests':0,'new_data_downloads':0,
        'browser_check':'PENDING_ACTUAL_AUTHOR_AND_INDEPENDENT_BROWSER'}
    (ROOT/'audits/ui_author_check.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))

if __name__=='__main__':main()
