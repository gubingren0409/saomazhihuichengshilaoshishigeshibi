"""Independent final ZIP integrity and fresh-service real-solver replay.

Does not import the author's packaging/verifier or stored route. One genuine
new APP solver request, to be reserved in the coordinator's 96-call budget.
"""
from pathlib import Path,PurePosixPath
from datetime import datetime
import argparse,hashlib,json,os,re,stat,subprocess,sys,time,urllib.request,uuid,zipfile
ROOT=Path(__file__).resolve().parents[1]

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,v):
    Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def api(url,body=None,timeout=15):
    r=urllib.request.Request(url,data=json.dumps(body).encode()if body is not None else None,
        headers={'Content-Type':'application/json'}if body is not None else{})
    return json.loads(urllib.request.urlopen(r,timeout=timeout).read())
def safe(name):
    p=PurePosixPath(name)
    if not name or'\\'in name or p.is_absolute()or'..'in p.parts or re.match(r'^[A-Za-z]:',name):raise ValueError('UNSAFE_PATH:'+name)
    return p

def run(archive,request_file,port,timeout):
    archive=archive.resolve();archive_sha=sha(archive);tag=datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
    scratch=ROOT/'runtime'/('independent_clean_'+tag);scratch.mkdir(parents=True,exist_ok=False);unpack=scratch/'unpacked';unpack.mkdir()
    result={'reviewer':'/root/face_review','role':'INDEPENDENT_FIXED_ARCHIVE_REAL_NEW_REQUEST_REPLAY','archive':str(archive),'archive_sha256':archive_sha,
        'scratch':str(scratch),'checks':[],'APP_solver_calls':0,'old_service_url':'http://127.0.0.1:53421/'}
    try:old_before=api(result['old_service_url']+'api/health')
    except Exception as e:old_before={'health_unavailable':str(e)}
    seen=set();protected={};entries=[]
    with zipfile.ZipFile(archive)as z:
        for info in z.infolist():
            name=info.filename;safe(name)
            if name.casefold()in seen or stat.S_ISLNK(info.external_attr>>16):raise ValueError('DUPLICATE_OR_SYMLINK:'+name)
            seen.add(name.casefold())
        if z.testzip()is not None:raise ValueError('CRC_FAILED')
        manifest_bytes=z.read('MANIFEST.json');manifest=json.loads(manifest_bytes);entries=manifest['entries']
        listed=[r['path']for r in entries]
        if len(listed)!=len(set(listed))or'MANIFEST.json'in listed:raise ValueError('DUPLICATE_OR_SELF_HASHED_MANIFEST_ENTRY')
        if set(z.namelist())!={r['path']for r in entries}|{'MANIFEST.json'}:raise ValueError('MANIFEST_MEMBER_SET')
        for row in entries:
            name=row['path'];safe(name);body=z.read(name)
            if len(body)!=row['bytes']or hashlib.sha256(body).hexdigest()!=row['sha256']:raise ValueError('MEMBER_HASH:'+name)
            destination=unpack/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(body);protected[name]=row['sha256']
        (unpack/'MANIFEST.json').write_bytes(manifest_bytes);protected['MANIFEST.json']=hashlib.sha256(manifest_bytes).hexdigest()
    result['checks'].append({'name':'INDEPENDENT_CRC_PATH_ALL_MEMBER_SHA_EXACT_MANIFEST','passed':True,'members':len(protected)})
    tests=subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests'],cwd=unpack,capture_output=True,text=True,timeout=120)
    testlog=scratch/'unittest_discover.txt';testlog.write_text(tests.stdout+'\n'+tests.stderr,encoding='utf-8')
    result['unittest_discover']={'command':'python -X utf8 -B -m unittest discover -s tests','exit_code':tests.returncode,
        'log':str(testlog),'log_sha256':sha(testlog),'stdout_tail':tests.stdout[-3000:],'stderr_tail':tests.stderr[-3000:]}
    result['checks'].append({'name':'CLEAN_UNPACK_UNITTEST_DISCOVER_REAL_EXECUTION','passed':tests.returncode==0})
    request=read(request_file);request=request.get('input',request);request={**request,'method':'F1','area_routing':'FULL_FACE','purpose':'APPROACH_OUTSIDE','request_id':'INDEPENDENT-CLEAN-'+uuid.uuid4().hex}
    result['request']=request;result['request_file_sha256']=sha(request_file)
    log=open(scratch/'temporary_service.log','w',encoding='utf-8');proc=None;response=None
    try:
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        proc=subprocess.Popen([sys.executable,'-X','utf8','-B',str(unpack/'scripts/serve_app.py'),'--port',str(port)],cwd=unpack,env=env,
            stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        statepath=unpack/'runs/service.json';end=time.monotonic()+35;state=None
        while time.monotonic()<end:
            if proc.poll()is not None:raise RuntimeError('CLEAN_SERVICE_EXITED:'+str(proc.returncode))
            if statepath.exists():
                candidate=read(statepath)
                if candidate.get('pid')==proc.pid and candidate.get('running'):state=candidate;break
            time.sleep(.3)
        if state is None:raise RuntimeError('CLEAN_SERVICE_START_TIMEOUT')
        health=api(state['url']+'api/health');result['temporary_service']={'pid':proc.pid,'url':state['url'],'health':health}
        if health.get('pid')!=proc.pid or health.get('service')!='PEDESTRIAN_AREA_SHORTEST_R1':raise ValueError('WRONG_SERVICE_IDENTITY')
        tick=time.perf_counter();response=api(state['url']+'api/plan',request,timeout=timeout);result['request_elapsed_s']=time.perf_counter()-tick
        result['APP_solver_calls']=int(bool(response.get('solver',{}).get('invoked')))
        write(scratch/'fresh_response.json',response)
        solver=response.get('solver',{});result['solver']={'status':response.get('status'),'run_id':response.get('run_id'),'request_id':response.get('request_id'),'solver':solver,'route_answer_cache':response.get('route_answer_cache')}
        passed=solver.get('invoked')and solver.get('answer_source')=='CURRENT_REQUEST_SOLVER'and response.get('route_answer_cache')=={'enabled':False,'hit':False}and response.get('input',{}).get('request_id')==request['request_id']and bool(response.get('route'))
        result['checks'].append({'name':'CLEAN_SERVICE_FRESH_FULL_FACE_F1_REQUEST_REAL_SOLVER','passed':bool(passed)})
    except Exception as e:result['execution_error']={'type':type(e).__name__,'message':str(e)}
    finally:
        if proc is not None and proc.poll()is None:
            try:
                state=read(unpack/'runs/service.json')
                if state.get('pid')==proc.pid:api(state['url']+'api/stop',{'pid':proc.pid})
                proc.wait(timeout=8)
            except Exception:
                proc.terminate();proc.wait(timeout=8)
        result['temporary_service_stopped']=proc is not None and proc.poll()is not None
        log.close()
    # Stop the temporary graph process before independent raw-geometry pass to
    # bound RAM. Only audit scripts inside this verified archive execute here.
    if response is not None and(unpack/'scripts/independent_app_check.py').exists():
        out=scratch/'independent_remeasurement.json'
        check=subprocess.run([sys.executable,'-X','utf8','-B',str(unpack/'scripts/independent_app_check.py'),str(scratch/'fresh_response.json'),'--output',str(out)],cwd=unpack,capture_output=True,text=True,timeout=90)
        result['remeasurement_process']={'exit_code':check.returncode,'stdout':check.stdout[-3000:],'stderr':check.stderr[-3000:]}
        if out.exists():
            measured=read(out);result['remeasurement_status']=measured['status'];result['remeasurement_sha256']=sha(out)
            result['checks'].append({'name':'INDEPENDENT_RAW_GEOMETRY_LENGTH_COST_ENDPOINT_REMEASUREMENT','passed':measured['status']=='PASS'})
    changed=[name for name,digest in protected.items()if not(unpack/name).is_file()or sha(unpack/name)!=digest]
    result['checks'].append({'name':'ALL_ORIGINAL_SHIPPED_FILES_UNCHANGED_AFTER_LIVE_REPLAY','passed':not changed,'changed':changed})
    try:old_after=api(result['old_service_url']+'api/health')
    except Exception as e:old_after={'health_unavailable':str(e)}
    result['old_service_before']=old_before;result['old_service_after']=old_after
    result['checks'].append({'name':'OLD_SERVICE_NOT_RESTARTED_OR_STOPPED','passed':old_before.get('status')=='UP'and old_after.get('status')=='UP'and old_before.get('pid')is not None and old_before.get('pid')==old_after.get('pid')})
    result['checks'].append({'name':'FIXED_ARCHIVE_UNCHANGED','passed':sha(archive)==archive_sha})
    result['status']='PASS'if not result.get('execution_error')and result['temporary_service_stopped']and all(c['passed']for c in result['checks'])else'REQUIRES_INSPECTION'
    write(ROOT/'audits/independent_clean_replay.json',result);print(json.dumps({'status':result['status'],'APP_solver_calls':result['APP_solver_calls'],'checks':len(result['checks']),'archive_sha256':archive_sha},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True,type=Path);p.add_argument('--request-file',required=True,type=Path);p.add_argument('--port',type=int,default=53437);p.add_argument('--timeout',type=int,default=240);a=p.parse_args();run(a.archive,a.request_file,a.port,a.timeout)
