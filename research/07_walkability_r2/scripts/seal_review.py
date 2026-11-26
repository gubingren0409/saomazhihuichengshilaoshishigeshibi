"""Create a fixed, scoped review archive with an independent content manifest."""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ("audits", "config", "src", "scripts", "tests", "data", "runs", "visuals", "references", "reviews")
TOP = ("README.md", "SCOPE_AND_METHOD.md", "RESULTS.md", "USER_REVIEW_NOTES.md", "STATUS.json", "requirements.txt")
SUFFIXES = {".md", ".json", ".csv", ".geojson", ".py", ".js", ".html", ".svg", ".png", ".txt", ".zip"}
NESTED = {"references/frozen_archives/R4_REV1_OPEN_REVIEW.zip", "references/frozen_archives/NORTH_ACCESS_R1_OPEN_REVIEW.zip"}
BLOCKED_NAMES = {"cookies", "cookies.sqlite", "local state", "login data", "secrets.json", "credentials.json"}
CREDENTIAL = re.compile(rb"(?:AMAP_(?:JS|WEB_SERVICE)_KEY|GEOAPIFY_API_KEY|AMAP_SECURITY_JS_CODE)\s*[:=]\s*[\"']?[A-Za-z0-9]{24,}",
                        re.IGNORECASE)


def safe(member):
    path = PurePosixPath(member)
    return (member == path.as_posix() and not path.is_absolute() and
            all(not (p.startswith(".") or p.casefold() in BLOCKED_NAMES or ":" in p or "\\" in p)
                for p in path.parts) and path.suffix.lower() in SUFFIXES and
            (path.suffix.lower() != ".zip" or member in NESTED))


def inspect_member(member, content):
    if not safe(member):
        raise ValueError(f"Unexpected archive member {member}")
    if Path(member).suffix.lower() not in {".zip", ".png"} and CREDENTIAL.search(content):
        raise ValueError(f"Credential-shaped content in {member}")


def check_nested(archives):
    for name in NESTED:
        source = archives[name]
        with ZipFile(source) as z:
            if z.testzip():
                raise ValueError(f"CRC mismatch in {name}")
            for member in z.namelist():
                p = PurePosixPath(member)
                if not p.parts or p.is_absolute() or any(x.startswith(".") or x.casefold() in BLOCKED_NAMES or
                         ":" in x or "\\" in x for x in p.parts):
                    raise ValueError(f"Unexpected nested path {name}:{member}")


def collect(root):
    files = [root / path for path in TOP]
    for folder in FOLDERS:
        files.extend(p for p in (root / folder).rglob("*") if p.is_file() and
                     "__pycache__" not in p.parts and p.suffix.lower() in SUFFIXES)
    entries = sorted({p.relative_to(root).as_posix(): p for p in files}.items())
    if not all(p.is_file() and p.resolve().is_relative_to(root.resolve()) and not p.is_symlink() for _, p in entries):
        raise ValueError("Missing or nonlocal package path")
    return entries


def add(zipfile, name, content):
    entry = ZipInfo(name, (2026, 11, 10, 0, 0, 0))
    zipfile.writestr(entry, content, ZIP_STORED if name.endswith((".zip", ".png")) else ZIP_DEFLATED)


def main(root, output):
    rows = []
    entries = collect(root)
    check_nested(dict(entries))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream, ZipFile(stream, "w") as z:
        for name, path in entries:
            data = path.read_bytes()
            inspect_member(name, data)
            rows.append(dict(path=name, bytes=len(data), sha256=sha256(data).hexdigest()))
            add(z, name, data)
        manifest = dict(schema=1, artifact="R4-WALKABILITY-R2_OPEN_REVIEW", entries=rows,
                        preserved_ancestors=sorted(NESTED), personal_profiles=0)
        add(z, "MANIFEST.json", (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode())
    with ZipFile(output) as z:
        if z.testzip() is not None or set(z.namelist()) != {"MANIFEST.json", *(r["path"] for r in rows)}:
            raise ValueError("Package CRC or manifest mismatch")
    print(json.dumps(dict(path=str(output), bytes=output.stat().st_size, members=len(rows)+1,
                          sha256=sha256(output.read_bytes()).hexdigest())))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--output", type=Path, default=ROOT / "delivery/OPEN_REVIEW.zip")
    a = p.parse_args()
    main(a.root.resolve(), a.output.resolve())
