"""Offline provenance/accounting summaries. Expects external source audit JSON."""
import argparse, collections, csv, hashlib, json, pathlib

def run(root, config):
    root=pathlib.Path(root); sources=json.loads(pathlib.Path(config).read_text(encoding='utf-8'))
    for row in sources:
        path=root/row['evidence_path'];row['evidence_sha256']=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else 'UNKNOWN'
        row['retrieval_date']='2026-11-12';row['public_release_approved']=False
    (root/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2),encoding='utf-8')
    with (root/'sources.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(sources[0]));w.writeheader();w.writerows(sources)
    ledger=[json.loads(s) for s in (root/'request_log.jsonl').read_text(encoding='utf-8').splitlines()]
    vector=[x for x in ledger if x['path'].startswith('samples/')];outcomes=collections.Counter()
    for row in vector:
        if row['status']=='RETAINED':
            data=json.loads((root/row['path']).read_text(encoding='utf-8'))
            outcomes['NONEMPTY_RETAINED' if data.get('features') or data.get('elements') else 'EMPTY_NO_OBSERVATION']+=1
        elif 'cap exceeded' in row.get('error',''):outcomes['BYTE_CAPPED_NOT_RETAINED']+=1
        elif 'timed out' in row.get('error',''):outcomes['TIMEOUT_UNKNOWN_TRANSFER_BYTES']+=1
        else:outcomes['OTHER_FAILED']+=1
    known=sum(x.get('bytes_received',0) for x in vector);unknown=sum(x['max_bytes'] for x in vector if 'bytes_received' not in x)
    summary=dict(http_request_attempts=len(ledger),terms_schema_capabilities_http_attempts=len(ledger)-len(vector),vector_http_attempts=len(vector),vector_outcomes=outcomes,vector_known_application_read_bytes=known,vector_retained_file_bytes=sum(x.get('bytes_received',0) for x in vector if x['status']=='RETAINED'),vector_unknown_timeout_application_read_bytes='UNKNOWN for original Overpass timeout',vector_total_actual_transfer_bytes='UNKNOWN; timeout read count and transport-level transfer were not measured',unknown_timeout_budget_reserve_bytes=unknown,budget_accounting_estimate_bytes=known+unknown,preview_budget_bytes=8_000_000,budget_accounting_estimate_excess_bytes=max(0,known+unknown-8_000_000),budget_accounting_note='Known application-read bytes plus an assumed timeout reserve is a budget accounting estimate, NOT a proven transfer upper bound. The original timed-out call used read(limit+1) with no retained read count; its configured max_bytes reserve excludes a possible additional sentinel byte and does not measure HTTP/TLS/socket transfer. The accounting estimate exceeds budget by 1 byte, but the true total transfer and actual budget excess are UNKNOWN. No more acquisition occurred; current fetch code reads no more than remaining cap.',remaining_manifest_items_not_attempted=6,map_api_cost=0,paid_api_calls=0,training_calls=0,split_freeze=False,blind_evaluation=False,web_search_accounting='Separate web search/open tools used official source pages; their transfer bytes and backend HTTP request counts are not exposed, and are not asserted zero. HTTP counts above refer only to audited Python downloader ledger.')
    (root/'collection_receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=pathlib.Path);p.add_argument('--config',required=True,type=pathlib.Path);a=p.parse_args();run(a.root,a.config)
