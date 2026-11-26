"""Independent final-archive safety/CRC/SHA and zero-solver certificate replay."""
from pathlib import Path,PurePosixPath,PureWindowsPath
import argparse,json,zipfile,hashlib,subprocess,sys,time,datetime,stat
BASELINE_SHA='d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed'
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--extract-to',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();start=time.time();a.receipt.parent.mkdir(parents=True,exist_ok=True);receipt={'reviewer':'/root/r2_independent','started_at':datetime.datetime.now().astimezone().isoformat(),'archive':str(a.archive.resolve()),'archive_sha256':digest(a.archive),'archive_bytes':a.archive.stat().st_size,'baseline_sha256':digest(a.baseline),'APP_solver_calls':0,'SSSP_calls':0,'checks':{},'replays':[],'limitations':['No new routes requested; independent certificates/provenance replay only. R1 baseline required separately for historical/raw geometry checks. Actual interactive browser review recorded separately.']}
    try:
        assert receipt['baseline_sha256']==BASELINE_SHA,'BASELINE_SHA_MISMATCH'
        dest=a.extract_to.resolve();assert not dest.exists()or not any(dest.iterdir()),'EXTRACT_DIRECTORY_NOT_EMPTY';dest.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(a.archive)as z:
            infos=z.infolist();names=[i.filename for i in infos];assert len(names)==len(set(names)),'DUPLICATE_MEMBERS';assert sum(i.file_size for i in infos)<1500000000,'EXTRACTION_SIZE_LIMIT';
            for i in infos:
                name=i.filename.replace('\\','/');pp=PurePosixPath(name);wp=PureWindowsPath(name);assert not pp.is_absolute()and not wp.is_absolute()and not wp.drive and '..'not in pp.parts and '\x00'not in name and ':'not in name,'UNSAFE_PATH';assert not stat.S_ISLNK(i.external_attr>>16),'SYMLINK';assert not i.flag_bits&1,'ENCRYPTED_MEMBER';assert dest in(dest/Path(*pp.parts)).resolve().parents or(dest/Path(*pp.parts)).resolve()==dest,'OUTSIDE_EXTRACT_ROOT'
            assert z.testzip()is None,'ZIP_CRC';receipt['checks']['member_path_duplicate_symlink_encryption_CRC']='PASS';manifest=json.loads(z.read('MANIFEST_SHA256.json'));rows=manifest['files'];expected={r['path']for r in rows}|{'MANIFEST_SHA256.json'};assert expected==set(names),'MANIFEST_MEMBERS';
            for r in rows:
                h=hashlib.sha256();size=0
                with z.open(r['path'])as f:
                    for chunk in iter(lambda:f.read(1048576),b''):size+=len(chunk);h.update(chunk)
                assert size==r['bytes']and h.hexdigest()==r['sha256'],'MANIFEST_CONTENT:'+r['path']
            receipt['checks']['all_content_SHA256']='PASS';receipt['members']=len(infos);receipt['content_files']=len(rows);z.extractall(dest)
        # Replay only this independent reviewer's known source files, whose hashes
        # must match the original current reviewer workspace before execution.
        root=Path(__file__).resolve().parents[1]
        scripts=['independent_baseline.py','independent_graph_certificates.py','independent_topology.py','independent_overlay_binding.py','independent_opportunity.py','independent_alternative_geometry.py','independent_face_graph.py','independent_ui_pool.py']
        outputs=['independent_baseline32.json','independent_graph_distance_certificates.json','independent_topology_lineage.json','independent_overlay_binding.json','independent_opportunity_certificates.json','independent_alternative_geometry.json','independent_face_graph_opportunity.json','independent_ui_pool.json']
        for name,outname in zip(scripts,outputs):
            rel=Path('src')/name;assert digest(dest/rel)==digest(root/rel),'REPLAY_SCRIPT_CHANGED:'+name;cmd=[sys.executable,'-X','utf8','-B',str(dest/rel)]
            if name not in('independent_graph_certificates.py','independent_topology.py','independent_face_graph.py','independent_ui_pool.py'):cmd+=['--baseline',str(a.baseline.resolve())]
            before=digest(dest/'audits'/outname);tick=time.time();r=subprocess.run(cmd,cwd=dest,capture_output=True,text=True,encoding='utf-8',timeout=120);log=a.receipt.parent/(a.receipt.stem+'_'+name+'.txt');log.write_text(r.stdout+'\n'+r.stderr,encoding='utf-8');assert r.returncode==0,'REPLAY_EXIT:'+name;result=json.loads((dest/'audits'/outname).read_text(encoding='utf-8'));assert result.get('status','').startswith('PASS'),'REPLAY_STATUS:'+name
            receipt['replays'].append({'script':str(rel),'script_sha256':digest(dest/rel),'elapsed_s':time.time()-tick,'status':result['status'],'result_sha256':digest(dest/'audits'/outname),'result_bytes_identical':digest(dest/'audits'/outname)==before,'log':str(log)})
        assert digest(a.archive)==receipt['archive_sha256'],'ARCHIVE_CHANGED';assert digest(a.baseline)==BASELINE_SHA,'BASELINE_CHANGED';receipt['checks']['original_archives_unchanged']='PASS';receipt['status']='PASS_FOR_FIXED_ARCHIVE_AND_ZERO_SOLVER_REPLAY'
    except Exception as e:
        receipt['status']='REQUIRES_INSPECTION';receipt['error']=repr(e)
    receipt['elapsed_s']=time.time()-start;receipt['finished_at']=datetime.datetime.now().astimezone().isoformat();a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False));return 0 if receipt['status'].startswith('PASS')else 1
if __name__=='__main__':raise SystemExit(main())
