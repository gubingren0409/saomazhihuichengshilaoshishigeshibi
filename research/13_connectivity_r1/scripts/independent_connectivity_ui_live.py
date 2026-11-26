"""Six predeclared actual Edge requests, only after root formal completion.

No routing fields are selected from saved answers. Unexpected POSTs are blocked.
Transport holds deliver the real server response unchanged.
"""
import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import time
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
OUT = ROOT / "audits/independent_ui_live"


async def main(url):
    plan_path = ROOT / "audits/independent_live_request_plan.json"
    assert sha256(plan_path.read_bytes()).hexdigest() == "52a669476e23600e712f596ade9084d615e371737ab394ff8daa81dac8f1de97"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if OUT.exists():
        assert OUT.is_dir() and not any(OUT.iterdir()), "Existing live evidence may not be overwritten or rerun"
    else:
        OUT.mkdir(exist_ok=False)
    checks, errors, requests, forbidden = [], [], [], []
    active = set(); late_held, late_release = asyncio.Event(), asyncio.Event()
    cases = {row["case_id"]: row for row in plan["ui_calls"]}
    result = {"reviewer": "/root/connectivity_review", "role": "ACTUAL_EDGE_SIX_PREDECLARED_LIVE_REQUESTS",
        "url": url, "physical_evidence_directory": str(OUT.resolve()), "request_plan_sha256": sha256(plan_path.read_bytes()).hexdigest(),
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(), "checks": checks,
        "requests": requests, "forbidden_POSTs": forbidden, "page_errors": errors,
        "user_observation": "PENDING_USER_OBSERVATION", "external_map_API_requests": 0,
        "APP_solver_calls": 0, "status": "IN_PROGRESS"}
    addendum = ROOT / "audits/independent_execution_schedule_addendum.json"
    if addendum.exists():
        result["execution_schedule_addendum"] = {"path": str(addendum.relative_to(ROOT)), "sha256": sha256(addendum.read_bytes()).hexdigest(), "record": json.loads(addendum.read_text(encoding="utf-8"))}

    def save():
        result["actual_route_POST_attempts"] = len(requests)
        result["unreceived_attempts_with_unknown_solver_status"] = [r["case_id"] for r in requests if not r.get("received")]
        (ROOT / "audits/independent_ui_live_review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    def check(name, value, detail=None):
        checks.append({"name": name, "passed": bool(value), "detail": detail})
        print(name + ": " + ("PASS" if value else "REQUIRES_INSPECTION"), flush=True)
        save()

    async def ready(page):
        await page.wait_for_function("window.__pedestrianAppState?.().mapReady && !window.__pedestrianAppState().mapLoading", timeout=240000)

    async def idle(page):
        await page.wait_for_function("window.__pedestrianAppState?.().mapReady && !window.__pedestrianAppState().planning", timeout=2400000)

    async def select(page, case):
        if await page.locator("#scene").input_value() != plan["fixed_fields"]["scene_id"]:
            await page.select_option("#scene", plan["fixed_fields"]["scene_id"]); await ready(page)
        if await page.locator("#door").input_value() != plan["fixed_fields"]["door_id"]:
            await page.select_option("#door", plan["fixed_fields"]["door_id"]); await ready(page)
        for field, key in [("start", "start_id"), ("method", "method"), ("connectivity-mode", "connectivity_mode")]:
            await page.select_option("#" + field, case[key])
        await page.select_option("#purpose", plan["fixed_fields"]["purpose"])
        current = await page.evaluate("controls()")
        expected = {**plan["fixed_fields"], **{k: case[k] for k in ("start_id", "method", "connectivity_mode")}}
        assert current == expected, (current, expected)

    async def export(page, stem):
        async with page.expect_download() as pending:
            await page.click("#json")
        download = await pending.value
        path = OUT / (stem + "-request-view.json"); await download.save_as(str(path))
        return json.loads(path.read_text(encoding="utf-8"))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=EDGE, headless=True,
            args=["--disable-gpu", "--disable-extensions", "--disable-background-networking", "--no-first-run", "--renderer-process-limit=1"])
        context = await browser.new_context(viewport={"width": 1600, "height": 1150}, accept_downloads=True)
        health_response = await context.request.get(url.rstrip("/") + "/api/health")
        health = await health_response.json()
        app_response = await context.request.get(url.rstrip("/") + "/app.js")
        served_app_sha = sha256(await app_response.body()).hexdigest()
        state = json.loads((ROOT / "runs/service.json").read_text(encoding="utf-8"))
        freeze = json.loads((ROOT / "audits/backend_freeze_r2.json").read_text(encoding="utf-8"))
        check("ACTUAL_CURRENT_SERVICE_AND_SERVED_APP_IDENTITY", health_response.ok and health.get("service") == "PED_AREA_CONNECTIVITY_R1" and health.get("pid") == state["pid"] and health.get("pid") not in {244836, 178908} and served_app_sha == sha256((ROOT / "app/app.js").read_bytes()).hexdigest(), {"health": health, "served_app_js_sha256": served_app_sha, "backend_freeze_code_sha256": freeze["code_sha256"]})
        assert checks[-1]["passed"], "Current service or APP identity mismatch; no POST permitted"
        async def route_post(route):
            body = json.loads(route.request.post_data or "{}")
            matches = [ident for ident in active if all(body.get(k) == value for k, value in
                {**plan["fixed_fields"], **{k: cases[ident][k] for k in ("start_id", "method", "connectivity_mode")}}.items())
                and not any(r["case_id"] == ident for r in requests)]
            if route.request.method != "POST" or len(matches) != 1 or set(body) != set(plan["fixed_fields"]) | {"start_id", "method", "connectivity_mode", "request_id"} or not str(body.get("request_id", "")).startswith("UI-"):
                forbidden.append({"url": route.request.url, "request": body, "active_cases": sorted(active)})
                save(); await route.abort(); return
            case_id = matches[0]
            receipt = {"case_id": case_id, "request": body, "submitted_monotonic": time.monotonic(), "received": False}
            requests.append(receipt); save(); print("ACTUAL_POST " + case_id, flush=True)
            response = await route.fetch(timeout=1200000)
            raw = await response.body(); answer = json.loads(raw)
            path = OUT / (case_id + "-response.json"); path.write_bytes(raw)
            receipt.update(received=True, http_status=response.status, response_path=str(path.relative_to(ROOT)),
                response_sha256=sha256(raw).hexdigest(), run_id=answer.get("run_id"),
                solver=answer.get("solver"), graph=answer.get("graph"), versions=answer.get("versions"),
                status=answer.get("status"), route_answer_cache=answer.get("route_answer_cache"),
                received_monotonic=time.monotonic())
            result["APP_solver_calls"] = sum(bool(r.get("solver", {}).get("invoked")) for r in requests)
            save(); print("ACTUAL_RESPONSE " + case_id + " " + str(answer.get("status")), flush=True)
            if case_id == "INDEPENDENT_UI_LATE_B2":
                late_held.set(); await late_release.wait()
            await route.fulfill(response=response, body=raw)

        async def block_mechanism(route):
            forbidden.append({"url": route.request.url, "request": route.request.post_data}); save(); await route.abort()
        await context.route("**/api/plan", route_post)
        await context.route("**/api/mechanism", block_mechanism)
        page = await context.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000); await ready(page)
            await select(page, cases["INDEPENDENT_UI_COMPARE_B3"])
            active = {"INDEPENDENT_UI_COMPARE_B0", "INDEPENDENT_UI_COMPARE_B3"}
            await page.click("#compare"); await idle(page)
            state = await page.evaluate("window.__pedestrianAppState()")
            compare_ids = [r["run_id"] for r in requests if r["case_id"] in active]
            check("REAL_COMPARE_TWO_RESPONSES_AND_SEPARATE_RUNS", len(compare_ids) == 2 and len(set(compare_ids)) == 2 and state["comparison_run_ids"] == compare_ids, state)
            chosen = await page.evaluate("objectRows.findIndex(o=>sourceId(o)==='way/564255372')")
            assert chosen >= 0; await page.select_option("#object", str(chosen))
            await page.locator("#svg").hover(); await page.mouse.wheel(0, -200); await page.wait_for_timeout(150)
            exported = await export(page, "compare")
            check("COMPARE_EXPORT_BINDS_REQUESTS_RESPONSES_VIEWS_OBJECT_SOURCE_GEOMETRY", exported["run_ids"] == compare_ids and len(exported["requests"]) == 2 and len(exported["responses"]) == 2 and bool(exported["visible_objects"]) and bool(exported["viewBoxes"].get("svg")) and exported["selected_object"]["properties"]["source_id"] == "way/564255372", {"run_ids": exported["run_ids"], "visible_objects": len(exported["visible_objects"]), "selected": exported["selected_object"]["properties"]})
            if not await page.locator("#geojson").is_disabled():
                async with page.expect_download() as pending:
                    await page.click("#geojson")
                download = await pending.value; await download.save_as(str(OUT / "compare-routes.geojson"))
                geo = json.loads((OUT / "compare-routes.geojson").read_text(encoding="utf-8"))
                check("ACTUAL_ROUTE_GEOJSON_EXPORT_BINDS_BOTH_RUNS", geo["run_ids"] == compare_ids and bool(geo["features"]), {"features": len(geo["features"]), "run_ids": geo["run_ids"]})
            await page.screenshot(path=str(OUT / "compare-actual-edge.png"), full_page=True)
            dynamic_index = await page.evaluate("objectRows.findIndex(o=>o.kind==='seam'&&o.properties?.accepted)")
            if dynamic_index >= 0:
                await page.select_option("#object", str(dynamic_index))
            else:
                await page.click("#full")
                await page.locator("#svg path[stroke='#17699c'],#svg path[stroke='#11806e'],#svg path[stroke='#d56425'],#svg path[stroke='#dc654b']").last.click(force=True)
            dynamic_selection = await page.evaluate("exportState().selected_object")
            check("ACTUAL_COMPUTED_SEAM_OR_ROUTE_SELECTED_BEFORE_STALE_TEST", bool(dynamic_selection), dynamic_selection)
            await page.screenshot(path=str(OUT / "selected-actual-computed-object.png"), full_page=True)
            # Each input invalidates displayed answers while preserving the loaded map.
            snapshots = []
            for field, value in [("method", "F1"), ("purpose", "ENTER_BUILDING"), ("connectivity-mode", "SOURCE_COMPLETE"), ("start", "node/1890877354")]:
                await page.select_option("#" + field, value)
                snapshots.append(await page.evaluate("({...window.__pedestrianAppState(),selected_object:exportState().selected_object,object_record:document.getElementById('object-record').textContent})"))
            check("ALL_ROUTING_CONTROL_SWITCHES_CLEAR_DISPLAY_AND_TRANSIENT_OBJECT_KEEP_MAP_STARTS", all(s["current_run_id"] is None and not s["comparison_run_ids"] and s["selected_object"] is None and not s["object_record"] and s["mapReady"] and s["starts_count"] > 0 for s in snapshots), snapshots)
            stale_export = await export(page, "controls-changed-no-stale-object")
            check("STALE_EXPORT_CANNOT_RETAIN_PREVIOUS_ROUTE_SEAM_OR_RESPONSE", not stale_export["selected_object"] and not stale_export["responses"] and not stale_export["run_ids"] and not stale_export["route_geometry"]["features"], {"selected_object": stale_export["selected_object"], "run_ids": stale_export["run_ids"]})

            active = {"INDEPENDENT_UI_NOVEL_B1"}; await select(page, cases[next(iter(active))])
            await page.click("#compute"); await idle(page)
            novel = await page.evaluate("window.__pedestrianAppState()")
            row = next(r for r in requests if r["case_id"] in active)
            check("NOVEL_ORIGINAL_NATIVE_START_ACTUAL_BUTTON_DISPLAYS_ITS_REAL_RUN", novel["current_run_id"] == row["run_id"] and bool(row.get("solver", {}).get("invoked")), novel)
            await export(page, "novel-source-complete")

            active = {"INDEPENDENT_UI_LATE_B2"}; await select(page, cases[next(iter(active))])
            await page.click("#compute"); await asyncio.wait_for(late_held.wait(), 1200)
            # Controls change only after the actual server has produced the held response.
            alternate_scene = await page.locator("#scene option").evaluate_all("xs=>xs.map(x=>x.value).find(x=>x!=='sh-huangpu-01')")
            await page.select_option("#scene", alternate_scene); await ready(page)
            await page.select_option("#scene", "sh-huangpu-01"); await ready(page)
            other_door = await page.locator("#door option").evaluate_all("xs=>xs.map(x=>x.value).find(x=>x!=='node/6897145227')")
            assert other_door
            await page.select_option("#door", other_door); await ready(page)
            await page.select_option("#door", "node/6897145227"); await ready(page)
            for field, value in [("purpose", "ENTER_BUILDING"), ("method", "F0"), ("connectivity-mode", "SOURCE_COMPLETE"), ("start", "node/10073042336")]:
                await page.select_option("#" + field, value)
            before_release = await page.evaluate("window.__pedestrianAppState()")
            late_release.set(); await idle(page)
            late = await page.evaluate("window.__pedestrianAppState()")
            receipt = next((r for r in late["request_history"] if r["run_id"] == next(x["run_id"] for x in requests if x["case_id"] == "INDEPENDENT_UI_LATE_B2")), {})
            check("REAL_LATE_RESPONSE_ISOLATED_AFTER_SCENE_DOOR_PURPOSE_METHOD_MODE_START_CHANGES", late["current_run_id"] is None and late["mapReady"] and late["controls"] == before_release["controls"] and not receipt.get("displayed") and receipt.get("ignored_reason") == "INPUT_CHANGED_DURING_REQUEST", {"before_release": before_release, "after_release": late})
            await export(page, "late-response-ignored")
            await page.screenshot(path=str(OUT / "late-response-isolated.png"), full_page=True)

            second = await context.new_page(); second.on("pageerror", lambda e: errors.append(str(e)))
            await second.goto(url, wait_until="domcontentloaded", timeout=60000); await ready(second)
            await select(page, cases["INDEPENDENT_UI_PARALLEL_F0"])
            await select(second, cases["INDEPENDENT_UI_PARALLEL_F1"])
            active = {"INDEPENDENT_UI_PARALLEL_F0", "INDEPENDENT_UI_PARALLEL_F1"}
            await asyncio.gather(page.click("#compute"), second.click("#compute"))
            await asyncio.gather(idle(page), idle(second))
            pair = [r for r in requests if r["case_id"] in active]
            states = await asyncio.gather(page.evaluate("window.__pedestrianAppState()"), second.evaluate("window.__pedestrianAppState()"))
            graph_ids = [(r.get("graph") or {}).get("unweighted_sha256", (r.get("versions") or {}).get("unweighted_graph_sha256")) for r in pair]
            check("PARALLEL_F0_F1_DISTINCT_RUN_SOLVERS_SAME_UNWEIGHTED_GRAPH", len(pair) == 2 and graph_ids[0] and graph_ids[0] == graph_ids[1] and len({r["run_id"] for r in pair}) == 2 and len({r["solver"].get("invocation_id") for r in pair}) == 2 and max(r["submitted_monotonic"] for r in pair) < min(r["received_monotonic"] for r in pair), {"pair": pair, "states": states})
            await export(page, "parallel-F0"); await export(second, "parallel-F1")
            await page.screenshot(path=str(OUT / "parallel-F0-actual-edge.png"), full_page=True)
            await second.screenshot(path=str(OUT / "parallel-F1-actual-edge.png"), full_page=True)
            check("EXACT_SIX_DECLARED_POSTS_ALL_REAL_SOLVERS_NO_ANSWER_CACHE", len(requests) == 6 and not forbidden and result["APP_solver_calls"] == 6 and all(r["received"] and r["route_answer_cache"] == {"enabled": False, "hit": False} for r in requests), {"actual_POSTs": len(requests), "APP_solver_calls": result["APP_solver_calls"]})
            check("NO_BROWSER_PAGE_ERRORS", not errors, errors)
            result["status"] = "PASS_FOR_REPORTED_ACTUAL_EDGE_LIVE_SCOPE" if all(c["passed"] for c in checks) else "REQUIRES_INSPECTION"
        except Exception as error:
            result["status"] = "INTERRUPTED_REQUIRES_INSPECTION"
            result["exception"] = repr(error)
            raise
        finally:
            late_release.set(); save()
            await context.close(); await browser.close()
    print(json.dumps({"status": result["status"], "APP_solver_calls": result["APP_solver_calls"], "POSTs": len(requests), "checks": len(checks)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--url", required=True)
    args = parser.parse_args(); asyncio.run(main(args.url))
