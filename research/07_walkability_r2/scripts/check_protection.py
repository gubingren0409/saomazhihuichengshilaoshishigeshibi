"""Compare this host's frozen originals and tracked Git state with startup evidence."""
import argparse
from hashlib import file_digest, sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def git(where, *args):
    return subprocess.run(["git", "--no-optional-locks", "-C", str(where), *args],
                          check=True, stdout=subprocess.PIPE).stdout


def main(out):
    before = json.loads((ROOT / "references/source_manifest.json").read_text(encoding="utf-8"))
    originals, repos = [], []
    for entry in before["protected_originals"]:
        path = Path(entry["path"])
        actual = {"bytes": path.stat().st_size, "sha256": digest(path)}
        originals.append(dict(path=entry["path"], actual=actual,
                              unchanged=all(entry[k] == v for k, v in actual.items())))
    for entry in before["git"]:
        where = Path(entry["path"])
        index = Path(git(where, "rev-parse", "--path-format=absolute", "--git-path", "index").decode("utf-8").strip())
        actual = {"head": git(where, "rev-parse", "HEAD").decode("ascii").strip(),
                  "index_sha256": digest(index),
                  "tracked_status_sha256": sha256(git(where, "status", "--porcelain=v1", "-z", "-uno")).hexdigest()}
        repos.append(dict(path=entry["path"], actual=actual,
                          unchanged=all(entry[k] == v for k, v in actual.items())))
    passed = all(row["unchanged"] for row in originals + repos)
    payload = {"status": "PASS" if passed else "CHANGED", "archives": originals, "git": repos,
               "scope": "original archives and two Git indexes, HEADs, tracked porcelain"}
    with out.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(payload["status"])
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "audits/protection_after.json")
    raise SystemExit(main(parser.parse_args().output))
