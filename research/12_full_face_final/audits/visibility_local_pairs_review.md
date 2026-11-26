# Fixed local-face mechanism comparison (R0)

These seven prelocked point pairs test full-face geometry, not entrance arrival, independent blind testing, current public access or global continuous optimality. No APP solver calls were consumed.

The same Ω and full-scene constraints are applied to old frozen band rows and new full-face segments. Therefore the local old branch is **BAND-C**, not a replacement for the original APP EDGE_BAND runs. Source-only full constraints do not import APP native access exceptions.

| Pair | BAND-C m | FULL_FACE m | Reduction m | Reduction % | Outside old 3m band m | Conflicts |
|---|---:|---:|---:|---:|---:|---:|
| sh-huangpu-01/relation/2153738/1 | 803.048693 | 525.908794 | 277.139899 | 34.511 | 195.586140 | 0 |
| sh-huangpu-01/relation/2153738/2 | 944.994499 | 416.793250 | 528.201250 | 55.895 | 198.660866 | 0 |
| sh-huangpu-01/relation/2153738/3 | 494.595531 | 368.679363 | 125.916168 | 25.458 | 179.329602 | 0 |
| sh-huangpu-01/relation/2385771/1 | 201.390346 | 163.722975 | 37.667370 | 18.704 | 157.545876 | 0 |
| sh-huangpu-01/relation/2385771/2 | 184.382427 | 160.005361 | 24.377066 | 13.221 | 144.730859 | 0 |
| sh-library/way/1160136226/1 | 39.197120 | 33.579785 | 5.617335 | 14.331 | 9.984202 | 0 |
| sh-library/way/1160136226/2 | 41.393884 | 38.859408 | 2.534476 | 6.123 | 0.000000 | 0 |

All seven old/new local paths exist; all seven shorten; six of seven new paths have positive length outside the geometric old 3m band. Query 7 is a direct-visibility improvement within the band. Every output segment passes face_edge_conflicts; all seven numeric_tolerance_admissions are zero. Thus this R0 mechanism evidence is not directly affected by the APP boundary-intersection portal numerical rejection diagnosed separately.

The old same-Ω row filter excludes north 6/79,362 rows (common road rule), south 4/18,740 (Ω/component coverage), library 0/5,435. These exclusions are disclosed in every per-pair JSON; the comparison is not claimed to be unchanged raw old-edge graph.

Actual elapsed: 101.049278s; APP calls: 0; actual local shortest queries: 7.

## Fixed inputs and code hashes

- data/face_pairs_lock.json: SHA256 68bbcf8a67c377260870d27f288cd0b679b0e21094558f9bb9706073cdd7c083
- data/face_selection_lock.json: SHA256 a3651f35953b879c2618db9cabf8c1c3397b6491fb07e93e90a29dbc91189258
- src/face_visibility.py: SHA256 c254cef623b958358d0a68402037a6a8e563f9dc11a68e9dbd592c704bc33f54
- src/face_geometry.py: SHA256 941648761f179e9c5cb93c38a79ec7970dc39a11f973499daef499accaeabc12
- scripts/run_face_pairs.py: SHA256 91b2e55581baf5fb862560afbf2cc4857c02989e53be389c0cc0678c41c32042
- runs/face_pairs/summary.json: SHA256 8d6b95327dfb80d13e85159e14ec24f33c0500fe3a156197d44f9bc434f4cf9b
