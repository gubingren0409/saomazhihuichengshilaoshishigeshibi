from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
from walkability_foundation.graph_costs import batch_costs,scalar_costs

class CostContractTests(unittest.TestCase):
    def test_parallel_options_are_minimum(self):
        self.assertEqual(batch_costs([[[4,0],[3,2]]],0)[0],3)
        self.assertEqual(batch_costs([[[4,0],[3,2]]],1)[0],4)
    def test_fixed_graph_cost_modes_and_zero_edges(self):
        groups=[[[0,0]],[[2,1],[2.5,0]],[[8,7],[12,0]]]
        for p in(0,1):np.testing.assert_array_equal(batch_costs(groups,p),scalar_costs(groups,p))
    def test_invalid_length_and_penalty_rejected(self):
        for g,p in[([[[1,2]]],0),([[]],0),([[[-1,0]]],0),([[[1,0]]],2)]:
            with self.assertRaises(ValueError):batch_costs(g,p)

if __name__=='__main__':unittest.main()
