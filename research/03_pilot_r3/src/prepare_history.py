"""Verify the R3 instructions and copy exact public/authorized R1/R2 evidence."""
from hashlib import sha256
import csv
import json
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
R1=ROOT.parent/"OSM_GEOAPIFY_PILOT_R1"
R2=ROOT.parent/"OSM_GEOAPIFY_PILOT_R2"
DOWNLOADS=Path.home()/"Downloads"
INPUT="OSM_GEOAPIFY_PILOT_R3_CODEX_INPUTS.zip"
SCORE="user_scores_20261109T110307129Z.csv"
ZIP_R1="delivery/OPEN_REVIEW_AB_COMPLETION.zip"
ZIP_R2="delivery/OPEN_REVIEW.zip"
R1_SELECTION=(
    "01_SOURCE_AND_PERMISSION_AUDIT.md","02_SAMPLE_AND_VIEWPORT_CONTRACT.md","03_API_AND_RENDER_IMPLEMENTATION.md",
    "09_AB_COMPLETION_RESULTS.md","data/LICENSE_NOTICE.md","data/sh-huangpu-01.osm.json",
    "runs/geofabrik_acquisition.json","runs/scene_contract.json","runs/local_route.json","runs/local_route.geojson",
    "runs/local_approach_diagnostic.json","runs/local_approach_diagnostic.geojson","runs/local_viewports.json",
    "runs/geoapify_walk_probe_proxy.json","runs/geoapify_static_completion.json","runs/geoapify_static_requests.json",
    "visuals/geoapify/ATTRIBUTION.md","visuals/geoapify/sh-huangpu-01_probe_walk.geojson",
)+tuple(f"visuals/{branch}/sh-huangpu-01_{v}_{k}.png"
    for branch in ("osm","geoapify") for v in ("detail","context") for k in ("base","route"))
R2_SELECTION=(
    "01_ROUTE_DIFFERENCE_DIAGNOSIS.md","02_MAP_VISUAL_VS_ROUTE_QUALITY.md","03_USER_FEEDBACK_TRACEABILITY.md",
    "04_NEXT_EXPERIMENT_DECISIONS.md","analysis/endpoint_metrics.json","analysis/topology.json",
    "audits/independent_review.md",f"inputs/{SCORE}",
)


def sha(data):
    return sha256(data).hexdigest()


def prepare(root=ROOT):
    entries=[]
    def check(role,path,expect=None,data=None,target=None):
        data=path.read_bytes() if data is None else data
        value=sha(data)
        if expect:
            assert value==expect,role
        if target:
            dst=root/target
            dst.parent.mkdir(parents=True,exist_ok=True)
            with dst.open("xb") as out:
                out.write(data)
        entries.append({"role":role,"source":str(path),"relative_copy":target or "",
                        "bytes":len(data),"sha256":value})
        return data
    task=DOWNLOADS/INPUT
    check("R3_PROMPT_ZIP",task,"790f6c84a2788bb1ab9f13c959f989ac2fe59c41b96bf57167f675a21e57c677")
    with ZipFile(task) as zip_:
        assert zip_.testzip() is None
        prefix=INPUT.removesuffix(".zip")+"/"
        for entry in json.loads(zip_.read(prefix+"MANIFEST_SHA256.json")):
            name=entry["path"]
            content=zip_.read(prefix+name)
            assert len(content)==entry["bytes"]
            check("R3_PROMPT_MEMBER",str(task)+"::"+name,entry["sha256"],content,f"inputs/prompt/{name}")
    for branch,folder,source,expected,selected in (
        ("r1",R1,ZIP_R1,"a4b902b530163477bdfd1092d7a88441c11e76950ee394cfb440213eb4453c12",R1_SELECTION),
        ("r2",R2,ZIP_R2,"50e147fba6cec20db02bf2aed8a00c679ad1d8ca2ca5f45c2a5a0db1c89518a2",R2_SELECTION),
    ):
        archive=folder/source
        check("HISTORICAL_SEALED_ZIP",archive,expected)
        with ZipFile(archive) as zip_:
            assert zip_.testzip() is None
            manifest={r["path"]:r for r in json.loads(zip_.read("MANIFEST.json"))["entries"]}
            for name in selected:
                content=check("HISTORICAL_FROZEN_MEMBER",folder/name,manifest[name]["sha256"],
                              target=f"inputs/{branch}/{name}")
                assert len(content)==manifest[name]["bytes"] and content==zip_.read(name)
    score=check("EXACT_USER_SCORE",DOWNLOADS/SCORE,"bf9031591b4d67be39ec7e0239432116a01f3197b414e88d3e8a682a68db108a",
                target=f"inputs/{SCORE}")
    assert score==(root/"inputs/r2/inputs"/SCORE).read_bytes()
    check("CITY_PBF_READ_ONLY",R1/"runtime/shanghai-261108.osm.pbf",
          "e4b83f15cc358d347c47708239f8c556d9819a69f43ff32f42a23c405733e8f6")
    audit=root/"audits/historical_sources.csv"
    audit.parent.mkdir(exist_ok=True)
    with audit.open("x",encoding="utf-8-sig",newline="") as out:
        writer=csv.DictWriter(out,fieldnames=list(entries[0]))
        writer.writeheader(); writer.writerows(entries)
    print(json.dumps({"verified_records":len(entries),"copies":sum(bool(row["relative_copy"]) for row in entries),
                      "old_score_exact":True,"second_round_user_score":"NOT_SUBMITTED_IN_LOCATED_INPUTS"}))


if __name__=="__main__":
    prepare()
