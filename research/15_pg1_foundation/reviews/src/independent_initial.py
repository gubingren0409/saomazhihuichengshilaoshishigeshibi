"""PG1 independent read-only input and historical ZIP audit; no solver imports."""
from pathlib import Path
import csv, hashlib, io, json, zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT.parent
OUT = ROOT / 'reviews'
def sha(data): return hashlib.sha256(data).hexdigest()
expected = {
    '00_README_FIRST.md': '0b49f19cd1313298a773f04c67001c6a86096d8ee92e667e78b07eef14465932',
    '01_ACCEPTANCE_CHECKLIST.md': 'd3006e25b67f9c1dda60f9653c703209ec218522fe0d4cd97f32381bf4d1397d',
    'SMART_CITY_WALKABILITY_FOUNDATION_PG1_CODEX_PROMPT.md': '6e7c01f4cc819944cc3f65345574aa91bd8a677511c840aa55e8ec0932157190',
}
result = {'at_utc': datetime.now(timezone.utc).isoformat(), 'role': 'actual separate independent reviewer', 'inputs': [], 'rules': [], 'historical': [], 'scope': {'new_map_requests': 0, 'new_paid_requests': 0, 'training': False, 'blind_test_used': False, 'old_solver_reruns': 0, 'overall_PG1': 'FOUNDATION_NOT_COMPLETE'}}
for name, digest in expected.items():
    p = ROOT / 'inputs' / ROOT.name / name
    b = p.read_bytes()
    actual = sha(b)
    result['inputs'].append({'path': str(p), 'bytes': len(b), 'sha256': actual, 'expected_match': actual == digest})
rules = json.loads((ROOT / 'audit/authoritative_rules.json').read_text(encoding='utf-8-sig'))
for rule in rules['rules']:
    try:
        b = Path(rule['path']).read_bytes()
        result['rules'].append({'path': rule['path'], 'sha256': sha(b), 'expected_match': sha(b) == rule['sha256']})
    except OSError as e:
        result['rules'].append({'path': rule['path'], 'status': 'NOT_VERIFIED', 'reason': type(e).__name__})
archives = [
    ('R2_FINAL', WORK / 'PED_AREA_CONNECTIVITY_R2_ROUTE_DIAGNOSIS/delivery/OPEN_REVIEW.zip', '3988e9fba95da70dc03b8191a177740a3ccd13602019afe3765e566648b55711'),
    ('R1_FINAL', WORK / 'PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip', 'd5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed'),
]
for label, p, digest in archives:
    rec = {'id': label, 'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes()), 'expected_sha256': digest}
    with zipfile.ZipFile(p) as z:
        rec['CRC_first_bad'] = z.testzip()
        rec['members'] = len(z.infolist())
        rec['unsafe_members'] = [n for n in z.namelist() if n.startswith(('/', '\\')) or '..' in Path(n).parts or ':' in n]
        statuses = [n for n in z.namelist() if n.endswith(('STATUS.json', 'FINAL_STATUS.json'))]
        rec['archive_statuses'] = {n: json.loads(z.read(n)) for n in statuses}
        manifests = [n for n in z.namelist() if Path(n).name.startswith('MANIFEST')]
        rec['manifest_members'] = manifests
        evidence_names = [n for n in z.namelist() if any(k in n.upper() for k in ['FAILED', 'REPLAY_RECEIPT', 'FINAL_DELIVERY'])]
        rec['failure_and_review_member_names'] = evidence_names
    rec['hash_pass'] = rec['sha256'] == digest
    result['historical'].append(rec)
OUT.mkdir(exist_ok=True)
(OUT / 'independent_initial.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
assert all(x['expected_match'] for x in result['inputs'])
assert all(x.get('expected_match') for x in result['rules'])
assert all(x['hash_pass'] and x['CRC_first_bad'] is None and not x['unsafe_members'] for x in result['historical'])
print(json.dumps({'input_sha_pass': len(result['inputs']), 'rule_sha_pass': len(result['rules']), 'historical_sha_crc_pass': [r['id'] for r in result['historical']], 'solver_calls': 0}, ensure_ascii=False))
