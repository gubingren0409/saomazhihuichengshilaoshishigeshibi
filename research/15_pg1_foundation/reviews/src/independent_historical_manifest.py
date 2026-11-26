"""Historical manifest check only; never starts solver or imports old source."""
from pathlib import Path
import hashlib, json, zipfile
ROOT=Path(__file__).resolve().parents[2]
archives=[ROOT.parent/'PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip',ROOT.parent/'PED_AREA_CONNECTIVITY_R2_ROUTE_DIAGNOSIS/delivery/OPEN_REVIEW.zip']
out=[]
for p in archives:
    with zipfile.ZipFile(p) as z:
        manifest=json.loads(z.read('MANIFEST_SHA256.json'))
        files=manifest['files']
        failures=[]
        for rec in files:
            b=z.read(rec['path'])
            if len(b)!=rec['bytes'] or hashlib.sha256(b).hexdigest()!=rec['sha256']:
                failures.append(rec['path'])
        names={n for n in z.namelist() if not n.endswith('/')}
        listed={r['path'] for r in files}
        out.append({'archive':str(p),'manifest_records':len(files),'checked_uncompressed_bytes':sum(r['bytes'] for r in files),'failures':failures,'unlisted_members':sorted(names-listed),'listed_missing':sorted(listed-names)})
(ROOT/'reviews/independent_historical_manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
assert all(not r['failures'] and not r['listed_missing'] and r['unlisted_members']==['MANIFEST_SHA256.json'] for r in out)
print(json.dumps([{'manifest_records':r['manifest_records'],'failures':len(r['failures'])} for r in out]))
