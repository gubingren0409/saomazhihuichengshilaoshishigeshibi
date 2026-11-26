"""Delegating instrumentation only; no original source or return values changed."""
from pathlib import Path
import time
from shapely.strtree import STRtree
def install_phase_timers():
 phases={};original_bytes=Path.read_bytes;original_text=Path.read_text;original_index=STRtree.__init__
 def read_bytes(p,*a,**kw):
  t=time.perf_counter()
  try:return original_bytes(p,*a,**kw)
  finally:phases['read_ms']=phases.get('read_ms',0)+(time.perf_counter()-t)*1000
 def read_text(p,*a,**kw):
  t=time.perf_counter()
  try:return original_text(p,*a,**kw)
  finally:phases['read_ms']=phases.get('read_ms',0)+(time.perf_counter()-t)*1000
 def index(obj,*a,**kw):
  t=time.perf_counter()
  try:return original_index(obj,*a,**kw)
  finally:phases['index_ms']=phases.get('index_ms',0)+(time.perf_counter()-t)*1000
 Path.read_bytes=read_bytes;Path.read_text=read_text;STRtree.__init__=index
 return phases
