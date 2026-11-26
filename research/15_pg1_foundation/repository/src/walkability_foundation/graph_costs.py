"""Frozen F0/F1 costs; parallel options remain alternatives, never additive."""
import numpy as np

def batch_costs(option_groups,penalty):
    if penalty not in(0,1):raise ValueError('Only frozen F0/F1 extra penalties 0/1 are allowed')
    counts=np.array([len(x)for x in option_groups],dtype=np.int64)
    if np.any(counts==0):raise ValueError('Empty option group')
    flat=np.array([[o[0],o[1]]for group in option_groups for o in group],dtype=float)
    if not np.all(np.isfinite(flat))or np.any(flat<0)or np.any(flat[:,1]>flat[:,0]+1e-7):raise ValueError('Invalid length/hypothesis contract')
    offsets=np.r_[0,np.cumsum(counts)[:-1]]
    return np.minimum.reduceat(flat[:,0]+penalty*flat[:,1],offsets)

def scalar_costs(option_groups,penalty):
    return np.array([min(o[0]+penalty*o[1]for o in group)for group in option_groups])
