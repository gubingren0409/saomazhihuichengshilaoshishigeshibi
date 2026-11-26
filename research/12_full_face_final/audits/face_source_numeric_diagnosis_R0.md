# R0 polygon/interface numerical diagnosis

This is a read-only implementation diagnosis of `runs/initial_app_pair/FULL_FACE.json`, not a new APP query or a change to any source geometry. The source file `src/face_geometry.py` remained at SHA256 `941648761f179e9c5cb93c38a79ec7970dc39a11f973499daef499accaeabc12` throughout.

The full machine evidence is `face_source_numeric_diagnosis_R0.json`, SHA256 `890dc9e6dc18f4c4682e2f3cbdfb52ad9dbd0545ff76e46f4fab15d4609f1f43`.

## Findings

For both actual museum faces, the serialized component and its parent Ω have identical vertex sets and normalized geometry hashes. They are topologically equal; their symmetric difference area and Hausdorff distance are zero. Their tiny reported area differences arise from coordinate/ring traversal order, not a different domain. The proposed `_road_parts` coordinate-drift explanation is therefore rejected for this run.

Boundary intersection coordinates returned by floating-point geometry operations are sometimes infinitesimally outside the polygon under the strict `covers` predicate. All affected interfaces in this run are derived line–face boundary intersection portals, not original registered doors or native nodes.

| Face | Interfaces | Strictly outside interfaces | Maximum interface–Ω distance | EPS-admitted visibility pairs subsequently rejected |
|---|---:|---:|---:|---:|
| relation/2153738 | 47 | 5 | 1.5863863436568492e-10 m | 34 |
| relation/2385771 | 379 | 99 | 2.028848462339517e-10 m | 14,491 |

The diagnostic re-enumerated the same tangent-filtered candidate pairs. Every one of the 34 and 14,491 tolerance-admitted pairs has at least one such outside interface. These counts exactly reproduce the respective run's `numeric_tolerance_admissions` and `constraint_rejections`. Some shallow-angle excursions have a larger outside line length than the endpoint's perpendicular error (up to 5.86743015595947e-7 m); this does not justify enlarging the polygon.

The current two-stage policy is inconsistent: the visibility roadmap initially accepts these pairs under EPS, while the common face callback strictly rejects them. R0 retains a valid, conservative finite graph, but this rejects intended source-supported interfaces and prevents an unqualified claim that every intended polygon visibility edge has been represented.

## Constraint-preserving repair proposal, not yet implemented here

Keep Ω, all holes, all raw coordinates, and the strict whole-edge callback unchanged. Canonicalize only an interface with a recorded original-line × face-boundary intersection certificate. Preserve its raw intersection, original edge/segment identity, and original arclength parameter. If numerical representation leaves it outside, select the nearest representable point along that same original source polyline on the strictly covered side, within an explicit numerical bound (proposed 1e-8 m). Record the corrected parameter and displacement, and use the actual split-segment endpoint as the graph coordinate. Reject an over-bound case or an isolated point-touch without a positive-length interior interval.

This conservative interface repair introduces no expanded walkable region and no cross-gap link. It must not move an original node or registered entrance. The visibility owner and independent reviewer must validate the final implementation and rerun affected results; this note does not claim that such a repair has already passed.
