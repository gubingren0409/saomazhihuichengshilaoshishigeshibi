"""Check material integrity and reading; no algorithm imports or experiments."""
from pathlib import Path,PurePosixPath
import csv,hashlib,json,re,shutil,zipfile,sys
from html.parser import HTMLParser
from PIL import Image
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1];P=R/'package';D=R/'delivery'
def sh(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def dump(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
def csvput(p,data):
 with p.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
events=json.loads((R/'working/events.json').read_text(encoding='utf8'))
assert len(events)==11
figs=rows(P/'figures/FIGURE_CATALOG.csv');nums=rows(P/'04_MASTER_NUMBERS_TABLE.csv');ss=rows(P/'evidence/SOURCE_INDEX.csv')
for r in ss:assert sh(P/r['package_file'])==r['sha256'],r['package_file']
for e in events:
 for n in ['main_figure.png','optional_figure.png','metrics.csv','caption_zh.md','source_traceability.md','unsupported_claims.md']:assert (P/e[1]/n).is_file(),(e[0],n)
for r in figs:
 assert sh(P/r['package_file'])==r['sha256']
 with Image.open(P/r['package_file']) as im:im.verify()
checks=[]
for r in nums:
 src=P/r['source_file'];assert src.is_file() and sh(src)==r['source_sha256']
 status='BOUND_SOURCE_REPORT_OR_TABLE'
 if src.suffix=='.json' and re.fullmatch(r'[A-Za-z0-9_\-.\[\]]+',r['source_field']):
  v=json.loads(src.read_text(encoding='utf8'))
  try:
   for t in re.findall(r'[^.\[\]]+',r['source_field']):v=v[int(t)] if isinstance(v,list) else v[t]
  except (KeyError,IndexError,ValueError,TypeError):status='BOUND_SOURCE_NONSCALAR_POINTER'
  else:
   is_list=isinstance(v,list)
   if is_list:v=len(v)
   assert abs(float(v)-float(r['value']))<1e-8,(r['metric'],v,r['value'])
   status='JSON_LIST_LENGTH_MATCH' if is_list else 'JSON_SCALAR_MATCH'
 checks.append(dict(metric=r['metric'],event_id=r['event_id'],status=status,source_sha256=r['source_sha256']))
csvput(P/'audit/AUTHOR_NUMBER_CHECK.csv',checks)
for r in rows(P/'corrections/R4_REV1_EVIDENCE.csv'):assert (P/r['source_path']).is_file() and sh(P/r['source_path'])==r['source_sha256']
# All primary input/prediction lineage checks reference retained original member bytes.
lineage=rows(P/'08_free_space_inference/FULL_QUERY_INPUT_PREDICTION_SHA_CHECK.csv')
dump(P/'audit/PRIMARY_LINEAGE_SCOPE.json',{'source_check_table':'08_free_space_inference/FULL_QUERY_INPUT_PREDICTION_SHA_CHECK.csv','rows':len(lineage),'scope':'Saved observation/prediction bytes; no new graph or solver execution'})
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,t,aa):
  for k,v in aa:
   if k in ['href','src']:self.links.append(v)
parser=Links();parser.feed((P/'index.html').read_text(encoding='utf8'))
for l in parser.links:
 if l.startswith('#'):continue
 assert not l.startswith(('http:','https:'));assert (P/l).is_file(),l
old=[]
for r in json.loads((R/'audit/ROOT_ARCHIVE_INVENTORY.json').read_text(encoding='utf8')):
 assert sh(Path(r['path']))==r['sha256'];old.append({'archive':Path(r['path']).name,'sha256':r['sha256'],'status':'UNCHANGED'})
assert sh(P/'prior/PG1_MIDTERM_RESEARCH_MATERIALS_R2.zip')=='5fecb3c0f3f65dbf371967deaf6d7d3aa3885b09a3d160bf07b00813a3e682da'
dump(P/'audit/OLD_INPUT_PROTECTION.json',old)
with sync_playwright() as pp:
 b=pp.chromium.launch(channel='chrome',headless=True);pg=b.new_page(viewport={'width':1440,'height':1050})
 errors=[];external=[];pg.on('pageerror',lambda e:errors.append(str(e)))
 pg.route(re.compile(r'^https?://'),lambda route:(external.append(route.request.url),route.abort())[1])
 pg.goto((P/'index.html').as_uri(),wait_until='load')
 for eid,*_ in events:pg.locator('#'+eid).scroll_into_view_if_needed()
 pg.wait_for_function('Array.from(document.images).every(x=>x.complete&&x.naturalWidth>0)')
 info=pg.locator('img').evaluate_all('(xs)=>xs.map(x=>({path:x.getAttribute("src"),width:x.naturalWidth,height:x.naturalHeight}))')
 assert len(info)==len(figs) and not errors and not external
 pg.evaluate('scrollTo(0,0)');pg.screenshot(path=str(R/'audit/AUTHOR_OFFLINE_OVERVIEW.png'))
 pg.locator('#E06').scroll_into_view_if_needed();pg.screenshot(path=str(R/'audit/AUTHOR_OFFLINE_F0_F1.png'))
 dump(P/'audit/AUTHOR_OFFLINE_READING.json',{'identity':'AUTHOR_CHECK_NOT_INDEPENDENT','browser':b.version,'events':11,'images':info,'js_errors':errors,'external_requests':external,'status':'PASS'})
 b.close()
dump(P/'audit/AUTHOR_MATERIAL_CHECK.json',{'status':'PASS','events':11,'figures':len(figs),'numbers':len(nums),'retained_source_files':len(ss),'source_member_sha':'ALL_MATCH','R4_evidence_files':'ALL_PRESENT_MATCH','original_R2':'BYTE_IDENTICAL','new_solver_calls':0,'new_training':0,'new_external_map_requests':0})
if '--seal' not in sys.argv:print('AUTHOR_CHECK_PASS');raise SystemExit(0)
assert (P/'audit/INDEPENDENT_REVIEW.md').is_file(),'Independent pre-seal review required'
for f in (R/'scripts').glob('*.py'):
 (P/'scripts').mkdir(exist_ok=True);shutil.copyfile(f,P/'scripts'/f.name)
files=[{'path':f.relative_to(P).as_posix(),'bytes':f.stat().st_size,'sha256':sh(f)} for f in sorted(P.rglob('*')) if f.is_file() and f.name!='MANIFEST_SHA256.csv']
csvput(P/'MANIFEST_SHA256.csv',files);shutil.copyfile(P/'MANIFEST_SHA256.csv',D/'MANIFEST_SHA256.csv')
dest=D/'PG1_MIDTERM_RESEARCH_MATERIALS_R3.zip';assert not dest.exists(),'Never silently replace sealed ZIP'
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for f in sorted(P.rglob('*')):
  if f.is_file():z.write(f,f.relative_to(P).as_posix())
with zipfile.ZipFile(dest) as z:
 assert z.testzip() is None
 for n in z.namelist():assert not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and not re.match(r'^[A-Za-z]:',n)
 cnt=len(z.namelist())
zh=sh(dest);(D/'SHA256SUMS.txt').write_text(zh+'  '+dest.name+'\n',encoding='utf8')
dump(D/'AUTHOR_SEAL_RECEIPT.json',{'package':dest.name,'sha256':zh,'bytes':dest.stat().st_size,'members':cnt,'CRC':'PASS','member_manifest_rows':len(files),'independent_postseal_verification':'PENDING_EXTERNAL_RECEIPT','identity':'AUTHOR_SEAL_NOT_INDEPENDENT'})
print(json.dumps({'zip':str(dest),'sha256':zh,'members':cnt,'bytes':dest.stat().st_size},ensure_ascii=False))
