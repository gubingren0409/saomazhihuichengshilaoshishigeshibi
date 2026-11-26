import sys,unittest,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_free_space import FreeSpaceCounterexamples
suite=unittest.TestSuite([FreeSpaceCounterexamples('test_11_thin_wall_and_corner_cut')])
with (ROOT/'audits/partition_regression_tests.txt').open('w',encoding='utf8') as f:
    result=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
(ROOT/'audits/partition_regression_tests.json').write_text(json.dumps({'status':'PASS' if result.wasSuccessful() else 'FAIL','tests':result.testsRun,'synthetic_surface_builds':2,'actual_source_minimal_fixtures':2,'scope':'Thin wall/corner cut plus exact near-coincident frozen coordinate masks; not new real recovery task'},indent=2),encoding='utf8')
print('PASS' if result.wasSuccessful() else 'FAIL')
raise SystemExit(0 if result.wasSuccessful() else 1)
