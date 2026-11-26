import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.planner import plan,scene_list
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--request',type=Path);p.add_argument('--list',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
    if not a.list:
        if not a.request:p.error('--request required unless --list is used')
        body=json.loads(a.request.read_text(encoding='utf-8'))
        if not isinstance(body,dict):p.error('Request JSON must be an object')
    result=scene_list() if a.list else plan(body)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text,encoding='utf-8')
    else:print(text)
