# 本轮交付覆盖与审核身份

本页是实现和证据覆盖表，不是用户验收单。上轮穿行观察保持 `PENDING_USER_OBSERVATION`，截图原请求保持 `SCREENSHOT_REQUEST_UNBOUND`。没有现场通行验证。

| 合同项 | 实际证据 | 范围 |
| --- | --- | --- |
| 固定输入和旧成果保护 | `audits/input_verification.json`、`audits/input_bindings.json`、`audits/protection_final.json` | 固定ZIP、12个必要原生输入、旧Git tracked status/HEAD/index；不是全历史工程重新审计 |
| 全源盘点和先锁定 | `data/connectivity/source_selection_lock.json`、`global_source_identity.json`、各场景source_inventory/relations/boundaries | 六裁片；P、Ω、重复原生身份和拒绝对象分开 |
| 精确接口、条件接缝实际入图 | `results/interface_evidence.csv`、`exact_interfaces.geojson`、`conditional_seams.geojson`、实际PREP叠图 | 接口、请求附着、假设段单列；有图边不等于现场公众可走 |
| 固定主比较与消融 | `data/formal_requests_lock.json`、`data/performance_replay_lock.json`、`results/sample_results.csv`、`paired_comparison.csv` | 104主比较、16事前锁定修复复算、1中断，共121正式尝试；保留首跑 |
| 合成正负例和整段几何 | `tests/`、`audits/root_tests_r2.json`、`audits/independent_*` | 作者72测试；独立原始几何、围栏/点触/层级等反例检查；不冒称现场数据 |
| 最终真实响应核验 | `audits/independent_canonical_review.json`、`independent_canonical_response_measurement.json` | 120份首跑/复算SHA；canonical104份响应独立量测，28组F0/F1同图且不同实际solver |
| 准备图连通分量 | `results/component_analysis_receipt.json`、`component_statistics.csv`、`topology_inputs/`、`audits/independent_component_review.json` | 作者24/24完整准备图SHA匹配；独立union-find/Kosaraju计数24/24一致；动态端点附着另记，不冒称现场连通 |
| 实时APP和异步回归 | `audits/independent_ui_live_review.json`、`independent_ui_live_visual_review.json`、`independent_frontend_literal_delta.json` | 六次真POST/新solver，12项交互断言；实测JS与最后纯文案差异均保留SHA |
| 真实图册与独立页面检查 | `visuals/`、`index.html`、`audits/independent_gallery_review.json` | 八张真实图、六个实际路线案例；实际Edge GET-only渲染、CSV/MD下载及最终HTML字节核对通过；用户自然语言观察另行待定 |
| 干净解包的新请求与最终字节 | 最终ZIP旁的包外独立回执 | 封包后执行，回执必须绑定最终ZIP SHA；本页不提前将该步骤写成PASS |

内部实际角色为 `/root`、`/root/connectivity_sources`、`/root/connectivity_stitch` 和未编写主实现的 `/root/connectivity_review`。内部独立审核不等于用户验收、外部GPT最终审核或实地核验。

原始P不移动、不扩张；Ω沿用原障碍、权限、层级和净空。条件接缝保持推断身份，F0倍率1、F1倍率2；不将它们标为原生道路。北门保留 `entrance=exit`，到门外和入馆资格分开。
