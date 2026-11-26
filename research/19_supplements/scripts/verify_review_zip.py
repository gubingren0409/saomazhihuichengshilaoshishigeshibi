"""Actual clean extraction and new solver execution, not a saved-route replay."""
from pathlib import Path,PurePosixPath
import argparse,zipfile,json,csv,hashlib,subprocess,datetime,time,uuid,sys
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];ap=argparse.ArgumentParser();ap.add_argument('--zip',required=True);args=ap.parse_args();archive=Path(args.zip).resolve();dest=ROOT/'delivery'/('VERIFY_EXTRACT_'+uuid.uuid4().hex);dest.mkdir();tick=time.perf_counter()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();archive_sha=sha(archive)
with zipfile.ZipFile(archive)as z:
 members=z.infolist();assert z.testzip()is None
 assert len(members)==len({m.filename for m in members})
 for m in members:
  path=PurePosixPath(m.filename);assert not path.is_absolute()and'..'not in path.parts and'\\'not in m.filename
  assert m.file_size<300_000_000
  assert m.filename.split('/')[-1]not in('.env',)and not m.filename.endswith(('.pkl','.pickle','.ttf','.woff','.woff2'))
 assert sum(m.file_size for m in members)<1_000_000_000
 z.extractall(dest)
manifest=list(csv.DictReader((dest/'manifests/FILE_SHA256.csv').open(encoding='utf-8-sig')));mismatch=[r['path']for r in manifest if sha(dest/r['path'])!=r['sha256']];assert not mismatch,mismatch
errors=[];resource_errors=[]
with sync_playwright()as p:
 browser=p.chromium.launch(channel='chrome',headless=True);version=browser.version;page=browser.new_page(viewport={'width':1500,'height':1150});page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  if r.request.url.startswith(('file:','data:','about:')):r.continue_()
  else:resource_errors.append(r.request.url.split('?')[0]);r.abort()
 page.route('**/*',route);page.goto((dest/'index.html').as_uri(),wait_until='load');page.wait_for_function('window.VIEWER_READY===true');page.locator('#scene').select_option('2');page.locator('#variant').select_option('0');page.locator('#near').click();page.locator('#full').click()
 images=page.locator('img').evaluate_all('(xs)=>xs.map(x=>{x.loading="eager";return x.src})');page.wait_for_function('Array.from(document.images).every(x=>x.complete && x.naturalWidth>0)');page.screenshot(path=str(ROOT/'delivery/CLEAN_EXTRACT_BROWSER.png'),full_page=False);browser.close()
assert not errors and not resource_errors,(errors,resource_errors)
command=[sys.executable,'-X','utf8','-B',str(dest/'scripts/replay_request.py'),'--case','library','--method','F1','--mode','FULL_FACE'];t=time.perf_counter();result=subprocess.run(command,cwd=str(dest),capture_output=True,text=True,encoding='utf-8',timeout=600);(ROOT/'delivery/CLEAN_EXTRACT_SOLVER.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8');assert result.returncode==0,result.stderr[-1000:]
lines=[line for line in result.stdout.splitlines()if line.startswith('{')];row=json.loads(lines[-1]);out=json.loads(Path(row['output_file']).read_text(encoding='utf-8'));assert row['status']=='PASS'and out['validation']['passed']and row['result']['solver']['invoked']and not row['route_answer_cache'];assert abs(row['route_length_m']-180.58111866323975)<1e-6
record={'timestamp':datetime.datetime.now().astimezone().isoformat(),'identity':'AUTHOR_SEPARATE_PROCESS_CLEAN_EXTRACT_CROSSCHECK_NOT_INDEPENDENT_REVIEWER','zip':str(archive),'zip_sha256':archive_sha,'zip_bytes':archive.stat().st_size,'member_count':len(members),'CRC':'PASS','path_safety':'PASS','member_sha256_checked':len(manifest),'member_mismatches':mismatch,'clean_directory':str(dest),'offline_browser':{'version':version,'javascript_errors':errors,'unexpected_external_resources':resource_errors,'loaded_local_images':len(images),'screenshot':'CLEAN_EXTRACT_BROWSER.png'},'new_actual_solver_call':{'command':command,'run_id':row['run_id'],'solver_invoked':True,'route_answer_cache':False,'status':row['status'],'route_length_m':row['route_length_m'],'geometry_signature':row['result'].get('geometry_signature'),'whole_route_check':out['validation']['passed'],'runtime_process_wall_ms':(time.perf_counter()-t)*1000,'result_file':row['output_file'],'result_sha256':sha(Path(row['output_file']))},'not_all_benchmarks_repeated':True,'field_truth_verified':False,'entire_historical_archive_collection_self_contained':False,'elapsed_ms':(time.perf_counter()-tick)*1000,'status':'PASS'}
receipt=ROOT/'delivery/SUPPLEMENTARY_VERIFICATION.json';receipt.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');sums=[]
for p in[archive,receipt,ROOT/'delivery/PACKAGING_RECEIPT.json',ROOT/'delivery/CLEAN_EXTRACT_BROWSER.png',ROOT/'delivery/CLEAN_EXTRACT_SOLVER.log']:sums.append(sha(p)+'  '+p.name)
(ROOT/'delivery/DELIVERY_SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8');print(json.dumps(record,ensure_ascii=False))
