"""Re-evaluate exactly the source segments, not full historical graph reconstruction."""
from experiment_core import *
from src.frozen_scene.native_adapter import Source
from src.frozen_scene.semantics import segment_decision,KEEP,REJECT
from shapely.geometry import box
from shapely.strtree import STRtree
D=ROOT/IDS['q6'];rows=list(csv.DictReader((D/'restored_native_edges.csv').open(encoding='utf-8-sig')))
manifest=json.loads((RUNTIME/'data/scene_manifest.json').read_text(encoding='utf-8'));sources={};indexes={};objects={};out=[];tick=time.perf_counter()
for r in rows:
 wid=int(r['source_id'].split('/')[1]);source=None
 for scene in manifest['scenes']:
  sid=scene['scene_id']
  if sid not in sources:sources[sid]=Source(json.loads((RUNTIME/scene['source_path']).read_text(encoding='utf-8')))
  if wid in sources[sid].ways:source=sources[sid];break
 if sid not in indexes:
  objects[sid],_=source.obstacles([]);indexes[sid]=STRtree([o['geometry']for o in objects[sid]])
 a,b=json.loads(r['native_nodes']);line=LineString([source.projected[a],source.projected[b]]);contacts=[objects[sid][int(i)]for i in indexes[sid].query(line,predicate='intersects')];tags=source.ways[wid].get('tags',{});ends=[source.nodes[n].get('tags',{})for n in(a,b)]
 s0=segment_decision(line,tags,contacts,'S0',native_nodes=(a,b),endpoint_tags=ends);s1=segment_decision(line,tags,contacts,'S1',native_nodes=(a,b),endpoint_tags=ends)
 out.append({'source_id':r['source_id'],'segment_index':r['segment_index'],'source_scene':sid,'S0':s0['status'],'S1':s1['status'],'S0_reasons':s0['reasons'],'S1_reasons':s1['reasons'],'status':'PASS'if s0['status']!=KEEP and s1['status']==KEEP else'FAIL','layer_scope':'Exact native segment only','geometry_length_m':line.length})
csvout(D/'grass_policy_recheck.csv',out)
grass={'id':'synthetic/grass','kind':'AREA','tags':{'landuse':'grass'},'geometry':box(0,0,10,10)};water={**grass,'id':'synthetic/water','tags':{'natural':'water'}};line=LineString([(1,5),(9,5)])
tests=[]
for name,tags,obs,expected in [('native_footway_in_grass',{'highway':'footway'},[grass],KEEP),('unmarked_line_in_grass',{},[grass],REJECT),('private_footway_in_grass',{'highway':'footway','access':'private'},[grass],REJECT),('footway_over_water_without_bridge',{'highway':'footway'},[water],REJECT)]:
 actual=segment_decision(line,tags,obs,'S1');tests.append({'name':name,'expected':expected,'actual':actual,'status':'PASS'if actual['status']==expected else'FAIL','data_role':'SYNTHETIC_UNIT_NOT_FIELD_OR_NEW_BUILDING'})
write(D/'outputs/grass_policy_unit_tests.json',tests)
record=base_row(IDS['q6'],'Q6-GRASS-CURRENT-FROZEN-POLICY-377','MULTI_FROZEN_SOURCES','','S0_S1_REEVALUATION','PASS'if all(r['status']=='PASS'for r in out)and all(t['status']=='PASS'for t in tests)else'FAIL');record.update(runtime_ms=(time.perf_counter()-tick)*1000,result={'source_segments':len(out),'S0_reject_S1_keep':sum(r['status']=='PASS'for r in out),'unit_tests':tests,'source_code':str((RUNTIME/'src/frozen_scene/semantics.py').relative_to(ROOT)),'source_code_sha256':hashlib.sha256((RUNTIME/'src/frozen_scene/semantics.py').read_bytes()).hexdigest(),'historical_full_graph_rebuilt':False},output_file='grass_policy_recheck.csv');append(IDS['q6'],record);write(D/'outputs/grass_policy_recheck_summary.json',record);print(json.dumps(record,ensure_ascii=False))
