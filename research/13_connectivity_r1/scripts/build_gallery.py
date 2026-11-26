"""Build the offline review page from verified existing outputs; no solver calls.

Only index.html is written. Run after summarize_results.py and copying the
approved plot outputs plus their JSON metadata into visuals/. --strict rejects
an unfinished matrix, stale summary, missing figures or unbound response hashes.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
MODES = {'FROZEN_FULL_FACE': 'B0 封存完整面', 'SOURCE_COMPLETE': 'B1 补齐源面',
         'EXACT_STITCH': 'B2 精确衔接', 'CONDITIONAL_SEAMS': 'B3 条件接缝'}
ROLES = {'BASELINE_POSITIVE': '固定合法门任务', 'BASELINE_REJECTION': '固定拒绝检查',
         'SOURCE_INTERFACE_MECHANISM': '原生接口机制查询（非入口任务）',
         'GAP_COST_PAIR': '接缝代价对照', 'SEAM_SENSITIVITY': '接缝阈值敏感性',
         'PRELOCKED_THRESHOLD_SENSITIVITY': '事前锁定的单因素阈值敏感性',
         'HISTORICAL_LONG_QUERY_NOT_SCREENSHOT_BOUND': '固定历史长绕行（不是截图复算）'}
SOURCE_FIGURES = ['museum_source_overview', 'six_scene_source_inventory']


def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else default


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def local_path(value):
    relative=Path(value)
    if relative.is_absolute()or'..'in relative.parts:raise ValueError('UNSAFE_RELATIVE_ARTIFACT_PATH')
    path=(ROOT/relative).absolute();resolved=path.resolve()
    if resolved.is_relative_to(ROOT.resolve()):return path
    # Only this task's audited storage relocation may resolve outside its
    # logical root. The final ZIP contains real members and needs no junction.
    bindings=read(ROOT/'audits/derived_storage_relocation.json',[])
    for binding in bindings:
        logical=Path(binding['logical']);physical=Path(binding['physical'])
        if path.is_relative_to(logical)and resolved==physical/path.relative_to(logical):return path
    raise ValueError('UNBOUND_EXTERNAL_ARTIFACT_PATH')


def e(value):
    return escape(str(value if value is not None else '未提供'), quote=True)


def number(value, suffix=' m'):
    try:
        return f'{float(value):,.2f}{suffix}' if value not in (None, '') else '—'
    except (TypeError, ValueError):
        return '—'


def json_text(value):
    return e(json.dumps(value, ensure_ascii=False, indent=2))


def data_uri(data, mime):
    return 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')


def download_link(relative, label, limit=200 * 1024):
    path = local_path(relative)
    if not path.is_file():
        return f'<span class="unavailable">{e(label)} · 待生成</span>'
    if path.stat().st_size <= limit:
        return (f'<a href="{data_uri(path.read_bytes(), "text/csv;charset=utf-8")}" '
                f'download="{e(path.name)}">{e(label)} ↓</a>')
    return f'<a href="{quote(relative, safe="/")}">{e(label)}（ZIP 内离线下载）</a>'


def figure(name, warnings):
    meta_path = ROOT / 'visuals' / f'{name}.json'
    meta = read(meta_path)
    if not isinstance(meta, dict):
        warnings.append(f'FIGURE_METADATA_PENDING:{name}')
        return None
    outputs = {}
    for item in meta.get('outputs', []):
        # Plot metadata records its original figures/visuals path; the delivery
        # copy must have exactly the same bytes in root visuals/.
        path = ROOT / 'visuals' / Path(item['path']).name
        if path.is_file() and digest(path) == item.get('sha256'):
            outputs[path.suffix] = path.relative_to(ROOT).as_posix()
        else:
            warnings.append(f'FIGURE_OUTPUT_HASH_UNAVAILABLE:{name}:{path.name}')
    if '.svg' not in outputs or '.png' not in outputs:
        return None
    return {'name': name, 'meta': meta, 'metadata_path': meta_path.relative_to(ROOT).as_posix(),
            'metadata_sha256': digest(meta_path), 'outputs': outputs}


def image_html(fig):
    if fig is None:
        return '<div class="pending-figure">图与 hash 元数据尚未汇集；完成后重新生成本页。</div>'
    outputs, meta = fig['outputs'], fig['meta']
    links=[]
    for ext,path in outputs.items():
        href=data_uri((ROOT/path).read_bytes(),'application/pdf')if ext=='.pdf'else quote(path,safe='/')
        links.append(f'<a href="{href}" download="{e(Path(path).name)}">{ext[1:].upper()}</a>')
    links.append(f'<a href="{data_uri((ROOT/fig["metadata_path"]).read_bytes(),"application/json")}" download="{e(Path(fig["metadata_path"]).name)}">图表元数据</a>')
    return (f'<a class="image-link" href="{quote(outputs[".svg"], safe="/")}">'
            f'<img src="{quote(outputs[".png"], safe="/")}" alt="{e(meta.get("question", fig["name"]))}" loading="lazy"></a>'
            f'<figcaption>{" · ".join(links)}<span>源图、范围和端点可核对 · 坐标 EPSG:32651</span></figcaption>')


def response_snapshot(item, row_by_path):
    path = local_path(item['path'])
    if not path.is_file() or digest(path) != item.get('sha256'):
        raise ValueError('SAVED_RESPONSE_HASH_MISMATCH:' + item['path'])
    row = row_by_path.get(item['path'])
    if row is None or row.get('response_sha256') != item['sha256'] or row.get('run_id') != item.get('run_id'):
        raise ValueError('FIGURE_NOT_BOUND_TO_FORMAL_CSV:' + item['path'])
    result = read(path)
    if result.get('run_id') != item.get('run_id'):
        raise ValueError('FIGURE_RESPONSE_RUN_ID_MISMATCH:' + item['path'])
    route, query = result.get('route') or {}, result.get('query') or {}
    request = result.get('normalized_request') or result.get('input') or {}
    inputs = {'scene_id': request.get('scene_id', query.get('scene_id')),
              'start_id': request.get('start_id', query.get('start', {}).get('id')),
              'target_id': request.get('door_id', query.get('end', {}).get('id')),
              'purpose': request.get('purpose', query.get('task_role', '未提供')),
              'method': request.get('method'), 'connectivity_mode': request.get('connectivity_mode', result.get('connectivity_mode')),
              'seam_max_m': request.get('seam_max_m', 2.0)}
    return {'run_id': result['run_id'], 'status': result.get('status'), 'request': request,
            'inputs': inputs, 'solver': result.get('solver'), 'versions': result.get('versions'),
            'validation': result.get('validation'), 'failure': result.get('failure'),
            'length_m': route.get('length_m'), 'cost_m': route.get('cost_weighted_m'),
            'exact_interface_m': row.get('exact_interface_m'), 'conditional_seam_m': row.get('conditional_seam_m'),
            'native_m': row.get('native_m'), 'mapped_derived_m': row.get('mapped_derived_m'),
            'door_front_hypothesis_m': row.get('door_front_hypothesis_m'),
            'interface_ids_used': route.get('interface_ids_used', []),
            'response_path': item['path'], 'response_sha256': item['sha256'],
            'mechanism_query': query if query else None}


def routed(result):
    return str(result.get('status', '')).startswith('ROUTED') and (result.get('validation') or {}).get('passed') is not False


def case_html(fig, index, row_by_path, warnings):
    try:
        if fig['meta'].get('same_base_and_extent') is not True or fig['meta'].get('route_coordinates_altered') is not False:
            raise ValueError('FIGURE_COMPARISON_GEOMETRY_SCOPE_UNCONFIRMED:' + fig['name'])
        snapshots = [response_snapshot(item, row_by_path) for item in fig['meta'].get('saved_results', [])]
        if len(snapshots) != 2:
            raise ValueError('FIGURE_NEEDS_TWO_REAL_RESPONSES:' + fig['name'])
        a, b = snapshots
        for key in ('scene_id', 'start_id', 'target_id', 'purpose'):
            if a['inputs'][key] != b['inputs'][key]:
                raise ValueError('FIGURE_ENDPOINT_OR_PURPOSE_MISMATCH:' + fig['name'] + ':' + key)
    except (KeyError, ValueError, OSError) as exc:
        warnings.append(str(exc))
        return None
    caption = '两侧均保留各自失败 / 可达状态，不用示意线代替完整路线。'
    if a['inputs']['method'] != b['inputs']['method']:
        caption = '两侧代价方法不同；这里只展示各自实际结果，不作同方法的增益计算。'
    elif not routed(a) and routed(b):
        caption = '比较前未形成合法完整路线，比较后实际可达；旧路线没有长度，不计算“缩短量”。'
    elif routed(a) and routed(b) and a['length_m'] is not None and b['length_m'] is not None:
        change = a['length_m'] - b['length_m']
        caption = ('两侧完整路线的几何长度保持相同；新增接口或候选不等于路线必然改变。' if abs(change) <= 1e-8 else
                   f'在这一相同输入对照中，几何长度减少 {number(change)}。' if change > 0 else
                   f'在这一相同输入对照中，几何长度增加 {number(-change)}；保留这一结果。')
    elif not routed(b):
        caption = '比较模式仍未形成合法完整路线；具体失败身份和阶段保留在下方。'
    rows = []
    for result in snapshots:
        mode = result['inputs']['connectivity_mode']
        label = '已形成合法完整路线' if routed(result) else '未形成合法完整路线'
        failure = (result.get('failure') or {}).get('code')
        rows.append(f'<tr><th>{e(MODES.get(mode, mode))}<small>{e(result["inputs"]["method"])}</small></th>'
                    f'<td>{e(label)}<small>{e(result["status"])}{(" · " + e(failure)) if failure else ""}</small></td>'
                    f'<td>{number(result["length_m"])}</td><td>{number(result["cost_m"], " 加权米")}</td>'
                    f'<td>{number(result["exact_interface_m"])}</td><td>{number(result["conditional_seam_m"])}</td></tr>')
    compact = {'figure_metadata_sha256': fig['metadata_sha256'], 'results': snapshots,
               'user_observation': 'PENDING_USER_OBSERVATION', 'route_geometry_edited': False}
    excerpt = data_uri(json.dumps(compact, ensure_ascii=False, indent=2).encode('utf-8'), 'application/json;charset=utf-8')
    identities = ''.join(f'<li><code>{e(r["run_id"])}</code> · {"实际调用求解器" if (r.get("solver") or {}).get("invoked") else "求解前拒绝"}'
                         f'<small>原始响应：{e(r["response_path"])}<br>SHA256 {e(r["response_sha256"])}</small></li>' for r in snapshots)
    return (f'<article class="case" id="{e(fig["name"])}"><div class="case-heading"><span class="ordinal">{index:02}</span>'
            f'<div><p class="eyebrow">实际案例 · {e(a["inputs"]["scene_id"])}</p><h3>{e(fig["meta"].get("question", fig["name"]))}</h3></div></div>'
            f'<figure>{image_html(fig)}</figure><p class="finding">{e(caption)}</p>'
            '<div class="table-scroll"><table><thead><tr><th>模式 / 方法</th><th>实际状态</th><th>几何长度</th><th>广义代价</th><th>精确接口段</th><th>条件接缝段</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="request">同一起点 <code>{e(a["inputs"]["start_id"])}</code> → 同一终点 <code>{e(a["inputs"]["target_id"])}</code>'
            f'<br>用途：{e(a["inputs"]["purpose"])}。机制终点不冒称建筑入口；原门 / 原生端点没有移动。</p>'
            f'<details><summary>查看真实 run IDs、输入、校验与失败身份</summary><ul class="run-list">{identities}</ul>'
            f'<a href="{excerpt}" download="{e(fig["name"])}-identity.json">下载身份摘录 JSON</a><pre>{json_text(compact)}</pre></details></article>')


CSS = """
:root{font-family:'Segoe UI','Microsoft YaHei',sans-serif;background:#f5f4ef;color:#263d34}*{box-sizing:border-box}body{margin:0}a{color:#226652;text-underline-offset:3px}a:hover{color:#9a5b2b}header{background:#153e35;color:#fff;padding:43px max(24px,calc((100vw - 1220px)/2)) 36px}.eyebrow{font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#788975;margin:0 0 7px}header .eyebrow{color:#c0d2b5}h1{font-size:clamp(27px,3vw,39px);line-height:1.35;margin:10px 0 15px;font-weight:650}header p{font-size:14px;line-height:1.9;color:#d9e4d9;max-width:900px;margin:0}.badges{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0}.badge{border:1px solid #68816d;padding:6px 11px;font-size:11px;border-radius:20px;color:#e1e7bc}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:22px}.actions a{display:inline-block;text-decoration:none;padding:11px 17px;border:1px solid #94b398;border-radius:5px;color:#edf6e8;font-size:13px}.actions .primary{background:#edf4df;color:#234c37;border-color:#edf4df}main{max-width:1268px;margin:auto;padding:26px 24px 55px}.progress{padding:16px 20px;border-left:4px solid #b59655;background:#f0ebd9;font-size:13px;line-height:1.8}.progress strong{display:block}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0 33px}.stat{padding:19px;background:#fff;border:1px solid #dce2d6;border-radius:7px}.stat b{display:block;font-size:28px;font-weight:600;margin-bottom:6px}.stat span{font-size:11px;color:#73806c}nav{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;padding:0 0 22px;border-bottom:1px solid #dce1d5}section{margin-top:35px}.section-head{display:flex;justify-content:space-between;align-items:baseline;gap:15px}h2{font-size:23px;font-weight:600;margin:0 0 12px}h3{font-size:19px;line-height:1.6;margin:0;font-weight:600}.section-note{font-size:13px;line-height:1.9;color:#6a7967;margin:0 0 22px}.source-card,.case{background:#fff;border:1px solid #d9e1d3;border-radius:8px;padding:23px;margin:18px 0}.source-card>p{font-size:13px;line-height:1.9;margin:15px 0 0}.source-card h3{margin-bottom:15px}figure{margin:0}.image-link{display:block}img{width:100%;height:auto;display:block;background:#fcfaf7;border:1px solid #edf0e7}figcaption{font-size:10px;line-height:1.8;display:flex;gap:10px;padding:9px 0;color:#7a8572;flex-wrap:wrap}figcaption span{margin-left:auto}.pending-figure{padding:60px 20px;text-align:center;background:#f5f6f0;border:1px dashed #cbd6c3;color:#7a8771;font-size:13px}.mode-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.mode{background:#e9eee2;padding:17px;border-top:3px solid #69937a;border-radius:4px}.mode b{font-size:13px}.mode p{font-size:12px;line-height:1.8;color:#687a66;margin:9px 0 0}.case-heading{display:flex;gap:14px;align-items:flex-start;margin-bottom:18px}.ordinal{font-size:28px;color:#a7b69c;line-height:1.1}.case-heading .eyebrow{margin-bottom:5px}.finding{font-size:14px;line-height:1.9;border-left:3px solid #91ab7e;padding:8px 13px;background:#f4f7ef;margin:16px 0}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px;line-height:1.7}th,td{padding:11px 10px;border-bottom:1px solid #e0e5d9;text-align:left;vertical-align:top;white-space:nowrap}thead th{background:#eff3e8;color:#687a60;font-size:11px;font-weight:500}tbody th{font-weight:600}small{display:block;color:#7a8772;font-weight:400;font-size:10px;line-height:1.8;white-space:normal;overflow-wrap:anywhere}.request{font-size:11px;line-height:1.9;color:#6b7c65;margin-top:16px}code{font:10px/1.7 Consolas,'Microsoft YaHei',monospace;overflow-wrap:anywhere}details{font-size:12px;line-height:1.9;margin-top:18px}summary{cursor:pointer;color:#4d7052}pre{font:10px/1.8 Consolas,'Microsoft YaHei',monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:400px;overflow:auto;background:#f5f7f1;padding:14px}.run-list{padding-left:18px}.run-list li{margin:10px 0}.download-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:13px}.download-grid>div{background:#fff;padding:18px;border:1px solid #dce4d5;border-radius:6px;font-size:12px;line-height:2}.download-grid b{display:block;font-size:13px;margin-bottom:6px}.unavailable{color:#8b9581}.boundary-note{background:#e9e8de;border:1px solid #d9ddcf;border-radius:7px;padding:20px;font-size:12px;line-height:2}.boundary-note p{margin:5px 0}.integrity{font-size:10px;line-height:1.9;color:#79866e}footer{border-top:1px solid #d5dfce;padding:22px 24px;text-align:center;color:#7c8872;font-size:10px;line-height:1.9}@media(max-width:800px){header{padding:27px 20px}.stats,.mode-grid{grid-template-columns:1fr 1fr}.download-grid{grid-template-columns:1fr}.source-card,.case{padding:15px}main{padding:20px 12px 35px}h2{font-size:20px}h3{font-size:17px}.section-head{display:block}.stat b{font-size:25px}figcaption span{margin-left:0}.request code{font-size:10px}}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-url', default='http://127.0.0.1:53441/')
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    parsed = urlparse(args.app_url)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'}:
        raise ValueError('APP_URL_MUST_BE_LOCAL_HTTP')
    warnings = []
    summary_path, csv_path = ROOT / 'results/summary.json', ROOT / 'results/sample_results.csv'
    summary = read(summary_path, {})
    progress = read(ROOT / 'results/formal_progress.json', {})
    rows = list(csv.DictReader(csv_path.open(encoding='utf-8-sig', newline=''))) if csv_path.is_file() else []
    row_by_path = {r['response_path']: r for r in rows if r.get('response_path')}
    registry = ROOT / 'results/formal_registry.jsonl'
    current_registry_sha = digest(registry) if registry.is_file() else None
    replay_registry=ROOT/'results/formal_replay_registry.jsonl'
    current_replay_sha=digest(replay_registry)if replay_registry.is_file()else None
    complete = (bool(summary) and bool(rows) and len(rows) == summary.get('formal_completed',summary.get('formal_attempts')) and
                summary.get('registry_sha256') == current_registry_sha and
                summary.get('replay_registry_sha256') == current_replay_sha and
                progress.get('completed') == progress.get('total') and bool(progress.get('total')))
    if not complete:
        warnings.append('FORMAL_SUMMARY_NOT_FINAL_OR_NOT_CURRENT')
    sources = {name: figure(name, warnings) for name in SOURCE_FIGURES}
    spec = read(ROOT / 'visuals/route_comparison_spec.json', {})
    names = [r['id'] for r in spec.get('cases', [])]
    if not names:
        names = [p.stem for p in sorted((ROOT / 'visuals').glob('*.json'))
                 if isinstance(read(p), dict) and read(p).get('saved_results')]
    cases = []
    for name in names[:6]:
        fig = figure(name, warnings)
        if fig:
            rendered = case_html(fig, len(cases) + 1, row_by_path, warnings)
            if rendered:
                cases.append(rendered)
    if len(cases) != 6:
        warnings.append(f'REPRESENTATIVE_CASES_AVAILABLE:{len(cases)}_OF_6')
    ready_sources = sum(v is not None for v in sources.values())
    if args.strict and (not complete or len(cases) != 6 or ready_sources != 2 or warnings):
        raise SystemExit(json.dumps({'status': 'GALLERY_NOT_READY', 'warnings': warnings}, ensure_ascii=False))
    completed = progress.get('completed', summary.get('formal_attempts', '未提供'))
    total = progress.get('total', '未提供')
    state = (f"104项固定比较已完成；实际正式尝试共{summary.get('formal_attempts')}次，其中包含{summary.get('formal_replays',0)}次已锁修复复算及{len(summary.get('formal_interrupted',[]))}次中断。角色表使用104项主比较分母，全部首跑/复算分别保留。独立复核与用户审核分开记录。") if complete else (
        f'正式运行尚未封存：进度记录为 {completed} / {total}。本页不预写整体收益；未绑定正式汇总的案例不进入下方主结果。')
    routed_count = sum(str(r.get('status', '')).startswith('ROUTED') and r.get('whole_validation_passed') not in {'False', 'false'} for r in rows)
    stats = [(summary.get('formal_attempts', '待汇总'), '实际正式尝试（含拒绝、修复复算与中断）'),
             (summary.get('solver_invocations', '待汇总'), '实际调用求解器的请求'),
             (routed_count if rows else '待汇总', '104项主比较中输出合法完整路线的请求'),
             (f'{len(cases) + ready_sources} / 8', '已核验 hash 并收录的图表')]
    stat_html = ''.join(f'<div class="stat"><b>{e(value)}</b><span>{e(label)}</span></div>' for value, label in stats)
    museum = sources['museum_source_overview']
    m = museum['meta'] if museum else {}
    gap = number(m.get('P_line_distance_m'))
    source_note = (f'南门面与东北侧长线直接间距为 {gap}。' if m else '南门面与东北侧长线存在直接正距离。') + (
        '但 way/178737608 已通过 node/1890935415 与 node/1891590997 分别连接该面和 way/564255372；不能把两个对象的直接间隙称为整个源网络断开。实际路由图准入仍需核对本次结果。')
    inventory = sources['six_scene_source_inventory']
    i = inventory['meta'] if inventory else {}
    inventory_note = (f'源准入 {i["source_admitted_scene_id_count"]} 个场景—对象记录，按原生身份去重为 {i["global_unique_source_faces"]} 个面；其中 {i["new_global_unique_source_faces"]} 个此前未被选入。' if i else
                      '源人口统计图尚未汇集；不以图层颜色或旧派生边清单代替完整源对象盘点。') + '跨裁片副本不是独立样本。草地、公园和未解析完整成员不因相邻而自动成为步行面。'
    counts = []
    for role, by_mode in summary.get('by_role_and_mode', {}).items():
        cells = ''.join(f'<td>{by_mode.get(mode, {}).get("routed", 0)} / {by_mode.get(mode, {}).get("attempted", 0)}</td>' for mode in MODES)
        counts.append(f'<tr><th>{e(ROLES.get(role, role))}</th>{cells}</tr>')
    totals = ('<div class="table-scroll"><table><thead><tr><th>请求角色（不混合分母）</th>' +
              ''.join(f'<th>{e(v)}</th>' for v in MODES.values()) + '</tr></thead><tbody>' + ''.join(counts) + '</tbody></table></div>') if counts else '<p class="section-note">正式分角色结果表尚未生成。</p>'
    graph_note = ('F0 / F1 配对的无权图 hash ' + ('全部一致' if summary.get('all_paired_graphs_equal') else '存在差异，需查看完整汇总') +
                  f'；实际核对 {len(summary.get("F0_F1_graph_pairs", []))} 组。') if summary else 'F0 / F1 同图核对待正式汇总。'
    downloads = ''.join(f'<p>{download_link(path, label)}</p>' for path, label in [
        ('results/sample_results.csv', '逐请求结果 CSV'), ('results/paired_comparison.csv', '同输入模式对照 CSV'),
        ('results/segment_evidence.csv', '完整路线分段证据 CSV'), ('results/interface_evidence.csv', '接口与接缝证据 CSV'),
        ('results/component_statistics.csv', '预处理图连通分量 CSV'),
        ('results/interface_component_membership.csv', '接口旧新分量身份 CSV')])
    generated = datetime.now(timezone.utc).isoformat(timespec='seconds')
    provenance = {'generated_at_utc': generated, 'summary_sha256': digest(summary_path) if summary_path.is_file() else None,
                  'sample_csv_sha256': digest(csv_path) if csv_path.is_file() else None,
                  'registry_sha256': current_registry_sha, 'replay_registry_sha256':current_replay_sha, 'formal_summary_current_and_complete': complete,
                  'verified_source_figures': ready_sources, 'verified_formal_route_case_figures': len(cases),
                  'warnings': warnings, 'gallery_solver_calls': 0, 'external_requests': 0,
                  'user_observation': 'PENDING_USER_OBSERVATION', 'screenshot_binding': 'SCREENSHOT_REQUEST_UNBOUND'}
    independent_path=ROOT/'audits/independent_review.md'
    independent_href=data_uri(independent_path.read_bytes(),'text/markdown;charset=utf-8')if independent_path.is_file()else'audits/independent_review.md'
    html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>步行面衔接 R1 · 源对象、实际路线与条件接缝</title><style>{CSS}</style></head><body>
<header><p class="eyebrow">OSM / GEOAPIFY · PEDESTRIAN AREA CONNECTIVITY R1</p><h1>从一块可走的广场，<br>到能接上周围步道的步行空间</h1><p>先分清源对象遗漏、真实接口漏接与地图间隙，再看新增连接有没有进入实际路线。图表来自冻结源几何与真实运行输出；边界原样保留，条件接缝单独记账。</p><div class="badges"><span class="badge">用户穿行观察仍待审核</span><span class="badge">截图原请求尚未唯一绑定</span><span class="badge">原登记门与起点不移动</span></div><div class="actions"><a class="primary" href="{e(args.app_url)}">打开本地实时 APP ↗</a><a href="#cases">查看实际路线对照</a><a href="README.md">复现与启动说明</a></div></header>
<main><div class="progress"><strong>{'当前汇总已完成' if complete else '过程材料 · 正式运行尚未封存'}</strong>{e(state)}</div><div class="stats">{stat_html}</div>
<nav><a href="#source">疑点与源对象</a><a href="#modes">四种模式</a><a href="#cases">实际案例</a><a href="#matrix">完整结果口径</a><a href="#evidence">复现与审核材料</a></nav>
<section id="source"><div class="section-head"><h2>图上有间隙，是否意味着网络没有接上？</h2><span class="integrity">源诊断图 {ready_sources} / 2</span></div><p class="section-note">原始边界 P、扣障后的 Ω 与独立原生线分开核对。颜色、线宽和直接距离都不能单独证明全网不可达。</p><article class="source-card"><h3>博物馆南门面与东北侧步道</h3><figure>{image_html(museum)}</figure><p>{e(source_note)}</p></article><article class="source-card"><h3>六个冻结裁片里，旧面集合遗漏了什么？</h3><figure>{image_html(inventory)}</figure><p>{e(inventory_note)}</p></article></section>
<section id="modes"><h2>每一步到底改变了什么？</h2><p class="section-note">四种模式均以完整合法面求路。B0 是封存完整面，不用历史边缘带冒充主基线；同输入比较不混入门、起点和用途变化。</p><div class="mode-grid"><div class="mode"><b>B0 · 封存完整面</b><p>上轮固定面集合与接口逻辑。本轮主基线。</p></div><div class="mode"><b>B1 · 补齐源面</b><p>补读原已存在的合格面，保持原接口与约束。</p></div><div class="mode"><b>B2 · 精确衔接</b><p>在 B1 同一面集合上修复真实相交、覆盖、共边和重叠接口。</p></div><div class="mode"><b>B3 · 条件接缝</b><p>加入整段约束合格的局部假设。主 2 米，0.5 / 5 米敏感性；10 米仅诊断。</p></div></div></section>
<section id="cases"><div class="section-head"><h2>哪些实际路线改变了，哪些保持不变？</h2><span class="integrity">已绑定正式输出 {len(cases)} / 6 个案例</span></div><p class="section-note">每张对照图保留完整折线、原始端点与各自 run ID。没有路线的模式展示失败身份，不画一条示意线替代。接缝没有被采用、收益为零或仍断开的结果一并保留。</p>{''.join(cases) if cases else '<div class="pending-figure">正式 CSV 与代表案例图尚未共同就绪；本页没有预设路线收益。</div>'}</section>
<section id="matrix"><h2>把完整分母与失败一同放回结果表</h2><p class="section-note">表内为“输出完整路线数 / 实际请求次数”。门任务、拒绝检查、机制查询和敏感性分开，避免把拒绝请求当作求路失败率。{e(graph_note)}</p>{totals}<p class="integrity">完整明细以逐请求 CSV 和原始 run 回执为准。路线更短不证明源边界更准确；无独立面积真值，不报告边界准确率或伪 IoU。</p></section>
<section id="evidence"><h2>怎样复现与核对？</h2><div class="download-grid"><div><b>运行与方法</b><a href="{e(args.app_url)}">实时 APP（本机服务）</a><br><a href="README.md">README · 启动 / 停止</a><br><a href="METHOD.md">METHOD · 方法</a><br><a href="RESULTS.md">RESULTS · 真实结果</a></div><div><b>逐请求与图中证据</b>{downloads}</div><div><b>独立审核与来源</b><a href="{independent_href}" download="independent_review.md">独立审核范围与未完成项</a><br><a href="SCOPE_AND_METHOD.md">范围与冻结基线</a><p>小型 CSV 内嵌下载，同时支持 file:// 与 HTTP；大表链接仅供 ZIP 内离线打开。</p></div></div><div class="boundary-note"><p><b>原生边界与条件空间的身份保持分开。</b>源 P 不动；Ω 沿用障碍、内环、权限、层级和既有 0.25 米面净空。草地内合法原生步道仍是独立线，不据此填平草地洞。</p><p>条件接缝保持 inferred 假设身份，F0 系数 1、F1 系数 2，未知实际宽度；不填回 P→Ω 的扣除部分，不跨道路中心线新造过街，不扩大原门心 30 米域，也不生成未登记入口。</p><p>本页面可离线打开；实时 APP 需要本机服务运行。当前状态保留 <code>PENDING_USER_OBSERVATION</code> 与 <code>SCREENSHOT_REQUEST_UNBOUND</code>，作者测试、独立核验、用户验收与现场验证分别记录。</p></div><details><summary>本页生成身份、源文件 hash 与缺项</summary><pre>{json_text(provenance)}</pre></details></section>
</main><footer>© OpenStreetMap contributors · ODbL · 冻结源对象与 EPSG:32651 米制计算<br>画廊生成时间 {e(generated)} · 只读取真实输出 · 本脚本求解器调用 0 / 外部请求 0</footer></body></html>'''
    (ROOT / 'index.html').write_text(html, encoding='utf-8')
    print(json.dumps({'output': 'index.html', 'sha256': digest(ROOT / 'index.html'), **provenance}, ensure_ascii=False))


if __name__ == '__main__':
    main()
