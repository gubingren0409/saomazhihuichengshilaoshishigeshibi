import math

def distance_errors(edges,ds,dt,source,target,path=None,tol=1e-7):
 errors=[]
 if abs(ds[source])>tol or abs(dt[target])>tol:errors.append('ANCHOR_NOT_ZERO')
 for u,v,w in edges:
  if w<0:errors.append('NEGATIVE_WEIGHT')
  if math.isfinite(ds[u]) and ds[v]>ds[u]+w+tol:errors.append('FORWARD_BELLMAN')
  if math.isfinite(dt[v]) and dt[u]>w+dt[v]+tol:errors.append('REVERSE_BELLMAN')
 if path is not None:
  cost=0
  e={(u,v):w for u,v,w in edges}
  for u,v in zip(path,path[1:]):
   if(u,v)not in e:errors.append('PATH_EDGE_MISSING');break
   cost+=e[u,v]
  if abs(cost-ds[target])>tol:errors.append('PRIMAL_DUAL_GAP')
 return errors

def simple_forced_join(left,right):
 nodes=left+right
 return nodes if len(set(nodes))==len(nodes)else None
