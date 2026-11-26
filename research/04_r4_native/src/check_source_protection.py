"""Verify source hashes and protected read-only Git state after R4 execution."""
import csv
import json
from pathlib import Path

from .prepare_sources import ROOT, digest, git_state


def check(root=ROOT):
    with (root / "data/manifest.csv").open(encoding="utf-8-sig", newline="") as f:
        records = list(csv.DictReader(f))
    checked = 0
    copied = 0
    for record in records:
        if record["status"] == "MISSING":
            continue
        source = Path(record["original_path"])
        expected = record["sha256"]
        assert source.stat().st_size == int(record["bytes"]) and digest(source.read_bytes()) == expected, source
        checked += 1
        if record["r4_path"]:
            dst = root / record["r4_path"]
            assert dst.stat().st_size == int(record["bytes"]) and digest(dst.read_bytes()) == expected, dst
            copied += 1
    original_state = json.loads((root / "audits/old_git_before.json").read_bytes())
    final_state = git_state()
    assert original_state == final_state, "Historical Git state differs"
    return {"status": "PASS", "protected_originals_rehashed": checked,
            "retained_r4_copies_rehashed": copied, "git_protection_pass": True,
            "git": final_state, "scope": "Manifest input originals and R4 copies; old Git HEAD/index/tracked status counts"}


if __name__ == "__main__":
    result = check()
    out = ROOT / "audits/source_protection_final.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
