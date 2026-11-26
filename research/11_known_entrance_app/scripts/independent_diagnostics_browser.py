"""Real read-only diagnostic page clicks; never calls /api/plan."""
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    url = json.loads((ROOT / 'runs/service.json').read_text('utf-8'))['url']
    receipt = {'reviewer': '/root/e2e_review', 'url': url + 'diagnostics', 'started_epoch': time.time(),
               'page_errors': [], 'requests': [], 'cases': [], 'tabs': []}
    out = ROOT / 'AUDIT/independent_diagnostics'
    out.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True, args=['--disable-background-networking'])
        context = browser.new_context(viewport={'width': 1500, 'height': 1100})
        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
        page = context.new_page()
        page.on('pageerror', lambda e: receipt['page_errors'].append(str(e)))
        page.on('request', lambda r: receipt['requests'].append({'method': r.method, 'url': r.url}))
        page.goto(url + 'diagnostics', wait_until='networkidle', timeout=90000)
        page.wait_for_function("document.querySelector('#case-select').options.length===7", timeout=30000)
        for index in range(7):
            page.select_option('#case-select', index=index)
            page.click('#show-block')
            row = {'index': index, 'title': page.locator('#diag-title').inner_text(),
                   'status': page.locator('#diag-status').inner_text(),
                   'point_ids': page.locator('#diag-metrics').inner_text(),
                   'component_table': page.locator('#component-table').inner_text(),
                   'block_viewbox': page.locator('#diag-map').get_attribute('viewBox'),
                   'path_count': page.locator('#diag-map path').count()}
            if index == 0:
                # First case T is the last, filled diamond path. Click its
                # painted centre, not label whitespace; S is offscreen after
                # correctly zooming to the blocker. No forced/synthetic click.
                marker = page.locator('#diag-map path').last
                marker.click()
                row['actual_pointer_object_evidence'] = page.locator('#evidence').inner_text()
                page.screenshot(path=str(out / 'failure-01.png'), full_page=True)
            receipt['cases'].append(row)
        for tab in ('grass', 'private', 'road'):
            page.click('#tab-' + tab)
            row = {'tab': tab, 'title': page.locator('#diag-title').inner_text(),
                   'status': page.locator('#diag-status').inner_text(),
                   'note': page.locator('#diag-note').inner_text(),
                   'path_count': page.locator('#diag-map path').count()}
            if tab == 'grass':
                before = page.locator('#diag-map path').last.get_attribute('d')
                page.select_option('#semantic-version', 'S0')
                after = page.locator('#diag-map path').last.get_attribute('d')
                row['s0_s1_focus_geometry_unchanged'] = before == after
                row['s0_evidence'] = page.locator('#evidence').inner_text()
                page.screenshot(path=str(out / 'grass-S0.png'), full_page=True)
                page.select_option('#semantic-version', 'S1')
            page.screenshot(path=str(out / (tab + '.png')), full_page=True)
            receipt['tabs'].append(row)
        receipt['no_plan_request'] = not any('/api/plan' in r['url'] for r in receipt['requests'])
        receipt['ended_epoch'] = time.time()
        browser.close()
    (ROOT / 'AUDIT/independent_diagnostics_browser.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
