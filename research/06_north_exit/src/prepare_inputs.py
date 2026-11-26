"""Bind the R1 brief to exact, portable excerpts of frozen local evidence."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
ATTACHMENT_SHA = "efb403f3f2c6e1fb9b1df85533145b7ae76a5cebb7b2d24fd7751caa39aa9748"
REVISION_SHA = "f2de5326ffbffe1e62c0fa5d622cec6645582342824ea1ae13716789d5af5ee0"
REVIEW_SHA = "a50ca7a6296da0b9bd1862b0808d4460c0913e876bf3bb17b10762fa3e527d4a"
SOURCES = (
    "RESULTS.md", "data/entrance_approach.json", "data/native_prefix_diagnostic.json",
    "data/native_prefix_diagnostic.geojson", "runs/experiment.json",
    "frozen_r4/data/source/sh-huangpu-01.osm.json", "frozen_r4/runs/source_scene_contracts.json",
    "frozen_r4/runs/experiment.json", "frozen_r4/src/frozen_r1/local_route.py",
    "src/native_adapter.py", "src/route_measure.py", "src/audit_native_prefix.py", "src/run_rev1.py",
    "src/area_model.py", "visuals/scene_data.js",
)
TRIAL = ("public/trial.json", "public/trial.geojson", "public/index.html",
         "src/run_trial.py", "src/build_comparison.py")
OPTIONAL_TRIAL = ("runtime/server.stdout.log", "runtime/server.stderr.log")
REVIEW = ("00_R4_QUESTIONS_REVIEW.md", "question_checks.json", "source_code_evidence.md")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe(name):
    p = PurePosixPath(name)
    return bool(p.parts) and not p.is_absolute() and ".." not in p.parts and "\\" not in name and ":" not in name


def check_zip(archive):
    names = archive.namelist()
    if len(names) != len(set(names)) or not all(safe(n) for n in names) or archive.testzip() is not None:
        raise ValueError("Unsafe or invalid input archive")


def manifest_zip(archive):
    check_zip(archive)
    doc = json.loads(archive.read("MANIFEST.json"))
    rows = doc["entries"] if isinstance(doc, dict) else doc
    entries = {r["path"]: r for r in rows}
    if len(entries) != len(rows) or set(archive.namelist()) != {"MANIFEST.json", *entries}:
        raise ValueError("Source archive membership differs")
    for path, row in entries.items():
        with archive.open(path) as file:
            if archive.getinfo(path).file_size != row["bytes"] or hashlib.file_digest(file, "sha256").hexdigest() != row["sha256"]:
                raise ValueError(f"Source archive content differs: {path}")
    return entries


def git_state(workspace):
    out = []
    for repo in (workspace, workspace / "project/Smart_Cities_and_Location_Services"):
        def git(*args):
            return subprocess.check_output(["git", "--no-optional-locks", "-C", str(repo), *args])
        index = Path(git("rev-parse", "--git-path", "index").decode("utf-8").strip())
        if not index.is_absolute():
            index = repo / index
        out.append(dict(repo=str(repo), head=git("rev-parse", "HEAD").decode("ascii").strip(),
                        index_sha256=digest(index),
                        tracked_status_sha256=sha(git("status", "--porcelain=v1", "-z", "--untracked-files=no"))))
    return out


def retain(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as file:
        file.write(data)


def prepare(attachment, workspace):
    rows = []
    hashes = {}

    def bind(source, role, data=None, to=None, expected=None):
        source_name = str(source)
        if data is None:
            source = Path(source)
            size, fingerprint = source.stat().st_size, digest(source)
        else:
            size, fingerprint = len(data), sha(data)
        if expected is not None and fingerprint != expected:
            raise ValueError(f"Source SHA mismatch: {source_name}")
        if to:
            retain(ROOT / to, Path(source).read_bytes() if data is None else data)
        else:
            if "::" not in source_name:
                hashes[source_name] = fingerprint
        if isinstance(source, Path) and "::" not in source_name:
            hashes[source_name] = fingerprint
        rows.append(dict(role=role, source=source_name, retained=to, bytes=size, sha256=fingerprint, status="VERIFIED_EXACT"))

    bind(attachment, "USER_ATTACHMENT", expected=ATTACHMENT_SHA)
    with ZipFile(attachment) as z:
        check_zip(z)
        prefix = attachment.stem + "/"
        listing = json.loads(z.read(prefix + "MANIFEST_SHA256.json"))
        if isinstance(listing, dict):
            listing = listing["entries"]
        if set(z.namelist()) != {prefix + "MANIFEST_SHA256.json", *(prefix + r["path"] for r in listing)}:
            raise ValueError("User attachment membership differs")
        for row in listing:
            n = row["path"]
            data = z.read(prefix + n)
            if len(data) != row["bytes"]:
                raise ValueError("User attachment length mismatch")
            bind(f"{attachment}::{n}", "TASK_CONTRACT", data, f"inputs/contract/{n}", row["sha256"])

    sealed = BASE / "OSM_GEOAPIFY_R4_REV1/delivery/OPEN_REVIEW.zip"
    rev = sealed.parent.parent
    bind(sealed, "R4_REV1_SEALED_BASELINE", expected=REVISION_SHA)
    with ZipFile(sealed) as z:
        entries = manifest_zip(z)
        for name in SOURCES:
            source = rev / name
            if digest(source) != entries[name]["sha256"]:
                raise ValueError(f"Installed source differs from sealed member: {name}")
            bind(source, "R4_REV1_PORTABLE_MEMBER", z.read(name), f"inputs/source/{name}", entries[name]["sha256"])

    prior = BASE / "OSM_GEOAPIFY_R4_REV1_NORTH_GAP_TRIAL"
    for name in TRIAL + OPTIONAL_TRIAL:
        path = prior / name
        if not path.is_file():
            rows.append(dict(role="PREVIOUS_NORTH_TRIAL", source=str(path), status="MISSING_INPUT"))
        elif name in TRIAL:
            bind(path, "PREVIOUS_NORTH_TRIAL", to=f"inputs/prior_trial/{Path(name).name}")
        else:
            # The local preview server logs are mutable UI records, not route provenance.
            rows.append(dict(role="PREVIOUS_UI_RUNTIME_NOT_USED", source=str(path), bytes=path.stat().st_size,
                             sha256=digest(path), status="OBSERVED_AT_PREPARATION_NOT_FROZEN"))

    review_zip = next((p for folder in BASE.glob("R4_REV1_INPUT_*")
                       for p in folder.rglob("R4_MAP_INFORMATION_REVIEW.zip") if digest(p) == REVIEW_SHA), None)
    if review_zip:
        bind(review_zip, "GPT_HISTORICAL_REVIEW_ARCHIVE", expected=REVIEW_SHA)
        with ZipFile(review_zip) as z:
            entries = manifest_zip(z)
            for name in REVIEW:
                bind(f"{review_zip}::{name}", "GPT_REVIEW_EVIDENCE", z.read(name),
                     f"inputs/prior_review/{name}", entries[name]["sha256"])
    else:
        rows.append(dict(role="GPT_HISTORICAL_REVIEW_ARCHIVE", status="MISSING_INPUT"))

    doc = dict(status="INPUTS_VERIFIED", attachment_sha256=ATTACHMENT_SHA, r4_rev1_zip_sha256=REVISION_SHA,
               source_rows=rows, protected_originals=hashes, git=git_state(workspace), external_requests=0)
    retain(ROOT / "data/input_manifest.json", (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(dict(verified=sum(x["status"] == "VERIFIED_EXACT" for x in rows),
                          retained=sum(bool(x.get("retained")) for x in rows),
                          missing=sum(x["status"] == "MISSING_INPUT" for x in rows))))


def check_originals(workspace):
    path = ROOT / "data/input_manifest.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    for file, original in doc["protected_originals"].items():
        if digest(Path(file)) != original:
            raise ValueError(f"Original source changed: {Path(file).name}")
    if git_state(workspace) != doc["git"]:
        raise ValueError("Protected Git state changed")
    result = dict(status="PASS", originals_rehashed=len(doc["protected_originals"]), git_repositories=len(doc["git"]))
    retain(ROOT / "audits/protection_after.json", (json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--attachment", type=Path, default=Path.home() / "Downloads/OSM_GEOAPIFY_R4_NORTH_ACCESS_R1_CODEX_INPUTS.zip")
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--recheck", action="store_true")
    a = p.parse_args()
    check_originals(a.workspace) if a.recheck else prepare(a.attachment, a.workspace)
