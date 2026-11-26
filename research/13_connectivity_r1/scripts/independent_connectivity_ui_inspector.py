"""Actual Edge regression for raw line source identity, no route requests."""
from hashlib import sha256
from pathlib import Path
import argparse
import asyncio
import json
import time

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


async def main(url):
    checks, posts, errors, served = [], [], [], {}
    started = time.perf_counter()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless=True,
            args=["--disable-gpu", "--disable-extensions", "--disable-background-networking", "--no-first-run", "--renderer-process-limit=1"])
        context = await browser.new_context(viewport={"width": 1600, "height": 1150}, accept_downloads=True)
        page = await context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        async def response(r):
            if r.url.endswith("/app.js"):
                served["app_js_sha256"] = sha256(await r.body()).hexdigest()
        page.on("response", response)
        async def block(route):
            posts.append(route.request.url); await route.abort()
        await page.route("**/api/plan", block)
        await page.route("**/api/mechanism", block)
        print("Edge launched; loading actual source view only", flush=True)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_function("window.__pedestrianAppState?.().mapReady && !window.__pedestrianAppState().mapLoading", timeout=240000)
            print("Actual source view ready", flush=True)
            for ident, expected in [("way/564255372", "原生线源几何"), ("way/178725446", "原始地图线几何")]:
                index = await page.evaluate("ident=>objectRows.findIndex(o=>sourceId(o)===ident)", ident)
                assert index >= 0
                await page.select_option("#object", str(index))
                text = await page.locator("#evidence").inner_text()
                raw_json = await page.locator("#object-record").text_content()
                obj = json.loads(raw_json)
                length_line = next(x for x in text.splitlines() if x.startswith("本段 "))
                checks.append({"source_id": ident, "passed": expected in length_line and "条件假设" not in length_line and obj["object"]["properties"]["source_id"] == ident,
                               "length_line": length_line, "inspector_text": text, "raw_machine_record_source_id": obj["object"]["properties"]["source_id"]})
            index = await page.evaluate("objectRows.findIndex(o=>sourceId(o)==='way/564255372')")
            await page.select_option("#object", str(index))
            await page.click("#why")
            await page.screenshot(path=str(ROOT / "audits/independent_ui_inspector_fixed.png"), full_page=True)
            async with page.expect_download() as info:
                await page.click("#json")
            download = await info.value
            await download.save_as(str(ROOT / "audits/independent_ui_inspector_fixed_request_view.json"))
        finally:
            await context.close(); await browser.close()
    result = {"reviewer": "/root/connectivity_review", "scope": "Actual Edge regression of raw eligible and restricted source-line inspector after UI-only repair; previous GET race/loader checks unaffected",
              "served_app": served, "checks": checks, "APP_solver_calls": 0, "blocked_plan_POST_attempts": posts, "page_errors": errors,
              "elapsed_s": time.perf_counter() - started, "status": "PASS_FOR_RAW_SOURCE_INSPECTOR_REGRESSION" if all(r["passed"] for r in checks) and not posts and not errors else "REQUIRES_INSPECTION",
              "reviewer_read_method_correction": "Closed details hides inner_text; text_content independently reads the actual existing JSON without opening/replacing it. Original GET checker alarm retained.",
              "limits": ["No route POST or solver", "No user or field acceptance"]}
    (ROOT / "audits/independent_ui_inspector_regression.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "served_app": served, "elapsed_s": result["elapsed_s"]}, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--url", required=True); a = p.parse_args()
    asyncio.run(main(a.url))
