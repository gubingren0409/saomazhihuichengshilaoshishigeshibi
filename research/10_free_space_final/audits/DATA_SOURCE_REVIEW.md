# 数据与原始来源复核

当前来源状态：**PASS_SOURCE_ACCESS_REPAIR_WITH_LIMITS（R1）**。R0曾因主25任务中1个域漏导已知私有停车面而交付PARTIAL；该封包和反例保留不变。随后核实合成记账算术多计2次，在实际剩余2次区域预算内完成同Goal的共同源约束修复，实际结果见本文R1节。这里的通过只限已取得源数据及规定检查，不证明现场可通行或公众可入馆。

## 真实身份与分工

`/root/free_constraints` 是与主实验实现不同的实际执行上下文，负责共同guards制作、源保护、S1实际回归和北门全程原始来源核查。该角色没有编写主F0/F1分类器、主图构建器或最短路求解器。

本角色制作了 `common_constraints.py` 和 `prepare_common.py`，其数据导出的自查不能冒称对自身实现的独立审核。`common_guard_source_review.json` 明确标作数据角色自查，使用不同几何核对过程但由同角色执行。共同约束、F0公式、全图边/终端、成本/可达集合及主评价的独立复算由实际不同上下文 `/root/free_evaluation` 承担，范围见其 `INDEPENDENT_REVIEW.md` 和机器回执。本文件不替该角色宣布未执行的检查。

北门原始全片复核使用冻结 `Source` 类仅解析OSM环与原始障碍，不调用作者分类器、`bind`、路由验证函数。它属于对主实现的不同上下文、不同检查路径的来源级核查；对完整地图解析器本身不是另写一套独立OSM解析实现。

## 输入、共同约束和版本

六份现有OSM原片SHA匹配完整冻结归档。R0准备55份V2 guards，其中25份主G80/N80、21份H80、8份40/160m、1份自然北门；准备导出不能写成已完成55个区域实验。R1只对W7新增V3 negative-area guard并设活动override，其余V2文件不改；原55份V2仍保留历史身份。

原observed、参考、查询、域及格网没有改动。机动车中心线从独立原源补导为共享零宽横穿限制，不虚构道路宽度，不把已有合法native步行连接抹掉。首版误删“与旧隐藏节点共享点的独立道路”已修复，原v1文件仍保存。v2不输出node/member数组，不读取reference塑造约束，也不按隐藏几何打孔。目标/被遮蔽整对象依赖按身份整体省略，所有几何只按固定观测窗口裁切。

主25任务取得158条按任务计数的道路约束；16任务有原observed步网没有的独立道路约束，5任务窗口内无取得motor中心线。55份guards共361条重复来源记录，标签与真实几何逐条吻合。30m评分域均在取得的clip footprint内，工程无数据面积为0；这不代表现实障碍已完整测绘。细节见 `CONSTRAINTS.md`、`common_guard_source_review.json`、`constraint_evidence.jsonl`。

活动指针为 `config/constraint_contract.json`，最终活动证据索引为 `data/constraint_evidence.jsonl`。初版合同/索引分别保存在 `constraint_contract_v1_initial.json`、`constraint_evidence_v1_initial.jsonl`，未被覆写消失。

## S1：本轮实际重建的源语义回归

`scripts/replay_s1_regression.py` 先核对15项借用代码、源片及原固定查询与嵌套冻结ZIP一致，再以独立子进程实际重建六clip的S0/S1，仅写本轮新目录。实际耗时81.58s。

得到377个去重原生片段、754有向arc，线长4158.602352m、与背景草地重叠3326.278327m。南门S0/S1均1067.371390401112m，原终点残差0；固定北侧1237.814718494129m→1166.0987072809223m，未加区域时原exit仍不可达。新生成的CSV与路线GeoJSON分别与冻结R3逐字节一致。详见 `s1_regression_actual.json`。

这些是保留已有步道的正确性回归，不是F0区域恢复分数，也不是现场实走结果。复用纯函数没有修改旧工程；该回归不构造新的预测区域，`region_builds=0`。

## 北门：最终全程来源检查

当前权限补全回执：`north_full_source_check_ACCESS_FINAL.json`，脚本：`scripts/audit_north_source.py`。它使用固定源权限登记，只接受具体原生foot-allowed way与精确共享边界的枚举例外，七次DOOR例外均为同一5.634348m源边，无buffer；没有native通配例外。前一 `north_full_source_check_PERMISSIONS_FINAL.json` 保留较早“面严格内部”检查身份。`north_full_source_check_FINAL.json` 是权限补审前8/8版本，旧解析器漏掉隐式闭合停车权限面和普通限制线，不能继续当成完整权限审核。初3/8版本的 `north_full_source_check.json` 和旧M0/M1校准的 `north_prior_source_check.json` 同样保留各自历史身份。

首次复核沿用冻结Source枚举4859个源对象；发现其权限枚举不全后直接从原片补审普通限制线及闭合私有面，当前共5009对象：4693建筑、21水体、70barrier、74背景政策、1保守bbox、144限制线、6新增权限面。0个完全无法定位对象。不能将这些对象全部称为精确实测障碍；缺少和错误标签仍可能存在。

最终7个方法/代价分支，各8个固定查询均可达；这是56条重复分支路线、8个原查询，不能说成56个独立场景。对所有实际路线逐段检查连续性、长度、源对象冲突、边来源、原生way几何与tags、面派生段的登记步行面覆盖及原查询起终点，得到源冲突0、断点0、出clip长度0、起终点误差0。缺少level的路段明确记为UNKNOWN，不被改写成实测同层。

北门路线原先的权限争议来自 `way/178730989`：原始是5节点闭合的416.812308m²停车环，`amenity=parking, access=private`，并非开放线墙。与明确 `foot=yes` 的原 `way/178719573` 及登记行人面 `relation/2153738` 只共享5.634348m边界，私有停车面与该登记行人面面积交集0。所有北门DOOR路线仅沿该精确原生共边，停车内部长度0。私有面内部仍禁止，只有逐ID、原始共享节点对定义的既有foot-allowed共边例外，既不开放停车场，也不允许一般新自由边或其他source way借此穿入。真实非闭合限制线不因此忽略。

## 主25任务的真实权限缺口：R0保留记录

`scripts/interpret_access_areas.py` 对六clip直接扫描原始闭合权限对象并核对源SHA，得到21份按clip重复的面记录、13个独特源ID、0解析失败；原始环、tag、精确共边例外保存在 `data/access_area_interpretations.json`，线权限仍按原线保留。该登记在生成时不读reference，也不修改observed。

`access_scope_26.json` 逐一检查25主域及北门原D30：**仅 `W7a6b5a10076_G_080` 与上述停车面内部相交128.388559m²，NORTH D30所有私有面交集0**。W7原observed、guards、common constraints均完全漏掉该权限对象。不是将整个闭合环误作线的问题，而是这个任务根本没导入该源对象。

W7的M1-C将该块保留UNKNOWN、推断面积0；F0/F1则将128.388559m²全设为假设可行。这是已取得原始地图中已知权限漏约束造成的区域冲突，不能继续统称参考外“未经证实”。该停车块与隐藏正例参考面积交集0，原正例覆盖分子不因本条更改。

W7的F0/F1两个实际查询路线均未穿入私有内部（长度0），M1-C两查询不达。因此区域违规和当前查询路径是否越界须分开报告；不能以路径没用该块掩盖区域错误，也不能将没有穿入的路线虚记为停车区穿越。详见 `common_constraint_gap_W7a6b5a10076.json`、`access_area_prediction_impact.json` 及 `data/source_diagnostics/private_parking_W7_missing_guard.geojson`。

R0当时按静态合成测试估算触及200上限，故停止区域运行并保留25分母和所有结果，形成 `OPEN_REVIEW_R0_PARTIAL.zip`。没有删除W7或修改其旧预测。后续实际计数核验发现算术多计，处理经过和R1结果如下，不能将R0的真实缺陷抹掉。

## R1：在证据修正后的剩余预算内修复

冷解包实跑12个合成测试实际14次fixture、28次区域构建；初版同样是test05三次、其余11项各一次，后续格片/终端检查均复用已有fixture。加单项test11的2次，科学合成总数应为30，不是原静态32。两独立上下文复核后追加算术更正，R0的原估计及ZIP不改。原研究执行上界170＋合成30－中断阶段更正2＝198，尚余2次。该推断有真实冷重放和源结构依据，但不是独立OS事件日志，详见 `synthetic_build_count_review.json` 和独立预算收据。

在父任务通知和冻结后，W7增加V3 guard：仅原始完整 `way/178730989` 私有面、tag、source ID/SHA及闭合事实，原80m观测窗口选取，不读取reference/query/prediction选形，不导入隐藏footway、member数组或原始源正向共边例外。源ID不属于被隐藏target/member/removed对象。共同约束增加D30内权限面，三组使用同一份；所有普通残余空间规则、原格网、端点、参考和代价保持。

V3在W7的权限面及blocked增量均128.388559m²，实际从同observed可见原生步道导出的边界例外数为0（北端5.63m在该D30之外）。私有内部不能因native foot=yes或bridge标签泛化放行。源导出核查为 `private_guard_v3_source_audit.json`，共同约束制作者的纯几何属性自查为 `private_guard_v3_contract_checks.json`；后者不调用预测区域构造或寻路。独立共同约束审核仍由 `/root/free_evaluation` 完成。

W7复用同observed、同冻结分类代码/配置的纯M0/M1缓存，MC/F0各构造一次，F1及固定有限代价仅重权。最后2次实际运行后研究上界为200。原W7七分支结果保存在 `runs/superseded/W7_PRIVATE_R0/`；旧R0 ZIP保持其SHA不变。

`scripts/audit_private_repair_r1.py` 没有导入classifier、region/graph builder或solver，逐一读取当前25主域＋NORTH的150个实际分支，按独立原源权限polygon和精确共边重新算：可行域已知权限面积冲突0（面积容差1e-6m²），实际路线私有内部/未获枚举边界例外冲突0（长度容差1e-6m）。W7三组现均将该块列RESTRICTED，推断覆盖0；原F0/F1两个既定查询仍到达且未穿私有内部。其余25场（含NORTH）的所有原预测与R0 ZIP逐字节一致，原25主分母不变。

R1缓存逐字段等于R0分类结果、仅4顶层字段；实际日志cache→当前surface.freeze→query，guard SHA吻合；无新正向隐藏例外。最终源复算回执为 `access_policy_FINAL_R1.json`。这修复了已发现的源导出缺陷，不构成新盲测，也不能因此声称地图中的未知权限或障碍已被解决。

原北门仍是 `node/6897145227`，WGS84 `[121.4706605, 31.2305674]`、EPSG:32651 `[354344.3888134466, 3456163.0891986894]`，`entrance=exit`，位移0。其入馆资格为 `NOT_ELIGIBLE_EXIT`；本轮只评估到门外，不能因路线短而推荐它作入馆门。

## 冻结后的终端绑定修复

初3/8不是源障碍证明：原LOCAL查询点没有进入排序前16个通用接口，且无原终端role，产生 `UNAVAILABLE_ENDPOINT`。主实现随后修复为冻结后核实同一observed中的精确可见ID/XY及源标签，再按旧1.6m容差、完整线段共同约束绑定。没有新门、没有移动原点，没有重新分类区域；原region/无权图哈希不变，仅终端附加图及路线变化。

`scripts/check_north_terminals_source.py` 没有调用主classifier、`bind`或验证函数，独立检查了91个终端记录。56次visible绑定对应7个独特源点：2个原OSM节点、5个登记步行面派生grid点。原ID/XY、标签、相邻有效源边、权限/明确层级兼容及1.6m容差全部通过。派生grid点与控制点均不能改称原生物理入口。原始已授权门/控制点保持原角色。结果见 `north_terminal_source_FINAL.json`。

## 预算与缓存补验

`budget_stage_cache_review.json` 保留原中断上界4次记录，同时按实际保存的完整worker仅有5输入、无必先写出的 `constraints.json`，支持追加上界-2修正。它不能证明恰好完成两次；实际0–2未知，按2保守计数。该判断依赖保存目录完整且未被外部删除，没有独立OS事件日志。

`cache_payload_review.json` 补验实际NORTH纯分类surface缓存：仅observed SHA、代码/配置bindings、M0/M1两个纯surface，二者与冻结历史区域逐字段一致且相同；无routes/query/reference/features/read_log等。首次实际分类日志保留“cache→当前区域freeze→query→完整前段图”的顺序。后续修复是明确记录的冻结后路由resume，读取前次预测元数据但旧路线不用于新候选或求解；不能把resume称作全新observed-only分类运行。

NORTH历史M0/M1区域属于复用，M1-C/F0新适配区域各构造一次、共2次；F1代价和终端路由修复不新增区域。全量预算的最终计数与上限由父任务的实验总账负责，本文件仅确认上述阶段证据，不替未检查的运行推断次数。

## 源保护及剩余限制

`protection_before.json`、`protection_after.json`、最终 `protection_final.json`：120个明确使用的旧文件SHA及两个Git仓库HEAD/index/完整tracked status一致。没有commit、reset、清理或改历史Git暂存；不是全仓无关文件的完整盘点。

本轮不含现场核验，不知道未标障碍、高差、即时门禁和公众权限。道路中心线未给出精确车道宽度，零冲突不能排除沿车道一侧错误走入未绘明车道。默认自由空间仍是假设；“可计算通”与“现实可通行”分开。已知障碍零误入仅验证对取得约束的遵守，不证明未知障碍安全。人工自然语言验收和GPT后续审核仍待用户执行。
