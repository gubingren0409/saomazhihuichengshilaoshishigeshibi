"""Repeat already-registered requests concurrently; no new geographical samples."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def post(url, payload):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            status = response.status
            value = json.load(response)
    except urllib.error.HTTPError as error:
        status, value = error.code, json.loads(error.read())
    return {'http_status': status, 'started_at_epoch': started, 'ended_at_epoch': time.time(), 'response': value}


def reduced(r):
    x = r['response']
    return {k: r[k] for k in ('http_status', 'started_at_epoch', 'ended_at_epoch')} | {
        k: x.get(k) for k in ('request_id', 'run_id', 'status', 'normalized_request', 'solver', 'versions', 'route_answer_cache')
    } | {'length_m': x.get('route', {}).get('length_m'), 'cost_weighted_m': x.get('route', {}).get('cost_weighted_m'),
         'segments_sha256': sha256(json.dumps(x.get('route', {}).get('segments'), sort_keys=True).encode()).hexdigest()}


def main():
    service = json.loads((ROOT / 'runs/service.json').read_text('utf-8'))
    url = service['url'] + 'api/plan'
    registered = json.loads((ROOT / 'runs/acceptance/fixed_requests.json').read_text('utf-8'))['requests']
    f0 = next(x for x in registered if x['request_id'] == 'APP-03')
    f1 = next(x for x in registered if x['request_id'] == 'APP-04')
    before = post(url, {**f0, 'request_id': 'INDEPENDENT-REPEAT-F0-BEFORE'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(post, url, {**q, 'request_id': f'INDEPENDENT-REPEAT-{q["method"]}-CONCURRENT'}) for q in (f0, f1)]
        concurrent = [f.result() for f in futures]
    after = post(url, {**f0, 'request_id': 'INDEPENDENT-REPEAT-F0-AFTER'})
    records = [reduced(x) for x in [before, *concurrent, after]]
    x, y = concurrent
    wrong_types = [post(url, value) for value in ([], None, 4)]
    receipt = {'reviewer': '/root/e2e_review', 'role': 'REPEATED_FIXED_QUERY_CORRECTNESS_NOT_NEW_APP_SAMPLES',
               'url': url, 'service_pid_at_start': service['pid'], 'actual_plan_repeats': 4,
               'concurrency_intervals_overlap': max(x['started_at_epoch'], y['started_at_epoch']) < min(x['ended_at_epoch'], y['ended_at_epoch']),
               'same_unweighted_graph': x['response']['versions']['unweighted_graph_sha256'] == y['response']['versions']['unweighted_graph_sha256'],
               'same_surface': x['response']['versions']['surface_sha256'] == y['response']['versions']['surface_sha256'],
               'f0_geometry_unchanged_before_concurrent_after': len({r['segments_sha256'] for r in (records[0], records[1], records[3])}) == 1,
               'distinct_run_ids': len({r['run_id'] for r in records}) == 4,
               'distinct_solver_invocations': len({r['solver']['invocation_id'] for r in records}) == 4,
               'all_solver_executed_cache_off': all(r['solver']['invoked'] and not r['route_answer_cache']['enabled'] and not r['route_answer_cache']['hit'] for r in records),
               'records': records,
               'non_object_validation_fixtures': [{'http_status': r['http_status'], 'response': r['response']} for r in wrong_types],
               'limits': 'Warm preprocessing concurrency only; this is not a cold multiuser load test or a latency percentile estimate'}
    (ROOT / 'AUDIT/independent_http_concurrency.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'records'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
