"""Synthetic relation fixtures, separate from the same-source OSM tasks."""
import json
from pathlib import Path

from shapely.geometry import LineString, Point, box, mapping

from src.context_policy import enhance
from src.region import INFERRED, build_surface

ROOT=Path(__file__).resolve().parents[1]
LOCAL=json.loads((ROOT/"config/frozen_region.json").read_text())
CONTEXT=json.loads((ROOT/"config/methods.json").read_text())["M1"]


def fixture(outside="none"):
    points={0:(0,0),1:(-20,0),2:(-35,0)}
    ways=[(0,1,1),(1,2,1)]
    if outside in {"linked","blocked"}:
        points.update({3:(-55,0),4:(-60,8),5:(-60,-8),10:(-57,12)})
        ways.extend([(2,3,1),(3,4,2),(3,5,3),(3,10,4)])
    if outside=="unrelated":
        points.update({6:(50,0),7:(60,0),8:(54,9),9:(56,-8)})
        ways.extend([(6,7,5),(6,8,6),(6,9,7)])
    hard=[]
    if outside=="blocked":
        hard=[{"id":"way/90","kind":"BARRIER","geometry":mapping(LineString([(-44,-4),(-44,4)])),
               "tags":{"barrier":"wall"}}]
    return {"task_id":"SYNTHETIC_CONTEXT","crs":"EPSG:32651","domain":{"anchor_xy":[0,0],"anchor_role":"FIXTURE"},
            "registered_entrance":None,"nodes":[{"id":f"node/{i}","xy":xy,"tags":{}} for i,xy in points.items()],
            "edges":[{"id":f"way/{s}/{u}/{v}","u":f"node/{u}","v":f"node/{v}","kind":"NATIVE_LINEAR",
                      "tags":{"highway":"footway"}} for a,b,s in ways for u,v in ((a,b),(b,a))],
            "context":{"hard":hard,"background":[],"support":[
                {"id":"way/80","kind":"PAVING","geometry":mapping(box(-1,-4,15,4)),"tags":{"surface":"paved"}}]}}


def result(mode):
    obs=fixture(mode)
    m0=build_surface(obs,LOCAL)
    return m0,*enhance(m0,obs,LOCAL,CONTEXT)


def test_connected_exterior_junction_changes_local_cells():
    a0,a1,empty=result("none")
    b0,b1,used=result("linked")
    assert a0.sha256==b0.sha256==a1.sha256
    assert b1.sha256!=b0.sha256
    assert not b0.masks[INFERRED].covers(Point(12,0))
    assert b1.masks[INFERRED].covers(Point(12,0))
    assert used["changed_cells"]>0 and used["used_witnesses_by_band"]["40–80"]>0
    assert not empty["changed_cells"]


def test_unrelated_exterior_component_cannot_grant_walkability():
    base,extended,features=result("unrelated")
    assert features["exterior_junctions"]==1
    assert features["eligible_portals"]==0 and base.sha256==extended.sha256


def test_outer_wall_breaks_path_based_witness():
    base,extended,features=result("blocked")
    assert features["exterior_junctions"]==1
    assert features["eligible_portals"]==0 and base.sha256==extended.sha256
