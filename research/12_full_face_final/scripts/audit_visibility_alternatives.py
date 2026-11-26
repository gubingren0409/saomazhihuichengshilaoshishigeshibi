"""Author post-run audit of saved alternatives; never calls the route solver.

The frozen R1 overlay's in-process audit counters classify only 'assumed' as a
penalized layer. They are NOT evidence of absent F1 competition. This external
receipt uses all actual APP hypothesis layers, without modifying frozen src.
"""
from pathlib import Path
import argparse,gzip,hashlib,json,math

ROOT=Path(__file__).resolve().parents[1]
HYPOTHESIS={'inferred','assumed','unknown'}
REPORT_RESOLUTION_M=1e-8  # reporting only; does not change any planner choice


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def key(segments,multiplier):
    length=sum(s['length_m']for s in segments)
    hypothetical=sum(s['length_m']for s in segments if s['layer']in HYPOTHESIS)
    return length+(multiplier-1)*hypothetical,hypothetical,length


def signature(segments):
    return sorted({(s['layer'],s.get('geometry_kind',''))for s in segments})


def audit(path,receipt_path,output):
    before=sha(path);receipt=read(receipt_path)
    if before!=receipt['derived_overlay_sha256']:raise ValueError('Saved overlay SHA does not match preprocessing receipt')
    counts={'arcs':0,'arcs_with_multiple_options':0,'options':0,'arcs_with_different_layer_or_geometry':0,
            'F0_canonical_only_would_lose_F1':0,'F0_geometric_winner_differs_from_F1':0,
            'canonical_F1_excess_above_report_resolution':0,'F0_vs_F1_cost_difference_above_report_resolution':0}
    max_loss=0.
    examples=[];layer_options={}
    with gzip.open(path,'rt',encoding='utf-8')as stream:
        for line in stream:
            row=json.loads(line)
            if row['kind']!='arc':continue
            counts['arcs']+=1;options=row.get('routing_alternatives',[row['segments']]);counts['options']+=len(options)
            for option in options:
                label=json.dumps(signature(option),ensure_ascii=False)
                layer_options[label]=layer_options.get(label,0)+1
            if len(options)<2:continue
            counts['arcs_with_multiple_options']+=1
            if len({json.dumps(signature(o))for o in options})>1:counts['arcs_with_different_layer_or_geometry']+=1
            f0=min(options,key=lambda ss:key(ss,1));f1=min(options,key=lambda ss:key(ss,2))
            canonical=row['segments'];loss=key(canonical,2)[0]-key(f1,2)[0]
            max_loss=max(max_loss,loss)
            if loss>0:counts['F0_canonical_only_would_lose_F1']+=1
            if key(f0,2)>key(f1,2):counts['F0_geometric_winner_differs_from_F1']+=1
            if loss>REPORT_RESOLUTION_M:counts['canonical_F1_excess_above_report_resolution']+=1
            if key(f0,2)[0]-key(f1,2)[0]>REPORT_RESOLUTION_M:counts['F0_vs_F1_cost_difference_above_report_resolution']+=1
            if (loss>0 or key(f0,2)>key(f1,2))and len(examples)<20:
                examples.append({'u':row['u'],'v':row['v'],'options':len(options),'canonical_signature':signature(canonical),
                                 'canonical_F0_m':key(canonical,1)[0],'canonical_F1_m':key(canonical,2)[0],
                                 'F1_winner_signature':signature(f1),'F1_cost_m':key(f1,2)[0],
                                 'canonical_only_F1_excess_m':loss})
    result={'role':'AUTHOR_EXTERNAL_ALTERNATIVE_AUDIT_NOT_INDEPENDENT_REVIEW','source_overlay':str(path.relative_to(ROOT)),
            'source_overlay_sha256':before,'preprocessing_receipt':str(receipt_path.relative_to(ROOT)),
            'preprocessing_receipt_sha256':sha(receipt_path),'counts':counts,'option_layer_signatures':layer_options,'examples':examples,
            'penalized_layers':sorted(HYPOTHESIS),'APP_solver_calls':0,'src_modified':False,
            'report_resolution_m':REPORT_RESOLUTION_M,'maximum_canonical_only_F1_excess_m':max_loss,
            'raw_positive_difference_caveat':'Raw >0 counts include floating summation differences; do not describe sub-resolution differences as material F1 improvements',
            'obsolete_in_process_counters':'assumed-only F1 competition counters NOT_USABLE_AS_NO_COMPETITION_EVIDENCE',
            'scope':'Saved full-face overlay alternatives only; source/local graph alternatives merged later by planner may add options',
            'status':'PASS'if before==sha(path)else'FAIL_INPUT_CHANGED'}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'output':str(output.relative_to(ROOT)),**counts},ensure_ascii=False))


def self_test():
    for layer in HYPOTHESIS:
        short=[{'layer':layer,'length_m':8.}];long=[{'layer':'derived','length_m':10.}]
        assert min([short,long],key=lambda ss:key(ss,1))==short
        assert min([short,long],key=lambda ss:key(ss,2))==long
        same=[{'layer':'derived','length_m':8.}]
        assert min([short,same],key=lambda ss:key(ss,1))==same
    print(json.dumps({'status':'PASS','cases':6,'penalized_layers':sorted(HYPOTHESIS),'APP_solver_calls':0}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--receipt');p.add_argument('--output');p.add_argument('--self-test',action='store_true');a=p.parse_args()
    if a.self_test:self_test()
    else:
        if not a.receipt or not a.output:p.error('--receipt and --output are required')
        receipt=(ROOT/a.receipt).resolve();path=(ROOT/read(receipt)['derived_overlay_path']).resolve();out=(ROOT/a.output).resolve()
        if ROOT.resolve()not in out.parents:raise ValueError('Output must stay inside task root')
        if out.exists():raise FileExistsError('Do not overwrite an existing alternative audit')
        audit(path,receipt,out)
