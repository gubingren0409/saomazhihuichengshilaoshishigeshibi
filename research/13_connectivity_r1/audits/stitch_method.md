# Connectivity implementation and author checks

Author role: `/root/connectivity_stitch`. This is implementation evidence and
author testing, separate from `/root/connectivity_review` and user acceptance.
The user's earlier crossing observation remains `PENDING_USER_OBSERVATION`.

## API and integration

`src.connectivity.build_connectivity_overlay(faces, source_graph, local_region,
common, cfg=None, mode='EXACT_STITCH', base_overlay=None, base_evidence=None)`
returns `(delta_graph, evidence)`. `base_overlay` can be a single graph or the
read-only list `[B1_overlay, B2_delta]`. The returned graph contains additive
arcs and only their necessary nodes. Compose all parent overlays with all
`routing_alternatives`; plain overwriting `nx.compose` is insufficient for
parallel options. The source and local graphs are not edited. The common
contract must cover the full acquired source footprint, never the door's D30.

`validate_connectivity_segment(segment, faces, common, evidence)` rechecks the
complete derived or conditional segment, source-domain ownership, constraint
coverage, obstacle clearance, source barriers, inference label and seam record.
Source-parent split replay remains additionally bound to the original parent
geometry, direction and option hash in `stitch_directed_splits`.

B0 and B1 use the frozen `face_visibility.build_overlay`. B2 adds all eligible
parent options, including `routing_alternatives` and `alternative_segments`.
Boundary contacts use the unchanged parent-arclength split helper and its
existing strict-cover, at-most-1e-8m numerical certificate. Endpoints retain
their original IDs, coordinates and complete node metadata. A matching frozen
portal is reused, and duplicate frozen arcs are omitted from the delta.

Positive-area or positive-edge compatible face components may share a derived
union. Its visibility model is the frozen `VisibilityRoadmap`; no other area
solver is introduced. Unchanged single components reuse the frozen corner and
required-point IDs, and only pairs involving a new portal require new checks.
Only affected positive-width unions rebuild their corner geometry. Each new
visible straight segment is split against the original face boundaries and
each resulting complete interval names its covering source face(s). A road
partition's entire coincident boundary is explicitly rejected as an interface.
Every new segment retains full-source road, permission and exact-gate checks.

B3 probes nearest face boundaries and native-line parent projections/endpoints
within 10m. The fixed accepted limit is 2m, with only 0.5m and 5m sensitivity
settings. Its minimum line links have unknown width; no inferred area patch,
source polygon buffer, convex hull, closing, door movement or entrance is
generated. Each accepted `CONDITIONAL_GAP_LINK` is an actual bidirectional graph
arc with `layer=inferred`; the existing solver applies F0=1 and F1=2. Its native
parent is split in the original direction. Candidate generation uses geometry
and source identities only, without query or route-result reads. Equal-distance
nearest boundary pairs are a deterministic finite interface policy, not a claim
of a continuous globally optimal gap location.

Point contacts never create a new component alias, including reassigning a
one-sided frozen native portal to the other face, or connecting to a native line
inside the opposite point-touching face through a separate gap candidate. An
already recorded two-sided native route remains available. No seam may restore
positive-length space removed between P and Ω, including a removed strip's
outer-boundary segment. Full .25m non-barrier areal obstacle clearance, existing
barrier opening rules, complete coverage and road-centreline refusal are checked
before graph insertion. Background policy exceptions belong only to the
unchanged native line and are never granted to a new gap link.

## Actual defects and corrections before formal routes

The first 17-case author run had three failures. Two were implementation defects:
(1) a face-to-native-line gap candidate could bypass a point-only face junction;
(2) an interior-only DE9IM mask check missed a gap lying on the boundary of a
P-to-Ω removed strip. Both were reproduced and repaired, respectively by checking
the line's supporting face relation and by measuring the complete removed
portion outside legal Ω. The third was a fixture assumption: GEOS chose the
other endpoint of an equal-distance nearest boundary interval. The obstacle
fixture now blocks the full narrow gap and does not assume endpoint ordering.

Subsequent author checks found that copying frozen portals by coordinates alone
could reassign a one-sided native point-touch identity to another component.
Portal inheritance now checks source-face/component ownership. A regression
retains pre-existing two-sided native topology while refusing the one-sided case.

Independent reviewer `/root/connectivity_review` identified two further issues
before formal routes: a road-separated shared boundary was labelled accepted,
and writing an accepted external native gap endpoint could overwrite its tags.
The first now has `ROAD_PARTITION_NO_NEW_FREE_CROSSING`; the second uses one node
writer that preserves all original metadata and asserts unchanged coordinates.
Dedicated road-partition and `entrance=exit` metadata regressions pass.

The switch to delta-only reuse initially invalidated a test that expected an
already frozen split arc to occur again in the delta. The assertion now checks
the combined graph, and a separate test requires zero B2 delta arcs for an
already complete unchanged single face. This is an API assertion correction,
not evidence of a missing route arc.

The first synthetic F0/F1 route-choice fixture put its query on the boundary
opposite the deterministic nearest seam. It was corrected to align the specified
synthetic endpoints with that predeclared geometric seam, without changing any
seam threshold or real-map sample. The real solver then chooses a 7m route using
the 1m inferred seam for F0 and the unchanged 7.5m native detour for F1; the graph
hash remains unchanged between the two solves.

## Verification scope

The 23 connectivity author tests cover the thirteen requested relation families
plus parent curvature/direction/length, source alternatives, complete segment
obstacles, .25m near-obstacle clearance, P/Ω removal boundaries, frozen threshold
sensitivity, coverage, inference costs, graph reuse and native metadata. They
run only small synthetic graph searches, not the real APP or formal route
matrix. The frozen visibility and parallel-cost tests run alongside them.
Numeric rejection evidence keeps the first actual geometry for each rejection
class; a rejected certificate is never repaired by increasing a snap radius.

This author scope does not establish field passability, boundary accuracy,
real-map route improvements, UI behaviour or final package replay. Those are
separate parent-task and independent-review responsibilities.

## Freeze 2: independently demonstrated gap-interior fence defect

The first frozen implementation SHA256 was
`e26bb592349c1ede4bd66f247266d7427dc2bcd61d1865cbcf182b7c5d989c76`.
Its source and tests are retained as `stitch_method_freeze1_connectivity.py` and
`stitch_method_freeze1_tests.py`; the earlier 56-test receipt is unchanged.

After the seven independently reported fixtures passed, the reviewer found an
additional counterexample, retained in
`audits/independent_gap_fence_counterexample.json`. Two P boundaries at x=4 and
x=5 leave a 1m gap containing a fence at x=4.5. That fence is .5m from either P,
so it is absent from both face-local barrier lists. The common .15m line mask
has a .30m opening at a real gate at (4.5,10.15). The old B3 seam at y=10 passed
through that aperture .15m away from the actual gate and was incorrectly added
to the graph. The prior author and independent fixture passes did not cover
this gap-interior source barrier case.

Freeze 2 adds an exact original-barrier check over every full-source common
constraint with `kind=BARRIER`, independently of face proximity. It uses
`source_geometry` and the original `gates` records, accepting only point
intersections within the inherited .001m gate tolerance with the gate itself on
the source barrier. A missing, empty, invalid or non-linear/non-point original
barrier fails closed for new conditional links; a buffered mask cannot establish
its exact source line. This checker runs in both B3 admission and replay
validation. The existing common mask and any additional source barrier point
continue to apply; the fix does not grant a new gate or clearance exception.
B0/B1, the B2 graph construction and all original source geometries are unchanged.

Two additional author test methods cover the exact gate positive case, the .15m
off-gate and no-gate negative cases, missing complete source line in admission
and replay, and a true route around a fence end. The latter permits a seam .3m
beyond the fence end while retaining the existing .15m mask's rejection at .1m.
The new receipt is `stitch_method_freeze2_tests.json`; it records 25 connectivity
tests plus the unchanged 31 visibility and 2 cost tests, 58 in total. The root
was told to keep any old B3 pilot observations as invalid pre-fix observations;
this implementation role did not modify the isolated pilot worker or start a
formal APP route matrix.
