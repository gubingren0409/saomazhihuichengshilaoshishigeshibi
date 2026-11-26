from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_public_tree import scan

class ReleaseAuditTests(unittest.TestCase):
 def tempdir(self):
  base=Path(__file__).resolve().parents[1]/'.pytest_cache';base.mkdir(exist_ok=True)
  return tempfile.TemporaryDirectory(dir=base)
 def test_secret_and_private_location_never_report_values(self):
  with self.tempdir()as d:
   root=Path(d);secret='gh'+'p_'+'z'*30;private='/'+'home'+'/'+'fake_person'+'/data'
   (root/'bad.txt').write_text(secret+'\n'+private)
   r=scan(root);self.assertEqual({x['category']for x in r['findings']},{'github_token','private_local_path'})
   self.assertNotIn(secret,str(r));self.assertNotIn(private,str(r))
 def test_hash_metadata_allowed_but_raw_artifact_rejected(self):
  with self.tempdir()as d:
   root=Path(d);(root/'registry.txt').write_text('sha256='+'f'*64);self.assertFalse(scan(root)['findings'])
   (root/'raw.geojson').write_text('{}');self.assertEqual(scan(root)['findings'][0]['category'],'RAW_GENERATED_SECRET_OR_LARGE_FILE')
