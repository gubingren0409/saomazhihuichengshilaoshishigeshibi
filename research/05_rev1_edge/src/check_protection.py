"""Record actual original source hashes and Git state without writing to either."""
import argparse
from hashlib import file_digest, sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def git_snapshot(path):
    def git(*args):
        return subprocess.check_output(["git", "--no-optional-locks", "-C", str(path), *args])

    index = Path(git("rev-parse", "--git-path", "index").decode("utf-8").strip())
    if not index.is_absolute():
        index = path / index
    state = git("status", "--porcelain=v1", "-z", "--untracked-files=no")
    return {"repo": str(path), "head": git("rev-parse", "HEAD").decode("ascii").strip(),
            "index_sha256": digest(index), "tracked_status_sha256": sha256(state).hexdigest(),
            "tracked_status_bytes": len(state)}


def snapshot(workspace, original_r4, input_zip, bundle_root):
    sealed = original_r4 / "delivery/OPEN_REVIEW.zip"
    input_frozen = bundle_root / "references/frozen/OSM_GEOAPIFY_R4_OPEN_REVIEW.zip"
    old_hash = digest(sealed)
    if old_hash != digest(input_frozen):
        raise ValueError("Installed R4 differs from supplied baseline archive")
    with ZipFile(input_frozen) as archive:
        records = json.loads(archive.read("MANIFEST.json"))["entries"]
    files = []
    for record in records:
        path = original_r4 / record["path"]
        if not path.is_file():
            files.append({"path": record["path"], "status": "NOT_INSTALLED_ARCHIVE_AVAILABLE"})
            continue
        content = digest(path)
        if path.stat().st_size != record["bytes"] or content != record["sha256"]:
            raise ValueError(f"Installed R4 member differs: {record['path']}")
        files.append({"path": record["path"], "sha256": content, "status": "PASS"})
    roots = [workspace, workspace / "project/Smart_Cities_and_Location_Services"]
    return {"original_r4_sealed_sha256": old_hash, "input_zip_sha256": digest(input_zip),
            "gpt_review_archive_sha256": digest(bundle_root / "references/frozen/R4_MAP_INFORMATION_REVIEW.zip"),
            "installed_r4_member_checks": files, "git": [git_snapshot(root) for root in roots]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("workspace", "old-r4", "input-zip", "bundle-root", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    result = snapshot(args.workspace, args.old_r4, args.input_zip, args.bundle_root)
    if args.compare and result != json.loads(args.compare.read_text(encoding="utf-8")):
        raise ValueError("Original inputs or Git state changed")
    with args.out.open("x", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"checked_r4_members": len(result["installed_r4_member_checks"]),
                      "matching_archives": True, "git_repositories": len(result["git"]),
                      "matched_initial_state": args.compare is not None}))
