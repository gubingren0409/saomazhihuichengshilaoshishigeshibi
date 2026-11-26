"""Correct the experimental intervention, not the frozen route algorithm."""
from pathlib import Path
import json,hashlib,datetime
ROOT=Path(__file__).resolve().parents[1];source=(ROOT/'scripts/run_entries_and_closures.py').read_text(encoding='utf-8')
source=source.replace('def closure_experiments(prepared,req,graph,baseline,index):','def closure_experiments(prepared,req,graph,baseline,index,run_prefix="Q7"):')
source=source.replace("s['layer']=='native'and s.get('edge_id')and s['length_m']>1]","s['layer']=='native'and s.get('edge_id')and s['length_m']>1 and s.get('tags',{}).get('highway')in{'footway','path','pedestrian','steps'}]")
source=source.replace('middle native baseline segment;','middle source-tagged footway/path/pedestrian/steps segment; selection before corrected outcomes;')
source=source.replace("f'outputs/dynamic_scenarios_{index}.json'","f'outputs/dynamic_scenarios_{run_prefix}_{index}.json'")
source=source.replace("f'Q7-{index}-{state}-{repeat}'","f'{run_prefix}-{index}-{state}-{repeat}'")
source=source.replace("f'Q7-NATIVE-API-CONTROL-{index}'","f'{run_prefix}-NATIVE-API-CONTROL-{index}'").replace("f'outputs/Q7-NATIVE-API-CONTROL-{index}.json'","f'outputs/{run_prefix}-NATIVE-API-CONTROL-{index}.json'")
p=ROOT/'scripts/run_entries_and_closures_v2.py';p.write_text(source,encoding='utf-8');compile(source,str(p),'exec')
record={'timestamp':datetime.datetime.now().astimezone().isoformat(),'reason':'Original museum S2 selected median native edge, but native includes road axes; selected way/1338361263 was residential. Protocol requires a native walkway. Library chosen way/1219527813 already footway.','correction':'Keep same museum registered south door, start, F1, graph and constraints; choose middle eligible source-tagged footway/path/pedestrian/steps >1m from the frozen baseline, before corrected state outcomes','selected_corrected_source_known_from_baseline':'way/178737605, footway','historical_or_frozen_core_modified':False,'original_museum_stress_test_retained':True,'results_not_method_improvement':'Closing a different eligible edge is a corrected intervention; changes cannot be called algorithm optimization','new_source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'run_prefix':'Q7-A1-NATIVE-WALKWAY','must_run_after_active_Q8_worker_finishes':True}
(ROOT/'audit/Q7_WALKWAY_INTERVENTION_CORRECTION_PROTOCOL.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(record)
