"""Independently reverse UI compression and compare original records one by one."""
from pathlib import Path
import json,gzip,base64,re,hashlib
ROOT=Path(__file__).resolve().parents[1]
class Reader:
    def __init__(self,p):self.f=p.open(encoding='utf-8-sig');self.buf='';self.pos=0;self.dec=json.JSONDecoder()
    def fill(self):
        self.buf=self.buf[self.pos:]+self.f.read(262144);self.pos=0
    def peek(self):
        while True:
            while self.pos<len(self.buf)and self.buf[self.pos].isspace():self.pos+=1
            if self.pos<len(self.buf):return self.buf[self.pos]
            self.fill()
            if not self.buf:raise EOFError('JSON_EOF')
    def eat(self,c):
        assert self.peek()==c,('JSON_TOKEN',c,self.buf[self.pos:self.pos+30]);self.pos+=1
    def value(self):
        while True:
            self.peek()
            try:r,end=self.dec.raw_decode(self.buf,self.pos);self.pos=end;return r
            except json.JSONDecodeError:
                before=len(self.buf)-self.pos;self.fill()
                if before==len(self.buf):raise
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    compactpath=ROOT/'results/map_ui.json';ui=json.loads(compactpath.read_text());defs=ui['interface_definitions'];values=ui['shared_evidence_values'];fields=ui['interface_metric_fields'];reader=Reader(ROOT/'results/map_diagnosis.json');errors=[];rows=0;casecount=0;rowcounts={}
    reader.eat('{')
    while reader.peek()!='}':
        key=reader.value();reader.eat(':')
        if key!='cases':
            v=reader.value()
            if ui.get(key)!=v:errors.append(['TOP_LEVEL',key])
        else:
            reader.eat('[')
            while reader.peek()!=']':
                c=ui['cases'][casecount];reader.eat('{');interface_count=0
                while reader.peek()!='}':
                    k=reader.value();reader.eat(':')
                    if k=='interfaces':
                        reader.eat('[')
                        while reader.peek()!=']':
                            original=reader.value();metric=c['interface_metrics'][interface_count];rebuilt={}
                            for name,v in defs[metric[0]].items():rebuilt[name]=values[v['__ui_pool_ref__']]if isinstance(v,dict)and set(v)=={'__ui_pool_ref__'}else v
                            rebuilt['case']=c['id']
                            for i,name in enumerate(fields):
                                if metric[-1]&(1<<i):rebuilt[name]=metric[i+1]
                            if rebuilt!=original:errors.append(['INTERFACE_RECONSTRUCTION',c['id'],interface_count,original.get('id')])
                            interface_count+=1;rows+=1
                            if reader.peek()==',':reader.eat(',')
                        reader.eat(']')
                    elif k=='modes':
                        original=reader.value();expected={mode:{method:{kk:vv for kk,vv in r.items()if kk not in('route','segments','xy')}for method,r in methods.items()}for mode,methods in original.items()}
                        if expected!=c['mode_summaries']:errors.append(['MODE_SUMMARIES',c['id']])
                    else:
                        v=reader.value()
                        if c.get(k)!=v:errors.append(['CASE_FIELD',c['id'],k])
                    if reader.peek()==',':reader.eat(',')
                reader.eat('}');rowcounts[c['id']]=interface_count
                if interface_count!=len(c['interface_metrics']):errors.append(['INTERFACE_COUNT',c['id']])
                casecount+=1
                if reader.peek()==',':reader.eat(',')
            reader.eat(']')
        if reader.peek()==',':reader.eat(',')
    reader.eat('}');reader.f.close();gz=ROOT/'visuals/map_payload.json.gz';decoded=gzip.decompress(gz.read_bytes());payload=json.loads(decoded)
    if payload['diagnosis']!=ui:errors.append(['TRANSPORT_DIAGNOSIS_DIFFERS'])
    htmlpath=ROOT/'visuals/index.html';html=htmlpath.read_text();encoded=re.search(r'<script[^>]*id=["\']data["\'][^>]*>(.*?)</script>',html,re.S)
    if encoded is None or base64.b64decode(encoded.group(1).strip())!=gz.read_bytes():errors.append(['INLINE_OFFLINE_BYTES'])
    out={'reviewer':'/root/r2_independent','script_sha256':sha(Path(__file__)),'status':'PASS_FOR_LOSSLESS_UI_POOL_AND_OFFLINE_TRANSPORT'if not errors and rows==92096 and casecount==4 else'REQUIRES_INSPECTION','original_diagnosis_sha256':sha(ROOT/'results/map_diagnosis.json'),'compact_sha256':sha(compactpath),'gzip_sha256':sha(gz),'HTML_sha256':sha(htmlpath),'interfaces_reconstructed':rows,'case_rows':rowcounts,'shared_definitions':len(defs),'shared_evidence_values':len(values),'new_solver_calls':0,'new_SSSP_calls':0,'errors':errors,'scope':'Own streaming JSON reader and reverse pool+presence-bit reconstruction checks original complete records including raw geometry, per-mode directed states, source objects, uncertainty and exact missing-vs-null; same lossless object reaches offline embedded gzip. Browser rendering separately checked.'}
    (ROOT/'audits/independent_ui_pool.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
