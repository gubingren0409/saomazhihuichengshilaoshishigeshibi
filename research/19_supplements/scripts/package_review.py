"""Seal the completed new task only; no historical data/model archive duplication."""
from pathlib import Path
import json,csv,hashlib,zipfile,datetime
ROOT=Path(__file__).resolve().parents[1];delivery=ROOT/'delivery';delivery.mkdir(exist_ok=True);man=ROOT/'manifests';man.mkdir(exist_ok=True)
assert json.loads((ROOT/'audit/validation.json').read_text(encoding='utf-8'))['status']=='PASS'
name='PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115_REVIEW.zip';dest=delivery/name
assert not dest.exists(),'FIXED_PACKAGE_EXISTS; do not overwrite a sealed review archive'
checksum_names={'manifests/FILE_SHA256.csv','manifests/ALL_NEW_FILES_SHA256.csv','manifests/PACKAGE_MEMBERS.csv'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def included(p):
 rel=p.relative_to(ROOT);parts=rel.parts
 if parts[0]=='delivery'or'__pycache__'in parts or'.git'in parts:return False
 if p.name=='.env'or p.suffix in('.pyc','.pkl','.pickle')or p.name.endswith('.tmp'):return False
 if parts[0]in('frozen_runtime','medium_runtime')and('runs'in parts or'derived_graphs'in parts):return False
 if parts[0]=='replay_runs':return False
 return True
policy='''# 封包范围

本ZIP含新代码、必要6裁片/冻结核心、两裁片派生输入、原始观测与主次版本、表、图、报告和核验记录。现有大归档/模型不重复复制，以SHA及成员索引引用；Q6全历史复算依赖原工程，不能声称全部旧实验离线自包含。当前门请求的源数据/核心已包含，可直接真实求路。

运行时runs/derived_graphs、独立重放输出、字节码和delivery目录不装入。没有凭据、浏览器配置、字体或模型pickle。ALL_NEW_FILES列出封包时新增工作文件及是否装入，包含缓存的SHA；所有校验清单自身和封包之后产生的外部回执不作循环自指。FILE_SHA256列出实际装入的非校验清单文件；清单字节本身由固定ZIP SHA与CRC绑定。ZIP及包外复验回执另有DELIVERY_SHA256SUMS。

复验是作者新进程/干净解包交叉检查，不是独立人员或现场认证。
'''
(ROOT/'PACKAGING_POLICY.md').write_text(policy,encoding='utf-8')
all_files=[p for p in sorted(ROOT.rglob('*'))if p.is_file()and p.relative_to(ROOT).parts[0]!='delivery'and p.relative_to(ROOT).as_posix()not in checksum_names]
records=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p),'included_in_review_zip':included(p),'exclusion_reason':''if included(p)else'Runtime cache/replay/bytecode/private-config guard; not needed for offline review'}for p in all_files]
def csvout(p,rows,fields):
 with p.open('w',encoding='utf-8-sig',newline='')as f:w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
csvout(man/'ALL_NEW_FILES_SHA256.csv',records,['path','bytes','sha256','included_in_review_zip','exclusion_reason'])
members=[r for r in records if r['included_in_review_zip']];csvout(man/'FILE_SHA256.csv',members,['path','bytes','sha256']);csvout(man/'PACKAGE_MEMBERS.csv',members,['path','bytes','sha256'])
to_pack=[p for p in sorted(ROOT.rglob('*'))if p.is_file()and included(p)]
with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
 for p in to_pack:z.write(p,p.relative_to(ROOT).as_posix())
with zipfile.ZipFile(dest)as z:
 bad=z.testzip();assert bad is None,bad
 assert len(z.namelist())==len(set(z.namelist()))
 assert all(not n.startswith(('/','\\'))and'..'not in Path(n).parts for n in z.namelist())
digest=sha(dest);(delivery/'REVIEW_SHA256.txt').write_text(digest+'  '+name+'\n',encoding='utf-8')
record={'timestamp':datetime.datetime.now().astimezone().isoformat(),'zip':str(dest),'sha256':digest,'bytes':dest.stat().st_size,'members':len(to_pack),'CRC':'PASS','author_only_not_independent_reviewer':True,'status':'PASS'};(delivery/'PACKAGING_RECEIPT.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(record,ensure_ascii=False))
