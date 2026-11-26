"""Recover exactly one completed server response after a client checkpoint.

Does not call HTTP or any solver; does not synthesize a missing response.
"""
from pathlib import Path
import json,hashlib,datetime
ROOT=Path(__file__).resolve().parents[1]
def main():
    check=json.loads((ROOT/'audits/execution_order_checkpoint.json').read_text());latest=check['pending'];ident=latest['attempt_id']
    path=ROOT/'results/formal_registry.jsonl';entries=[json.loads(x)for x in path.read_text().splitlines()]
    if any(x['attempt_id']==ident for x in entries):print('ALREADY_RECORDED_NO_ACTION');return
    matches=[]
    for p in (ROOT/'runs/app').glob('*.json'):
        d=json.loads(p.read_text(encoding='utf-8'))
        if d.get('input')==latest['request']:
            if d.get('versions',{}).get('code_sha256')!=latest['code_sha256']:raise ValueError('CODE_EPOCH_MISMATCH')
            matches.append((p,d))
    if not matches:raise SystemExit('STILL_WAITING_FOR_ACTUAL_SERVER_RESULT_NO_RETRY_DISPATCHED')
    if len(matches)!=1:raise RuntimeError('AMBIGUOUS_SERVER_RESULTS')
    p,d=matches[0];lock=json.loads((ROOT/'data/formal_requests_lock.json').read_text());original=next(r for r in lock['requests']if r['attempt_id']==ident)
    result={**original,'run_id':d['run_id'],'status':d['status'],'solver_invoked':d.get('solver',{}).get('invoked',False),
        'path':p.relative_to(ROOT).as_posix(),'result_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'length_m':d.get('route',{}).get('length_m'),
        'cost_m':d.get('route',{}).get('cost_weighted_m'),'validation_passed':d.get('validation',{}).get('passed'),'elapsed_s':d.get('elapsed_s'),
        'expected_matches':d['status']==original['expected_status']if original.get('expected_status')else None,
        'delivery':'EXACT_ACTUAL_SERVER_RESULT_RECOVERED_AFTER_CLIENT_CHECKPOINT_NO_NEW_REQUEST','recovered_at':datetime.datetime.now().astimezone().isoformat()}
    with path.open('a',encoding='utf-8')as f:f.write(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    (ROOT/'audits/checkpoint_response_recovery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
