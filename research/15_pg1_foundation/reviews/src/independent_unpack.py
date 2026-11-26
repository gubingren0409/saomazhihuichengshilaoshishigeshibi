"""Validate final ZIP bytes/CRC/all manifest entries before own safe extraction."""
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone
import argparse,hashlib,json,stat,zipfile
ROOT=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--expected-sha',required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
archive=args.archive.resolve();target=args.out.resolve()
assert target.is_relative_to((ROOT/'reviews').resolve()) and not target.exists()
digest=hashlib.sha256(archive.read_bytes()).hexdigest();assert digest==args.expected_sha
receipt={'at_utc':datetime.now(timezone.utc).isoformat(),'archive':str(archive),'archive_sha256':digest,'archive_bytes':archive.stat().st_size,'extracted_root':str(target),'reviewer_solver_calls':0}
with zipfile.ZipFile(archive)as z:
    infos=z.infolist();normalized=set()
    for info in infos:
        name=info.filename.replace('\\','/');p=PurePosixPath(name)
        assert not p.is_absolute()and '..'not in p.parts and ':'not in name and not name.startswith('/')
        assert all(part.rstrip('. ')==part for part in p.parts)
        assert not any(part.split('.')[0].upper()in{'CON','PRN','AUX','NUL',*('COM'+str(i)for i in range(1,10)),*('LPT'+str(i)for i in range(1,10))}for part in p.parts)
        assert not any(part.lower()=='.git'for part in p.parts)
        assert stat.S_IFMT(info.external_attr>>16)!=stat.S_IFLNK
        assert name.casefold()not in normalized;normalized.add(name.casefold())
    assert z.testzip()is None
    members={info.filename for info in infos if not info.is_dir()}
    manifests=[n for n in members if PurePosixPath(n).name=='MANIFEST_SHA256.json']
    shallow=min(len(PurePosixPath(n).parts)for n in manifests)
    rootmanifests=[n for n in manifests if len(PurePosixPath(n).parts)==shallow]
    assert len(rootmanifests)==1
    manifest_name=rootmanifests[0];prefix=str(PurePosixPath(manifest_name).parent)
    prefix=''if prefix=='.'else prefix+'/'
    manifest=json.loads(z.read(manifest_name));records=manifest['files']if isinstance(manifest,dict)else manifest
    listed=set();total=0
    for row in records:
        member=prefix+row['path'];assert member not in listed;listed.add(member);body=z.read(member)
        assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256'];total+=len(body)
    assert members==listed|{manifest_name}
    target.mkdir(parents=True)
    for info in infos:
        dest=(target/Path(*PurePosixPath(info.filename).parts)).resolve();assert dest.is_relative_to(target)
        if info.is_dir():dest.mkdir(parents=True,exist_ok=True)
        else:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(info))
    receipt.update(member_count=len(members),manifest_records=len(records),content_bytes=total,CRC='PASS',all_manifest_size_sha='PASS',safe_paths='PASS',package_root=str(target/prefix),status='PASS_PACKAGE_BYTES_ONLY_PENDING_REPLAY')
(ROOT/'reviews/final_unpack_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:receipt[k]for k in ['archive_sha256','member_count','manifest_records','content_bytes','status']}))
