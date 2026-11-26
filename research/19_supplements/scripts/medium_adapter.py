"""New input adapter only: byte-identical core, merged inputs, exact union coverage."""
from experiment_core import *
from src import scene_data
from shapely.geometry import shape
def activate_medium():
 root=ROOT/'medium_runtime'
 P.ROOT=root;scene_data.ROOT=root
 actual_coverage=shape(json.loads((root/'data/actual_coverage_union.geojson').read_text(encoding='utf-8')))
 # Frozen API accepts one bbox. Preserve nonrectangular acquired coverage here,
 # rather than claiming that the empty bbox corners were observed.
 scene_data.source_coverage=lambda unused_bounds:actual_coverage
 assert P.code_identity()==P.IMPORTED_CODE_SHA,'BYTE_FROZEN_CORE_MISMATCH'
