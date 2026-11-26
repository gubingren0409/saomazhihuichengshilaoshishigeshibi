"""Offline source-contract and evidence-map production; never downloads or solves routes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import html
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def contracts(root: Path, old: Path):
    phase = old / "phase2"
    registry = json.loads((phase / "candidate_registry.json").read_text(encoding="utf-8"))
    layers = json.loads((phase / "layer_audit.json").read_text(encoding="utf-8"))
    sources = json.loads((phase / "sources.json").read_text(encoding="utf-8"))
    evidence = []
    for candidate in registry:
        for rel, expected in candidate["source_hashes"].items():
            p = phase / rel
            actual = sha(p)
            assert actual == expected, f"Old candidate input changed: {p}"
            evidence.append({"candidate": candidate["scene_id"], "path": str(p), "sha256": actual,
                             "bytes": p.stat().st_size, "kind": "EXISTING_RETAINED_FEATURE_RESPONSE"})
    for source in sources:
        p = phase / source["evidence_path"]
        assert sha(p) == source["evidence_sha256"], f"License evidence changed: {p}"
        evidence.append({"source_id": source["source_id"], "path": str(p), "sha256": sha(p),
                         "bytes": p.stat().st_size, "kind": "HISTORICAL_TERMS_EVIDENCE_NOT_NEW_WEB_CHECK"})
    out = []
    for candidate in registry:
        cid = candidate["scene_id"]
        nyc = candidate["provider"] == "NYC"
        retained = bool(candidate["source_hashes"])
        audit = [r for r in layers if r["scene_id"] == cid]
        counts = {r["layer"]: r["features"] for r in audit}
        source_refs = [{"file": f"phase2/{p}", "sha256": h} for p, h in candidate["source_hashes"].items()]
        specs = [
            ("A", "地图显示保真", "TESTABLE_GEOMETRY_RENDER_ONLY" if retained else "MISSING_INPUT_METADATA_ONLY",
             "建筑轮廓与内环可核对；NYC另有登记人行面。" if retained else "仅保留检索窗口和元数据，未保留几何。",
             "独立时相图面/实地边界参考未取得；图层完整性、目标名称与建筑ID关联待核。",
             "可做源几何到渲染一致性检查；不能据此证明地图完整或现实精度。"),
            ("B", "道路侧别/人行道关系", "PARTIAL_INPUT_MISSING_ROAD_RELATION_AND_REFERENCE" if nyc else "MISSING_INPUT_AND_REFERENCE",
             "已有原生人行道面，可作侧向几何输入。" if nyc else "没有保留可用道路轴、人行道或过街几何。",
             "缺道路轴/车行范围、方向、侧别绑定、过街及层级；缺独立道路侧别参考。",
             "缺入口不阻止本模块研究；NYC可准备几何输入，但当前不能完整评价道路—侧别关系。"),
            ("C", "步行面—步道接口", "PARTIAL_FACE_INPUT_MISSING_LINE_AND_REFERENCE" if nyc else "MISSING_INPUT_AND_REFERENCE",
             "已有登记人行面及内环；面并非已核验的线网。" if nyc else "YLRE步行/道路/绿地请求没有保留成功几何，不能把UNKNOWN当空图层。",
             "缺步道线、原生接点/接口、连接方向/层级及独立接通参考；人行面采集规范存在范围限制。",
             "无需先取得门坐标即可研究面线衔接；当前仅NYC具部分面输入。"),
            ("D", "已登记门末段整链", "MISSING_INPUT_AND_REFERENCE",
             "当前没有可空间匹配的原生门坐标/角色及完整外部网络。",
             "缺稳定门ID/坐标/角色、合法起点、步网、门前连接及独立连续通路参考。",
             "Oodi官方文字说明三个朝向入口及开放时间，仅建筑级文字证据，不是门坐标标签；建筑多边形不能替代入口。" if cid == "hel_oodi" else "建筑轮廓、人行面均不能替代登记门或真实可通行证据。"),
        ]
        for module, label, status, actual, missing, scope in specs:
            out.append({"candidate_id": cid, "name": candidate["name"], "module": module,
                        "module_name": label, "status": status, "retained_counts": counts,
                        "available": actual, "missing_input_or_reference": missing,
                        "supported_scope": scope, "input_exposure": "EXPOSED_AUTHOR_AND_REVIEWER",
                        "reference_exposure": "NO_COORDINATE_GOLD_ACQUIRED; historical source observations exposed",
                        "group": candidate["provisional_group"], "split": "UNASSIGNED_NOT_FROZEN",
                        "source_files": source_refs, "license": candidate["license"],
                        "public_release": "NOT_APPROVED"})
    write_json(root / "contracts/module_contracts.json", out)
    with (root / "contracts/module_contracts.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(out[0]))
        writer.writeheader()
        for row in out:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in row.items()})
    write_json(root / "contracts/source_verification.json", {
        "checked_at": datetime.now(timezone.utc).isoformat(), "new_http_requests": 0,
        "new_data_bytes": 0, "verified_files": evidence,
        "historical_budget_caveat": "8,000,001B is historical accounting (known reads plus reserved timeout), not verified actual network upper bound or new remaining allowance",
        "candidate_status": "All five remain exposed; no validation/blind groups frozen",
        "old_343_manifest": "Referenced fixed Foundation package; no old source files modified"})
    license_rows = [{"source_id": s["source_id"], "data_url": s["data_url"],
                     "terms_url": s["terms_url"], "license": s["license"],
                     "evidence_sha256": s["evidence_sha256"], "evidence_original": str(phase / s["evidence_path"]),
                     "storage": s["storage"], "redistribution": s["redistribution"],
                     "limitation": s["limits"], "last_observation": s["retrieval_date"],
                     "current_web_check": "NOT_PERFORMED_NO_NEW_REQUESTS"} for s in sources]
    write_json(root / "contracts/license_reference_audit.json", license_rows)
    header = "|候选|A 图面|B 道路侧别|C 面线衔接|D 已知门整链|\n|---|---|---|---|---|\n"
    table = ""
    for candidate in registry:
        cid = candidate["scene_id"]
        statuses = [r for r in out if r["candidate_id"] == cid]
        cells = ["可检源→图一致性；独立参考缺失" if r["module"] == "A" and candidate["source_hashes"]
                 else "仅元数据" if r["module"] == "A"
                 else "部分面输入；线/关系/参考缺失" if r["module"] in ["B", "C"] and candidate["provider"] == "NYC"
                 else "输入与参考缺失" for r in statuses]
        table += f"|{candidate['name']}|" + "|".join(cells) + "|\n"
    text = "# 已有五候选的分模块合同\n\n" + header + table + "\n"
    text += "本轮只读核验6份已保留的非空几何响应与8份来源许可证据，未发起任何新HTTP请求。NYC共692个建筑、172个人行面；Helsinki保留371个建筑（Oodi112、Meilahti259）。Kallio仍为元数据窗口，数量未知。人行面内环保留；Meilahti两个不与原请求框相交的对象保留历史异常身份。\n\n"
    text += "五个候选全部已暴露，不是盲集。上海六裁片共享道路/对象，仍只作为开发组；NYC与Helsinki分别保守归为同城市网络未知组，不随机拆分相邻裁片。公共输入暴露与评价参考暴露分栏；没有取得坐标级独立金标准，不等于已存在未曝光盲标签。\n\n"
    text += "缺门坐标不会自动否定B/C的研究价值；但只有建筑面也不能证明D准备完成。NYC的人行面可作为B/C的部分输入，尚缺道路轴、原生线网、接口、层级和独立关系参考。Helsinki当前只有建筑几何，不能以失败或超限请求推定其他图层不存在。\n\n"
    text += "许可沿用2026-11-12已保存证据，本轮未更新网站观察。NYC并非默认CC0；Helsinki的CC BY4.0证据包括官方检索观察，不能冒称保存了403页面的许可全文。OSM、Geofabrik、BBBike属于同一数据家族，不构成三份独立真值。所有现有材料保持本地审核身份，首次公开未批准。\n\n"
    text += "旧8,000,001B是已知读取量加超时预留的预算记账，不是实测网络总流量上界；不转作本轮新额度。补取提案另见next_acquisition_proposal.md，尚未执行。\n"
    (root / "contracts/module_contracts.md").write_text(text, encoding="utf-8")
    proposal = {
        "status": "PROPOSED_NOT_EXECUTED_REQUIRES_NEW_USER_AUTHORIZATION",
        "new_requests_this_round": 0, "new_bytes_this_round": 0,
        "purpose": "Only fill B/C road-side and face-line input/reference gaps; do not grow building counts",
        "sites": [
            {"candidate": "nyc_lincoln_center", "window": "One 200m×200m subwindow inside existing candidate, fixed from source geometry before method results",
             "modules": ["B", "C"], "source": "NYC official OpenData sidewalk dataset52n9-sdep already retained; identify official road/curb and crossing layer from dataset metadata before retrieval",
             "fields": ["native_id", "road/curb full geometry", "coordinate system and units", "capture date", "side relation", "crossing endpoints", "level/access if available"],
             "requests_max": 4, "read_bytes_max": 2000000,
             "reference": "Separate manually reviewed source-native road/side and exact line/face interface table, reviewed without proposed-route outputs; not inferred door labels",
             "license_gate": "NYC OpenData Terms plus actual road-layer agency/additional conditions must permit local research copy; no public redistribution assumption"},
            {"candidate": "hel_oodi", "window": "One200m×200m subwindow inside existing Oodi bbox; retain full intersecting polygons with holes",
             "modules": ["B", "C"], "source": "Existing Helsinki WFS metadata: avoindata:YLRE_Katu_ja_viherosat_kevytliikenne_alue and ajorata_alue, explicit srsName/bbox CRS",
             "fields": ["native_id", "area geometry with holes", "road/sidewalk type", "date", "source CRS", "connecting line/node if schema actually supplies it", "access/level if present"],
             "requests_max": 4, "read_bytes_max": 2000000,
             "reference": "Independent schema/geometry/interface audit; no connectivity truth unless original line/node evidence is available",
             "license_gate": "Retain City of Helsinki/HRI attribution, CC BY4.0 evidence and modification notice; verify actual layer coverage/conditions"}],
        "total_requests_max": 8, "total_read_bytes_max": 4000000,
        "request_accounting": "Count failed/timeouts/redirects and retries; read strict remaining cap without cap+1 sentinel; unknown transport bytes separately",
        "stop_conditions": ["No applicable source license", "CRS/schema unresolved", "first response empty/capped: report exact blocker and stop branch rather than whole-city expansion", "8requests or4MB total read reached", "No native line/connectivity reference: keep C partial, no fabricated interfaces", "No independent reference: no accuracy claim or blind freeze"],
        "D_known_door": "Not included in this small proposal; requires separate registered coordinate/role and continuous-path reference acquisition approval",
        "split": "All existing sites remain EXPOSED; group/network independence reviewed before any later split freeze"}
    write_json(root / "contracts/next_acquisition_proposal.json", proposal)
    (root / "contracts/next_acquisition_proposal.md").write_text(
        "# 下一次补取提案（本轮未执行）\n\n只针对Lincoln Center与Oodi现有候选各一个200×200米窗口补B/C，不新增建筑计数任务。具体字段、来源和许可门见同名JSON。\n\n"
        "总上限8次HTTP请求、4,000,000字节读取；每场景最多4次、2,000,000字节，失败、重定向及重试均记账。不把历史超时预留折成新额度。首次响应无覆盖/超限或CRS不明，停止该分支，保留缺项。\n\n"
        "NYC：先从官方元数据确认道路/路缘与过街层，再取原生ID、完整几何、CRS/单位/日期、道路侧别、接点与可得层级权限。已有52n9-sdep人行面复用。数据集机构附加条款未核对，不公开分发。\n\n"
        "Oodi：依据现有WFS元数据，对轻交通面与车行面分别作显式CRS小窗请求，保留内环；字段依实际schema，缺失层级/权限写UNKNOWN，不能补造。沿用并复核Helsinki/HRI CC BY4.0署名和修改说明。\n\n"
        "评价参考另存：由实际独立人员先审原生道路侧别和线面接口，不向其展示候选算法结果；原生线/接点不够时只做输入及图面检查，不声称获得通达真值。已知门D不在此次补取提案中，另需原生坐标/角色与连续通路参考。所有已有候选保持EXPOSED，不冻Validation/Blind。\n\n"
        "本文件只是待批准方案；本轮请求数=0，新增采集字节=0。\n", encoding="utf-8")
    return {"module_rows": len(out), "source_files_verified": len(evidence),
            "candidate_count": len(registry), "new_requests": 0}


def edge_layer(edge):
    text = str(edge.get("layer", edge.get("evidence", edge.get("kind", "")))).lower()
    if "cross" in text:
        return "crossing"
    if any(s in text for s in ["hyp", "conditional", "default"]):
        return "hypothesis"
    if any(s in text for s in ["tag", "explicit_side"]):
        return "tag_derived"
    if any(s in text for s in ["native", "footway", "sidewalk"]):
        return "native"
    if any(s in text for s in ["road", "axis", "shared"]):
        return "road_axis"
    return "tag_derived" if edge.get("side") not in [None, "axis"] else "native"


def map_html(root: Path, data):
    document = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PG1 街区侧通道 · 真实地图对照</title><link rel="stylesheet" href="maps/viewer.css"></head><body>
<header><p class="subtitle">SMART-CITY-WALKABILITY-FOUNDATION-PG1 · 有限续执行 · 开发诊断</p><h1>道路轴、原生步道与条件侧向通道</h1><p>同一冻结原始地图、同一局部窗口、同一固定查询；切换结果不会触发新的求路。</p></header>
<main><p><a href="http://127.0.0.1:53511/foundation/">回看旧六场景原始地图与当前输出</a>（依赖本机53511服务及原固定包；本页新三窗口地图可离线打开）</p><div class="notice"><strong>先看线的身份：</strong>蓝色为原生步道，紫色为标签支持的侧向表示，橙色虚线为缺标条件假设。侧向通道的显示偏移标为 <strong>SCHEMATIC</strong>，不代表实测道路宽度、净空或精确步程。弯点可能显示分段间隙，不能据此宣称物理连续；跨路只保留原有适用连接。R0把两侧压成同点的零长度结果不算成功；同侧广场/原生步道接口仍需独立核验。</div>
<p id="error" role="alert"></p><p class="muted">细淡线保留原始地图上下文，较粗彩线为实际图边；源中可见不等于已准入路由。没有实际宽度时，示意侧向线不用于净空或障碍通过证明。</p><p>原生步道保留原对象ID；道路—人行道侧别绑定和全部物理平行重复尚未独立确认。不能将侧向候选称为已恢复的真实人行道；本轮还未把它接入完整业务到门路线。</p><div class="controls"><label>固定窗口 <select id="window"></select></label><label>固定查询 <select id="query"></select></label><button id="reset">恢复完整窗口</button><label><input type="checkbox" id="show-route" checked>显示已运行路线</label><button id="export">导出该查询与当前视野</button></div>
<div id="layers"></div><p><span class="swatch" style="border-color:#2d3238;border-top-width:4px"></span> 黑色粗线：本次计算路线；示意/假设路段仍为虚线，与玫瑰色原有过街分开。</p><p id="window-note"></p><p class="muted">窗口按源道路结构预先选定；场景名表示冻结裁片来源，目标建筑本体未必落入本局部窗口。滚轮缩放、拖动平移；三个面板视野联动；点选对象查看证据。起/终为固定图查询绑定，非用户GPS或新登记入口。</p>
<div class="compare">__PANELS__</div><p class="scale" id="source-hash"></p>
<div class="below"><section><h2>本次实际保存的对照结果</h2><table id="results"></table><p>这是有限开发机制查询。SCHEMATIC图的代价是拓扑代理量，不能写成精确步程收益。没有路线保留失败，不补画连接。</p><h2>对象证据</h2><button id="evidence-export">导出所选对象证据</button><pre id="evidence"></pre></section><section><h2>查询身份与视野</h2><p>下方是本轮真实正式查询及结果的显示副本，页面不声称重新运行求解器。</p><pre id="request"></pre></section></div>
<h2>候选材料按模块可用到哪一步</h2><p>缺门坐标不自动否定道路侧别和面线衔接研究；建筑面本身也不能证明末段整链准备完成。</p>__CONTRACT_TABLE__
<p><a href="contracts/module_contracts.md">模块合同说明</a> · <a href="contracts/module_contracts.csv">机器可读合同 CSV</a> · <a href="contracts/next_acquisition_proposal.md">下一次小规模补取提案（未执行）</a> · <a href="DECISION_BRIEF.md">本轮简报</a> · <a href="reviews/author_algorithm_review.md">作者算法检查</a></p>
<h2>代表性同图对照</h2><div class="figures">__FIGURES__</div></main>
<footer><p>© OpenStreetMap contributors · 冻结源裁片；非实时导航。原生几何、派生表示与条件假设分别保留身份。G0公开待批准；G1视觉验收待用户；G2分组未冻结；父Goal未完成。</p></footer>
<script>window.TRIAL_DATA=__DATA__;</script><script src="maps/viewer.js"></script></body></html>'''
    panels = ""
    captions = {"R0": ("当前道路轴 / 共享街道表示", "保持父方法已准入的原生/道路轴身份。"),
                "R1": ("原生步道 + 标签侧向表示", "无独立几何的侧向边仍为逻辑表示。"),
                "R2": ("增加缺标条件侧向通道", "条件许可与源地图事实分开；不生成假设过街。")}
    for variant, (title, caption) in captions.items():
        panels += f'<section class="panel"><h2>{variant} · {title}</h2><p class="summary" id="summary-{variant}"></p><svg class="map" id="map-{variant}" aria-label="{variant}真实地图对照"></svg><p class="caption">{caption} SCHEMATIC偏移仅用于显示。</p></section>'
    contracts_path = root / "contracts/module_contracts.json"
    table = ""
    if contracts_path.exists():
        rows = json.loads(contracts_path.read_text(encoding="utf-8"))
        table = "<table><tr><th>候选</th><th>A 图面</th><th>B 侧别</th><th>C 面线</th><th>D 已知门</th></tr>"
        for cid in dict.fromkeys(r["candidate_id"] for r in rows):
            selected = [r for r in rows if r["candidate_id"] == cid]
            table += "<tr><td>" + html.escape(selected[0]["name"]) + "</td>" + "".join(
                f'<td title="{html.escape(r["supported_scope"])}">' + (
                    "源→图可检，独立参考缺失" if r["status"].startswith("TESTABLE") else
                    "部分输入，关系/参考缺失" if r["status"].startswith("PARTIAL") else
                    "仅元数据" if r["status"].endswith("METADATA_ONLY") else "缺输入与参考") + "</td>" for r in selected) + "</tr>"
        table += "</table>"
    figures = "".join(f'<figure><a href="figures/{p.name}"><img loading="lazy" src="figures/{p.name}" alt="{html.escape(p.stem)}真实数据对照"></a><figcaption>{html.escape(p.stem)} · 同一源窗口与视野</figcaption></figure>' for p in sorted((root / "figures").glob("*.png")))
    document = document.replace("__PANELS__", panels).replace("__CONTRACT_TABLE__", table).replace("__FIGURES__", figures)
    document = document.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (root / "index.html").write_text(document, encoding="utf-8")


def figures(root: Path, data):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MplPath
    from shapely.geometry import shape
    from shapely.geometry.polygon import orient
    plt.rcParams.update({"font.family": "Microsoft YaHei", "axes.unicode_minus": False,
                         "font.size": 10, "figure.facecolor": "#fcfaf7", "axes.facecolor": "#fcfaf7"})
    palette = {"road_axis": "#70757a", "native": "#5b9fbe", "tag_derived": "#8177a8", "hypothesis": "#d49757", "crossing": "#b97589"}
    written = []
    def geometry(ax, geom, tags):
        if not geom:
            return
        g = shape(geom)
        if g.geom_type == "Polygon":
            g = orient(g, sign=1.0)
            verts, codes = [], []
            for ring in [g.exterior, *g.interiors]:
                c = list(ring.coords)
                verts.extend(c)
                codes.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(c)-2) + [MplPath.CLOSEPOLY])
            fill = "#d7d3cf" if tags.get("building") else "#dce6d0" if tags.get("landuse") == "grass" or tags.get("natural") == "wood" else "#d3eaf5" if tags.get("natural") == "water" else "#eee8dd"
            ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=fill, edgecolor="#aaa297", linewidth=.45, zorder=1))
        elif g.geom_type.startswith("Multi") or g.geom_type == "GeometryCollection":
            from shapely.geometry import mapping
            for part in g.geoms:
                geometry(ax, mapping(part), tags)
        elif g.geom_type == "LineString":
            x, y = g.xy
            native = tags.get("highway") in ["footway", "path", "pedestrian", "steps"]
            ax.plot(x, y, color="#5b9fbe" if native else "#a4a8ab" if tags.get("highway") else "#857d70", linewidth=.65, alpha=.35 if native else 1, zorder=2)
            if tags.get("name") and tags.get("highway"):
                mid = g.interpolate(.5, normalized=True)
                ax.text(mid.x, mid.y, tags["name"], fontsize=6, color="#70757a", clip_on=True)
        elif g.geom_type == "Point":
            ax.plot(g.x, g.y, ".", color="#857d70", markersize=2, zorder=2)
    for w in data["windows"]:
        bounds = w["bounds_xy"]
        for close in [False, True]:
            fig, axes = plt.subplots(1, 3, figsize=(18, 9.5), dpi=120)
            b = list(bounds)
            if close:
                cx, cy = (b[0]+b[2])/2, (b[1]+b[3])/2
                hw, hh = (b[2]-b[0])*.29, (b[3]-b[1])*.29
                b = [cx-hw, cy-hh, cx+hw, cy+hh]
            for ax, variant in zip(axes, ["R0", "R1", "R2"]):
                for f in w.get("source_features", []):
                    geometry(ax, f.get("geometry"), f.get("tags", {}))
                edges = w["variants"][variant].get("edges", [])
                for e in edges:
                    xy = e.get("xy", (e.get("geometry") or {}).get("coordinates"))
                    if not xy:
                        continue
                    k = edge_layer(e)
                    ax.plot([p[0] for p in xy], [p[1] for p in xy], color=palette[k],
                            linestyle="--" if k in ["tag_derived", "hypothesis"] else "-", linewidth=1.25, zorder=3)
                q = (w.get("queries") or [{}])[0]
                result = q.get("results", {}).get(variant, {})
                route = set(str(eid) for eid in result.get("edge_ids", result.get("path_edge_ids", [])))
                for e in edges:
                    if str(e["edge_id"]) not in route:
                        continue
                    xy = e.get("xy", (e.get("geometry") or {}).get("coordinates"))
                    if xy:
                        ax.plot([p[0] for p in xy], [p[1] for p in xy], color="#2d3238", linewidth=2.6,
                                linestyle="--" if e.get("geometry_status") == "SCHEMATIC" or edge_layer(e) == "hypothesis" else "-", zorder=5)
                binding = q.get("bindings", {}).get(variant, {})
                for label, nid, color in [("起", binding.get("start"), "#2d3238"), ("终", binding.get("end"), "#a24860")]:
                    p = w.get("nodes", {}).get(nid)
                    if isinstance(p, dict):
                        p = p.get("xy")
                    if p:
                        ax.plot(*p, "o", color=color, markersize=5, markeredgecolor="white", zorder=6)
                        ax.annotate(label, p, xytext=(6, 7), textcoords="offset points", color=color, fontsize=9)
                ax.set_xlim(b[0], b[2]); ax.set_ylim(b[1], b[3]); ax.set_aspect("equal")
                ax.set_title(f"{variant}  ·  {result.get('status', 'NO_SAVED_RESULT')}\n{len(edges)} 条图边 · 固定查询 {q.get('query_id', '')}", fontsize=11, pad=12)
                ax.ticklabel_format(style="plain", useOffset=False)
                ax.tick_params(labelsize=6)
                ax.set_xlabel("EPSG:32651 东向 / m", fontsize=8)
                if ax is axes[0]:
                    ax.set_ylabel("EPSG:32651 北向 / m", fontsize=8)
                ax.annotate("N", xy=(.95, .93), xytext=(.95, .82), xycoords="axes fraction", ha="center", arrowprops={"arrowstyle": "->", "color": "#2d3238"})
            handles = [Line2D([0], [0], color=palette[k], linestyle="--" if k in ["tag_derived", "hypothesis"] else "-", lw=2, label=l)
                       for k, l in [("road_axis", "道路轴"), ("native", "原生步道"), ("tag_derived", "标签派生 SCHEMATIC"), ("hypothesis", "默认假设 SCHEMATIC"), ("crossing", "原有过街")]]
            handles.append(Line2D([0], [0], color="#2d3238", lw=2.6, label="计算路线（示意/假设为虚线）"))
            fig.legend(handles=handles, loc="lower center", ncol=6, frameon=False, bbox_to_anchor=(.5, .055), fontsize=9)
            fig.suptitle(f"{w.get('label', w['window_id'])} · {'局部细图' if close else '完整固定窗口'}", fontsize=17, y=.965)
            fig.text(.5, .923, f"{w.get('selected_road_id', '')} · 来源时相 {w.get('source_timestamp', 'UNKNOWN')} · SHA256 {w.get('source_sha256', '')[:16]}…（完整值见 maps/trial_map_data.json）", ha="center", fontsize=9, color="#70757a")
            fig.text(.5, .025, "侧向显示偏移为SCHEMATIC；不代表实测道路宽度、净空或精确步程。© OpenStreetMap contributors · 细淡线为源上下文，粗线为图边", ha="center", fontsize=10, color="#70757a")
            fig.subplots_adjust(left=.065, right=.985, top=.84, bottom=.17, wspace=.20)
            name = f"{w['window_id']}_{'detail' if close else 'comparison'}.png"
            fig.savefig(root / "figures" / name, dpi=120, facecolor="#fcfaf7")
            plt.close(fig)
            written.append(name)
    write_json(root / "contracts/figure_build_receipt.json", {"renderer": "Matplotlib Agg", "files": written,
               "map_input_sha256": sha(root / "maps/trial_map_data.json"), "solver_calls": 0,
               "build_code_sha256": sha(Path(__file__)), "viewer_code_sha256": sha(root / "maps/viewer.js"),
               "identity": "visualization of actual saved trial outputs; zoom crops are display only"})
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--old", type=Path)
    parser.add_argument("--contracts", action="store_true")
    parser.add_argument("--maps", action="store_true")
    parser.add_argument("--figures", action="store_true")
    args = parser.parse_args()
    if args.contracts:
        if args.old is None:
            parser.error("--contracts requires --old old Foundation directory (read-only)")
        print(json.dumps(contracts(args.root, args.old), ensure_ascii=False))
    if args.maps or args.figures:
        data = json.loads((args.root / "maps/trial_map_data.json").read_text(encoding="utf-8"))
        if args.figures:
            print(json.dumps({"figures": figures(args.root, data)}, ensure_ascii=False))
        map_html(args.root, data)
        print(json.dumps({"map_windows": len(data["windows"]), "index": str(args.root / "index.html"), "new_solver_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
