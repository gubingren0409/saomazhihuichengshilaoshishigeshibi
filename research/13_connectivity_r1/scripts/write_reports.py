"""Write evidence-bound report drafts; --apply updates the four final MD files.

No solver, source compiler, app, method or gallery is changed. Final application
requires the primary summary and all prelocked replacement runs to be complete.
Even final report text keeps final sealing/user observation pending; a report
generator cannot certify its own final ZIP or its external replay receipt.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import posixpath

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / 'reviews/report_drafts'
MODES = ['FROZEN_FULL_FACE', 'SOURCE_COMPLETE', 'EXACT_STITCH', 'CONDITIONAL_SEAMS']
LABELS = dict(zip(MODES, ['B0 封存完整面', 'B1 补齐源面', 'B2 精确衔接', 'B3 条件接缝']))
ROLE_NAMES = {'BASELINE_POSITIVE': '固定合法门任务', 'BASELINE_REJECTION': '固定拒绝检查',
              'SOURCE_INTERFACE_MECHANISM': '接口机制查询', 'GAP_COST_PAIR': '接缝代价对照',
              'PRELOCKED_THRESHOLD_SENSITIVITY': '预锁单因素敏感性',
              'HISTORICAL_LONG_QUERY_NOT_SCREENSHOT_BOUND': '历史长绕行，非截图复算'}


def file_sha(path):
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


class Inputs:
    def __init__(self):
        self.bindings = {}; self.responses = {}; self.errors = []

    def path(self, relative):
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('INPUT_PATH_MUST_BE_PROJECT_RELATIVE:' + str(relative))
        return ROOT / path

    def bind(self, relative):
        path = self.path(relative)
        if not path.is_file():
            return None
        self.bindings[Path(relative).as_posix()] = {'sha256': file_sha(path), 'bytes': path.stat().st_size}
        return path

    def read(self, relative, default=None):
        path = self.bind(relative)
        return json.loads(path.read_text(encoding='utf-8-sig')) if path else default

    def csv(self, relative):
        path = self.bind(relative)
        if path is None:
            return []
        with path.open(encoding='utf-8-sig', newline='') as stream:
            return list(csv.DictReader(stream))

    def jsonl(self, relative):
        path = self.bind(relative)
        if path is None:
            return []
        with path.open(encoding='utf-8') as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def response(self, relative, expected_sha=None):
        if relative in self.responses:
            result = self.responses[relative]
        else:
            raw = self.read(relative)
            if raw is None:
                self.errors.append('MISSING_RESPONSE:' + relative)
                return None
            route = raw.get('route') or {}; segments = route.get('segments', [])
            result = {'run_id': raw.get('run_id'), 'status': raw.get('status'),
                'request': raw.get('normalized_request') or raw.get('input') or {},
                'query': raw.get('query') or {}, 'failure': raw.get('failure'),
                'solver': raw.get('solver') or {}, 'validation': raw.get('validation') or {},
                'code_sha256': raw.get('versions', {}).get('code_sha256'),
                'graph_sha256': raw.get('versions', {}).get('unweighted_graph_sha256', raw.get('graph', {}).get('unweighted_sha256')),
                'length_m': route.get('length_m'), 'cost_m': route.get('cost_weighted_m'),
                'xy_sha256': sha256(json.dumps([s['xy'] for s in segments], separators=(',', ':')).encode()).hexdigest(),
                'seam_m': sum(s['length_m'] for s in segments if s.get('geometry_kind') in ('CONDITIONAL_GAP_LINK', 'CONDITIONAL_GAP_PATCH')),
                'front_hypothesis_m': sum(s['length_m'] for s in segments if s['layer'] in ('inferred', 'unknown', 'assumed') and s.get('geometry_kind') not in ('CONDITIONAL_GAP_LINK', 'CONDITIONAL_GAP_PATCH')),
                'exact_interface_m': sum(s['length_m'] for s in segments if s.get('geometry_kind') == 'SOURCE_SUPPORTED_INTERFACE'),
                'cache': raw.get('preprocessing_cache') or {}, 'elapsed_s': raw.get('elapsed_s'),
                'seams': raw.get('connectivity_evidence', {}).get('seams', []),
                'interface_ids_used': route.get('interface_ids_used', []),
                'response_path': relative, 'response_sha256': self.bindings[relative]['sha256']}
            self.responses[relative] = result
        if expected_sha and result['response_sha256'] != expected_sha:
            self.errors.append('RESPONSE_HASH_MISMATCH:' + relative)
        return result


def number(value, places=2):
    return f'{float(value):.{places}f}' if value is not None and value != '' else '—'


def md(value):
    return str(value if value is not None else '—').replace('|', '\\|').replace('\n', ' ')


def table(headers, rows):
    return ('| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join('---' for _ in headers) + ' |\n' +
            '\n'.join('| ' + ' | '.join(md(v) for v in row) + ' |' for row in rows) + '\n')


def link(target, label, document):
    relative = posixpath.relpath(target, posixpath.dirname(document) or '.')
    return f'[{label}]({relative})'


def collect(inputs):
    summary = inputs.read('results/summary.json', {})
    progress = inputs.read('results/formal_progress.json', {})
    original = inputs.jsonl('results/formal_registry.jsonl')
    replays = inputs.jsonl('results/formal_replay_registry.jsonl')
    replay_lock = inputs.read('data/performance_replay_lock.json', {})
    formal_lock = inputs.read('data/formal_requests_lock.json', {})
    interrupted = [inputs.read(p.relative_to(ROOT).as_posix()) for p in sorted((ROOT / 'results').glob('interrupted_formal_*.json'))]
    replacements = {r['supersedes_attempt_id']: r for r in replays}
    planned = {r['attempt_id'] for r in replay_lock.get('entries', [])}
    effective = [replacements.get(r['attempt_id'], r) for r in original]
    pending_replays = sorted(planned - replacements.keys())
    target = len(formal_lock.get('requests', [])) or progress.get('total')
    sample_rows = inputs.csv('results/sample_results.csv')
    count_ok = (summary.get('formal_completed') == len(effective) == target and
                summary.get('formal_replays') == len(replays) == len(planned) and not pending_replays and
                summary.get('formal_attempts') == len(original) + len(replays) + len(interrupted))
    hashes_ok = (summary.get('registry_sha256') == inputs.bindings.get('results/formal_registry.jsonl', {}).get('sha256') and
                 summary.get('replay_registry_sha256') == inputs.bindings.get('results/formal_replay_registry.jsonl', {}).get('sha256'))
    complete = bool(summary) and count_ok and hashes_ok and len(sample_rows) == len(effective)
    if summary and not count_ok:
        inputs.errors.append('SUMMARY_COUNT_BINDING_INCOMPLETE')
    if summary and not hashes_ok:
        inputs.errors.append('SUMMARY_REGISTRY_HASH_NOT_CURRENT')
    core_summary = inputs.read('results/core32_review.json', {})
    core_rows = inputs.csv('results/core32_comparison.csv') or inputs.csv('results/core32_review.csv')
    core = []
    for row in core_rows:
        results = []
        for mode in MODES:
            run_id = row.get(mode + '_run_id')
            if not run_id:
                continue
            result = inputs.response('runs/app/' + run_id + '.json', row.get(mode + '_response_sha256'))
            if result:
                for key in ('scene_id', 'door_id', 'start_id', 'method', 'purpose'):
                    if result['request'].get(key) != row.get(key):
                        inputs.errors.append('CORE_INPUT_MISMATCH:' + run_id + ':' + key)
                if result['request'].get('connectivity_mode') != mode:
                    inputs.errors.append('CORE_MODE_MISMATCH:' + run_id)
                results.append(result)
        core.append({'input': {k: row.get(k) for k in ('request_id', 'scene_id', 'door_id', 'start_id', 'method', 'purpose')},
            'results': results, 'all_cost_equal': len(results) == 4 and len({r['cost_m'] for r in results}) == 1,
            'all_xy_equal': len(results) == 4 and len({r['xy_sha256'] for r in results}) == 1})
    if core_summary.get('each_has_all_four_modes') and not (len(core) == 8 and all(len(c['results']) == 4 for c in core)):
        inputs.errors.append('CORE_SUMMARY_COMPLETENESS_MISMATCH')
    if core_summary.get('all_eight_costs_unchanged_across_modes') and not all(c['all_cost_equal'] for c in core):
        inputs.errors.append('CORE_SUMMARY_COST_MISMATCH')
    if core_summary.get('whole_coordinate_lists_equal_for_all') and not all(c['all_xy_equal'] for c in core):
        inputs.errors.append('CORE_SUMMARY_XY_MISMATCH')
    effective_by_key = {}
    for record in effective:
        q = record['request']
        effective_by_key[(q.get('mechanism_id'), q.get('method'), q.get('connectivity_mode'), float(q.get('seam_max_m', 2)))] = record
    endpoint_lock = inputs.read('data/connectivity/mechanism_request_endpoints_lock.json', {})
    mechanism_ids = sorted({q['mechanism_id'] for q in endpoint_lock.get('queries', [])})
    mechanisms = {}
    for mechanism in mechanism_ids:
        mechanisms[mechanism] = {}
        for mode in MODES:
            rec = effective_by_key.get((mechanism, 'F0', mode, 2.0))
            if rec:
                if rec.get('supersedes_attempt_id') is None and rec['attempt_id'] in planned:
                    mechanisms[mechanism][mode] = {'pending': True, 'old_observation_status': rec['status'],
                        'old_observation_length_m': rec.get('length_m'), 'old_response_path': rec.get('path')}
                else:
                    mechanisms[mechanism][mode] = inputs.response(rec['path'], rec.get('result_sha256'))
    source = inputs.read('data/connectivity/global_source_identity.json', {})
    scene_manifest = inputs.read('data/scene_manifest.json', {})
    omega_count = 0; relations = []
    for scene in scene_manifest.get('scenes', []):
        sid = scene['scene_id']
        faces = inputs.read(f'data/connectivity/{sid}_faces.json', [])
        omega_count += sum(f.get('status') == 'ADMITTED' and bool(f.get('components')) for f in faces)
        relations.extend(inputs.read(f'data/connectivity/{sid}_relations.json', []))
    passed_sha = set(); audit_rows = []
    response_audits = set((ROOT / 'audits').glob('independent_formal_responses*.json'))
    canonical_measurement = ROOT / 'audits/independent_canonical_response_measurement.json'
    if canonical_measurement.is_file():
        response_audits.add(canonical_measurement)
    for path in sorted(response_audits):
        report = inputs.read(path.relative_to(ROOT).as_posix(), {})
        for row in report.get('rows', []):
            if not row.get('errors') and not row.get('whole_geometry_errors') and row.get('sha256'):
                passed_sha.add(row['sha256'])
        audit_rows.append({'path': path.relative_to(ROOT).as_posix(), 'status': report.get('status'),
                           'scope': report.get('scope'), 'response_rows': len(report.get('rows', []))})
    independent_covered = sum(r.get('result_sha256') in passed_sha for r in effective)
    ancillary = {}
    for relative in ['audits/backend_freeze_r2.json', 'audits/root_tests_r2.json',
        'audits/independent_review.md', 'audits/independent_source_inventory_summary.json',
        'audits/independent_source_relation_review.json', 'audits/independent_museum_native_chain.json',
        'audits/independent_gap_fence_counterexample.json', 'audits/independent_gap_fence_regression_12a30f7571fe.json',
        'audits/independent_fix4_review.json', 'audits/independent_performance_cache_review.json',
        'audits/independent_ui_live_review.json', 'audits/independent_ui_live_response_review.json',
        'audits/independent_ui_live_visual_review.json', 'audits/independent_frontend_literal_delta.json',
        'audits/frontend_literal_delta_fixed.json', 'audits/independent_mechanism_endpoint_diagnosis.json',
        'audits/development_run_registry.json', 'audits/independent_live_request_plan.json',
        'audits/protection_first_encoding_alert.json', 'audits/protection_final.json',
        'audits/independent_canonical_review.json', 'audits/independent_m08_source_snapshot.json',
        'audits/independent_component_review.json', 'audits/independent_m08_layer_review.json',
        'results/mechanism_endpoint_diagnosis.json', 'results/component_analysis_receipt.json']:
        if relative.endswith('.md'):
            inputs.bind(relative)
        else:
            ancillary[relative] = inputs.read(relative, {})
    components = inputs.csv('results/component_statistics.csv')
    component_receipt = ancillary.get('results/component_analysis_receipt.json', {})
    if component_receipt.get('identity_failures'):
        inputs.errors.append('COMPONENT_PREPARED_IDENTITY_FAILURES')
    if component_receipt and component_receipt.get('verified_prepared_graphs') != len(components):
        inputs.errors.append('COMPONENT_RECEIPT_CSV_COUNT_MISMATCH')
    if ancillary.get('audits/protection_final.json', {}).get('all_match') is False:
        inputs.errors.append('PROTECTED_INPUT_FINAL_MISMATCH')
    errata = inputs.csv('results/evidence_field_errata.csv')
    timing = {}
    for mode in MODES:
        rs = [r for c in core for r in c['results'] if r['request'].get('connectivity_mode') == mode]
        timing[mode] = {'cold': [r['cache']['load_or_prepare_s'] for r in rs
            if r['cache'].get('hit') is False and isinstance(r['cache'].get('load_or_prepare_s'), (int, float))],
            'warm': [r['elapsed_s'] for r in rs if r['cache'].get('hit') is True and isinstance(r['elapsed_s'], (int, float))]}
    return {'summary': summary, 'progress': progress, 'original_count': len(original), 'effective': effective,
        'replays': len(replays), 'planned_replays': len(planned), 'pending_replays': pending_replays,
        'interrupted_count': len(interrupted), 'actual_count': len(original) + len(replays) + len(interrupted),
        'primary_target': target, 'complete': complete, 'core': core, 'core_summary': core_summary,
        'mechanisms': mechanisms, 'source': source, 'omega_nonempty': omega_count,
        'relations_count': len(relations), 'omega_separated': sum(r.get('separation_introduced_by_omega', False) for r in relations),
        'P_contact_then_omega_gap': sum(r.get('P', {}).get('distance_m') == 0 and
            isinstance(r.get('omega', {}).get('distance_m'), (int, float)) and r['omega']['distance_m'] > 0 for r in relations),
        'independent_covered': independent_covered, 'independent_batches': audit_rows,
        'ancillary': ancillary, 'components': components, 'errata': errata, 'timing': timing}


def mechanism_value(result):
    if not result:
        return '尚无完成记录'
    if result.get('pending'):
        return '待锁定复放；旧观察 ' + (number(result.get('old_observation_length_m')) + ' m' if result.get('old_observation_length_m') is not None else result.get('old_observation_status', '无路线'))
    if not str(result.get('status')).startswith('ROUTED'):
        failure = result.get('failure') or {}
        stage = (failure.get('stage') + ': ') if failure.get('stage') else ''
        return (result.get('status', '无状态') + ('（已调用求解器）' if result.get('solver', {}).get('invoked') else '（求解前返回）') +
            ' / ' + stage + failure.get('code', '未形成完整路线'))
    return number(result['length_m']) + ' m；接缝 ' + number(result['seam_m'], 6) + ' m'


def render(facts, inputs, destination):
    L = lambda path, label: link(path, label, destination)
    core = facts['core']; all_main = len(core) == 8 and all(len(c['results']) == 4 for c in core)
    unchanged = all_main and all(c['all_cost_equal'] and c['all_xy_equal'] for c in core)
    stage = '正式数据已汇总；封包和包外独立重放仍待最终回执' if facts['complete'] else '阶段稿：正式矩阵与锁定复放尚未全部完成'
    population = facts['source']; primary = len(facts['effective'])
    counts = (f'主请求已有完成记录 {primary}/{facts["primary_target"]}，其中仍待锁定替换 {len(facts["pending_replays"])} 项；已完成复放 {facts["replays"]}/{facts["planned_replays"]}；'
              f'中断 {facts["interrupted_count"]} 次。实际正式尝试 {facts["actual_count"]} 次，主结果分母不包含复放与中断。')
    source_text = (f'完整扫描六个冻结裁片后，源准入共有 {population.get("scene_id_area_count", "待汇总")} 个场景—对象记录，'
        f'按 type/id、version 与源时间戳去重为 {population.get("global_unique_type_id_version_timestamp_count", "待汇总")} 个原生面；'
        f'旧数据中新增纳入 {population.get("added_scene_id_area_count", "待汇总")} 个场景记录、'
        f'{population.get("global_new_vs_any_old_unique_count", "待汇总")} 个此前从未选入的唯一原生面。'
        f'{facts["omega_nonempty"]} 个场景面具有非空合法 Ω。跨裁片副本不作为独立面积证据。')
    main_claim = ('主 8 请求分别在四模式下求解，共 32 个响应。全部八组的广义代价和完整分段 XY 坐标序列均保持相同，'
        '本轮没有改善这些固定业务请求的路线。接点增多、派生段标签改变或补入更多面，均不能改写这个零新增收益结果。') if unchanged else (
        f'主请求目前核对 {len(core)} 组；代价及完整坐标序列一致的组数为 {sum(c["all_cost_equal"] and c["all_xy_equal"] for c in core)}。未完整的比较不提前作结论。')
    classifications = {}
    for mode in MODES:
        rs = [r for c in core for r in c['results'] if r['request'].get('connectivity_mode') == mode]
        classifications[mode] = (sum(r['front_hypothesis_m'] + r['seam_m'] == 0 for r in rs),
                                 sum(r['front_hypothesis_m'] + r['seam_m'] > 0 for r in rs))
    if all_main and len(set(classifications.values())) == 1:
        known, conditional = next(iter(classifications.values()))
        main_claim += f' 每个模式均有 {known} 个无假设的原生/已标面派生结果和 {conditional} 个条件结果；条件部分来自原门前假设域，不是新接缝收益。'
    states = ['PENDING_USER_OBSERVATION', 'SCREENSHOT_REQUEST_UNBOUND']
    provenance = f'数据绑定见 {L(facts.get("report_bindings_path", "reviews/report_drafts/source_bindings.json"), "报告输入及 SHA 清单")}；本生成器只读取保存输出，没有调用求解器。'
    chain = facts['ancillary'].get('audits/independent_museum_native_chain.json', {})
    gap = number(chain.get('direct_P_to_564255372_distance_m'), 6)
    chain_text = (f'博物馆南门 P 与东北侧 way/564255372 的直接间距为 {gap} m。原生 way/178737608 已经通过 '
        'node/1890935415 与 node/1891590997 把该面与长线连接起来。后续部分段与既有 private service / 建筑限制相遇；'
        '这需要分别核对源拓扑和计算图，不能说成整条链缺少步道，也不通过补线撤销原限制。')
    m = facts['mechanisms']
    mechanism_table = table(['预锁机制（F0）', 'B0', 'B1', 'B2', 'B3'],
        [[name] + [mechanism_value(m[name].get(mode)) for mode in MODES] for name in m])
    mechanism_notes = []
    a, b = m.get('M02', {}).get('FROZEN_FULL_FACE'), m.get('M02', {}).get('SOURCE_COMPLETE')
    if a and b and not a.get('pending') and not b.get('pending') and a.get('length_m') is not None and b.get('length_m') is not None:
        mechanism_notes.append(f'M02 的 B0→B1 为 {number(a["length_m"], 4)}→{number(b["length_m"], 4)} m，减少 {number(a["length_m"]-b["length_m"], 4)} m；这说明既有源面补读能影响这一局部查询。')
    a, b = m.get('M04', {}).get('SOURCE_COMPLETE'), m.get('M04', {}).get('EXACT_STITCH')
    if a and b and not a.get('pending') and not b.get('pending'):
        mechanism_notes.append(f'M04 的 B1 状态为 {a.get("status")}，B2 状态为 {b.get("status")}、长度 {number(b.get("length_m"), 4)} m；未形成旧路线时不计算缩短量。'
            f'新路线包含 {number(b.get("exact_interface_m"), 4)} m 源支持接口派生段，使用接口 ID {len(b.get("interface_ids_used", []))} 个；查询边界附着与预处理跨面接口在证据表按生成范围区分。')
    else:
        mechanism_notes.append('M04 的旧 B2 观察仍保留；锁定复放未完成前不将其作为最终恢复连通结论。')
    b = m.get('M06', {}).get('CONDITIONAL_SEAMS')
    if b and not b.get('pending'):
        accepted = [r for r in b['seams'] if r.get('accepted') and r.get('entered_graph')]
        query = b.get('query', {}); pair = {query.get('a_source_id'), query.get('b_source_id')} - {None}
        matched = [r for r in accepted if pair and pair.issubset(set(r.get('source_ids', []) + r.get('source_area_ids', [])))]
        mechanism_notes.append(f'M06 的预锁对象对 Ω 间距为 {number(query.get("omega_distance_m"), 6)} m；'
            f'匹配该对象对的已入图候选记录 {len(matched)} 条，本次 B3 路线使用接缝 {number(b.get("seam_m"), 6)} m。'
            f'该准备图的全部已入图候选记录为 {len(accepted)} 条。方向或重复次数不是独立物理接缝数；已入图也不等于被这条路线采用。')
    else:
        mechanism_notes.append('M06 的候选入图与路线采用以新复放回执为准；旧“已入图但未采用”的观察不提前冒充最终结果。')
    m7 = [r for r in m.get('M07', {}).values() if r and not r.get('pending')]
    if len(m7) == 4 and all(str(r['status']).startswith('ROUTED') for r in m7):
        mechanism_notes.append('M07 的直接 P/Ω 关系包含约束分隔，但四模式均可沿原路网绕行，长度分别为 ' +
            ' / '.join(number(r['length_m'], 4) for r in m7) + ' m；没有填回扣除区，也不能称为全网不可达。')
    m8 = [r for r in m.get('M08', {}).values() if r and not r.get('pending')]
    if len(m8) == 4 and all(r['status'] == 'NO_VALID_ROUTE' and r.get('solver', {}).get('invoked') for r in m8):
        mechanism_notes.append('层级反例 M08 四模式均在实际调用求解器后返回 NO_VALID_ROUTE；原 layer=1 节点及其已有非地面原生连接保留，当前起点无法到达该目标。它不是端点未绑定或目标零度孤点的结论，也不是现实不可通行的全局证明。')
        isolation = facts['ancillary'].get('audits/independent_m08_source_snapshot.json', {})
        if isolation.get('disjoint_from_start_weak_component') and isolation.get('canonical_structure_sha256_verified'):
            mechanism_notes.append(f'独立源图快照计数显示该目标入度 {isolation.get("target_in_degree")}、出度 {isolation.get("target_out_degree")}，'
                f'所属弱分量含 {isolation.get("target_weak_component_size")} 个节点，均保留显式layer=1身份；它与起点分量不同。'
                '先前“零度孤点”假说已被实测反证，首报保留，不将其写成算法或源地图事实。')
    modes_text = ('B0 是封存 FULL_FACE；B1 仅补齐已有源面；B2 在同一面集合上修复精确接口；B3 再加入条件接缝。'
        'P 保持原始边界，Ω 沿用源障碍、内环、权限、层级与 0.25 m 面净空。'
        '接缝是 inferred 的未知宽度逻辑线，F0 系数 1、F1 系数 2。探测 10 m，主上限 2 m，单因素 0.5 / 5 m；'
        '不填回 P→Ω 扣除部分，不跨道路中心线新造过街，不扩大原门心 30 m 域，不生成入口。')
    limits = ('真实铺装边界和现场可通行性没有独立真值；不报告边界准确率或伪 IoU。道路仅有中心线政策，不是实测路宽。'
        '源权限和层级仍受冻结数据与普通室外地面假设限制。机制样本来自事前锁定的原生节点/原始边界节点，'
        '不是建筑入口任务，也不代表全部地图。北门保持 entrance=exit，到门外与入馆资格分开。')
    full_summary = facts['summary']
    totals_rows = [[ROLE_NAMES.get(role, role)] + [f'{by.get(mode, {}).get("routed", 0)} / {by.get(mode, {}).get("attempted", 0)}' for mode in MODES]
                  for role, by in full_summary.get('by_role_and_mode', {}).items()]
    primary_table = table(['请求角色', 'B0 路由/请求', 'B1 路由/请求', 'B2 路由/请求', 'B3 路由/请求'], totals_rows) if totals_rows else '正式分角色汇总尚未生成。\n'
    main_rows = []
    for c in core:
        r = c['results'][0] if c['results'] else {}
        q = c['input']
        main_rows.append([q['request_id'], q['door_id'], q['method'], number(r.get('length_m')), number(r.get('cost_m')),
            number(r.get('front_hypothesis_m'), 5), number(r.get('seam_m'), 5),
            '四模式逐段相同' if c['all_cost_equal'] and c['all_xy_equal'] else '见逐响应差异'])
    main_table = table(['请求', '原登记门', '方法', '长度 m', '代价 加权米', '原门前假设 m', '新增接缝 m', '模式差异'], main_rows)
    near_f0 = next((c['results'][0] for c in core if c['input']['request_id'] == 'APP-03' and c['results']), None)
    near_f1 = next((c['results'][0] for c in core if c['input']['request_id'] == 'APP-04' and c['results']), None)
    weighting_note = (f'同一北门近起点的 F0 门前假设为 {number(near_f0["front_hypothesis_m"], 5)} m；'
        f'F1 为 {number(near_f1["front_hypothesis_m"], 5)} m，总长 {number(near_f1["length_m"])} m、'
        f'广义代价 {number(near_f1["cost_m"])} 加权米。F1 选择较少假设的稍长路径，权重不解释为现实风险概率。') if near_f0 and near_f1 else ''
    timing_rows = []
    for mode, values in facts['timing'].items():
        cold, warm = values['cold'], values['warm']
        timing_rows.append([LABELS[mode], f'{number(min(cold))}–{number(max(cold))} s' if cold else '无此类记录',
            f'{number(min(cold)/60)}–{number(max(cold)/60)} min' if cold else '—',
            f'{number(min(warm))}–{number(max(warm))} s' if warm else '无此类记录', len(cold), len(warm)])
    timing_table = table(['模式', '冷准备实际区间', '换算分钟', '缓存命中请求实际区间', '冷样本', '命中样本'], timing_rows)
    timing_note = ('计时表只统计上述主 32 响应：冷准备取原 preprocessing_cache.load_or_prepare_s，缓存命中取整次响应 elapsed_s。'
        '它们来自不同请求，不是一个连续延迟分解。冷构建可达数分钟，命中后仍有图组合、实际搜索、整段校验与序列化成本。'
        '54.39 s 是单个北面缓存候选的隔离 roadmap 重放，不包含整个 APP 管线，不能当作冷启动承诺。')
    component_receipt = facts['ancillary'].get('results/component_analysis_receipt.json', {})
    component_text = ('已收到 ' + str(component_receipt.get('verified_prepared_graphs', '未提供')) + ' 个准备图的分量统计；'
        f'身份失败项 {len(component_receipt.get("identity_failures", []))}。这些图位于查询绑定之前，弱/强分量只描述冻结计算网络，'
        '不代表公众现实通行。新增面也会新增节点，分量总数不能直接当作共同节点对的可达率提升。\n\n' +
        table(['场景 / 原门命名空间', '模式', '节点', '弧', '弱分量', '强分量'],
            [[r.get('scene_id', '') + ' / ' + r.get('door_id', ''), LABELS.get(r.get('mode'), r.get('mode')),
              r.get('nodes'), r.get('arcs'), r.get('weak_components'), r.get('strong_components')] for r in facts['components']])) if component_receipt else '准备图分量统计尚无完成回执，本稿不预报数量或连通率。'
    errata_text = (f'描述性字段 connectivity_evidence.parent_mode 有 {len(facts["errata"])} 条已列旁表的继承旧值。' if facts['errata'] else
        '原响应的描述性 parent_mode 继承旧值问题已在独立 PREP 审核中记录；最终旁表尚未汇总。') + (
        'B2 的概念父模式为 B1，B3 为 B2；实际准备链以 PREP.cache_key / parent_cache_key 和冻结 planner 的叠图列表为准。'
        '原始响应不重写；该字段错误与几何、代价及实际父缓存身份分开报告。')
    tests = facts['ancillary'].get('audits/root_tests_r2.json', {}).get('observed_result', {})
    ui = facts['ancillary'].get('audits/independent_ui_live_review.json', {})
    delta = facts['ancillary'].get('audits/frontend_literal_delta_fixed.json', {})
    frontend_text = (f'独立实际 Edge 共 {ui.get("APP_solver_calls", "待回执")} 次求解器调用；'
        f'已记录通过的交互断言 {sum(x.get("passed", False) for x in ui.get("checks", []))} 项。'
        f'实际测试 JS 的 SHA 前缀为 {delta.get("tested_js_sha256", "待绑定")[:8]}，交付 JS 为 {delta.get("delivered_js_sha256", "待绑定")[:8]}；'
        f'一处纯显示字面替换{ "已有精确字节证明" if delta.get("exact_one_literal_byte_replacement") is True else "仍待精确字节证明"}，不把字面补丁冒称一次新的全 UI 实测。')
    development = facts['ancillary'].get('audits/development_run_registry.json', {})
    independent_plan = facts['ancillary'].get('audits/independent_live_request_plan.json', {})
    separate_counts = (f'开发阶段另记 {development.get("total_attempted_including_interrupted", "待回执")} 次尝试，'
        f'其中完成 {development.get("completed_count", "待回执")} 次、实际调用求解器 {development.get("completed_solver_invocations", "待回执")} 次；'
        f'独立 UI 已实际调用 {ui.get("APP_solver_calls", "待回执")} 次，最终新包重放预留 '
        f'{independent_plan.get("maximum_new_final_clean_solver_calls", "待预锁")} 次，是否实际完成以包外回执为准。它们不混入主请求分母。')
    independence = (f'按原响应 SHA 匹配，已读独立单响应回执覆盖当前选定响应记录 {facts["independent_covered"]}/{primary} 条；待复放的旧记录不作为修复后最终结果。'
        '这只表示这些单响应的已声明检查范围；PREP 图、所有未采用接缝、完整图分量与最终 ZIP 各有独立范围，不互相替代。')
    failures = ('保留并修复了间隙内部围栏未被面附近列表覆盖、非精确门穿越、点触别名、原节点标签被覆盖、道路分区报告、'
        '源面关系/端点绑定、重复角点 N² 重建、派生网格内部端点批量升为 VG 接点，以及 APP 迟到响应和旧选中对象残留等问题。'
        '源约束和原始边界不因修复而放松。旧 B2/B3 的所有已完成相关记录在看新结果前整组锁定复放，旧告警、旧源码、'
        '中断和被替换响应均保留；正确性修复与方法增益分列。')
    protection = facts['ancillary'].get('audits/protection_final.json', {})
    first_protection = facts['ancillary'].get('audits/protection_first_encoding_alert.json', {})
    protection_text = ('保护检查的首次 status 文本 hash 警报已保留；该次 HEAD、index 与源数据 hash 没有变化。'
        '对齐初始命令的 quotepath / 文本序列化口径后，最终复核 all_match=true；不把口径误报写成受保护 Git 实际发生改动。') if protection.get('all_match') is True and first_protection.get('all_match') is False else (
        '旧工程与 Git 保护以实际保存回执为准；本生成器不另行调用 Git 或停止服务。')
    if destination.endswith('DECISION_BRIEF.md'):
        return f'''# 步行面衔接：本轮可支持的判断

{stage}。用户观察仍为 `{states[0]}`，截图原请求仍为 `{states[1]}`；本稿不宣布整项目或现场通行已验收。

{main_claim}

{source_text}

{' '.join(mechanism_notes)} 这些是局部接口机制，不是新增建筑入口，也不是主业务成功率的替代分母。

{chain_text}

建议保留完整源盘点、精确接口、整段约束和可审计的条件接缝实现；在当前主业务样本上只报告路线未变。条件连接继续保持假设身份，参数不因案例结果增大。{limits}

{counts} {provenance}
'''
    if destination.endswith('RESULTS.md'):
        return f'''# 结果与适用范围

{stage}。用户观察 `{states[0]}`；截图身份 `{states[1]}`。主结果不借用上轮已报告的穿行缩短量。

## 固定门任务的主要结果

{main_claim}

{main_table}
表内每行含同一请求的四模式对照；主32的完整 run ID / hash 在 {L('results/core32_comparison.csv', '主任务对照 CSV')} 与原始响应中。无假设的原生/已标面派生结果和原门前条件结果分开；主路线使用的新接缝均以表内实际长度为准。F0 / F1 的不同是原假设代价偏好，不是新增衔接模式收益。{weighting_note}

## 只在局部机制出现的改变

{mechanism_table}
{' '.join(mechanism_notes)} 机制终点是锁定的原生对象/原边界节点，不冒称入口。待复放项明确保留旧观察身份，不纳入最终结论。

## 源对象、几何与限制

{source_text} 共核对 {facts['relations_count']} 个活动关系，其中 {facts['omega_separated']} 条带有 Ω 引起距离变化的标记；其内 {facts['P_contact_then_omega_gap']} 条为原 P 接触而 Ω 有正间距。这些数字不表示源边界画错。{chain_text}

{modes_text} 角点触、跨层、明确私有限制、围栏无精确允许开口、障碍净空和道路中心线冲突的直接新接口保持拒绝；已有合法原生绕行不因此消失。草地内合法原生线保留独立通道，不填平整块草地。

## 分母、复放与耗时

{counts} 正式预算上限 128 次。{separate_counts}

{primary_table}
{timing_table}
{timing_note}

## 准备图分量与记录勘误

{component_text}

{errata_text} 详见 {L('results/evidence_field_errata.csv', '字段勘误旁表')}。

## 校验范围和限制

{independence} {frontend_text}

{limits} {failures}

最终归档是否可进入 `READY_FOR_GPT_AND_USER_REVIEW` 必须由封包后的包外独立回执决定，本报告生成器不作该宣告。{provenance}
'''
    if destination.endswith('EXPERIMENT_BRIEF.md'):
        return f'''# 实验简报：从源面到可解释的接口

本轮问题是：已标步行面如何与周围登记步道和相邻面形成连续计算空间。仅使用六份既有冻结裁片，新增外部地图/API、付费、训练、CV/VLM 和入口生成均为 0；计算使用 EPSG:32651，源坐标与门/起点不移动。当前为{stage}。

{modes_text} 面内继续复用冻结 VisibilityRoadmap；父折线按弧长精确切分，保留方向、层级、权限、长度和 F0/F1 平行选项。1e-8 m 数值证书与米级地图间隙分开，不增加吸附半径。

{source_text}

{main_claim} {' '.join(mechanism_notes)} {chain_text}

{counts} {separate_counts} 冻结请求、拒绝检查、机制和单因素敏感性分别汇总，不能把它们的成功数混成一个率。无独立面积真值，不报告边界准确率。{timing_note}

作者原测试回执记录 {tests.get('tests_run', '待回执')} 项、失败 {tests.get('failures', '待回执')}、错误 {tests.get('errors', '待回执')}；它与独立原几何审查、实际 Edge 交互、最终空目录解包求路分开。{independence}

{limits} 用户意见保持 `{states[0]}`，截图保持 `{states[1]}`。实现与证据可供审核，不代替用户判断。方法详见 {L('METHOD.md','METHOD')}，真实过程见 {L('PROCESS.md','PROCESS')}。{provenance}
'''
    return f'''# 作者自检：范围、实际证据与尚待事项

作者角色为工程实现与报告生成，不是独立审核者或用户。当前{stage}；用户观察 `{states[0]}`，截图 `{states[1]}`。本文件不签发最终封包或整项目验收。

## 已按保存输出核对

{source_text}

{main_claim} 本生成器逐个核验主32原始响应 SHA、原输入、四模式代价与完整分段 XY 指纹，而不是从截图推断。{counts}

作者交付测试回执为 {tests.get('tests_run', '待回执')} 项，失败 {tests.get('failures', '待回执')}、错误 {tests.get('errors', '待回执')}；来源是 {L('audits/root_tests_r2.json','实际测试回执')}。代码版本由 {L('audits/backend_freeze_r2.json','后端冻结清单')} 绑定，B0/B1合法旧输出保留当时的代码 SHA，不追写成新 epoch。

## 独立者已经覆盖的范围

{independence} 独立者从原始 OSM 重建 P/Ω 和关系，另查父线切分、整段约束、未采用接缝、准备图及实际 UI；具体对象和未覆盖内容以 {L('audits/independent_review.md','独立审核正文')} 和逐份 hash 回执为准，不将作者自检改名为独立验收。

{frontend_text} 实际下载的请求/视野 JSON、GeoJSON 和已查看 PNG 有独立回执；没有因纯文案修改追加求路。

## 保留的缺陷和纠正

{failures} 性能缓存只在同源组件唯一、坐标逐值相同、完整约束与可见图代码绑定、旧关联弧整段复验以及严格 subset / 逐线 added-disjoint 证书下复用。数值面积小不作为相等证明。北面实际证书 Q.covers(R)=true，先前口头将几何不相等误当非子集的说法已纠正，原机器证书未改。

{errata_text}

## 尚待封包后完成

正式数据未齐时不应用此稿。齐备后仍需最终图册绑定、新包清单/CRC/成员 hash、空目录解包、当前装箱测试和预锁新合法请求的独立重放。最终包外回执必须绑定最后交付 ZIP；封包后任何字或代码变动都须重封重验，不能让旧回执覆盖新包。

{component_text}

{limits} {protection_text} 旧工程、旧服务和 Git 保护由保存回执核对；没有 commit/push、公开发布或停止无关服务。工程状态和用户验收保持分开。{provenance}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Apply the four final reports only after complete current summary binding')
    args = parser.parse_args()
    inputs = Inputs(); facts = collect(inputs)
    facts['report_bindings_path'] = 'reviews/report_source_bindings.json' if args.apply else 'reviews/report_drafts/source_bindings.json'
    core_complete = len(facts['core']) == 8 and all(len(c['results']) == 4 for c in facts['core'])
    if args.apply and (not facts['complete'] or not core_complete or inputs.errors):
        raise SystemExit(json.dumps({'status': 'FINAL_REPORT_INPUTS_NOT_READY', 'primary': len(facts['effective']),
            'replays_pending': facts['pending_replays'], 'errors': inputs.errors}, ensure_ascii=False))
    DRAFTS.mkdir(parents=True, exist_ok=True)
    final_names = ['DECISION_BRIEF.md', 'RESULTS.md', 'EXPERIMENT_BRIEF.md', 'reviews/author_review.md']
    outputs = []
    for name in final_names:
        destination = name if args.apply else 'reviews/report_drafts/' + Path(name).name
        path = ROOT / destination; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(facts, inputs, destination), encoding='utf-8')
        outputs.append({'path': destination, 'sha256': file_sha(path), 'bytes': path.stat().st_size})
    binding = {'generated_utc': datetime.now(timezone.utc).isoformat(), 'mode': 'FINAL_REPORTS_APPLIED_PENDING_SEAL' if args.apply else 'DRAFTS_ONLY',
        'generator_sha256': file_sha(Path(__file__)), 'data_complete': facts['complete'],
        'primary_completed': len(facts['effective']), 'primary_target': facts['primary_target'],
        'replays_completed': facts['replays'], 'replays_planned': facts['planned_replays'],
        'interrupted': facts['interrupted_count'], 'actual_formal_attempts': facts['actual_count'],
        'core_queries': len(facts['core']), 'all_core_cost_and_xy_unchanged': len(facts['core']) == 8 and all(c['all_cost_equal'] and c['all_xy_equal'] for c in facts['core']),
        'independent_response_SHA_coverage': facts['independent_covered'], 'input_errors': inputs.errors,
        'inputs': inputs.bindings, 'outputs': outputs, 'report_generator_solver_calls': 0,
        'user_observation': 'PENDING_USER_OBSERVATION', 'screenshot_binding': 'SCREENSHOT_REQUEST_UNBOUND',
        'seal_status': 'FINAL_ZIP_AND_EXTERNAL_REPLAY_RECEIPT_ARE_SEPARATE_PENDING_ACTIONS'}
    (ROOT / facts['report_bindings_path']).write_text(json.dumps(binding, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in binding.items() if k != 'inputs'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
