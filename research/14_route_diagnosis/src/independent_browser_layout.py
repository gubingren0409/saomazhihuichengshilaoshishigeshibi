"""Small actual browser check of retained sidebar horizontal position."""
from pathlib import Path
import json,hashlib
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
def main():
    rows=[]
    with sync_playwright()as p:
        b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':1520,'height':1100});page.route('**/*',lambda r:r.continue_()if r.request.url.startswith('http://127.0.0.1:53451/')else r.abort());page.goto('http://127.0.0.1:53451/');page.wait_for_function('window.R2_VIEW_DATA && document.querySelectorAll(".card").length===4')
        for i in range(4):
            page.locator('.card').nth(i).click();page.locator('#interfaceTable tbody tr').first.click();m=page.locator('aside').evaluate('(e)=>({scrollLeft:e.scrollLeft,clientWidth:e.clientWidth,scrollWidth:e.scrollWidth,rect:e.getBoundingClientRect().toJSON(),titleRect:e.querySelector("h3").getBoundingClientRect().toJSON(),document_scroll_x:window.scrollX,document_scroll_width:document.documentElement.scrollWidth,viewport_width:window.innerWidth})');rows.append({'case':i,**m})
        page.locator('#fit').click();page.locator('.mapgrid').screenshot(path=str(ROOT/'audits/independent_browser/full_layout.png'));b.close()
    result={'reviewer':'/root/r2_independent','HTML_sha256':hashlib.sha256((ROOT/'visuals/index.html').read_bytes()).hexdigest(),'rows':rows,'status':'PASS'if all(r['scrollLeft']==0 and r['document_scroll_x']==0 and r['document_scroll_width']<=r['viewport_width']for r in rows)else'REQUIRES_INSPECTION','scope':'Actual independent browser selected first interface in all four cards; no POST or external requests. Horizontal sidebar and document geometry recorded.'};(ROOT/'audits/independent_browser_layout.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
