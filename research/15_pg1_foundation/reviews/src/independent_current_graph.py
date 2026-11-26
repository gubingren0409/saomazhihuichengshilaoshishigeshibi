"""Compare current B3 inventory exports directly to immutable saved R1 result bytes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,zipfile
from pyproj import Transformer
from shapely.geometry import shape
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(os.environ.get('PG1_REVIEW_R1_ZIP',ROOT.parent/'PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip'))
project=Transformer.from_crs(4326,32651,always_xy=True).transform
out={'at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Source-to-derived UNKNOWN envelope lineage and exact saved B3 inventory bytes; no author code or solver invocation','scenes':[],'new_solver_calls':0}
with zipfile.ZipFile(BASE)as z:
    for folder in sorted((ROOT/'phase1/data').iterdir()):
        sid=folder.name;scene=json.loads((folder/'scene.json').read_text(encoding='utf8'));g=json.loads((folder/'current_graph.json').read_text(encoding='utf8'));summary=g['summary']
        raw=json.loads(z.read(f'data/scenes/{sid}/source.osm.json'));objs={f"{o['type']}/{o['id']}":o for o in raw['elements']};nodes={o['id']:project(o['lon'],o['lat'])for o in raw['elements']if o['type']=='node'}
        raw_render_ids={f['properties']['source_id']for f in scene['features']}
        unknown=scene['imported_only_features']
        for f in unknown:
            p=f['properties'];obj=objs[p['source_id']]
            assert p['source_id']not in raw_render_ids and p['source_geometry_available']is False and p['import_kind']=='UNKNOWN'
            assert p['geometry_basis']=='IMPORTED_ADAPTER_FALLBACK_BOUNDING_BOX_NOT_ORIGINAL_SOURCE_GEOMETRY'
            assert p['tags']==obj.get('tags',{})
            if obj['type']=='way':refs=obj.get('nodes',[])
            else:refs=[n for m in obj.get('members',[])if m['type']=='way'and f"way/{m['ref']}"in objs for n in objs[f"way/{m['ref']}"]['nodes']]
            xy=[nodes[n]for n in refs if n in nodes];assert xy
            expected=[min(x for x,y in xy)-.01,min(y for x,y in xy)-.01,max(x for x,y in xy)+.01,max(y for x,y in xy)+.01]
            assert max(abs(a-b)for a,b in zip(shape(f['geometry']).bounds,expected))<1e-6
        record={'scene_id':sid,'imported_unknown_envelopes':len(unknown)}
        if 'historical_run_id'not in summary:
            assert sid in ['sh-wukang','sh-newworld']
            assert all(not g[k]for k in ['interfaces','seams','portals','faces'])
            assert all(summary[k]is None for k in ['global_nodes','global_arcs','current_exact_interfaces','current_seam_candidates','current_accepted_seams'])
            record['saved_graph_status']='UNKNOWN_NOT_ZERO'
        else:
            member='runs/'+summary['path'].replace('\\','/').split('/runs/',1)[1]
            body=z.read(member);assert hashlib.sha256(body).hexdigest()==summary['sha256'];saved=json.loads(body)
            ce=saved['connectivity_evidence'];fn=saved['face_network']
            assert g['interfaces']==ce.get('interfaces',[]) and g['seams']==ce.get('seams',[])
            assert g['portals']==(ce.get('stitch_portals',[])or ce.get('portals',[]))
            assert g['faces']==(ce.get('faces')or fn.get('faces',[]))
            assert summary['global_graph_record']==saved['graph']
            assert summary['full_face_overlay_nodes']==fn['nodes']and summary['full_face_overlay_arcs']==fn['arcs']
            assert summary['seam_delta_nodes']==ce['nodes']and summary['seam_delta_arcs']==ce['arcs']
            assert summary['current_accepted_seams']==sum(s.get('accepted')is True for s in g['seams'])
            record.update(saved_graph_status='EXACT_SAVED_B3_INVENTORY',saved_member=member,saved_sha256=summary['sha256'],interfaces=len(g['interfaces']),seam_candidates=len(g['seams']),accepted_seams=summary['current_accepted_seams'],portals=len(g['portals']),faces=len(g['faces']),global_graph_edges='NOT_EXPORTED_NO_COLD_REBUILD')
        out['scenes'].append(record)
assert sum(r['imported_unknown_envelopes']for r in out['scenes'])==54
assert sum(r['saved_graph_status']=='EXACT_SAVED_B3_INVENTORY'for r in out['scenes'])==4
(ROOT/'reviews/independent_current_graph.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'scenes':6,'fixed_saved_B3_inventories':4,'graph_unknown_scenes':2,'derived_unknown_envelopes':54,'new_solver_calls':0}))
