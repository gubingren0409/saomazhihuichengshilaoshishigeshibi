# Final R2 fixed local-face mechanism replay

Status: PASS. Seven fixed pairs, not seven entrances. APP solver calls: 0. Actual repeated local shortest queries: 7. Elapsed: 102.121s.

All seven R2 full-face lengths are exactly equal to the retained R0 lengths; all output segment-conflict lists are empty. Six of seven use positive length outside the old geometric 3m band.

| Pair | BAND-C m | FULL_FACE m | Reduction m | Reduction % | Outside old band m |
|---|---:|---:|---:|---:|---:|
| sh-huangpu-01/relation/2153738/1 | 803.049 | 525.909 | 277.140 | 34.51 | 195.586 |
| sh-huangpu-01/relation/2153738/2 | 944.994 | 416.793 | 528.201 | 55.89 | 198.661 |
| sh-huangpu-01/relation/2153738/3 | 494.596 | 368.679 | 125.916 | 25.46 | 179.330 |
| sh-huangpu-01/relation/2385771/1 | 201.390 | 163.723 | 37.667 | 18.70 | 157.546 |
| sh-huangpu-01/relation/2385771/2 | 184.382 | 160.005 | 24.377 | 13.22 | 144.731 |
| sh-library/way/1160136226/1 | 39.197 | 33.580 | 5.617 | 14.33 | 9.984 |
| sh-library/way/1160136226/2 | 41.394 | 38.859 | 2.534 | 6.12 | 0.000 |

Old local branch: same-Omega BAND-C, not unchanged APP baseline. North 6/79,362 old rows and south 4/18,740 are excluded by the same domain/common-rule filter; library excludes 0/5,435. Each per-pair JSON preserves these counts and the source edge IDs.

face_pairs_R1 names the first replay run; source code is final R2 fc3c...

Final visibility source SHA256: fc3c6220f8ac8f97847f01a355deba6c29680850ad44ec1f9a139c60cac5d56c
Fixed pair lock SHA256: 68bbcf8a67c377260870d27f288cd0b679b0e21094558f9bb9706073cdd7c083
R2 replay summary SHA256: 8554d634bd209b925dfacd66e692fec7edfb24b04bc0d877fad0078eaef05b43

This author replay is separate from the independent reference, the final APP matrix, and the clean-package replay.
