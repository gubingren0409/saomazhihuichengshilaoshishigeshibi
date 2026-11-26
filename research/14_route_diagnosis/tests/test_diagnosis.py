from pathlib import Path
import sys,unittest,math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import diagnose as D
from certificates import distance_errors,simple_forced_join
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components,breadth_first_order
class DiagnosisTests(unittest.TestCase):
 def test_directed_reach_is_not_wcc(self):
  g=csr_matrix(([1,1],([0,2],[1,1])),shape=(3,3))
  self.assertEqual(connected_components(g,directed=True,connection='weak')[0],1)
  self.assertNotIn(2,breadth_first_order(g,0,directed=True,return_predecessors=False))
 def test_parallel_min_does_not_sum(self):
  native=(10.,0.,(),(),'SOURCE_SNAPSHOT');hyp=(7.,7.,(),('i',),'CONDITIONAL_GAP_LINK');xy={'a':(0,0),'b':(1,0)};e={('a','b'):[native,hyp]}
  self.assertEqual(float(D.sparse(xy,e,1)[4][0,1]),7)
  self.assertEqual(float(D.sparse(xy,e,2)[4][0,1]),10)
 def test_delete_new_option_retains_native_parent(self):
  opts=[(10.,0.,(),(),'SOURCE_SNAPSHOT'),(7.,7.,(),('i',),'CONDITIONAL_GAP_LINK')]
  kept=[o for o in opts if o[4]!='CONDITIONAL_GAP_LINK']
  self.assertEqual(D.choose(kept,2)[0],10)
 def test_forced_option_cannot_reselect_cheaper_parent(self):
  n=(10.,0.,(),(),'SOURCE_SNAPSHOT');hyp=(7.,7.,(),('i',),'CONDITIONAL_GAP_LINK');xy={'a':(0,0),'b':(1,0)};e={('a','b'):[n,hyp]}
  self.assertEqual(D.path_output(['a','b'],xy,e,2)['cost_m'],10)
  forced=D.path_output(['a','b'],xy,e,2,('a','b',hyp))
  self.assertEqual(forced['cost_m'],14);self.assertIn('i',forced['segments'][0]['interface_ids'])
 def test_spur_walk_is_not_simple_alternative(self):
  self.assertIsNone(simple_forced_join(['s','j','leaf'],['j','t']))
  self.assertEqual(simple_forced_join(['s','u'],['v','t']),['s','u','v','t'])
 def test_owner_incidence_does_not_mean_selected_owner(self):
  selected={"u":"a","v":"b","layer":"native","source_id":"way/parent","length_m":1}
  self.assertNotIn("way/new-face",D.option([selected])[2])
 def test_tight_edge_and_positive_slack(self):
  ds={'s':0,'u':1,'t':2};dt={'s':2,'u':1,'t':0}
  self.assertEqual(ds['s']+1+dt['u']-ds['t'],0)
  self.assertGreater(ds['s']+3+dt['t']-ds['t'],0)
 def test_primal_dual_certificate_and_corruption(self):
  e=[('s','u',1),('u','t',1),('s','t',3)];ds={'s':0,'u':1,'t':2};dt={'s':2,'u':1,'t':0}
  self.assertEqual(distance_errors(e,ds,dt,'s','t',['s','u','t']),[])
  bad=[('s','u',.5),*e[1:]]
  self.assertIn('FORWARD_BELLMAN',distance_errors(bad,ds,dt,'s','t'))
if __name__=='__main__':unittest.main()
