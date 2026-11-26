"""Replay finite-graph cost/path certificates without calling a route solver."""
from pathlib import Path
import argparse,json,hashlib,math
import numpy as np

def main():
 p=argparse.ArgumentParser();p.add_argument('--probe',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();rows=[]
 for path in sorted((a.probe/'runs').glob('*.json')):
  r=json.loads(path.read_text(encoding='utf-8'));cert=a.probe/(r['case']+'_'+r['method']+'_certificate.npz')
  with np.load(cert,allow_pickle=False)as c:
   ids=c['ids'].tolist();ds=c['ds'];u=c['u'];v=c['v'];cost=c['cost'];idx={s:i for i,s in enumerate(ids)};finite=np.isfinite(ds[u]);assert np.all(np.isfinite(ds[v[finite]]));residual=float(np.max(ds[v[finite]]-ds[u[finite]]-cost[finite],initial=-np.inf));assert residual<1e-7;assert abs(ds[idx[r['start_id']]])<1e-7
   assert abs(ds[idx[r['door_id']]]-r['cost_m'])<1e-7;assert abs(sum(s['cost_m']for s in r['segments'])-r['cost_m'])<1e-7
   keys=list(zip(u.tolist(),v.tolist()));assert len(set(keys))==len(keys);weights=dict(zip(keys,cost.tolist()));nodepath=[r['segments'][0]['u']]+[s['v']for s in r['segments']];assert len(set(nodepath))==len(nodepath)
   for s in r['segments']:assert abs(weights[idx[s['u']],idx[s['v']]]-s['cost_m'])<1e-7
   assert nodepath[0]==r['start_id']and nodepath[-1]==r['door_id'];assert r['segments'][0]['xy'][0]==r['start_xy']and r['segments'][-1]['xy'][-1]==r['door_xy']
   rows.append({'invocation_id':r['invocation_id'],'nodes':len(ids),'arcs':len(keys),'dual_residual_m':residual,'primal_cost_m':r['cost_m'],'status':'PASS','certificate_sha256':hashlib.sha256(cert.read_bytes()).hexdigest()})
 assert len(rows)==8
 report={'status':'PASS','rows':rows,'new_solver_calls':0,'new_SSSP_calls':0,'scope':'Author certificate replay, finite source mask; source geometry and permissions inherited from fixed graph, independent review separate.'};a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'status':'PASS','rows':8,'new_solver_calls':0}))
if __name__=='__main__':main()
