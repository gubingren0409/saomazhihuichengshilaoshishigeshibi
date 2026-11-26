"""Export actual two-axis region objects and route segments without duplicating F1 geometry."""
import gzip,json,hashlib
import networkx as nx
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf8'))
def main():
    index=[]
    for folder in sorted((ROOT/'data/predictions').iterdir()):
        if not folder.is_dir():continue
        for name in ['M1-C','F0']:
            p=folder/(name+'.json')
            if not p.exists():continue
            d=read(p);s=d['surface'];out=ROOT/'data/regions'/folder.name/(name+'.geojson.gz');out.parent.mkdir(parents=True,exist_ok=True)
            with gzip.open(ROOT/d['graph']['graph_path'],'rt',encoding='utf8') as f:record=json.load(f)
            graph=nx.Graph();graph.add_nodes_from(n['id'] for n in record['nodes']);graph.add_edges_from((e['u'],e['v']) for e in record['edges'])
            interfaces={x['id'] for x in record['interfaces']};labels={}
            for k,component in enumerate(sorted(nx.connected_components(graph),key=lambda a:min(a))):
                access='WEAK_INTERFACE_PRESENT_NOT_DIRECTIONAL_OR_PUBLIC_PROOF' if component & interfaces else 'DISCONNECTED'
                for ident in component:labels[ident]=(f'weak_graph_component/{k}',access)
            features=[]
            for c in s['cells']:
                ident=c['region_id'];component,access=labels.get(ident,(None,'NOT_ADMITTED_TO_GRAPH'))
                props={k:v for k,v in c.items() if k!='geometry'}
                props.update(geometry_component_id=c['component_id'],derived_weak_graph_component_id=component,network_access=access,
                             graph_provenance_sha256=record['graph_sha256'],constraint_id_namespace='ORIGINAL_SOURCE_ID_RESOLVED_BY_CONTRACT_SOURCE_ID')
                features.append({'type':'Feature','id':ident,'geometry':c['geometry'],'properties':props})
            data={'type':'FeatureCollection','crs':{'type':'name','properties':{'name':'EPSG:32651'}},'surface_sha256':s['sha256'],'domain':s['domain'],
                  'features':features}
            with gzip.GzipFile(filename=str(out),mode='wb',mtime=0) as f:f.write(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode())
            index.append({'id':folder.name,'method':name,'path':out.relative_to(ROOT).as_posix(),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'surface_sha256':s['sha256']})
            if name=='F0':index.append({'id':folder.name,'method':'F1','geometry_alias':out.relative_to(ROOT).as_posix(),'surface_sha256':s['sha256'],'reason':'Identical cells; only finite route costs differ'})
        out=ROOT/'data/routes'/folder.name;out.mkdir(parents=True,exist_ok=True)
        for p in sorted(folder.glob('*.json')):
            d=read(p);data={k:d[k] for k in ('input_id','method','lambda_value','query_sha256','constraint_sha256','routes','base_routes')}
            with gzip.GzipFile(filename=str(out/(p.stem+'.json.gz')),mode='wb',mtime=0) as f:f.write(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode())
    (ROOT/'data/regions/index.json').write_text(json.dumps(index,indent=2),encoding='utf8')
    print('region records',len(index))
if __name__=='__main__':main()
