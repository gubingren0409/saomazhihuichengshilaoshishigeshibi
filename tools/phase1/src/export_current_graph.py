"""Export existing R1 B3 graph inventories/interfaces without importing a solver.

No graph is constructed. Whole global graphs not present as exports remain
NOT_EXPORTED; absence of a formal result is UNKNOWN, never a zero-edge claim.
"""
import argparse, collections, gzip, hashlib, json
from pathlib import Path

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb')as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':')),encoding='utf8')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--source-root',type=Path,required=True);ap.add_argument('--runtime',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    old=a.source_root.resolve(); runtime=a.runtime.resolve();out=a.out.resolve()
    if out==old or old in out.parents or out==runtime or runtime in out.parents:raise ValueError('ISOLATED_OUTPUT_REQUIRED')
    if sha(a.baseline)!='d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed':raise ValueError('FIXED_FINAL_R1_REQUIRED')
    manifest={r['path']:r['sha256']for r in read(old/'MANIFEST_SHA256.json')['files']}
    rel='data/connectivity/mechanism_queries_lock.json'
    if sha(old/rel)!=manifest[rel]:raise ValueError('MECHANISM_SCENE_LOCK_SHA_MISMATCH')
    mech={r['mechanism_id']:r['scene_id']for r in read(old/rel)['selected']}
    registry=[json.loads(l)for l in (runtime/'results/formal_registry.jsonl').read_text(encoding='utf8').splitlines()]
    scene_index=read(out/'scene_index.json');summaries=[]
    for scene in scene_index:
        ident=scene['scene_id']; folder=out/'data'/ident;hist=read(folder/'historical_route.json');path=hist.get('path');expected=hist.get('sha256');scope='HISTORICAL_APP_RESULT'
        if not path:
            choices=[r for r in registry if mech.get(r.get('request',{}).get('mechanism_id'))==ident and r.get('request',{}).get('connectivity_mode')=='CONDITIONAL_SEAMS'and r.get('request',{}).get('seam_max_m',2)==2]
            choices.sort(key=lambda r:r.get('path',''),reverse=True)
            if choices:path=str(runtime/choices[0]['path']);expected=choices[0]['result_sha256'];scope='HISTORICAL_MECHANISM_RESULT_NOT_APP_ENTRANCE_TASK'
        face_ids=[f['source_id']for f in read(old/'data/connectivity'/f'{ident}_faces.json')]
        if not path:
            summary={'scene_id':ident,'current_graph_result_status':'NO_FORMAL_CURRENT_RESULT_FOUND; INSTANTIATION_UNKNOWN','full_global_graph_edges':'NOT_EXPORTED','global_nodes':None,'global_arcs':None,'current_exact_interfaces':None,'current_seam_candidates':None,'current_accepted_seams':None,'source_complete_face_inventory_count':len(face_ids),'source_complete_face_ids':face_ids,'face_inventory_is_not_proof_of_instantiated_graph':True,'old_r4_mapped_edges':scene['frozen_mapped_edge_count'],'fresh_solver_calls':0,'vg_rebuilds':0}
            write(folder/'current_graph.json',{'summary':summary,'interfaces':[],'seams':[],'portals':[],'faces':[]});summaries.append(summary);continue
        if sha(path)!=expected:raise ValueError('HISTORICAL_GRAPH_RESULT_SHA_MISMATCH')
        d=read(path);ce=d.get('connectivity_evidence',{});fn=d.get('face_network',{});interfaces=ce.get('interfaces',[]);seams=ce.get('seams',[]);portals=ce.get('stitch_portals',[])or ce.get('portals',[])
        actual_faces=ce.get('faces',[])or fn.get('faces',[])
        summary={'scene_id':ident,'current_graph_result_status':'EXISTING_B3_RESULT_READ_ONLY','evidence_scope':scope,'path':path,'sha256':expected,'historical_run_id':d['run_id'],'historical_result_status':d['status'],'mode':d.get('connectivity_mode'),'full_global_graph_edges':'NOT_EXPORTED; NO_COLD_RECONSTRUCTION','global_graph_record':d.get('graph'),'source_base_graph_record':{k:v for k,v in d.get('versions',{}).get('source',{}).items()if k in ['combined_graph_nodes','combined_graph_arcs','mapped_edge_rows','native_kept_segments']},'full_face_overlay_nodes':fn.get('nodes'),'full_face_overlay_arcs':fn.get('arcs'),'seam_delta_nodes':ce.get('nodes'),'seam_delta_arcs':ce.get('arcs'),'old_area_ids':ce.get('old_area_ids'),'added_source_complete_area_ids':ce.get('added_area_ids'),'actual_current_face_ids':[f['source_id']for f in actual_faces],'actual_current_face_count':len(actual_faces),'source_complete_face_inventory_count':len(face_ids),'source_complete_face_ids':face_ids,'current_exact_interfaces':len(interfaces),'current_exact_entered_graph':sum(r.get('entered_graph')is True for r in interfaces),'current_seam_candidates':len(seams),'current_accepted_seams':sum(r.get('accepted')is True for r in seams),'current_rejected_seams':sum(r.get('accepted')is False for r in seams),'current_portal_records':len(portals),'seam_max_m':ce.get('seam_max_m'),'full_common_sha256':ce.get('full_common_sha256'),'old_r4_mapped_edges':scene['frozen_mapped_edge_count'],'source_crs':'EPSG:4326','working_crs':'EPSG:32651','fresh_solver_calls':0,'vg_rebuilds':0,'scope_note':'Full-face overlay, exact interfaces and seam delta counts are different inventories and must not be summed as a unique global graph.'}
        write(folder/'current_graph.json',{'summary':summary,'interfaces':interfaces,'seams':seams,'portals':portals,'faces':actual_faces})
        lineage=collections.defaultdict(lambda:{'exact_interface_ids':[],'accepted_seam_ids':[],'rejected_seam_ids':[]})
        for r in interfaces:
            for k in set(r.get('source_ids',[])+r.get('source_area_ids',[])):lineage[k]['exact_interface_ids'].append(r.get('id'))
        for r in seams:
            for k in set(r.get('source_ids',[])+r.get('source_area_ids',[])):lineage[k]['accepted_seam_ids'if r.get('accepted')else'rejected_seam_ids'].append(r.get('id'))
        with gzip.open(folder/'current_graph_object_lineage.jsonl.gz','wt',encoding='utf8')as f:
            for k,v in sorted(lineage.items()):f.write(json.dumps({'scene_id':ident,'source_id':k,'historical_run_id':d['run_id'],'result_sha256':expected,**v},separators=(',',':'))+'\n')
        summaries.append(summary);print(ident,summary['actual_current_face_count'],len(interfaces),len(seams),scope,flush=True)
    write(out/'current_graph_inventory.json',summaries)
if __name__=='__main__':main()
