"""Actual Edge read-only final gallery rendering and download audit; no POST."""
import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


async def main(url):
    checks, errors, posts, foreign, failures = [], [], [], [], []
    def check(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        print(name + ": " + ("PASS" if passed else "REQUIRES_INSPECTION"), flush=True)
    screenshots = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless=True,
            args=["--disable-gpu", "--disable-extensions", "--disable-background-networking", "--no-first-run", "--renderer-process-limit=1"])
        context = await browser.new_context(viewport={"width": 1500, "height": 1150}, accept_downloads=True)
        page = await context.new_page(); page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: failures.append({"url": response.url, "status": response.status}) if response.status >= 400 else None)
        async def guard(route):
            request = route.request
            if request.method != "GET":
                posts.append({"method": request.method, "url": request.url}); await route.abort(); return
            target = urlparse(request.url)
            if target.scheme in {"http", "https"} and target.netloc != urlparse(url).netloc:
                foreign.append(request.url); await route.abort(); return
            await route.continue_()
        await context.route("**/*", guard)
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            text = await page.locator("body").inner_text()
            check("FINAL_PAGE_HAS_COMPLETE_MATRIX_AND_PENDING_USER_OBSERVATION", "正式运行尚未封存" not in text and "104" in text and "PENDING_USER_OBSERVATION" in text and "SCREENSHOT_REQUEST_UNBOUND" in text, {"title": await page.title(), "body_prefix": text[:1800]})
            images = page.locator("img")
            for i in range(await images.count()):
                await images.nth(i).scroll_into_view_if_needed()
                await images.nth(i).evaluate("image=>image.decode()")
            info = await images.evaluate_all("xs=>xs.map(x=>({src:x.getAttribute('src'),complete:x.complete,width:x.naturalWidth,height:x.naturalHeight,alt:x.alt}))")
            check("ALL_EIGHT_REAL_PNG_IMAGES_DECODED", len(info) == 8 and all(r["complete"] and r["width"] > 500 and r["height"] > 300 for r in info), info)
            check("NO_PENDING_FIGURE_OR_UNAVAILABLE_DATA_PLACEHOLDER", await page.locator(".pending-figure,.unavailable").count() == 0)
            await page.evaluate("window.scrollTo(0,0)"); await page.wait_for_timeout(150)
            path = ROOT / "audits/independent_gallery_header.png"; await page.screenshot(path=str(path)); screenshots.append(str(path.relative_to(ROOT)))
            cards = page.locator("article.case")
            for i in range(min(await cards.count(), 6)):
                card = cards.nth(i)
                await card.scroll_into_view_if_needed()
                path = ROOT / "audits" / ("independent_gallery_case_" + str(i + 1) + ".png")
                await card.screenshot(path=str(path)); screenshots.append(str(path.relative_to(ROOT)))
            await page.locator("#matrix").scroll_into_view_if_needed()
            path = ROOT / "audits/independent_gallery_matrix.png"; await page.screenshot(path=str(path)); screenshots.append(str(path.relative_to(ROOT)))
            # The first inlined small CSV download proves a real browser export,
            # rather than a DOM-only link inventory.
            csv_link = page.locator("a[download$='.csv']").first
            if await csv_link.count():
                async with page.expect_download() as pending:
                    await csv_link.click()
                download = await pending.value
                destination = ROOT / "audits/independent_gallery_download.csv"; await download.save_as(str(destination))
                check("ACTUAL_BROWSER_CSV_DOWNLOAD_NONEMPTY", destination.stat().st_size > 100, {"suggested_filename": download.suggested_filename, "bytes": destination.stat().st_size, "sha256": sha256(destination.read_bytes()).hexdigest()})
            else:
                check("ACTUAL_BROWSER_CSV_DOWNLOAD_NONEMPTY", False, "No embedded CSV download link")
            review_link = page.locator("a[download='independent_review.md']").first
            if await review_link.count():
                async with page.expect_download() as pending:
                    await review_link.click()
                download = await pending.value
                destination = ROOT / "audits/independent_gallery_downloaded_review.md"; await download.save_as(str(destination))
                check("ACTUAL_INDEPENDENT_MD_DOWNLOAD_MATCHES_FROZEN_REVIEW", sha256(destination.read_bytes()).hexdigest() == sha256((ROOT / "audits/independent_review.md").read_bytes()).hexdigest(), {"bytes": destination.stat().st_size, "sha256": sha256(destination.read_bytes()).hexdigest()})
            else:
                check("ACTUAL_INDEPENDENT_MD_DOWNLOAD_MATCHES_FROZEN_REVIEW", False, "No HTTP-safe embedded independent review download")
            check("GET_ONLY_NO_EXTERNAL_REQUEST_OR_BROWSER_ERROR", not posts and not foreign and not errors and not failures,
                {"blocked_non_GET": posts, "blocked_foreign": foreign, "page_errors": errors, "HTTP_failures": failures})
        finally:
            await context.close(); await browser.close()
    result = {"reviewer": "/root/connectivity_review", "scope": "Actual final Edge gallery GET rendering, all eight PNG decodes, case screenshots and a real CSV download; images viewed separately",
        "APP_solver_calls": 0, "POST_attempts": posts, "external_requests_blocked_before_send": foreign,
        "url": url, "served_gallery_file_sha256": sha256((ROOT / "index.html").read_bytes()).hexdigest(),
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(), "checks": checks, "actual_screenshots": screenshots,
        "user_observation": "PENDING_USER_OBSERVATION", "status": "PASS_FOR_FINAL_GALLERY_GET_RENDER_AND_DOWNLOAD_SCOPE" if checks and all(r["passed"] for r in checks) else "REQUIRES_INSPECTION"}
    (ROOT / "audits/independent_gallery_review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": len(checks), "screenshots": len(screenshots), "APP_solver_calls": 0}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--url", required=True)
    asyncio.run(main(parser.parse_args().url))
