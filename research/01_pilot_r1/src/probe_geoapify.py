"""One explicitly authorized, journaled Geoapify walking probe for the frozen case."""
import argparse
from hashlib import sha256
from ipaddress import ip_address
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener, getproxies, proxy_bypass

from .geoapify import Geoapify, GeoapifyError, NoRedirect, read_api_key

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "runs/geoapify_walk_probe.json"
LIMIT_HEADER = re.compile(
    r"(?:x-)?(?:rate-?limit|quota|credits?|geoapify-credits?)(?:-[a-z]{1,20}){0,4}|retry-after"
)


class SingleRequest:
    def __init__(self, proxy=None):
        self.opener = build_opener(ProxyHandler({"https": proxy} if proxy else {}), NoRedirect())
        self.attempts = 0
        self.names = []
        self.numeric = {}

    def _quota_metadata(self, headers):
        for key in headers.keys():
            name = key.lower()
            if LIMIT_HEADER.fullmatch(name):
                self.names.append(name)
                value = headers.get(key, "").strip()
                if re.fullmatch(r"[0-9]{1,10}", value):
                    self.numeric[name] = int(value)

    def open(self, request, *, timeout):
        if self.attempts:
            raise RuntimeError("SINGLE_PROBE_LIMIT")
        self.attempts += 1
        try:
            result = self.opener.open(request, timeout=timeout)
        except HTTPError as error:
            self._quota_metadata(error.headers)
            raise
        self._quota_metadata(result.headers)
        return result


def eligible_local_proxy():
    first = json.loads(RECEIPT.read_text(encoding="utf-8"))
    if first["status"] != "UPSTREAM_TRANSPORT_ERROR" or first["receipt"]["status_code"] is not None:
        raise RuntimeError("PROXY_RETRY_REQUIRES_PRIOR_TRANSPORT_FAILURE")
    proxy = getproxies().get("https", "")
    if not proxy or proxy_bypass("api.geoapify.com"):
        raise RuntimeError("NO_ELIGIBLE_LOCAL_PROXY")
    parsed = urlsplit(proxy if "://" in proxy else "http://" + proxy)
    if parsed.scheme != "http" or parsed.username or parsed.password or not parsed.hostname:
        raise RuntimeError("NO_ELIGIBLE_LOCAL_PROXY")
    if parsed.hostname != "localhost" and not ip_address(parsed.hostname).is_loopback:
        raise RuntimeError("NO_ELIGIBLE_LOCAL_PROXY")
    return proxy


def run(use_existing_proxy=False):
    receipt_path = RECEIPT.with_name("geoapify_walk_probe_proxy.json") if use_existing_proxy else RECEIPT
    proxy = eligible_local_proxy() if use_existing_proxy else None
    scene_path = ROOT / "runs/scene_contract.json"
    contract = scene_path.read_bytes()
    scene = json.loads(contract)
    if scene["scene_id"] != "sh-huangpu-01" or scene.get("frozen_before_route") is not True:
        raise RuntimeError("FROZEN_FIRST_SCENE_REQUIRED")
    ledger = SingleRequest(proxy)
    client = Geoapify(read_api_key(ROOT), confirmed_free=True, opener=ledger)
    asset = ROOT / "visuals/geoapify/sh-huangpu-01_probe_walk.geojson"
    if asset.exists():
        raise RuntimeError("PRIOR_PROBE_ASSET_PRESENT")
    state = {"scene_id": scene["scene_id"], "authorization": "USER_AUTHORIZED_SINGLE_ROUTING_PROBE",
             "project_free_quota": "NOT_INDEPENDENTLY_VERIFIED", "scope": "ONE_ROUTE_REQUEST_NO_UPGRADE",
             "scene_contract_sha256": sha256(contract).hexdigest(), "status": "RESERVED",
             "transport": "EXISTING_LOCAL_HTTPS_PROXY" if proxy else "DIRECT"}
    with receipt_path.open("x", encoding="utf-8") as out:
        json.dump(state, out, indent=2)
    try:
        result = client.walk_route(scene["start"], scene["target"])
    except GeoapifyError as error:
        state.update(status=error.code, receipt=error.receipt)
    else:
        line = result.data["geojson"]
        line["attribution"] = result.data["attribution"]
        data = (json.dumps(line, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        asset.parent.mkdir(parents=True, exist_ok=True)
        with asset.open("xb") as out:
            out.write(data)
        state.update(status="LIVE_ROUTE_RETURNED", receipt=result.receipt,
                     route={k: v for k, v in result.data.items() if k != "geojson"},
                     geojson={"path": asset.relative_to(ROOT).as_posix(), "sha256": sha256(data).hexdigest()})
    state.update(requests_attempted=ledger.attempts, quota_headers_seen=sorted(set(ledger.names)),
                 quota_numeric_headers=ledger.numeric, static_map_requests=0)
    temp = receipt_path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(receipt_path)
    output = {k: state[k] for k in ("status", "requests_attempted", "quota_headers_seen", "quota_numeric_headers")}
    output["http_status"] = state.get("receipt", {}).get("status_code")
    if "route" in state:
        output.update({k:state["route"][k] for k in ("provider_distance_m", "provider_duration_s",
                                                   "start_offset_m", "target_offset_m")})
    print(json.dumps(output))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--existing-local-proxy", action="store_true",
                     help="retry once after a recorded direct transport failure through the existing local proxy")
    options = cli.parse_args()
    try:
        run(options.existing_local_proxy)
    except GeoapifyError as error:
        print(error.code)
        sys.exit(2)
    except (OSError, KeyError, ValueError, RuntimeError):
        print("PROBE_NOT_COMPLETED_CHECK_REDACTED_RECEIPT")
        sys.exit(2)
