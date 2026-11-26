"""Material integrity and offline reading checks. Never imports a route solver."""
from pathlib import Path, PurePosixPath
import csv, hashlib, json, re, shutil, zipfile
from datetime import datetime
from zoneinfo import ZoneInfo
from html.parser import HTMLParser
from urllib.parse import unquote
from PIL import Image
from playwright.sync_api import sync_playwright

R=Path(__file__).resolve().parents[1];P=R/'package';D=R/'delivery'
def digest(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def put(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
def csvput(p,data):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
events=sorted(x for x in P.iterdir() if x.is_dir() and re.match(r'^\d\d_',x.name))
assert len(events)==12
for e in events:
    for n in ['main_figure.png','metrics.md','metrics.csv','caption_zh.md','story_note_zh.md','source_traceability.md']:assert (e/n).is_file(),str(e/n)
figs=rows(P/'FIGURE_MANIFEST.csv');nums=rows(P/'MASTER_NUMBERS_TABLE.csv');sources=rows(P/'SOURCE_MANIFEST.csv')
for x in sources:assert digest(P/x['package_path'])==x['source_sha256'],x['package_path']
for x in figs:
    assert digest(P/x['output_file'])==x['sha256']
    with Image.open(P/x['output_file']) as im:im.verify()
    assert x['event_id']!='5' or x['suitable_for_main_slide']=='no'
json_checks=[]
for r in nums:
    f=P/r['source_file'];assert digest(f)==r['source_sha256']
    field=r['field'];status='TEXT_REPORT_SOURCE_RETAINED'
    if f.suffix=='.json' and re.fullmatch(r'[a-zA-Z0-9_.\[\]]+',field):
        d=json.loads(f.read_text(encoding='utf8'))
        for token in re.findall(r'[^.\[\]]+',field):d=d[int(token)] if isinstance(d,list) else d[token]
        assert abs(float(d)-float(r['value']))<1e-9,(r['metric'],d,r['value'])
        status='JSON_SCALAR_RECHECK_PASS'
    json_checks.append({'event_id':r['event_id'],'metric':r['metric'],'status':status,'source_sha256':r['source_sha256']})
csvput(P/'audit/NUMBER_SOURCE_RECHECK.csv',json_checks)
# A separate process is an author integrity check, not an independent reviewer.
depcheck=[]
for r in rows(R/'audit/READ_DEPENDENCIES_SHA256.csv'):
    actual=digest(Path(r['path']));assert actual==r['sha256'];depcheck.append({'archive':Path(r['path']).name,'expected_sha256':r['sha256'],'actual_sha256':actual,'status':'UNCHANGED'})
put(P/'audit/OLD_PACKAGE_PROTECTION_CHECK.json',depcheck)
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in ['src','href']:self.links.append(value)
l=Links();l.feed((P/'index.html').read_text(encoding='utf8'))
for link in l.links:
    if link.startswith('#'):continue
    assert not re.match(r'https?://',link),link
    assert (P/unquote(link.split('#')[0])).is_file(),link
for e in events:
    t=(e/'source_traceability.md').read_text(encoding='utf8')
    for link in re.findall(r'\]\(([^)]+)\)',t):assert (e/link).resolve().is_file(),link
put(P/'audit/MATERIAL_INTEGRITY.json',{'identity':'AUTHOR_MATERIAL_CHECK_SEPARATE_PROCESS_NOT_INDEPENDENT_REVIEW','events':12,'main_eligible_events':11,'figures':len(figs),'number_records':len(nums),'source_records':len(sources),'image_decode':'PASS','source_sha256':'PASS','own_html_links':'PASS','own_trace_links':'PASS','event5':'REQUESTED_CAUSAL_NARRATIVE_NOT_VERIFIED','new_solver_calls':0,'new_external_requests':0,'new_independent_reviewer':False})
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
    errors=[];external=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.route(re.compile(r'^https?://'),lambda route:(external.append(route.request.url),route.abort())[1])
    page.goto((P/'index.html').as_uri(),wait_until='load')
    for i in range(1,13):
        page.locator(f'#e{i}').scroll_into_view_if_needed()
        page.locator(f'#e{i} img').first.wait_for()
    page.wait_for_function('Array.from(document.images).every(x=>x.complete&&x.naturalWidth>0)')
    imageinfo=page.locator('img').evaluate_all('(xs)=>xs.map(x=>({file:x.getAttribute("src"),width:x.naturalWidth,height:x.naturalHeight}))')
    page.evaluate('scrollTo(0,0)');page.screenshot(path=str(R/'audit/BROWSER_OVERVIEW.png'))
    page.locator('#e8').scroll_into_view_if_needed();page.screenshot(path=str(R/'audit/BROWSER_NORTH.png'))
    assert not errors and not external
    put(P/'audit/OFFLINE_BROWSER_CHECK.json',{'identity':'AUTHOR_BROWSER_CHECK_NOT_INDEPENDENT_REVIEW','browser':browser.version,'sections':12,'images':imageinfo,'javascript_errors':errors,'external_requests':external,'result':'PASS'})
    browser.close()
# Include only the new packaging/rendering code, not old algorithms or runtime data.
for f in (R/'scripts').glob('*.py'):
    dst=P/'scripts'/f.name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dst)
(P/'scripts/README.md').write_text('这些脚本仅提取、绘图与检查材料，没有调用路由求解器。build_materials.py重建图件需要原固定研究工程；verify_and_package.py的封包步骤也按工作区布局运行。收到材料者直接离线打开index.html即可阅读，无须安装环境或运行脚本。历史算法和全量数据没有重复打包。\n',encoding='utf8')
manifest=[{'path':f.relative_to(P).as_posix(),'bytes':f.stat().st_size,'sha256':digest(f)} for f in sorted(P.rglob('*')) if f.is_file() and f.name!='FILE_SHA256.csv']
csvput(P/'FILE_SHA256.csv',manifest)
target=D/'PG1_MIDTERM_RESEARCH_MATERIALS_R2.zip'
assert not target.exists(),'Do not overwrite an already sealed package'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for f in sorted(P.rglob('*')):
        if f.is_file():z.write(f,f.relative_to(P).as_posix())
zh=digest(target);extract=D/'CLEAN_VERIFY'
assert not extract.exists();extract.mkdir()
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    for n in z.namelist():
        q=PurePosixPath(n);assert not q.is_absolute() and '..' not in q.parts and not re.match(r'^[A-Za-z]:',n)
    z.extractall(extract);member_count=len(z.namelist())
for r in rows(extract/'FILE_SHA256.csv'):assert digest(extract/r['path'])==r['sha256'],r['path']
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1050})
    errors=[];external=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.route(re.compile(r'^https?://'),lambda route:(external.append(route.request.url),route.abort())[1])
    page.goto((extract/'index.html').as_uri(),wait_until='load')
    for i in range(1,13):page.locator(f'#e{i}').scroll_into_view_if_needed()
    page.wait_for_function('Array.from(document.images).every(x=>x.complete&&x.naturalWidth>0)')
    loaded=page.locator('img').count();assert loaded==len(figs) and not errors and not external
    page.evaluate('scrollTo(0,0)');page.screenshot(path=str(D/'CLEAN_READING.png'))
    bv=browser.version;browser.close()
assert digest(target)==zh
receipt={'status':'PASS','identity':'AUTHOR_CLEAN_EXTRACTION_AND_OFFLINE_READING_NOT_INDEPENDENT_REVIEWER','package':target.name,'zip_sha256':zh,'bytes':target.stat().st_size,'members':member_count,'crc':'PASS','path_safety':'PASS','file_sha256_checks':len(manifest),'all_file_hashes':'PASS','clean_offline_chrome':bv,'sections':12,'loaded_images':loaded,'external_requests':external,'js_errors':errors,'new_experiments':0,'new_route_calculations':0,'historical_reports_modified':False,'scientific_limitations':['Event 5 requested north-only causal history is NOT_VERIFIED','Map and conditional route evidence is not field passage proof','Historical independent reviews retained; no new independent role claimed'],'completed_asia_shanghai':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()}
put(D/'MATERIALS_VERIFICATION.json',receipt)
(D/'SHA256SUMS.txt').write_text(f'{zh}  {target.name}\n{digest(D/"MATERIALS_VERIFICATION.json")}  MATERIALS_VERIFICATION.json\n',encoding='utf8')
put(R/'STATUS.json',{'task':'PG1_MIDTERM_RESEARCH_MATERIALS_R2','status':'READY_FOR_GPT_REVIEW','events_prepared':12,'main_figure_eligible_events':11,'event5':'CAUSAL_HISTORY_NOT_VERIFIED','figures':len(figs),'number_records':len(nums),'archive_sha256':zh,'new_experiments':False,'stopped':True})
(R/'CHECKPOINT.md').write_text('材料已封包并在干净目录解包核验；12个事件齐备，事件5保留历史因果证据缺口。新实验与新求路均为0。固定包、包外校验回执在delivery/。停止，等待GPT和用户审核。\n',encoding='utf8')
print(json.dumps(receipt,ensure_ascii=False))
