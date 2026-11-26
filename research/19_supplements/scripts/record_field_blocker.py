from pathlib import Path
import csv,json,datetime
ROOT=Path(__file__).resolve().parents[1];EID='Q6-FIELD-TRUTH-COMPARISON-R1';D=ROOT/EID
def csvout(name,rows,fields):
 with (D/name).open('w',encoding='utf-8-sig',newline='')as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
reason='NO_INDEPENDENT_TIMESTAMPED_FIELD_SURVEY_PHOTOS_OR_TRACKS; ONLY_2_EXISTING_REGISTERED_BUILDING_SITES_NOT_3'
slots=[]
for b in range(3):
 for target in range(2):
  row=dict(experiment_id=EID,run_id=f'FIELD-PLANNED-SLOT-{b+1}-{target+1}',scene_id=['sh-huangpu-01','sh-library','UNFILLED_THIRD_BUILDING_SLOT'][b],building_id=['way/161090899','way/293434188',''][b],entrance_id='',method='INDEPENDENT_FIELD_SURVEY_REQUIRED',input_version='No admissible field input supplied',status='BLOCKED_BY_MISSING_INPUT',result={'planned_slot_only':True,'actually_surveyed':False,'field_observations':0},failure_reason=reason,route_length_m=None,assumption_length_m=None,runtime_ms=None,source_edge_count=None,derived_edge_count=None,assumption_edge_count=None,output_file='route_level_comparison.csv')
  slots.append(row)
with (D/'raw_results.jsonl').open('w',encoding='utf-8')as f:
 for row in slots:f.write(json.dumps(row,ensure_ascii=False)+'\n')
csvout('route_level_comparison.csv',[{k:v for k,v in r.items()if k!='result'}for r in slots],[k for k in slots[0]if k!='result'])
csvout('field_truth_segment_labels.csv',[],['route_id','segment_id','building_id','entrance_id','observation_time','independent_observer','exists','walkable','same_level','open','temporary_obstacle','evidence_photo_or_track','status'])
csvout('algorithm_field_confusion_matrix.csv',[dict(status='BLOCKED_BY_MISSING_INPUT',TP='',FP='',FN='',TN='',observed_segment_denominator=0,reason=reason)],['status','TP','FP','FN','TN','observed_segment_denominator','reason'])
(D/'summary.json').write_text(json.dumps({'status':'BLOCKED_BY_MISSING_INPUT','planned_route_slots':6,'actual_field_routes':0,'actual_field_segments':0,'confusion_metrics':None,'source_role':'Desktop OSM outputs are not field truth','missing_inputs':['Independent human observer and timestamped survey','Legally shareable photos or tracks aligned to frozen routes','Third qualified building and a second qualified target where missing','Field same-level/open/access/temporary-state labels'],'network_requests':0,'physical_site_visit_performed':False},ensure_ascii=False,indent=2),encoding='utf-8')
(D/'field_protocol.md').write_text('''# 现场真值协议与本轮阻断

本轮没有接收到与这些登记门对应的独立、带时间戳现场记录。0条现场路线、0条现场路段标签。六行是待调查槽位，不是已经开展或失败的六次实地测试；混淆矩阵不可计算，不能填0冒充无误差。

调查前应冻结原场景、门用途、地图/代码SHA与算法请求及路线，再由独立人员记录每段存在性、可走性、同层、开放、临时障碍、日期及照片/轨迹。北exit不改作入馆入口。当前仅两处有合格登记门的建筑，第三建筑与缺少的第二门外目标需要真实输入，不能用代理点补足。

现场人员和材料均未提供，本轮不进行网络图片替代、AI现场打标、GPS伪造或照片生成。一次观察只能支持相应日期和案例，动态状态另列。用户补充真实材料后可使用本目录的空表及固定算法版本继续，当前没有自行开启采集。
''',encoding='utf-8')
print('FIELD_TRUTH_BLOCKER_RECORDED_NO_FAKE_LABELS')
