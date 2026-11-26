import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.planner import plan,scene_list
from src.mechanism import plan_mechanism
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--request',type=Path);p.add_argument('--list',action='store_true');p.add_argument('--output',type=Path);p.add_argument('--area-routing',choices=['FULL_FACE']);p.add_argument('--connectivity-mode',choices=['FROZEN_FULL_FACE','SOURCE_COMPLETE','EXACT_STITCH','CONDITIONAL_SEAMS']);p.add_argument('--mechanism',action='store_true');a=p.parse_args()
    if not a.list:
        if not a.request:p.error('--request required unless --list is used')
        body=json.loads(a.request.read_text(encoding='utf-8'))
        if not isinstance(body,dict):p.error('Request JSON must be an object')
    if not a.list and a.area_routing:body['area_routing']=a.area_routing
    if not a.list and a.connectivity_mode:body['connectivity_mode']=a.connectivity_mode
    result=scene_list() if a.list else plan_mechanism(body)if a.mechanism else plan(body)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text,encoding='utf-8')
    else:print(text)
