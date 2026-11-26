"""Report exact run denominators, and build the source manifest without opening secrets."""
import csv
from hashlib import sha256
from pathlib import Path
from .compare_r3 import ROOT,load,save_json,csv_out


def num(v,n=2):
    return "—" if v is None else f"{v:.{n}f}"


def role(s):
    target=s.get("target_role","UNKNOWN")
    if "TAGGED" in str(target):
        return "OSM_TAGGED"
    if "PROXY" in str(target) or "DIAGNOSTIC" in str(target):
        return "PROXY_OR_UNCERTAIN"
    return str(target or "UNKNOWN")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def build(root=ROOT):
    data=load(root/"runs/comparison.json")
    contract=load(root/"runs/scene_contracts.json")
    local=load(root/"runs/local_results.json")
    hosted=load(root/"runs/hosted_results.json") if (root/"runs/hosted_results.json").exists() else {"scenes":[]}
    cases=data["scenes"]; new=[x for x in cases if not x["historical"]]
    slots=len(new)*2
    paired=sum(x["verified_paired_views"] for x in new)
    local_results=sum(x["local"]["length_m"] is not None for x in new)
    hosted_results=sum(x["hosted"]["length_m"] is not None for x in new)
    refs=sum(role(x)=="OSM_TAGGED" for x in new)
    # No independent route/entrance truth or new user preferences are available.
    blocked=paired<slots or hosted_results==0 or not new
    judgment="INCONCLUSIVE" if blocked or refs<len(new) else "NO_DECISIVE_DIFFERENCE"
    actual_status="PARTIAL_WITH_EVIDENCE" if paired<slots or not new else "READY_FOR_USER_VISUAL_REVIEW"
    receipts=[r.get("receipt",{}) for s in hosted["scenes"] for r in s.get("requests",[])]
    seconds=sum(r.get("elapsed_s") or 0 for r in receipts)
    estimated_credits=sum(r.get("estimated_credits") or 0 for r in receipts)
    known_credits=sum(r.get("actual_credits") is not None for r in receipts)
    source_bytes=sum((root/s["osm_clip"]).stat().st_size for s in contract["scenes"] if s.get("osm_clip"))
    hosted_200=sum(r.get("status_code")==200 for r in receipts)
    overview={"status":actual_status,"judgment":judgment,"dual_paths":"RETAIN",
              "new_frozen_buildings":len(new),"historical_buildings":1,
              "new_paired_views":paired,"new_planned_views":slots,"local_request_routes_returned":local_results,
              "hosted_routes_returned":hosted_results,"osm_tagged_target_references":refs,
              "new_field_checks":0,"human_visual":"PENDING_USER_REVIEW",
              "gpt_acceptance":"PENDING_GPT_REVIEW","hosted_requests_attempted":hosted.get("requests_attempted",0),
              "hosted_halt_reason":hosted.get("halt_reason"),"http_200_count":hosted_200,
              "hosted_request_seconds_sum":round(seconds,2),"estimated_credits":round(estimated_credits,2),
              "actual_credit_receipts":known_credits,"local_clip_bytes":source_bytes,
              "account_charge":"UNKNOWN_NO_PURCHASE_OR_UPGRADE"}
    save_json(root/"runs/summary.json",overview)
    status=load(root/"STATUS.json")
    status.update(overview,phase="SEALED_FOR_REVIEW",state=actual_status)
    save_json(root/"STATUS.json",status)

    lines=["# 冻结样本与视野合同","","本轮在同一上海日期版 OSM 数据下先冻结对象、入口参考、起点和视野，再运行各自路线。所有冻结项留在分母。上海博物馆单列为历史回放，原来两个视野、原评分与请求沿用。","",
        "| 新样本 | 类别及口径 | OSM 对象 | 请求参考等级 | 近景 / 上下文 |",
        "| --- | --- | --- | --- | --- |"]
    for c in contract["scenes"]:
        lines.append(f"| {c['label']} | {c['category']} · {c.get('category_evidence_note','')} | {c.get('building_native_id','—')} | {role(c)} | {'/ '.join(str(v.get('zoom','—')) for v in c.get('views',{}).values()) or '—'} |")
    lines+=["","两档 1200×900、正北、无倾斜。尺度从 WGS84/投影范围和实际像素核验。入口来源分为 OSM 标签、代理和未知。本轮没有现场验证入口。某个 OSM 标记存在，只说明地图中有这个对象。","",
            f"冻结合同 SHA256 `{digest(root/'runs/scene_contracts.json')}`。 [锁定合同](runs/scene_contracts.json) · [预登记判定规则](runs/decision_protocol.json)",""]
    (root/"02_SAMPLE_AND_VIEWPORT_CONTRACT.md").write_text("\n".join(lines),encoding="utf-8")

    lines=["# 配对实测结果","",f"新增冻结 {len(new)} 栋，{paired}/{slots} 档取得可核验同尺度双侧图。历史上海博物馆 1 栋、2 档另计。新样本人工评判为 PENDING_USER_REVIEW，现场验证为 0。","",
        "| 建筑 | 类型 | 同尺度档 | 本地状态 | 本地冻结路线 m | 本地吸附 m | 托管折线 m | 托管末点到请求参考 m |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |"]
    for c in cases:
        target=c["local_status"]+(" · "+c["local_failure_reason"] if c["local_failure_reason"] else "")
        lines.append(f"| {c['label']} | {c['category']} | {c['verified_paired_views']}/2 | {target} | {num(c['local']['length_m'])} | {num(c['local_snap_distance_m'])} | {num(c['hosted']['length_m'])} | {num(c['hosted']['target_gap_m'])} |")
    lines += ["","本地返回量只统计冻结请求折线。诊断折线另列在数据表。托管折线长度是 WGS84 椭球复算。末点到同一请求参考的距离与提供方内部吸附量分别处理，近距离不等于入口身份正确。","",
        "## 地图覆盖与归因","","本地源矢量可逐项核对建筑、步道和开放空间。托管图保留原始署名和实际 PNG，图面内容评价留给用户，托管矢量覆盖、快照时点和内部图规则保持 UNKNOWN。局部线几何贴合比例是与同一 OSM 快照中带步行标签的源线 2 米缓冲的重合比例，不能替代托管边 ID 或通行验证。障碍结果限于已取得的 OSM 建筑轮廓和平面检查。","",
        "| 建筑 | 上下文开放空间 | 带步行标签源线 | 机动车中心线 | 过街点或线 | 本地折线近源线 | 托管折线近源线 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for c in cases:
        lines.append(f"| {c['label']} | {c.get('native_open_space_objects_in_context','—')} | {c.get('native_pedestrian_tagged_ways_in_context','—')} | {c.get('native_road_centerlines_in_context','—')} | {c.get('native_crossings_in_context','—')} | {num(c.get('local_geometry_support',{}).get('line_near_tagged_osm_pedestrian_fraction'),3)} | {num(c.get('hosted_geometry_support',{}).get('line_near_tagged_osm_pedestrian_fraction'),3)} |")
    conflicts=[(c["label"],sorted({ref for branch in ("local","hosted") for ref in c.get(branch+"_geometry_support",{}).get("osm_footprint_intersection_way_ids",[])})) for c in cases]
    lines+=["","本地矢量按冻结 R1 规则表达，托管采用 osm-bright-smooth 样式。样式差异在各档可配对复查，哪些符号更易读、是否持续影响视觉使用待用户评分。图面中看不到要素不能区分样式省略与源数据缺失。"]
    for label,ids in conflicts:
        if ids:
            lines.append(f"- {label}出现路线和 OSM 轮廓平面重叠（{', '.join(ids)}），需核对通道和楼层；当前记录为平面告警。")
    by_id={c["scene_id"]:c for c in new}
    world=by_id.get("sh-newworld",{})
    expo=by_id.get("sh-exhibition",{})
    lines+=["","## 两个影响后续设计的反例","",
        f"- **新世界城**。本地起点吸附于 way/1047377660，目标吸附于 way/85796883。去掉方向后两端仍位于不同分量（4,741 与 34 个节点）。托管返回 {num(world.get('hosted',{}).get('length_m'))} 米折线，末点离代理目标 {num(world.get('hosted',{}).get('target_gap_m'))} 米。其内部连边与放行证据未公开，本地分量缺口可复算。 [拓扑记录](audits/local_newworld_topology.json)",
        f"- **上海展览中心**。共同请求下两条路线均有返回，长度分别 {num(expo.get('local',{}).get('length_m'))} 和 {num(expo.get('hosted',{}).get('length_m'))} 米，距同一代理点均约 20 米。地图快照、图构建、权重与路权的贡献暂不能拆开。",
        "- 托管折线在新世界城、上海展览中心与本地带显式步行标签的线贴合很少。这个指标会漏掉可步行的共享街道，也看不到托管原生边 ID。仅用于选取诊断对象。 [统一底图](visuals/routes/index.html)",
        "","## 工程成本与证据限制","","本地成本来自现有城市快照裁切、固定图构建和渲染；后续可在归档裁片上离线复跑。托管成本来自 HTTPS 请求、响应留存、配准与可能的服务限制；既有账号，无新购买或升级。余额及实际入账费用以服务商控制台为准。","",
        f"- 本地路由及渲染实际耗时合计 {sum(x.get('elapsed_s',0) for x in local['scenes']):.2f} 秒（每场景加总，不代表并行墙钟）。",
        f"- 新增本地五个原生裁片合计 {source_bytes:,} 字节。全市快照只读复用，封包仅含裁片。",
        f"- 托管尝试 {hosted.get('requests_attempted',0)} 次，HTTP 200 共 {hosted_200} 次，HTTP 用时加总 {seconds:.2f} 秒。中断记录为 {hosted.get('halt_reason') or '无服务终止门触发'}。",
        f"- 按脱敏收据估算 {estimated_credits:.2f} credits。可见实际 credits 的收据为 {known_credits}/{len(receipts)}，其余保持 UNKNOWN。 [托管流水](runs/hosted_results.json)",
        f"- 新样本本地冻结路线 {local_results}/{len(new)}、托管返回路线 {hosted_results}/{len(new)}。两个状态定义不同；路径长短和重复差异用于工程诊断。","",
        "人工可读性、真实路权、内部拓扑、实体门位和最终选型均有各自证据门槛。公开条款对保存原始带署名图与研究训练用途分别约束。 [许可审计](01_SOURCE_AND_PERMISSION_AUDIT.md) · [逐场景证据表](runs/comparison.csv)",""]
    (root/"03_PAIRED_COMPARISON_RESULTS.md").write_text("\n".join(lines),encoding="utf-8")

    lines=["# 双路径决定","",f"判定 `{judgment}`。保留本地 OSM 与 Geoapify 两条数据路径。", "",
           f"实跑证据显示两侧能产生不同路由状态、末点和几何。本地对照 {local_results}/{len(new)}，托管结果 {hosted_results}/{len(new)}。{refs}/{len(new)} 个请求目标来自 OSM 标签入口，其余保留代理或未知身份。现有样本没有独立路径真值或实体门核验。新增用户盲评仍待填写。工程差异据实保留，无法据此淘汰任何路径。","",
           "本地侧具备可追溯矢量和离线路由。托管侧具备静态图和路线服务；图像本身不提供步行图语义。两边共享 OSM 地理来源。可在共同接口运行相同的路线和端点核查；拓扑机制需要双方同等可追溯空间上下文。对缺失字段保持 UNKNOWN，并将共同可用子集与全信息扩展分开。","",
           "下一阶段优先研究**开放空间边界与已知人行道之间的证据化接入**，同时将入口身份、步道接点、实际折线末点和拒答条件分开。R2 上海博物馆的三个边界接点和约 55 米共同末段缺口提供直接机制线索。R3 新世界城的分量缺口说明接入候选还要核查整条路线的连通性，上海展览中心的末点偏离说明长短比较之外还需检查门前连接。两栋的代理目标只能支持工程诊断。","",
           "[共同中间表示](08_COMMON_INTERMEDIATE_REPRESENTATION.md) · [双路径机制合同](09_DUAL_PATH_ALGORITHM_ROADMAP.md)",""]
    (root/"05_DECISION_ON_TWO_PATHS.md").write_text("\n".join(lines),encoding="utf-8")
    print(overview)


if __name__=="__main__":
    build()
