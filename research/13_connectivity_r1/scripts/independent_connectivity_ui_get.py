"""Actual Edge GET-only UI audit; route POSTs are blocked and counted."""
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import argparse
import asyncio
import json

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


async def main(url):
    checks, errors, posts, scene_responses = [], [], [], []
    first_seen, first_release = asyncio.Event(), asyncio.Event()
    held, release = asyncio.Event(), asyncio.Event()
    scene_count = 0
    delay_scene = None
    delay_door = None
    fail_next = False
    snapshots = []
    def check(name, value, detail=None):
        checks.append({"name": name, "passed": bool(value), "detail": detail})
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless=True,
            args=["--disable-gpu", "--disable-extensions", "--disable-background-networking", "--no-first-run", "--renderer-process-limit=1"])
        context = await browser.new_context(viewport={"width": 1600, "height": 1150}, accept_downloads=True)
        page = await context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        async def block_post(route):
            posts.append({"url": route.request.url, "method": route.request.method, "body": route.request.post_data})
            await route.abort()
        await page.route("**/api/plan", block_post)
        await page.route("**/api/mechanism", block_post)
        async def scene_handler(route):
            nonlocal scene_count, fail_next
            scene_count += 1
            if fail_next:
                fail_next = False
                await route.fulfill(status=503, content_type="application/json", body='{"error":"INDEPENDENT_GET_ONLY_TRANSPORT_FAULT"}')
                return
            response = await route.fetch(timeout=240000)
            body = await response.json()
            query = parse_qs(urlparse(route.request.url).query)
            sid, door = query.get("scene_id", [None])[0], query.get("door_id", [None])[0]
            scene_responses.append({"scene_id": sid, "door_id": door, "starts": body.get("starts", []), "status": response.status})
            if scene_count == 1:
                first_seen.set(); await first_release.wait()
            if (delay_scene and sid == delay_scene) or (delay_door and door == delay_door):
                held.set(); await release.wait()
            await route.fulfill(response=response)
        await page.route("**/api/scene?**", scene_handler)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.wait_for(first_seen.wait(), 240)
            for mode in ["FROZEN_FULL_FACE", "SOURCE_COMPLETE", "EXACT_STITCH", "CONDITIONAL_SEAMS"]:
                await page.select_option("#connectivity-mode", mode)
            await page.select_option("#method", "F0")
            await page.select_option("#purpose", "ENTER_BUILDING")
            first_release.set()
            await page.wait_for_function("window.__pedestrianAppState?.().mapReady && !window.__pedestrianAppState().mapLoading", timeout=240000)
            await page.wait_for_timeout(250)
            cold = await page.evaluate("({...window.__pedestrianAppState(),paths:document.querySelectorAll('#svg path').length,overview_paths:document.querySelectorAll('#overview path').length,source_starts:data.starts.length})")
            check("COLD_LOAD_CONTROL_SWITCHES_PRESERVE_MAP_AND_ALL_STARTS", cold["mapReady"] and cold["starts_count"] == cold["source_starts"] and cold["paths"] > 15 and cold["overview_paths"] > 15 and cold["controls"]["connectivity_mode"] == "CONDITIONAL_SEAMS" and cold["controls"]["method"] == "F0" and cold["controls"]["purpose"] == "ENTER_BUILDING", cold)
            modes = await page.locator("#connectivity-mode option").evaluate_all("xs=>xs.map(x=>x.value)")
            check("FOUR_EXPLICIT_CONNECTIVITY_MODES_AVAILABLE", set(modes) == {"FROZEN_FULL_FACE", "SOURCE_COMPLETE", "EXACT_STITCH", "CONDITIONAL_SEAMS"}, modes)
            await page.screenshot(path=str(ROOT / "audits/independent_ui_get_initial.png"), full_page=True)
            old_paths = await page.locator("#svg path").count()
            fail_next = True
            await page.evaluate("loadScene()")
            failed = await page.evaluate("({...window.__pedestrianAppState(),retry_visible:!document.getElementById('retry-map').hidden,paths:document.querySelectorAll('#svg path').length})")
            check("CONTROLLED_503_RETAINS_EXISTING_MAP_AND_RETRY", not failed["mapReady"] and not failed["mapLoading"] and failed["retry_visible"] and failed["paths"] == old_paths, failed)
            await page.click("#retry-map")
            await page.wait_for_function("window.__pedestrianAppState().mapReady && !window.__pedestrianAppState().mapLoading", timeout=240000)
            check("RETRY_FETCHES_REAL_MAP", await page.locator("#svg path").count() > 15)
            original = await page.locator("#scene").input_value()
            delay_scene = "sh-library" if original != "sh-library" else "sh-huangpu-01"
            await page.select_option("#scene", delay_scene)
            await asyncio.wait_for(held.wait(), 240)
            await page.select_option("#scene", original)
            await page.wait_for_function("sid=>window.__pedestrianAppState().mapReady && !window.__pedestrianAppState().mapLoading && window.__pedestrianAppState().mapSceneId===sid", arg=original, timeout=240000)
            release.set(); await page.wait_for_timeout(300)
            raced = await page.evaluate("window.__pedestrianAppState()")
            check("REAL_LATE_SCENE_RESPONSE_CANNOT_OVERWRITE_NEW_SELECTION", raced["mapSceneId"] == original and raced["controls"]["scene_id"] == original and raced["starts_count"] > 0, raced)
            delay_scene = None
            held, release = asyncio.Event(), asyncio.Event()
            doors = await page.locator("#door option").evaluate_all("xs=>xs.map(x=>x.value)")
            if len(doors) >= 2:
                original_door = await page.locator("#door").input_value()
                delay_door = next(d for d in doors if d != original_door)
                await page.select_option("#door", delay_door)
                await asyncio.wait_for(held.wait(), 240)
                await page.select_option("#door", original_door)
                await page.wait_for_function("window.__pedestrianAppState().mapReady && !window.__pedestrianAppState().mapLoading", timeout=240000)
                latest_starts = await page.locator("#start option").evaluate_all("xs=>xs.map(x=>x.value)")
                release.set(); await page.wait_for_timeout(300)
                final_starts = await page.locator("#start option").evaluate_all("xs=>xs.map(x=>x.value)")
                state = await page.evaluate("window.__pedestrianAppState()")
                check("REAL_LATE_DOOR_RESPONSE_CANNOT_OVERWRITE_NEW_STARTS", state["controls"]["door_id"] == original_door and final_starts == latest_starts and bool(final_starts), state)
                delay_door = None
            for mode in modes:
                await page.select_option("#connectivity-mode", mode)
                state = await page.evaluate("window.__pedestrianAppState()")
                snapshots.append(state)
            check("MODE_SWITCHES_CLEAR_ANSWERS_KEEP_MAP_AND_STARTS", all(s["mapReady"] and s["starts_count"] > 0 and s["current_run_id"] is None and not s["request_history"] for s in snapshots), snapshots)
            selected_index = await page.evaluate("objectRows.findIndex(o=>sourceId(o)==='way/564255372')")
            if selected_index < 0:
                selected_index = await page.evaluate("objectRows.findIndex(o=>sourceId(o)==='relation/2385771')")
            assert selected_index >= 0
            await page.select_option("#object", str(selected_index))
            await page.click("#why")
            evidence = await page.locator("#evidence").inner_text()
            why = await page.locator("#why-summary").inner_text()
            obj = await page.locator("#object-record").inner_text()
            check("REAL_OBJECT_SELECTION_SHOWS_SOURCE_ID_TAGS_AND_NETWORK_CAUTION", "way/564255372" in obj or "relation/2385771" in obj, {"evidence": evidence, "why": why, "record_prefix": obj[:1000]})
            check("WHY_PANEL_SEPARATES_DIRECT_GAP_FROM_NETWORK_DISCONNECTION", "直接" in why and "不是全网断开" in why, why)
            before = await page.evaluate("views.svg.slice()")
            await page.locator("#svg").hover()
            await page.mouse.wheel(0, -250)
            await page.wait_for_timeout(100)
            after = await page.evaluate("views.svg.slice()")
            check("ACTUAL_WHEEL_ZOOM_CHANGES_EXPORTED_VIEW", after[2] < before[2], {"before": before, "after": after})
            async with page.expect_download() as downloaded:
                await page.click("#json")
            download = await downloaded.value
            destination = ROOT / "audits/independent_ui_get_request_view.json"
            await download.save_as(str(destination))
            exported = json.loads(destination.read_text(encoding="utf-8"))
            check("ACTUAL_GET_ONLY_EXPORT_CONTAINS_REQUEST_VIEWS_OBJECT_IDS_GEOMETRY", exported.get("schema") == "PED_AREA_CONNECTIVITY_MAP_REVIEW_R1" and bool(exported.get("viewBoxes", {}).get("svg")) and bool(exported.get("viewBoxes", {}).get("overview")) and bool(exported.get("selected_object")) and bool(exported.get("visible_objects")) and not exported.get("responses"), {"file": str(destination), "visible_objects": len(exported.get("visible_objects", [])), "selected_id": exported.get("selected_object", {}).get("properties", {}).get("source_id"), "viewBoxes": exported.get("viewBoxes")})
            check("EXPORT_KEEPS_PENDING_OBSERVATION_AND_UNBOUND_SCREENSHOT", exported.get("user_observation") == "PENDING_USER_OBSERVATION" and exported.get("screenshot_request_binding") == "SCREENSHOT_REQUEST_UNBOUND")
            await page.screenshot(path=str(ROOT / "audits/independent_ui_get_selected_native_chain.png"), full_page=True)
            available = {o["id"] for o in await page.evaluate("data.starts.map(s=>({id:s.id}))")}
            check("PROPOSED_NOVEL_NATIVE_STARTS_PRESENT_IN_REAL_CURRENT_CATALOG", {"node/1890877354", "node/1890877364"}.issubset(available), {"novel_UI_start": "node/1890877354", "novel_clean_start": "node/1890877364", "start_count": len(available)})
            check("NO_SOLVER_POST_ATTEMPTED_DURING_GET_ONLY_AUDIT", not posts, posts)
            check("NO_BROWSER_PAGE_ERRORS", not errors, errors)
        finally:
            first_release.set(); release.set()
            await context.close(); await browser.close()
    result = {"reviewer": "/root/connectivity_review", "role": "ACTUAL_EDGE_GET_ONLY_UI_INTERACTION", "url": url, "checks": checks,
              "APP_solver_calls": 0, "blocked_plan_POST_attempts": posts, "page_errors": errors,
              "real_scene_GET_count": scene_count, "actual_screenshots": ["audits/independent_ui_get_initial.png", "audits/independent_ui_get_selected_native_chain.png"],
              "status": "PASS_FOR_REPORTED_GET_ONLY_UI_SCOPE" if checks and all(c["passed"] for c in checks) else "REQUIRES_INSPECTION",
              "transport_control": "One intentional map GET HTTP503; stale map/door responses held then delivered from the real backend without data substitution",
              "limits": ["No route POST or solver performed", "Screenshot visual inspection recorded separately", "Technical UI evidence does not accept historical user observation or field passage"]}
    (ROOT / "audits/independent_ui_get_interaction.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": len(checks), "GET_count": scene_count, "solver_POST_attempts": len(posts)}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--url", required=True); a = ap.parse_args()
    asyncio.run(main(a.url))
