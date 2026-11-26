"""Verify and mirror the exact R1 evidence needed for read-only R2."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import shutil
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
R1 = ROOT.parent / "OSM_GEOAPIFY_PILOT_R1"
DOWNLOADS = Path.home() / "Downloads"
SCORE = "user_scores_20261109T110307129Z.csv"
R2_ZIP = "OSM_GEOAPIFY_PILOT_R2_CODEX_INPUTS.zip"
R1_ZIP = "delivery/OPEN_REVIEW_AB_COMPLETION.zip"
R1_EXPECTED = "a4b902b530163477bdfd1092d7a88441c11e76950ee394cfb440213eb4453c12"
R2_EXPECTED = "67f6ad5cfff8fbaafe5f199bfa71b0b050fe7b828ce92413e47983c656240a77"
SCORE_EXPECTED = "bf9031591b4d67be39ec7e0239432116a01f3197b414e88d3e8a682a68db108a"
R1_SELECTED = [
    "01_SOURCE_AND_PERMISSION_AUDIT.md","02_SAMPLE_AND_VIEWPORT_CONTRACT.md",
    "03_API_AND_RENDER_IMPLEMENTATION.md","04_EXPERIMENT_RESULTS.md",
    "05_HUMAN_REVIEW_GUIDE.md","09_AB_COMPLETION_RESULTS.md","data/LICENSE_NOTICE.md","data/manifest.csv",
    "data/sh-huangpu-01.osm.json","src/local_route.py","runs/pilot_plan.json","runs/scene_contract.json",
    "runs/geofabrik_acquisition.json","runs/local_route.json","runs/local_route.geojson",
    "runs/local_approach_diagnostic.json","runs/local_approach_diagnostic.geojson",
    "runs/local_viewports.json","runs/geoapify_walk_probe.json","runs/geoapify_walk_probe_proxy.json",
    "runs/geoapify_static_requests.json","runs/geoapify_static_completion.json",
    "runs/gallery_input.json","runs/maplibre_viewer_input_completed.json",
    "audits/INDEPENDENT_REVIEW.md","audits/INDEPENDENT_AB_COMPLETION.md","audits/independent_geoapify.json",
    "visuals/geoapify/ATTRIBUTION.md","visuals/geoapify/sh-huangpu-01_probe_walk.geojson",
    "visuals/blind_review/index.html",
] + [f"visuals/{src}/sh-huangpu-01_{view}_{kind}.png" for src in ("osm","geoapify")
     for view in ("detail","context") for kind in ("base","route")]


def digest(data):
    return sha256(data).hexdigest()


def copy_bytes(data, destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(data)


def collect(root, r1, downloads):
    rows=[]
    def add(role,source,data,copy=None,record="OBSERVED"):
        if copy:
            copy_bytes(data,root/copy)
        rows.append({"role":role,"original_source":str(source),"copy_path":str(copy or "").replace("\\","/"),
                     "bytes":len(data),"sha256":digest(data),"evidence_status":record})

    input_zip=downloads/R2_ZIP
    add("r2_input_zip",input_zip,input_zip.read_bytes())
    assert rows[-1]["sha256"]==R2_EXPECTED
    with ZipFile(input_zip) as archive:
        assert archive.testzip() is None
        prefix=R2_ZIP.removesuffix(".zip")+"/"
        for entry in json.loads(archive.read(prefix+"MANIFEST_SHA256.json")):
            data=archive.read(prefix+entry["path"])
            assert len(data)==entry["bytes"] and digest(data)==entry["sha256"]
            add("r2_prompt_input",str(input_zip)+"::"+entry["path"],data,Path("inputs/r2_prompt")/entry["path"])

    review=r1/R1_ZIP
    add("sealed_r1_archive",review,review.read_bytes())
    assert rows[-1]["sha256"]==R1_EXPECTED
    verification=r1/"delivery/OPEN_REVIEW_AB_COMPLETION_VERIFICATION.json"
    data=verification.read_bytes()
    assert json.loads(data)["zip_sha256"]==R1_EXPECTED
    add("r1_archive_verification",verification,data,Path("inputs/r1")/"OPEN_REVIEW_AB_COMPLETION_VERIFICATION.json")
    with ZipFile(review) as archive:
        assert archive.testzip() is None
        entries={entry["path"]:entry for entry in json.loads(archive.read("MANIFEST.json"))["entries"]}
        for path in R1_SELECTED:
            source=r1/path
            data=source.read_bytes()
            ref=entries[path]
            assert len(data)==ref["bytes"] and digest(data)==ref["sha256"] and data==archive.read(path),path
            add("r1_frozen_artifact",source,data,Path("inputs/r1")/path)
        for path in sorted(p for p in entries if p.startswith("visuals/blind_review/assets/")):
            data=(r1/path).read_bytes()
            assert len(data)==entries[path]["bytes"] and digest(data)==entries[path]["sha256"],path
            add("r1_blind_alias_verified",r1/path,data)

    score=downloads/SCORE
    data=score.read_bytes()
    assert digest(data)==SCORE_EXPECTED
    add("user_original_score",score,data,Path("inputs")/SCORE)
    mapping=r1/"07_BLIND_REVEAL_MAP_PRIVATE.csv"
    add("r1_local_mapping",mapping,mapping.read_bytes(),None)
    pbf=r1/"runtime/shanghai-261108.osm.pbf"
    if pbf.is_file():
        data=pbf.read_bytes()
        receipt=json.loads((r1/"runs/geofabrik_acquisition.json").read_bytes())
        assert len(data)==receipt["source_bytes"] and digest(data)==receipt["source_sha256"]
        add("r1_city_pbf_reference",pbf,data)
    rows.extend([
        {"role":"raw_geoapify_routing_http_body","original_source":"R1 code/receipt retains normalized provider coordinates",
         "copy_path":"","bytes":"","sha256":"","evidence_status":"UNKNOWN_NOT_RETAINED_IN_R1"},
        {"role":"geoapify_routing_graph","original_source":"No hosted internal graph or weight traces in R1",
         "copy_path":"","bytes":"","sha256":"","evidence_status":"UNKNOWN_NOT_AVAILABLE"},
    ])
    fields=list(rows[0])
    with (root/"source_evidence_index.csv").open("x",encoding="utf-8-sig",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"rows":len(rows),"mirrored":sum(bool(r["copy_path"]) for r in rows),"r1_zip_sha":R1_EXPECTED,
                      "score_sha":SCORE_EXPECTED,"raw_hosted_http_body":"NOT_RETAINED"}))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--r1",type=Path,default=R1)
    parser.add_argument("--downloads",type=Path,default=DOWNLOADS)
    args=parser.parse_args()
    collect(ROOT,args.r1,args.downloads)
