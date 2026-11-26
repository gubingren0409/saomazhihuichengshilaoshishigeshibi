"""Run one genuine hosted comparison using the frozen local first scene."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from .geoapify import ATTRIBUTION, STATIC_STYLE, Geoapify, GeoapifyError


ROOT = Path(__file__).resolve().parents[1]
SCENE_ID = "sh-huangpu-01"
IMAGE_DIR = Path("visuals/geoapify")
RUN_PATH = Path("runs/geoapify_first.json")
ATTEMPT_LOCK = Path("runs/geoapify_first_live.lock")
AUDIT_PATH = Path("01_SOURCE_AND_PERMISSION_AUDIT.md")
TERMINAL = {"UPSTREAM_HTTP_401", "UPSTREAM_HTTP_402", "UPSTREAM_HTTP_403", "UPSTREAM_HTTP_429", "UPSTREAM_TRANSPORT_ERROR"}
SOURCE_LINKS = (
    "https://www.geoapify.com/static-maps-api/",
    "https://apidocs.geoapify.com/docs/maps/static/#attribution",
    "https://www.geoapify.com/routing-api/",
    "https://www.geoapify.com/terms-and-conditions/",
)


def _write_status(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _save_file(root, relative, content):
    with (root / relative).open("xb") as file:
        file.write(content)
    return {"path": relative.as_posix(), "sha256": sha256(content).hexdigest(), "bytes": len(content)}


def _contract(root):
    raw = (root / "runs" / "scene_contract.json").read_bytes()
    spec = json.loads(raw)
    if spec.get("scene_id") != SCENE_ID or set(spec.get("views", {})) != {"detail", "context"}:
        raise ValueError("Unexpected or unfrozen first-scene specification")
    if not all(view.get("width") == 1200 and view.get("height") == 900 for view in spec["views"].values()):
        raise ValueError("The first-scene view dimensions do not match the 1200×900 contract")
    return spec, sha256(raw).hexdigest()


def execute(root, *, confirmed_free=False):
    root = Path(root)
    status_path = root / RUN_PATH
    state = {
        "status": "PARTIAL_WITH_EVIDENCE",
        "branch_status": "NOT_RUN",
        "scene_id": SCENE_ID,
        "provider": "Geoapify",
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "new_paid_purchase": False,
        "actual_credits": None,
        "requests": [],
        "view_pair_status": "VIEWPORT_NOT_VERIFIED",
        "route_on_provider_image": "PENDING_VERIFIED_BOUNDS",
        "user_visual_review": "PENDING_USER_REVIEW",
    }
    if (root / ATTEMPT_LOCK).exists():
        raise GeoapifyError("FIRST_LIVE_ATTEMPT_ALREADY_RESERVED")
    try:
        client = Geoapify.from_env(root, confirmed_free=confirmed_free)
        spec, contract_sha = _contract(root)
        audit = (root / AUDIT_PATH).read_bytes()
        if not all(source.encode("ascii") in audit for source in SOURCE_LINKS):
            raise GeoapifyError("PERMISSION_AUDIT_INCOMPLETE")
    except GeoapifyError as error:
        state["branch_status"] = error.code
        _write_status(status_path, state)
        return state
    except (OSError, KeyError, TypeError, AttributeError, ValueError):
        state["branch_status"] = "FIRST_SCENE_OR_PERMISSION_AUDIT_NOT_READY"
        _write_status(status_path, state)
        return state

    state.update(
        scene_contract_sha256=contract_sha,
        permission_audit_sha256=sha256(audit).hexdigest(),
        permission_use="Attribution-preserving static maps and routing geometry",
        source_urls=list(SOURCE_LINKS),
        account_quota="OPERATOR_CONFIRMED_EXISTING_FREE_QUOTA",
    )
    try:
        with (root / ATTEMPT_LOCK).open("x", encoding="utf-8") as lock:
            lock.write(state["started_utc"] + "\n")
    except FileExistsError:
        raise GeoapifyError("FIRST_LIVE_ATTEMPT_ALREADY_RESERVED") from None

    (root / IMAGE_DIR).mkdir(parents=True, exist_ok=True)
    attribution_text = (
        "# Geoapify first scene attribution\n\n"
        "- [© OpenStreetMap contributors](https://www.openstreetmap.org/copyright)\n"
        "- [© OpenMapTiles](https://openmaptiles.org/)\n"
        "- [Powered by Geoapify](https://www.geoapify.com/)\n\n"
        "The service returned the saved PNG bytes. Use the original map credits "
        "and these links in associated displays. Geographic extents are not yet independently verified.\n"
    ).encode("utf-8")
    state["attribution_notice"] = _save_file(root, IMAGE_DIR / "ATTRIBUTION.md", attribution_text)

    requests = [("walk", None), *((name, spec["views"][name]) for name in ("detail", "context"))]
    for name, view in requests:
        entry = {"operation": name, "state": "ATTEMPT_STARTED"}
        state["requests"].append(entry)
        state["branch_status"] = "LIVE_IN_PROGRESS"
        _write_status(status_path, state)
        try:
            if name == "walk":
                result = client.walk_route(spec["start"], spec["target"])
                route = result.data
                geom = route["geojson"]
                file_path = IMAGE_DIR / f"{SCENE_ID}_walk.geojson"
                content = (json.dumps(geom, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                entry["route"] = {k: v for k, v in route.items() if k != "geojson"}
            else:
                result = client.static_map(view["bounds"], width=view["width"], height=view["height"])
                params = result.receipt["parameters"]
                if (params.get("attribution") != "default" or params.get("style") != STATIC_STYLE
                        or result.receipt.get("attribution") != list(ATTRIBUTION)):
                    raise GeoapifyError("ATTRIBUTION_CONTRACT_MISMATCH", result.receipt)
                file_path = IMAGE_DIR / f"{SCENE_ID}_{name}_base.png"
                content = result.data
            entry.update(state="LIVE_SAVED", receipt=result.receipt, asset=_save_file(root, file_path, content))
        except GeoapifyError as error:
            entry.update(state=error.code, receipt=error.receipt)
            if error.code in TERMINAL:
                break
        _write_status(status_path, state)

    saved = sum(request["state"] == "LIVE_SAVED" for request in state["requests"])
    state["branch_status"] = "LIVE_RESULTS_AWAITING_VIEWPORT_QA" if saved == 3 else "LIVE_INCOMPLETE"
    state["saved_asset_count"] = saved
    state["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_status(status_path, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirmed-free", action="store_true",
        help="Confirm an existing Geoapify project with enough free credits and no new charges.",
    )
    args = parser.parse_args()
    try:
        state = execute(ROOT, confirmed_free=args.confirmed_free)
    except GeoapifyError as error:
        print(error.code)
        return 2
    except OSError:
        print("LOCAL_WRITE_ERROR_CHECK_RUN_RECEIPT")
        return 2
    print(state["branch_status"])
    return 0 if state["branch_status"] == "LIVE_RESULTS_AWAITING_VIEWPORT_QA" else 2


if __name__ == "__main__":
    raise SystemExit(main())

