"""Create a byte-identical, portable subset of the user's sealed R4 baseline."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


OLD_SHA = "36d83fb2d792b33457968f1c649099380cc5cffa1e7b561c1dd6463fd82ce2f3"
OLD_MEMBER = "references/frozen/OSM_GEOAPIFY_R4_OPEN_REVIEW.zip"
REVIEW_SHA = "a50ca7a6296da0b9bd1862b0808d4460c0913e876bf3bb17b10762fa3e527d4a"
REFERENCE_MEMBERS = (
    "runs/source_scene_contracts.json", "runs/source_open_spaces.json",
    "runs/experiment.json", "runs/protocol_core.json", "runs/dual_paths.json",
    "src/frozen_r1/local_route.py", "src/core.py", "src/prepare_sources.py",
    "src/run_experiment.py", "data/source/LICENSE_NOTICE.md",
    "data/source/historical/r2_topology.json", "data/source/historical/r2_endpoint_metrics.json",
    "data/historical_b0_recomputed.csv", "data/registered_entrances.csv",
    "01_RESEARCH_CONTRACT_AND_SCOPE.md", "03_EDGE_CONNECTION_METHOD.md", "04_EXPERIMENT_RESULTS.md",
)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def safe(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe frozen member path")
    return Path(*p.parts)


def freeze(bundle_root, output_root):
    if output_root.exists():
        raise FileExistsError(f"Frozen baseline root already exists: {output_root}")
    archive = bundle_root / OLD_MEMBER
    if digest(archive.read_bytes()) != OLD_SHA:
        raise ValueError("Frozen archive does not match authorized input")
    if digest((bundle_root / "references/frozen/R4_MAP_INFORMATION_REVIEW.zip").read_bytes()) != REVIEW_SHA:
        raise ValueError("GPT source-review archive does not match authorized input")
    records = []
    with ZipFile(archive) as handle:
        if handle.testzip() is not None:
            raise ValueError("Old archive CRC mismatch")
        index = {row["path"]: row for row in json.loads(handle.read("MANIFEST.json"))["entries"]}
        if len(index) != 140 or len(handle.namelist()) != 141 or set(handle.namelist()) != set(index) | {"MANIFEST.json"}:
            raise ValueError("Old archive manifest membership mismatch")
        for path, row in sorted(index.items()):
            safe(path)
            b = handle.read(path)
            if len(b) != row["bytes"] or digest(b) != row["sha256"]:
                raise ValueError(f"Frozen member mismatch: {path}")
        scenes = json.loads(handle.read("runs/source_scene_contracts.json"))["scenes"]
        paths = set(REFERENCE_MEMBERS)
        for scene in scenes:
            for key in ("osm_clip", "historical_local_route", "historical_local_diagnostic", "historical_hosted_route"):
                if scene.get(key):
                    paths.add(scene[key])
        output_root.mkdir(parents=True)
        for path in sorted(paths):
            dst = output_root / safe(path)
            dst.parent.mkdir(parents=True, exist_ok=True)
            with dst.open("xb") as stream:
                stream.write(handle.read(path))
            records.append(index[path])
    receipt = dict(identity="FROZEN_R4_VERIFIED_BYTE_COPY", original_archive_sha256=OLD_SHA,
                   original_manifest_entries=140, original_archive_bytes=9457831,
                   gpt_review_archive_sha256=REVIEW_SHA, entries=records)
    (output_root / "BASELINE_MANIFEST.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    result = freeze(args.bundle_root.resolve(), args.output_root.resolve())
    print(json.dumps({k: len(v) if k == "entries" else v for k, v in result.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
