"""Conservative release scan. Reports locations/categories, never matched secret text."""
from pathlib import Path
import argparse,hashlib,json,re,datetime

SECRET=[('github_token',re.compile(r'gh[pousr]_[A-Za-z0-9_]{20,}')),('aws_key',re.compile(r'AKIA[A-Z0-9]{16}')),('private_key',re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----')),('credential_assignment',re.compile(r'''(?i)(?:api[_-]?key|security[_-]?code|access[_-]?token|password|secret)\s*[:=]\s*["']([A-Za-z0-9_./+\-=]{16,})["']'''))]
PRIVATE=[('private_local_path',re.compile(r'(?:[A-Za-z]:[\\/](?:Users|智慧城市和位置服务)[\\/]|'+r'/ho'+r'me/[^/]+/)')),('literal_coordinate_pair',re.compile(r'\[\s*-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}\s*\]'))]
DENIED={'.zip','.npz','.gz','.png','.jpg','.jpeg','.svg','.geojson','.gpkg','.pbf','.rdf','.ttl','.parquet','.db','.sqlite'}
def scan(root):
 rows=[];findings=[]
 for p in sorted(root.rglob('*')):
  if not p.is_file()or any(x in('.git','__pycache__')for x in p.relative_to(root).parts):continue
  rel=p.relative_to(root).as_posix();b=p.read_bytes();row={'path':rel,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};rows.append(row)
  if p.name.startswith('.env')or p.suffix.lower()in DENIED or len(b)>2000000:findings.append({'path':rel,'category':'RAW_GENERATED_SECRET_OR_LARGE_FILE'})
  try:text=b.decode('utf-8-sig')
  except UnicodeError:findings.append({'path':rel,'category':'NON_TEXT_NOT_APPROVED'});continue
  for category,pattern in SECRET+PRIVATE:
   for m in pattern.finditer(text):findings.append({'path':rel,'line':text.count('\n',0,m.start())+1,'category':category})
 return {'at':datetime.datetime.now().astimezone().isoformat(),'files':rows,'findings':findings,'scan_status':'PASS_NO_AUTOMATED_FINDINGS'if not findings else'REQUIRES_REVIEW','license_status':'USER_CODE_LICENSE_UNSPECIFIED; NO_RAW_MAP_DATA_OR_LEGACY_CODE_RELICENSED','first_push_approved':False,'limitations':'Conservative patterns cannot prove privacy or legal compliance. Exact inventory requires independent review and explicit user approval.'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=scan(a.root);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'files':len(r['files']),'findings':r['findings'],'status':r['scan_status']}));return 0 if not r['findings']else 1
if __name__=='__main__':raise SystemExit(main())
