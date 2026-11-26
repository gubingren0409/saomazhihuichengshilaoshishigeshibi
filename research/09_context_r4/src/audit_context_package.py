"""Audit the sealed review independently of its builder and replay runner."""
import argparse
from hashlib import file_digest
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import stat
from zipfile import ZipFile

from .context_audit_common import ROOT, require, write

FROZEN = "input_contract/frozen/WALKABILITY_R3_OPEN_REVIEW.zip"
FROZEN_SHA256 = "d623af231c6eabeace1d3c8e284787a51b7d83782c6c8f7990d16b27f5c0cd0e"
EXPECTED = {
    "README.md", "STATUS.json", "RESULTS.md", "SCOPE_AND_METHOD.md", "USER_REVIEW_NOTES.md",
    "runs/context_metrics.json", "runs/context_metrics.csv", "data/task_manifest.json",
    "audits/INDEPENDENT_REVIEW.md", "audits/context_input_audit.json", "audits/context_isolation_probe.json",
    "audits/context_feature_spatial.json", "audits/context_north_independent.json",
    "audits/context_visual_geometry.json", "audits/context_browser_check.json", "visuals/index.html",
    "scripts/replay_context.py", "src/audit_context_package.py", FROZEN,
}
WINDOWS_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"{s}{n}" for s in ("COM", "LPT") for n in range(1, 10))}
PRIVATE_NAMES = {".env", ".git", "login data", "cookies", "credentials.json", "local state", "__pycache__"}


def safe(info):
    name = info.filename
    path = PurePosixPath(name)
    return bool(path.parts) and path.as_posix() == name and not path.is_absolute() and all(
        part not in (".", "..") and part == part.rstrip(" .")
        and not re.search(r'[:\\<>"|?*\x00-\x1f]', part)
        and part.casefold() not in PRIVATE_NAMES
        and part.split(".", 1)[0].upper() not in WINDOWS_NAMES
        for part in path.parts
    ) and not stat.S_ISLNK(info.external_attr >> 16)


def inspect(archive, label, depth=0):
    require(depth <= 4, f"Unexpected nested archive depth at {label}")
    files = archive.infolist()
    names = set(archive.namelist())
    require(len(files) == len({name.casefold() for name in names}), f"Duplicate extraction path at {label}")
    require(all(safe(info) for info in files), f"Unsafe extraction name or type at {label}")
    require("MANIFEST.json" in names, f"No manifest at {label}")
    content = json.loads(archive.read("MANIFEST.json"))
    rows = content["entries"] if isinstance(content, dict) else content
    manifest = {row["path"]: row for row in rows}
    require(len(manifest) == len(rows) and set(manifest) == names - {"MANIFEST.json"},
            f"Manifest paths do not cover archive exactly at {label}")
    nested = []
    uncompressed = 0
    for info in files:
        if info.filename == "MANIFEST.json":
            continue
        expected = manifest[info.filename]
        require(expected["bytes"] == info.file_size, f"Size mismatch at {label}/{info.filename}")
        with archive.open(info) as stream:
            digest = file_digest(stream, "sha256").hexdigest()
        require(digest == expected["sha256"], f"Hash mismatch at {label}/{info.filename}")
        uncompressed += info.file_size
        if info.filename.endswith(".zip"):
            with ZipFile(BytesIO(archive.read(info))) as child:
                nested.append(inspect(child, info.filename, depth + 1))
    return {"archive": label, "members": len(files), "member_crc_and_sha256": "PASS",
            "uncompressed_payload_bytes": uncompressed, "nested": nested}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT/"delivery/independent_package_check.json")
    args = parser.parse_args()
    with ZipFile(args.archive) as archive:
        receipt = inspect(archive, args.archive.name)
        names = set(archive.namelist())
        require(EXPECTED <= names, f"Essential artifacts missing {sorted(EXPECTED - names)}")
        manifest = json.loads(archive.read("MANIFEST.json"))
        require(next(row["sha256"] for row in manifest["entries"] if row["path"] == FROZEN) == FROZEN_SHA256,
                "Frozen R3 binding changed")
        scored = json.loads(archive.read("runs/context_metrics.json"))
        require(len(scored["rows"]) == 280 and not scored["missing_run_rows"], "Controlled scoring denominator changed")
        report = archive.read("audits/INDEPENDENT_REVIEW.md").decode("utf-8-sig")
        require("/root/context_review" in report, "Independent author identity missing")
        browser = json.loads(archive.read("audits/context_browser_check.json"))
        require(browser["status"] == "PASS", "Browser receipt not successful")
        expected_page = next(row["sha256"] for row in manifest["entries"] if row["path"] == "visuals/index.html")
        require(browser["page_sha256"] == expected_page, "Browser receipt is from a different offline page")
        require(len(browser["figures"]) >= 4, "Representative views missing")
        for figure in browser["figures"]:
            stem = "visuals/figures/"
            png = archive.read(stem + figure["png"])
            svg = archive.read(stem + figure["svg"])
            require(png.startswith(b"\x89PNG\r\n\x1a\n") and b"<svg" in svg[:250],
                    f"Unusable figure {figure['png']}")
    with args.archive.open("rb") as stream:
        digest = file_digest(stream, "sha256").hexdigest()
    write(args.out, {"status":"INDEPENDENT_ZIP_INTEGRITY_PASS", "reviewer":"/root/context_review",
                     "archive_path":str(args.archive.resolve()), "sha256":digest,
                     "bytes":args.archive.stat().st_size, "checked":receipt, "controlled_scored_runs":280,
                     "browser_receipt_bound_to_sealed_page":expected_page, "representative_figures":len(browser["figures"]),
                     "scope":"Streamed CRC/SHA, safe paths, manifested nested artifacts and sealed display identity. Algorithm replay is a separate receipt."})
    print(f"Independent ZIP integrity passed for {receipt['members']} top-level members with SHA256 {digest}")


if __name__ == "__main__":
    main()
