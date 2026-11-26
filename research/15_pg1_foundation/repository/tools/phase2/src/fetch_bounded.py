"""Bounded public source/terms audit. No authentication, bulk endpoints or paging.
Run with --manifest JSON. Each configured response has a hard byte cap.
"""
import argparse, datetime, hashlib, json, pathlib, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]

def run(manifest, root=ROOT):
    global ROOT
    ROOT = pathlib.Path(root).resolve()
    ledger = ROOT / 'request_log.jsonl'
    for item in json.loads(pathlib.Path(manifest).read_text(encoding='utf-8')):
        target = (ROOT / item['path']).resolve()
        if not target.is_relative_to(ROOT):
            raise ValueError('path escapes phase2')
        if target.exists():
            print('EXISTS', item['path']); continue
        entry = {**item, 'utc': datetime.datetime.now(datetime.UTC).isoformat(), 'status': 'FAILED'}
        limit=item['max_bytes']
        if item['path'].startswith('samples/'):
            prior=[json.loads(s) for s in ledger.read_text(encoding='utf-8').splitlines()] if ledger.exists() else []
            # A failed old read may have transferred bytes before timing out.
            # Reserve its whole response cap rather than asserting zero bytes.
            used=sum(x.get('bytes_received',x['max_bytes']) for x in prior if x['path'].startswith('samples/'))
            limit=min(limit,8_000_000-used)
            if limit<=0: raise RuntimeError('8 MB preview budget exhausted, including unknown failed-transfer reserves')
        entry['effective_byte_cap']=limit
        start = time.monotonic()
        try:
            req = urllib.request.Request(item['url'], headers={'User-Agent':'PG1-bounded-academic-source-audit/1.0'})
            with urllib.request.urlopen(req, timeout=45) as response:
                chunks=[]; entry['bytes_received']=0
                while True:
                    remaining=limit-entry['bytes_received']
                    if remaining<=0: break
                    block=response.read(min(65536,remaining))
                    if not block: break
                    chunks.append(block); entry['bytes_received']+=len(block)
                    if entry['bytes_received']>=limit: break
                content=b''.join(chunks)
                entry.update(http_status=response.status, final_url=response.url, bytes_received=len(content), content_type=response.headers.get('Content-Type'))
            if len(content)>=limit and response.headers.get('Content-Length')!=str(limit):
                raise ValueError('byte cap exceeded; response not retained')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            entry.update(status='RETAINED', sha256=hashlib.sha256(content).hexdigest())
        except Exception as exc:
            entry['error'] = str(exc)
        entry['seconds'] = round(time.monotonic()-start,3)
        with ledger.open('a', encoding='utf-8') as f: f.write(json.dumps(entry, ensure_ascii=False)+'\n')
        print(entry['status'], item['path'], entry.get('bytes_received'), entry.get('error',''))

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--manifest', required=True); p.add_argument('--root', type=pathlib.Path, default=ROOT)
    args=p.parse_args(); run(args.manifest,args.root)
