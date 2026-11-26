"""Verify frozen R3 adapter artifacts and retain R4's replay inputs."""
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
R3 = ROOT.parent / "OSM_GEOAPIFY_PILOT_R3"
R3_ZIP_SHA = "13ffb6be75ca0b26710dd3d68bba2951e99539fa06eb51ab4d8195ea487e8c30"
PROMPT_ZIP_SHA = "706f776ad62e71348ecd39e69df2ebb8cf5e8e16f85c6beaee3f244cb81a2b7e"
SCENES = ("sh-huangpu-01", "sh-wukang", "sh-tower", "sh-newworld", "sh-library", "sh-exhibition")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(data, size, checksum, label):
    if len(data) != size or sha(data) != checksum:
        raise ValueError(f"Frozen input mismatch: {label}")


def retain(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f"Existing replay copy differs: {path.name}")
    else:
        with path.open("xb") as handle:
            handle.write(data)


def prepare(root=ROOT, r3=R3):
    rows = []

    def record(role, source, data, copy=None):
        if copy:
            retain(root / copy, data)
        rows.append(dict(role=role, source=str(source), retained=copy or "", bytes=len(data),
                         sha256=sha(data), completeness="VERIFIED_EXACT"))

    prompt = Path.home() / "Downloads" / "OSM_GEOAPIFY_R4_CODEX_INPUTS.zip"
    prompt_bytes = prompt.read_bytes()
    verify(prompt_bytes, len(prompt_bytes), PROMPT_ZIP_SHA, prompt.name)
    record("R4_USER_INPUT_ARCHIVE", prompt, prompt_bytes)
    with ZipFile(prompt) as archive:
        if archive.testzip() is not None:
            raise ValueError("R4 user archive CRC failed")
        prefix = prompt.stem + "/"
        manifest = json.loads(archive.read(prefix + "MANIFEST_SHA256.json"))
        expected = {prefix + "MANIFEST_SHA256.json", *(prefix + row["path"] for row in manifest)}
        if set(archive.namelist()) != expected:
            raise ValueError("Unexpected R4 input members")
        for row in manifest:
            name = row["path"]
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
                raise ValueError("Unsafe prompt member")
            data = archive.read(prefix + name)
            verify(data, row["bytes"], row["sha256"], name)
            record("R4_USER_INPUT_MEMBER", f"{prompt}::{name}", data, f"inputs/prompt/{name}")

    archive_path = r3 / "delivery/OPEN_REVIEW.zip"
    data = archive_path.read_bytes()
    verify(data, len(data), R3_ZIP_SHA, archive_path.name)
    record("R3_SEALED_ARCHIVE", archive_path, data)
    with ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("R3 frozen archive CRC failed")
        manifest = {item["path"]: item for item in json.loads(archive.read("MANIFEST.json"))["entries"]}

        def freeze(role, name, target=None):
            source = r3 / name
            data = source.read_bytes()
            entry = manifest[name]
            verify(data, entry["bytes"], entry["sha256"], name)
            if archive.read(name) != data:
                raise ValueError(f"Archive source mismatch: {name}")
            record(role, source, data, target)

        for scene in SCENES:
            for side in ("local", "hosted"):
                name = f"{scene}.{side}.json"
                freeze("FROZEN_COMMON_IR", f"runs/common_ir/{name}", f"data/ir/{name}")
        freeze("FROZEN_COMMON_IR_SUMMARY", "runs/common_ir/summary.json", "data/ir/r3_summary.json")
        for name in ("01_SOURCE_AND_PERMISSION_AUDIT.md", "05_DECISION_ON_TWO_PATHS.md",
                     "08_COMMON_INTERMEDIATE_REPRESENTATION.md", "09_DUAL_PATH_ALGORITHM_ROADMAP.md"):
            freeze("FROZEN_R3_REFERENCE", name, f"inputs/r3/{name}")
        for name in ("runs/hosted_results.json", "inputs/r1/runs/geoapify_static_requests.json",
                     "inputs/r1/runs/geoapify_static_completion.json", "inputs/r1/runs/geoapify_walk_probe_proxy.json"):
            freeze("HOSTED_FROZEN_REQUEST_RECEIPTS", name, "data/hosted_evidence/" + Path(name).name)
        for scene in SCENES:
            historical = scene == "sh-huangpu-01"
            if not historical:
                name = f"{scene}_routing_response.json"
                freeze("HOSTED_FROZEN_RAW_RESPONSE", f"hosted/{name}", f"data/hosted_evidence/{name}")
            base = ("inputs/r1/" if historical else "") + "visuals/geoapify"
            for view in ("detail", "context"):
                for kind in ("base", "route"):
                    freeze("HOSTED_FROZEN_ORIGINAL_PNG_REFERENCE", f"{base}/{scene}_{view}_{kind}.png")

    path = root / "audits/ir_evidence.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(dict(verified=len(rows), retained=sum(bool(row["retained"]) for row in rows),
                          hosted_png_hash_only=24, external_requests=0)))


if __name__ == "__main__":
    prepare()
