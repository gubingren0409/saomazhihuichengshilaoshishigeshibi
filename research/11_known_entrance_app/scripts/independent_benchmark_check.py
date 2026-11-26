"""Independent post-prediction regression geometry and numerator audit.

Needs the declared frozen baseline only for manifest labels/source identities;
it never invokes a predictor or loads positive reference geometry into one.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from independent_check import (IndependentSource, digest, read, route_metrics,
                               source_route_check)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--baseline', type=Path, required=True)
    ap.add_argument('--batch', default='R2_unified')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = read(args.baseline / 'data/task_manifest.json')
    labels = {r['id']: r for r in manifest['instances']}
    folders = sorted((root / 'runs/benchmark' / args.batch).glob('*/result.json'))
    summary = defaultdict(lambda: defaultdict(lambda: {'queries': 0, 'reached': 0}))
    rows, identity_errors, read_errors = [], [], []
    source_cache = {}
    for path in folders:
        ident = path.parent.name
        declared = labels[ident]
        source_id = declared['group']
        if source_id not in source_cache:
            source_cache.clear()
            source_cache[source_id] = IndependentSource(root / 'data/scenes' / source_id / 'source.osm.json')
        source = source_cache[source_id]
        j = read(path)
        queries = {q['query_id']: q for q in read(path.parent / 'query.json')['queries']}
        if j['methods']['F0']['graph_sha256'] != j['methods']['F1']['graph_sha256'] or j['methods']['F0']['surface_sha256'] != j['methods']['F1']['surface_sha256']:
            identity_errors.append(ident)
        if j.get('reference_reads') != 0 or j.get('query_answer_cache') not in (False, 'DISABLED'):
            read_errors.append({'input_id': ident, 'reference_reads': j.get('reference_reads'), 'query_answer_cache': j.get('query_answer_cache')})
        for method, obj in j['methods'].items():
            for qid, route in obj['routes'].items():
                q = queries[qid]
                summary[method][declared['label']]['queries'] += 1
                summary[method][declared['label']]['reached'] += int(route['reached'])
                metrics = route_metrics(route['edges'], q['source']['xy'], q['target']['xy'], 2 if method == 'F1' else 1)
                if route['reached']:
                    metrics['saved_length_error_m'] = abs(route['length_m'] - metrics['length_m'])
                    metrics['saved_cost_error_m'] = abs(route['cost_m'] - metrics['cost_m'])
                source_result = source_route_check(source, route['edges']) if route['edges'] else None
                rows.append({'input_id': ident, 'query_id': qid, 'label': declared['label'],
                             'method': method, 'reached': route['reached'], 'status': route['status'],
                             'metrics': metrics, 'source_check': source_result,
                             'result_sha256': digest(path)})
    result = {'reviewer': '/root/e2e_review', 'role': 'POST_PREDICTION_EVALUATION_ONLY',
              'author_scoring_or_constraint_functions_called': False,
              'source_role': 'Independent raw geometry parser; positive reference not read',
              'parents': len(folders), 'method_query_rows': len(rows), 'summary': dict(summary),
              'f0_f1_identity_errors': identity_errors, 'recorded_read_identity_errors': read_errors,
              'rows': rows,
              'limits': ['Recorded file-read audit inspected; not an OS-level syscall proof',
                         'Raw source geometric checks are not complete physical/layer/public-access verification',
                         'Same-source exposed benchmark, not new independent scenes']}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    violations = []
    for r in rows:
        m = r['metrics']
        source = r['source_check'] or {}
        if m['continuity_gaps'] or m['saved_segment_errors'] or (r['reached'] and max(m.get('saved_length_error_m', 0), m.get('saved_cost_error_m', 0), m.get('start_residual_m') or 0, m.get('end_residual_m') or 0) > 1e-6):
            violations.append({'input_id': r['input_id'], 'query_id': r['query_id'], 'method': r['method'], 'kind': 'ROUTE_METRIC_OR_CONTINUITY'})
        for key in ('area_conflicts', 'native_source_errors', 'new_lawn_conflicts', 'derived_source_errors', 'explicit_direction_errors'):
            if source.get(key):
                violations.append({'input_id': r['input_id'], 'query_id': r['query_id'], 'method': r['method'], 'kind': key, 'items': source[key]})
    print(json.dumps({'parents': len(folders), 'method_query_rows': len(rows), 'summary': dict(summary),
                      'f0_f1_identity_errors': identity_errors, 'recorded_read_identity_errors': read_errors,
                      'violations': violations}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
