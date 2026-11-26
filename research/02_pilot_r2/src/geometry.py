"""Read frozen route/OSM evidence and measure in WGS84 or Shanghai UTM zone 51N."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path

from pyproj import Geod, Transformer
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
R1 = ROOT / "inputs/r1"
GEOD = Geod(ellps="WGS84")
PROJECT = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True).transform
UNPROJECT = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True).transform


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def project(shape_):
    return transform(PROJECT,shape_)


def distance(a,b):
    return GEOD.inv(*a,*b)[2]


def length(coords):
    xs,ys = zip(*coords)
    return GEOD.line_length(xs,ys)


class Evidence:
    def __init__(self,r1=R1):
        self.root=r1
        self.scene=read(r1/"runs/scene_contract.json")
        self.probe=read(r1/"runs/geoapify_walk_probe_proxy.json")
        self.failure=read(r1/"runs/local_route.json")
        self.diagnostic=read(r1/"runs/local_approach_diagnostic.json")
        original=read(r1/"runs/local_approach_diagnostic.geojson")
        hosted_path=r1/self.probe["geojson"]["path"]
        assert digest(hosted_path)==self.probe["geojson"]["sha256"]
        hosted=read(hosted_path)
        self.local=original["geometry"]["coordinates"]
        self.hosted_parts=[row["geometry"]["coordinates"] for row in hosted["features"]]
        assert len(self.hosted_parts)==1 and self.local==self.diagnostic["geometry"]["coordinates"]
        self.hosted=self.hosted_parts[0]
        assert self.failure["geometry"] is None and read(r1/"runs/local_route.geojson")["geometry"] is None
        assert digest(r1/"runs/scene_contract.json")==self.probe["scene_contract_sha256"]
        self.start=self.scene["start"]
        self.target=self.scene["target"]
        self.nodes={}
        self.ways={}
        self.relations={}
        self.incident=defaultdict(list)
        tables={"node":self.nodes,"way":self.ways,"relation":self.relations}
        self.snapshot=read(r1/"data/sh-huangpu-01.osm.json")
        for row in self.snapshot["elements"]:
            tables[row["type"]][row["id"]]=row
            if row["type"]=="way":
                for id_ in set(row["nodes"]):
                    self.incident[id_].append(row["id"])

    def coord(self,node_id):
        node=self.nodes[node_id]
        return (node["lon"],node["lat"])

    def way(self,way_id):
        return LineString([self.coord(i) for i in self.ways[way_id]["nodes"]])

    def building(self,way_id):
        return Polygon(self.way(way_id).coords)

    @property
    def target_building(self):
        return shape(self.scene["building_footprint"])

    def plaza(self):
        relation=self.relations[2385771]
        [outer]=[self.way(r["ref"]).coords for r in relation["members"] if r["role"]=="outer"]
        holes=[self.way(r["ref"]).coords for r in relation["members"] if r["role"]=="inner"]
        return Polygon(outer,holes)

    def relevant_ways(self, extent):
        for id_,row in self.ways.items():
            tags=row.get("tags",{})
            if not(tags.get("highway") or tags.get("building") or tags.get("landuse") or
                   tags.get("leisure") or tags.get("natural") or tags.get("waterway")):
                continue
            refs=row.get("nodes",[])
            if len(refs)<2 or any(i not in self.nodes for i in refs):
                continue
            line=self.way(id_)
            if not extent.intersects(line) and not (line.is_ring and extent.intersects(Polygon(line.coords))):
                continue
            yield id_,tags,line
