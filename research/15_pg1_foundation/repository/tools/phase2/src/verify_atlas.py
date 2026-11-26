"""Offline browser/geometry rendering check. Requires Playwright and local Edge.
No browser download or HTTP server is used. Screenshots contain review data.
"""
import argparse, json, pathlib
from playwright.sync_api import sync_playwright

def run(root):
    root=pathlib.Path(root).resolve(); output=root/'visual_check';output.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport=dict(width=1400,height=1100),device_scale_factor=1)
        page.goto((root/'index.html').as_uri());page.wait_for_load_state('load')
        sections=page.locator('section');checks=[]
        for i in range(sections.count()):
            section=sections.nth(i);ident=section.get_attribute('id')
            section.screenshot(path=str(output/f'{ident}.png'))
            paths=section.locator('svg path').count()
            check=dict(scene_id=ident,svg_paths=paths,metadata_only='METADATA EXTENT ONLY' in section.inner_text(),screenshot=f'visual_check/{ident}.png')
            first=section.locator('input').first
            first.uncheck();check['toggle_hides_layer']=section.locator('g[style*="display: none"]').count()>0 or check['metadata_only']
            first.check();checks.append(check)
        browser.close()
    (root/'visual_check_receipt.json').write_text(json.dumps(dict(browser='local Edge via Playwright; offline file URI',author_check_only=True,checks=checks),indent=2),encoding='utf-8')
    print(json.dumps(checks))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=pathlib.Path);run(p.parse_args().root)
