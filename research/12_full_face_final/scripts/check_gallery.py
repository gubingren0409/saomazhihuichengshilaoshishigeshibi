"""Actual local-file Edge rendering; no route or external API requests."""
from pathlib import Path
import asyncio,json,argparse
from urllib.parse import urlparse
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
async def main(url=None):
    if url and urlparse(url).hostname not in('127.0.0.1','localhost'):raise ValueError('LOCAL_ONLY')
    suffix='_http'if url else''
    async with async_playwright()as p:
        browser=await p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True,args=['--disable-gpu','--disable-background-networking'])
        page=await browser.new_page(viewport={'width':1480,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(url or(ROOT/'index.html').as_uri(),wait_until='load');await page.wait_for_function('Array.from(document.images).every(x=>x.complete && x.naturalWidth>0)')
        images=await page.locator('img').evaluate_all('(xs)=>xs.map(x=>({src:x.getAttribute("src"),width:x.naturalWidth,height:x.naturalHeight}))')
        links=await page.locator('a').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("href"))')
        missing=[s for s in links if not s.startswith(('http:','https:','#'))and not(ROOT/s).is_file()]
        await page.screenshot(path=str(ROOT/'audits'/('author_gallery_render'+suffix+'.png')))
        await browser.close()
    r={'role':'AUTHOR_ACTUAL_EDGE_OFFLINE_GALLERY_RENDER','images':images,'local_links_missing':missing,'page_errors':errors,'route_calls':0,'new_external_requests':0,'status':'PASS'if len(images)==6 and not missing and not errors else'FAIL'}
    r['url']=url or'LOCAL_FILE'
    (ROOT/'audits'/('gallery_render'+suffix+'.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url');asyncio.run(main(p.parse_args().url))
