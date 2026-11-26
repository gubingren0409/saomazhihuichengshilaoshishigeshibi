# Data and evaluation contract

Each source/scene must bind building identity and holes, registered entrance identity/role/source linkage, separate public/opening status, pedestrian line topology, sidewalks/crossings, pedestrian area interior/rings, barriers/permissions/levels, coordinate semantics, coverage, license and timestamp. An official building polygon alone does not qualify an entrance or route reference.

Use per-dimension GOLD/SILVER/BRONZE with evidence; not a universal dataset tier. Empty responses caused by a CRS/query error are NO_OBSERVATION, not real zero objects. An observed sidewalk polygon is not a verified connected pedestrian network. A metadata extent must not be drawn as an observed building.

Four distinct scopes remain explicit: source coverage, actually inspected objects, routing admission and display viewport. Missing tag values are UNKNOWN; unknown is separate from known conflict and from a planning assumption. Derived UNKNOWN boxes/buffers are not source geometries.

Grouping uses complete buildings/sites, shared ways/relations, overlapping/adjacent dependent street networks and repeated snapshots. Conservative city-level groups in discovery are proposals, not proof of independence; a distance buffer alone cannot establish network independence. Preserve exact shared IDs and geometry checks. Freeze neither validation nor blind splits before G2.

Report micro denominators for source records/edges/queries and macro denominators for eligible independent sites/groups. Shared scene-records and repeated queries do not become independent buildings. Do not compute accuracy/IoU or true navigation success without the corresponding independent reference. Discovery previews are exposed; a later blind evaluation needs independent curation and protected references.
