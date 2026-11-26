"""Verify existing evidence; append missing closeout, never rerun old experiments."""
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'SMART_CITY_WALKABILITY_FOUNDATION_PG1'
SHA = '7c9ed58766177e8906defc257555b0d7ba0d92c8e97129a691f9f6e72dffef7c'

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

def main():
    archive = OLD / 'delivery/PG1_FOUNDATION_REVIEW.zip'
    receipt_path = OLD / 'delivery/INDEPENDENT_DELIVERY_RECEIPT.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8-sig'))
    checks = []
    assert digest(archive) == SHA == receipt['archive_sha256']
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        m = json.loads(z.read('MANIFEST_SHA256.json'))
        files = m['files']
        for r in files:
            b = z.read(r['path'])
            assert len(b) == r['bytes'] and hashlib.sha256(b).hexdigest() == r['sha256'], r['path']
        assert len(z.namelist()) == 344 and len(files) == 343
    for r in receipt['evidence']:
        p = OLD / 'delivery' / r['path'].replace('\\', '/')
        ok = p.is_file() and p.stat().st_size == r['bytes'] and digest(p) == r['sha256']
        checks.append(dict(r, actual_path=str(p), match=ok))
        assert ok, p
    replay = json.loads((OLD / 'delivery/INDEPENDENT_MACHINE_REPLAY_RECEIPT.json').read_text())
    replay_checks = []
    base = Path(replay['extracted_root'])
    for r in replay['steps']:
        p = base / 'reviews' / (r['name'] + '.json')
        src = base / 'reviews/src' / (r['name'] + '.py')
        assert digest(p) == r['replayed_output_sha256'], p
        assert digest(src) == r['frozen_review_source_sha256'], src
        replay_checks.append({'name': r['name'], 'output_path': str(p), 'output_sha256': digest(p),
                              'source_path': str(src), 'source_sha256': digest(src)})
    public = []
    with (OLD / 'audit/PUBLIC_FILE_INVENTORY.csv').open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            p = OLD / 'repository' / r['path']
            assert digest(p) == r['sha256']
            public.append({'path': r['path'], 'sha256': r['sha256']})
    assert len(public) == 38
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
    result = {'checked_at': now, 'old_delivery_chain': 'COMPLETE', 'archive': str(archive),
              'archive_bytes': archive.stat().st_size, 'archive_sha256': SHA,
              'manifest_files_checked': len(files), 'receipt_path': str(receipt_path),
              'receipt_sha256': digest(receipt_path), 'original_receipt_time_utc': receipt['at_utc'],
              'evidence_files_checked': checks, 'existing_replay_outputs_checked': replay_checks,
              'original_public_files_checked': public, 'new_old_experiment_calls': 0,
              'Bad_Request_root_cause': 'UNKNOWN_NO_SPECIFIC_ERROR_LOG',
              'preserved_history': {'original_started_at': '2026-11-12T15:21:50+08:00',
                  'sealed_at': m['sealed_at'], 'historical_goal_service_status': 'blocked',
                  'sealed_pending_snapshot': 'UNCHANGED'},
              'G0_PUBLICATION': 'PENDING_USER_APPROVAL', 'G1_VISUAL_ACCEPTANCE': 'PENDING_USER_REVIEW',
              'G2_SPLIT_FREEZE': 'NOT_APPROVED', 'PARENT_GOAL_COMPLETE': False}
    (ROOT / 'audit/old_delivery_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    final_path = OLD / 'delivery/FINAL_STATUS.json'
    report_path = OLD / 'delivery/RECOVERY_REPORT.md'
    if final_path.exists() or report_path.exists():
        raise RuntimeError('Append targets already exist; inspect instead of overwrite')
    final_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    report = f'''# 旧轮交付恢复记录

旧轮交付链：COMPLETE。当前补写时间：{now}。

原启动2026-11-12 15:21:50+08；封包时间{m['sealed_at']}；包外独立回执时间{receipt['at_utc']}。
保留原blocked/中断事件、旧STATUS和CHECKPOINT及封包内PENDING，不回写历史状态。
Bad Request没有具体错误日志支持，根因为UNKNOWN；不归因任务复杂、上下文或网络。

本次实际读取固定ZIP（344成员/343内容，CRC、逐成员字节/SHA均一致）、包外独立回执、9项引用证据、5份已有独立复验输出及对应5份源码、38项公开候选文件。没有重跑六场景、下载或旧8次探针。
原ZIP SHA256：{SHA}。原本地commit：3134c0ea68e00871ed6dc86ca7bc905071449dae。
这证明既有交付证据闭合，不等于当前新增机制或整个父Goal通过。

G0公开仍待用户批准；G1视觉待用户验收；G2分组冻结未批准。整个父Goal未完成。
本次只新增包外FINAL_STATUS.json与本记录；未修改封存ZIP、旧证据或旧38文件。
机器核验细节见同目录FINAL_STATUS.json，以及续执行目录audit/old_delivery_verification.json。
'''
    report_path.write_text(report, encoding='utf-8')
    (ROOT / 'RECOVERY_REPORT.md').write_text(report, encoding='utf-8')
    print(json.dumps({'old_delivery_chain': 'COMPLETE', 'checked_at': now, 'manifest': len(files),
                      'receipt_evidence': len(checks), 'existing_replay_outputs': len(replay_checks),
                      'public_files': len(public)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
