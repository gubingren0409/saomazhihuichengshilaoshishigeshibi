"""Lambda=1 correctness replay on actual serialized shared benchmark graphs.

Own graph reconstruction and Dijkstra; no author routing/weight functions.
Stored predictions provide only the comparison value and authorized terminal
bind records, never the path to search. This is not a new parameter experiment.
"""
import argparse
import gzip
import json
import math
from pathlib import Path

import networkx as nx

from independent_check import denied, digest, read


def arc(graph, u, v, segments):
    length = sum(sum(math.dist(a, b) for a, b in zip(s['xy'], s['xy'][1:])) for s in segments)
    if not graph.has_edge(u, v) or length < graph[u][v]['cost']:
        graph.add_edge(u, v, cost=length, segments=segments)


def reconstruct_native(obs, rejected):
    graph = nx.DiGraph()
    nodes = {n['id']: n for n in obs['nodes']}
    graph.add_nodes_from((n, {'xy': row['xy']}) for n, row in nodes.items())
    for e in obs['edges']:
        u, v = e['u'], e['v']
        if u == v or any(denied(t) for t in (e.get('tags', {}), nodes[u].get('tags', {}), nodes[v].get('tags', {}))):
            continue
        layer = 'derived' if e['kind'].startswith('DERIVED') else 'native'
        arc(graph, u, v, [{'xy': [nodes[u]['xy'], nodes[v]['xy']], 'layer': layer}])
    graph.remove_edges_from((e['u'], e['v']) for e in rejected)
    return graph


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch', default='R2_unified')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    rows = []
    for path in sorted((root / 'runs/benchmark' / args.batch).glob('*/result.json')):
        j = read(path)
        obs = read(path.parent / 'observed.json')
        queries = read(path.parent / 'query.json')['queries']
        with gzip.open(path.parent / 'graphs.json.gz', 'rt', encoding='utf-8') as f:
            stored = json.load(f)['F0']
        native = reconstruct_native(obs, stored['native_rejected'])
        region = nx.DiGraph()
        region.add_nodes_from((r['id'], {'xy': r['xy']}) for r in stored['nodes'])
        for e in stored['edges']:
            arc(region, e['u'], e['v'], e['segments'])
        has_assumed = any(s['layer'] in {'inferred', 'assumed', 'unknown'} for _, _, row in region.edges(data=True) for s in row['segments'])
        for q in queries:
            graph = region.copy() if q.get('scope') == 'LOCAL_REGION_ONLY' else nx.compose(native, region)
            for term in j['methods']['F0']['terminals']:
                if term['query_id'] != q['query_id']:
                    continue
                key, target, segments = term['id'], term['attach'], term['segments']
                graph.add_node(key, xy=term['xy'])
                arc(graph, key, target, segments)
                arc(graph, target, key, [{**s, 'xy': s['xy'][::-1]} for s in reversed(segments)])
            a, b = q['source']['id'], q['target']['id']
            reached = False
            length = None
            try:
                # Explicit finite multiplier=1 on all hypothetical layers.
                length = nx.dijkstra_path_length(graph, a, b, weight=lambda u, v, e: sum(
                    sum(math.dist(x, y) for x, y in zip(s['xy'], s['xy'][1:])) *
                    (1.0 if s['layer'] in {'inferred', 'unknown', 'assumed'} else 1.0)
                    for s in e['segments']))
                reached = True
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                pass
            expected = j['methods']['F0']['routes'][q['query_id']]
            rows.append({'input_id': path.parent.name, 'query_id': q['query_id'],
                         'actual_dijkstra_called': a in graph and b in graph,
                         'graph_contains_assumed_edges': has_assumed,
                         'lambda1_reached': reached, 'f0_reached': expected['reached'],
                         'lambda1_length_m': length, 'f0_length_m': expected['length_m'],
                         'length_difference_m': length - expected['length_m'] if reached and expected['reached'] else None,
                         'serialized_graph_sha256': digest(path.parent / 'graphs.json.gz')})
    failures = [r for r in rows if r['lambda1_reached'] != r['f0_reached'] or r['length_difference_m'] is not None and abs(r['length_difference_m']) > 1e-6]
    result = {'reviewer': '/root/e2e_review', 'role': 'FINITE_COST_CORRECTNESS_ONLY_NO_PARAMETER_SELECTION',
              'author_routing_functions_called': False, 'lambda': 1, 'queries': len(rows),
              'queries_on_graphs_containing_assumed_edges': sum(r['graph_contains_assumed_edges'] for r in rows),
              'actual_dijkstra_calls': sum(r['actual_dijkstra_called'] for r in rows),
              'failures': failures, 'rows': rows,
              'limits': 'Reconstructs source graph from observed plus recorded common rejection list and serialized regional graph; uses authorized terminal bindings, not stored path answers. Verifies reachability and shortest cost, not unique tie path. Separate raw-source checks cover route constraints.'}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
