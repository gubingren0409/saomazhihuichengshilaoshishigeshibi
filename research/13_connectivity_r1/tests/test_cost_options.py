import copy
import unittest
import networkx as nx
from src.planner import _weighted_route,graph_sha,compose_prepared

class CostOptions(unittest.TestCase):
    def test_finite_cost_can_reverse_parallel_preference_without_graph_mutation(self):
        g=nx.DiGraph();g.add_node('a',xy=(0,0));g.add_node('b',xy=(1,0))
        short=[dict(layer='inferred',length_m=8,xy=[(0,0),(1,0)])]
        known=[dict(layer='derived',length_m=10,xy=[(0,0),(1,0)])]
        g.add_edge('a','b',segments=short,routing_alternatives=[short,known])
        before=copy.deepcopy(g['a']['b']);sha=graph_sha(g)
        a,_,_= _weighted_route(g,'a','b',1);b,_,_=_weighted_route(g,'a','b',2)
        self.assertEqual(a['segments'][0]['layer'],'inferred')
        self.assertEqual(b['segments'][0]['layer'],'derived')
        self.assertEqual(g['a']['b'],before);self.assertEqual(graph_sha(g),sha)
    def test_compose_does_not_discard_longer_mapped_alternative(self):
        source=nx.DiGraph();source.add_node('a',xy=(0,0));source.add_node('b',xy=(1,0))
        source.add_edge('a','b',segments=[dict(layer='inferred',length_m=8,xy=[(0,0),(1,0)])])
        overlay=nx.DiGraph();overlay.add_nodes_from(source.nodes(data=True));overlay.add_edge('a','b',segments=[dict(layer='derived',length_m=10,xy=[(0,0),(1,0)])])
        region=type('R',(),{'internal':nx.DiGraph()})()
        graph=compose_prepared(dict(source=source,region=region,face_overlay=overlay))
        self.assertEqual(len(graph['a']['b']['routing_alternatives']),2)
        result,_,_=_weighted_route(graph,'a','b',2)
        self.assertEqual(result['segments'][0]['cost_m'],10)

if __name__=='__main__':unittest.main()
