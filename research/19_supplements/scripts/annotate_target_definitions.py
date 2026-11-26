from pathlib import Path
import csv,json
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q2-LOCAL-ENTRY-AUDIT-R1';rows=list(csv.DictReader((D/'target_definition_comparison.csv').open(encoding='utf-8-sig')))
for r in rows:
 r.update(target_definition_is_registered_condition=r['target_definition']=='REGISTERED_DOOR',target_source_id_equals_registered_door=r['target_id']==r['entrance_id'],target_coordinate_coincides_with_registered_door=float(r['endpoint_to_registered_door_m'])<=1e-6,legacy_target_is_registered_door_column_meaning='Experimental branch label only, not the native source object identity; library outside-control is the same registered source point')
with(D/'target_definition_comparison_annotated.csv').open('w',encoding='utf-8-sig',newline='')as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print('TARGET_DEFINITION_IDENTITY_ANNOTATED',len(rows))
