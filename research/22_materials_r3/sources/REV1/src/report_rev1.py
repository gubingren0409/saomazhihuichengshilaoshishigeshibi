"""Summarize the actual R4-REV1 records without changing any run."""
import argparse
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = "R1_AREA_EDGE_MAIN"
WIDTHS = ((1, "R1_WIDTH_1M"), (3, MAIN), (5, "R1_WIDTH_5M"))
REACHED = "EXTERIOR_REACHED_CONDITIONAL"


def read(root, name):
    return json.loads((root / name).read_text(encoding="utf-8-sig"))


def meters(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def rows(variants, name):
    return {x["scene_id"]: x for x in variants[name]["scenes"]}


def write(root, name, lines):
    (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(root=ROOT):
    experiment = read(root, "runs/experiment.json")
    resource = read(root, "runs/resource_use.json")
    entry = read(root, "data/entrance_approach.json")
    diagnostic = read(root, "data/native_prefix_diagnostic.json")
    exact_edge_check = read(root, "runs/edge_geometry_audit.json")
    cases = {s["scene_id"]: s for s in experiment["case_catalog"]}
    runs = experiment["runs"]
    cfg = experiment["config"]
    museum = cfg["museum"]["scene_id"]
    h0 = rows(runs, "H0_FROZEN_B0")
    ablation = rows(runs, "R1_WITHOUT_DERIVED_EDGES")
    main_rows = rows(runs, MAIN)
    south, north = entry["south"], entry["north"]["main"]
    library = entry["library"]
    added = sum(x["truly_added_edges_unique"] for x in main_rows.values())
    directed = sum(x["truly_added_edges_directed"] for x in main_rows.values())
    edge_kinds = Counter()
    rejected = Counter()
    dedup = 0
    for case in main_rows.values():
        for area in case["areas"]:
            edge_kinds.update(area.get("edge_kind_counts", {}))
            rejected.update(area.get("rejected", {}))
            dedup += area.get("deduplicated", 0)
    if sum(edge_kinds.values()) != added:
        raise ValueError("Derived edge count does not reconcile")
    if exact_edge_check["edge_records"] != added:
        raise ValueError("Exact geometry receipt does not match edge count")
    checks = sum(x["matches_frozen"] for x in h0.values())
    restored = sum(x["same_topology_and_native_weights"] and x["same_strict_entrances"] for x in ablation.values())
    selected = south["selected"]
    south_trials = south["all_contacts"]
    chosen = (f"主设置下三个接点中选用 {selected['contact_id']}。从原起点到原南门的整条路径约 "
              f"{meters(selected['length_m'])} 米，末点距登记点 {meters(selected['gap_m'], 6)} 米。"
              if selected else "主设置下没有通过完整路线口径的南门连接。")
    statuses = Counter(r["status"] for r in south_trials)
    summary = dict(case_count=len(cases), baseline_matches=checks, ablation_matches=restored,
                   main_unique_edge_records=added, main_directed_edge_arcs=directed, main_edge_kinds=dict(edge_kinds),
                   deduplicated_native_candidates=dedup, rejected_candidate_events=dict(rejected),
                   south_trials=len(south_trials), south_trial_statuses=dict(statuses),
                   south_selected=selected, north=north, library=library,
                   exact_geometry_duplicates=exact_edge_check["exact_duplicate_segment_records"],
                   prefix_diagnostic=diagnostic["records"],
                   provider_requests=experiment["external_requests"], field_checks=experiment["field_checks"])
    (root / "runs/summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# R4-REV1 实验结果", "",
             chosen + f"北西出口的门外状态为 {north['exterior_approach']}，入馆角色为 {north['inbound_eligibility']}。",
             "", "[打开地图同图对照](visuals/index.html) · [完整逐门记录](data/entrance_approach.json)", "",
             "## 南侧三个接点", "",
             "南广场为 `relation/2385771`。两个源草地内环保留。冻结 H0/H1 均无严格到门路线。下表以同一原起点走原生图至指定接点，再经南广场派生图到原门。长度单位为米。",
             "", "| 接点及原生线 | 条件路线状态 | 原生段 | 边缘段及原生接点端口 | 门前端口 | 投影总长 | 椭球复算 | 门坐标残差 |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in south_trials:
        sections = r["section_lengths_m"]
        lines.append(f"| {r['contact_id']} · {', '.join(r['contact_source_way_ids'])} | {r['status']} | "
                     f"{meters(sections.get('NATIVE_LINEAR'))} | "
                     f"{meters(sections.get('DERIVED_FROM_TAGGED_PEDESTRIAN_AREA'))} | "
                     f"{meters(sections.get('DERIVED_TERMINAL_CONNECTOR'),3)} | "
                     f"{meters(r['length_m'])} | {meters(r['length_geodesic_m'])} | {meters(r['gap_m'],6)} |")
    lines += ["", f"各试走的平面障碍复核为 `{json.dumps([r['obstacle_conflicts'] for r in south_trials], ensure_ascii=False)}`。"
              "原生段延用冻结拓扑，派生段及端口逐段复核。",
              "", "## 北侧门外与入馆角色", "",
              "| 项目 | 原图 | 3 米派生图 |", "| --- | --- | --- |"]
    old = entry["north"]["old"]
    for label, key, numeric in (("到门外状态", "exterior_approach", False),
                                ("到可达位置长度 m", "length_m", True),
                                ("剩余投影缺口 m", "gap_m", True),
                                ("剩余椭球缺口 m", "gap_geodesic_m", True),
                                ("最近可达源边", "reachable_edge", False),
                                ("入馆资格", "inbound_eligibility", False)):
        vals = [meters(r.get(key), 4) if numeric else r.get(key, "—") for r in (old, north)]
        lines.append(f"| {label} | {vals[0]} | {vals[1]} |")
    gap = north.get("gap_evidence", {})
    lines += ["", f"北西门保留 `{north['entrance_role']}` 角色和原坐标 `{north['original_coordinate']}`。"
              f"北侧源步行面的边界距离为 {meters(north.get('source_face_gap_m'),4)} 米，"
              f"最近可达沿网位置为 `{north.get('reachable_network_position')}`。"
              f"测距线中无支撑部分 {meters(gap.get('unsupported_length_m'),4)} 米，保留为 `GAP_DIAGNOSTIC_NOT_ROUTABLE`。"
              "门外与入馆资格独立记录。", "", "## 原生前缀的只读障碍诊断", ""]
    for record in diagnostic["records"]:
        if record["subject"] == "SOUTH_CONTACT":
            lines.append(f"- 南接点 {record['contact_id']} 的原最短前缀与围栏 way/178733289 平面相交。只读视图改走原图已有的其他边，复用原派生后缀，到原南门共 {meters(record['total_m'])} 米。")
        elif record["subject"] == "NORTH_APPROACH":
            alt = record["alternate"]
            lines.append(f"- 北侧原最短前缀与草地 way/178732700 平面相交。只读视图中，另一条 {meters(alt.get('length_m'))} 米的已有路网路线到达同一测距起点，仍留 {meters(alt.get('gap_m'),4)} 米。")
    lines += ["", "只读视图按已标障碍过滤查询候选，原路网签名前后一致。保留首次主实验的判定与选路。 [独立诊断输出](data/native_prefix_diagnostic.json)",
              "", "## 六场景与消融", "",
              f"原始线网回放 {checks}/{len(cases)} 与冻结记录一致。移除新增层后 {restored}/{len(cases)} 恢复原拓扑、原边权和严格门结果。"
              f"旧 R4 实际新增为 0。本轮 3 米配置新增 {added:,} 条带来源的计算边记录（{directed:,} 条有向弧）。"
              f"原生几何重复过滤记录为 {dedup:,}，跨来源面精确重复几何为 {exact_edge_check['exact_duplicate_segment_records']:,}。候选拒绝以候选尝试计，见机器结果中的逐面原因。",
              "", "| 场景 | 原冻结请求 | 新计算边记录 | 原分量 → 新分量 | 起点新增可达图节点 | 说明 |",
              "| --- | --- | ---: | ---: | ---: | --- |"]
    for ident, row in main_rows.items():
        area = ", ".join(f"{a['area_id']} {a['status']}" for a in row["areas"]) or "冻结范围内无适用焦点面"
        lines.append(f"| {cases[ident]['label']} | {h0[ident]['status']} | {row['truly_added_edges_unique']:,} | "
                     f"{row['native_graph']['weak_components']} → {row['graph']['weak_components']} | {row['graph']['reachable_nodes'] - row['native_graph']['reachable_nodes']:,} | {area} |")
    lines += ["", "新增可达图节点以辅助网格节点为主，另有接上的已登记门节点。", "", f"图书馆原路线 {meters(library['old']['length_m'])} 米，新路线 {meters(library['main']['length_m'])} 米。"
              "其他代理目标保留原身份，参与局部图诊断。",
              "", "## 固定带宽对照", "",
              "| 宽度 m | 六场景派生边记录 | 南侧从指定接点接通 | 南侧合格路径 | 最短有效总长 m |",
              "| ---: | ---: | ---: | ---: | ---: |"]
    for width, run in WIDTHS:
        records = rows(runs, run)
        trials = records[museum]["south_contacts"]
        valid = [r["length_m"] for r in trials if r["status"] == REACHED]
        lines.append(f"| {width} | {sum(r['truly_added_edges_unique'] for r in records.values()):,} | "
                     f"{sum(r['derived_contact_to_door_connected'] for r in trials)}/{len(trials)} | "
                     f"{len(valid)}/{len(trials)} | {meters(min(valid, default=None))} |")
    lines += ["", f"作者实跑约 {meters(resource['elapsed_s'], 1)} 秒。主设置保持 3 米，1 米和 5 米用于敏感性解释。",
              "", "## 证据边界", "",
              "本地算法增强使用可追溯的结构化 OSM。Geoapify 仍是历史路线基线，内部图和通行限制未公开。本轮外部请求与现场核验均为 0。"
              "冻结快照覆盖、楼层和现场权限限制结论。六个场景均已被观察，结果仅用于开发和回归。",
              "", "[允许域](data/allowed_domains.geojson) · [逐边记录](data/edge_evidence.jsonl) · "
              "[完整路线](data/routes.geojson) · [机器实验矩阵](runs/experiment.json) · [独立审核](audits/INDEPENDENT_REVIEW.md)"]
    write(root, "RESULTS.md", lines)
    print(json.dumps({key: val for key, val in summary.items() if key not in {"south_selected","north","library","prefix_diagnostic"}}, ensure_ascii=False))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=ROOT)
    main(cli.parse_args().root.resolve())
