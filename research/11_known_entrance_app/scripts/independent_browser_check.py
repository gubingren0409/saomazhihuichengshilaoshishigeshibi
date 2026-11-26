"""Real local browser inspection; optional UI computation is explicitly selected.

Never adds a hidden option or returns a stored answer. Only existing visible
selector options may be selected. The parent task controls fresh request count.
"""
import argparse
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', required=True)
    ap.add_argument('--payload', type=Path)
    ap.add_argument('--compute', action='store_true')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    receipt = {'reviewer': '/root/e2e_review', 'browser': 'Playwright real Microsoft Edge',
               'url': args.url, 'started_at_epoch': time.time(), 'console_errors': [],
               'local_requests': [], 'blocked_nonlocal_requests': [], 'computation_requested': args.compute}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True,
                                    args=['--disable-background-networking', '--disable-component-update'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)

        def only_local(route):
            if route.request.url.startswith(('http://127.0.0.1:', 'http://localhost:', 'data:', 'blob:')):
                route.continue_()
            else:
                receipt['blocked_nonlocal_requests'].append(route.request.url)
                route.abort()

        context.route('**/*', only_local)
        page = context.new_page()
        page.on('pageerror', lambda e: receipt['console_errors'].append(str(e)))
        page.on('request', lambda r: receipt['local_requests'].append({'url': r.url, 'method': r.method,
                                                                     'post_data': r.post_data if '/api/plan' in r.url else None}))
        page.goto(args.url, wait_until='networkidle', timeout=180000)
        page.wait_for_function("document.querySelector('#start').options.length>0", timeout=180000)
        if args.payload:
            body = json.loads(args.payload.read_text(encoding='utf-8-sig'))
            page.select_option('#scene', body['scene_id'])
            page.wait_for_function("document.querySelector('#door').options.length>0 && document.querySelector('#start').options.length>0", timeout=180000)
            page.select_option('#door', body['door_id'])
            page.wait_for_function("document.querySelector('#status').textContent.includes('地图就绪')", timeout=180000)
            choices = page.locator('#start option').evaluate_all('(xs)=>xs.map(x=>x.value)')
            if body['start_id'] not in choices:
                raise ValueError('REGISTERED_PAYLOAD_START_NOT_VISIBLE_IN_UI: ' + body['start_id'])
            page.select_option('#start', body['start_id'])
            page.select_option('#method', body['method'])
            page.select_option('#purpose', body.get('purpose', 'APPROACH_OUTSIDE'))
        receipt['selected_inputs'] = page.evaluate("Object.fromEntries(['scene','door','start','method','purpose'].map(k=>[k,document.getElementById(k).value]))")
        receipt['visible_start_count'] = page.locator('#start option').count()
        receipt['map_path_count_before'] = page.locator('#svg path').count()
        if args.compute:
            with page.expect_response(lambda r: '/api/plan' in r.url and r.request.method == 'POST', timeout=600000) as captured:
                page.click('#compute')
            response = captured.value
            receipt['http_status'] = response.status
            result = response.json()
            receipt['returned_run_id'] = result.get('run_id')
            receipt['returned_request_id'] = result.get('request_id')
            receipt['solver'] = result.get('solver')
            receipt['result_status'] = result.get('status')
            args.output.with_suffix('.response.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            page.wait_for_function("!document.querySelector('#json').disabled", timeout=20000)
            with page.expect_download() as download:
                page.click('#json')
            d = download.value
            export_path = args.output.with_suffix('.export.json')
            d.save_as(export_path)
            exported = json.loads(export_path.read_text('utf-8'))
            receipt['export_request_matches_response'] = exported.get('request_id') == result.get('request_id') and exported.get('run_id') == result.get('run_id')
            with page.expect_download() as geo_download:
                page.click('#geojson')
            geo_path = args.output.with_suffix('.geojson')
            geo_download.value.save_as(geo_path)
            geo = json.loads(geo_path.read_text('utf-8'))
            receipt['geojson_export_matches_actual_route'] = geo == result['route']['geojson']
            receipt['geojson_crs'] = geo.get('crs')
            saved_response = page.request.get(args.url.rstrip('/') + '/api/runs/' + result['run_id'])
            receipt['get_run_status'] = saved_response.status
            receipt['get_run_matches_actual_response'] = saved_response.json() == result
            page.click('#close')
            page.locator('#svg text').filter(has_text='★').first.click()
            receipt['actual_pointer_door_evidence'] = page.locator('#evidence').inner_text()
            page.screenshot(path=str(args.output.with_suffix('.computed-door.png')), full_page=True)
            page.click('#full')
            page.screenshot(path=str(args.output.with_suffix('.computed-full.png')), full_page=True)
            page.select_option('#method', 'F0' if receipt['selected_inputs']['method'] == 'F1' else 'F1')
            receipt['stale_result_cleared_on_input_change'] = page.locator('#json').is_disabled() and '输入已变化' in page.locator('#status').inner_text()
        receipt['status_text'] = page.locator('#status').inner_text()
        receipt['map_path_count_after'] = page.locator('#svg path').count()
        page.click('#close')
        receipt['close_viewbox'] = page.locator('#svg').get_attribute('viewBox')
        page.click('#full')
        receipt['full_viewbox'] = page.locator('#svg').get_attribute('viewBox')
        page.screenshot(path=str(args.output.with_suffix('.png')), full_page=True)
        receipt['screenshot'] = args.output.with_suffix('.png').as_posix()
        receipt['closed_at_epoch'] = time.time()
        browser.close()
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
