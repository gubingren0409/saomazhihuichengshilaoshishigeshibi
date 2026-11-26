"""Actually count fixture invocations, distinct from real-map experiment builds."""
import argparse,sys,unittest,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import test_free_space
def main(out):
    counter={'fixture_calls':0}
    original=test_free_space.fixture
    def counted(*a,**kw):
        counter['fixture_calls']+=1
        return original(*a,**kw)
    test_free_space.fixture=counted
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_free_space)
    out.mkdir(parents=True,exist_ok=True)
    with (out/'tests.txt').open('w',encoding='utf8') as f:result=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
    data=dict(status='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,**counter,
              synthetic_region_builds=counter['fixture_calls']*2,role='SYNTHETIC_ONLY_NOT_REAL_RECOVERY')
    (out/'test_receipt.json').write_text(json.dumps(data,indent=2),encoding='utf8');print(json.dumps(data));return 0 if result.wasSuccessful() else 1
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();raise SystemExit(main(a.out))
