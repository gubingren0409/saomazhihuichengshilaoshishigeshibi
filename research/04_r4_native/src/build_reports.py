"""Build the R4 decision and experiment tables from retained result records."""
from collections import Counter
import csv
import json
from pathlib import Path

from .run_dual_paths import read

ROOT = Path(__file__).resolve().parents[1]


def fmt(value):
    return f"{value:.2f}" if value is not None else "—"


def save(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(root=ROOT):
    experiment = read(root / "runs/experiment.json")
    scenes = experiment["scenes"]
    museum = next(row for row in scenes if row["scene_id"] == "sh-huangpu-01")
    dual = read(root / "runs/dual_paths.json")
    source = read(root / "runs/source_scene_contracts.json")
    metrics = {}
    for v in ("B0", "B1", "B2", "B3"):
        applicable = [row for row in scenes if row["eligible_entrance_count"] >= (2 if v == "B3" else 1)]
        metrics[v] = dict(applicable_scenes=len(applicable),
                          eligible_entries=sum(row["eligible_entrance_count"] for row in applicable),
                          valid_entry_routes=sum(row["variants"][v]["valid_entry_route_count"] for row in applicable))
    with (root / "data/edge_candidate_evidence.csv").open(encoding="utf-8-sig", newline="") as handle:
        candidates = list(csv.DictReader(handle))
    with (root / "data/connectivity_changes.csv").open(encoding="utf-8-sig", newline="") as handle:
        connectivity = list(csv.DictReader(handle))
    with (root / "data/added_edges.csv").open(encoding="utf-8-sig", newline="") as handle:
        added = list(csv.DictReader(handle))
    candidate_statuses = Counter(row["status"] for row in candidates)
    if len(added) != candidate_statuses["VERIFIED"]:
        raise ValueError("Actual additions and candidate evidence disagree")
    if len(added) != sum(row["verified_b1_edges"] + row["verified_b2_additional_edges"] for row in scenes):
        raise ValueError("Verified edge count mismatch")
    museum_candidates = Counter((row["variant"], row["status"]) for row in candidates
                                 if row["scene_id"] == museum["scene_id"])
    museum_service = next(row["hosted"] for row in dual["scenes"] if row["scene_id"] == museum["scene_id"])
    baselines_matching = sum(row["local_b0_frozen_replay"]["match"] for row in scenes)
    b1_edges = sum(row["verified_b1_edges"] for row in scenes)
    b2_edges = sum(row["verified_b2_additional_edges"] for row in scenes)
    no_net_effect = all(row["weak_component_delta_from_b0"] == "0" for row in connectivity)
    summary = dict(status="READY_FOR_USER_REVIEW", scenes=len(scenes), source_frozen_count=len(source["scenes"]),
                   b0_frozen_replay_matches=baselines_matching, b1_verified_edges=b1_edges,
                   b2_additional_verified_edges=b2_edges, verified_added_edges=len(added),
                   verified_edge_geometry_pass=sum(row["geometry_check"] == "PASS" for row in added),
                   strict_entry_metrics=metrics, evidence_rows=len(candidates), candidate_statuses=dict(candidate_statuses), field_checks=0,
                   new_geoapify_requests=0, new_buildings=0, user_visual="PENDING_USER_REVIEW",
                   gpt_review="PENDING_GPT_REVIEW", no_weak_component_changes=no_net_effect,
                   retained_paths=["LOCAL_OSM", "GEOAPIFY"], museum_b0_snap_gap_m=museum["local_b0_frozen_replay"]["target_gap_m"],
                   museum_hosted_endpoint_gap_m=museum_service["target_gap_m"])
    (root / "runs/summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# B0–B3 实验结果", "",
             f"固定六个场景全部保留，B0 与历史冻结请求的状态、几何、长度及两端吸附 {baselines_matching}/{len(scenes)} 完全一致。"
             f"B1 新增 {b1_edges} 条，B2 额外新增 {b2_edges} 条。候选逐边表 {len(candidates)} 行，其中原图已有 {candidate_statuses['ALREADY_IN_B0']}、拒绝 {candidate_statuses['REJECTED']}。实际新增表单列。", "",
             "| 场景 | 焦点开放空间 | 外边界原生接点 / 几何近邻 | 缺证边界段 | B1 新边 | B2 额外新边 | 适用入口 | B0 / B1 / B2 分量 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in scenes:
        graph = " / ".join(str(row["variants"][v]["graph"]["weak_components"]) for v in ("B0", "B1", "B2"))
        lines.append(f"| {row['label']} | {row['open_space_count']} | {row['boundary_contact_count']} / {row.get('geometric_boundary_candidate_count',0)} | "
                     f"{row['unsupported_boundary_segments']} | {row['verified_b1_edges']} | "
                     f"{row['verified_b2_additional_edges']} | {row['eligible_entrance_count']} | {graph} |")
    lines += ["", "边界接触与几何近邻分别按场景内的面–原生节点对计数。近邻只作诊断。"
              "缺证边界段按绘制的外环相邻顶点段计数。原始冻结请求结果和严格入口指标采用各自的口径。", "",
              "## 登记入口", "",
              "| 场景 | 入口 | 变体 | 状态与失败理由 | 路线 m | 到入口 m | 平面障碍告警 |",
              "| --- | --- | --- | --- | ---: | ---: | --- |"]
    for row in scenes:
        for v in ("B0", "B1", "B2"):
            for route in row["variants"][v]["routes"]:
                lines.append(f"| {row['label']} | {route['target_native_id']} | {v} | "
                             f"{route['status']} {route['failure_reason'] or ''} | {fmt(route['length_m'])} | "
                             f"{fmt(route['target_gap_m'])} | {', '.join(route['obstacle_ids']) or '—'} |")
    rates = "、".join(f"{v} {metrics[v]['valid_entry_routes']}/{metrics[v]['eligible_entries']}" for v in ("B0", "B1", "B2"))
    b3_note = ("B3 所有建筑均缺少两个适用入口，计为不适用。"
               if metrics["B3"]["applicable_scenes"] == 0 else
               f"B3 适用 {metrics['B3']['applicable_scenes']} 栋。")
    lines += ["", f"严格地图入口可达率为 {rates}。路线必须到达原生登记坐标且没有本轮检查中的平面障碍冲突。{b3_note}"
              "代理点全部在分母之外，馆舍出口另行记录，所有结果均无现场认证。", "",
              "## 上海博物馆南侧", "",
              f"- 原始 B0 最近网络点离南门登记参考 {fmt(museum['local_b0_frozen_replay']['target_gap_m'])} 米，"
              f"超过 35 米冻结门槛。历史 Geoapify 末点距同一请求目标 {fmt(museum_service['target_gap_m'])} 米。",
              f"- B1 原图已有源线段 {museum_candidates['B1','ALREADY_IN_B0']}，正式新增 {museum['verified_b1_edges']}。"
              f"B2 原图已有源线段 {museum_candidates['B2','ALREADY_IN_B0']}，额外新增 {museum['verified_b2_additional_edges']}。"
              "源线候选按面与原生段配对，已在原图的源线段按观察记账。",
              "- 南门与广场外环的原生关系、外围接点、草地内环和路线断点保留在交互视图。",
              "", "## 连通性与敏感性", "",
              ("B0–B2 弱连通分量均未改变。" if no_net_effect else "逐场景分量变化详见数据表。"),
              f"新增边几何检查通过 {summary['verified_edge_geometry_pass']}/{len(added)}。零新增时合法率为 N/A。"
              "以下只比较预先登记的几何容差，精确原生共享节点门槛保持相同。", "",
              "拒绝记录以源线段–面配对为分母。无法执行的图门禁以共同输入的两侧场景为分母，结果 12/12 缺字段。入口未达结果单列。", "",
              "| 容差 m | 源线候选对 | B1 正式新增 | B2 额外正式新增 |",
              "| ---: | ---: | ---: | ---: |"]
    main = read(root / experiment["protocol"])["geometry_tolerance_m"]
    lines.append(f"| {main:.2f}（主） | {len(candidates)} | {b1_edges} | {b2_edges} |")
    for m in sorted({t["tolerance_m"] for row in scenes for t in row["sensitivity"]}):
        rows = [t for row in scenes for t in row["sensitivity"] if t["tolerance_m"] == m]
        lines.append(f"| {m:.2f} | {sum(t['source_line_candidates'] for t in rows)} | "
                     f"{sum(t['verified_b1'] for t in rows)} | {sum(t['verified_b2_additional'] for t in rows)} |")
    lines += ["", "[实际新增边](data/added_edges.csv) · [候选逐边证据](data/edge_candidate_evidence.csv) · [原生外环与接点](data/boundary_candidates.csv) · [逐入口结果](data/entrance_access.csv) · "
              "[图分量变化](data/connectivity_changes.csv) · [机器结果](runs/experiment.json) · [交互图](visuals/index.html)"]
    save(root / "04_EXPERIMENT_RESULTS.md", lines)
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
