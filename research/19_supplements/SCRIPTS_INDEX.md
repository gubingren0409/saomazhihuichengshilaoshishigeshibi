# 源码阅读顺序

先看 `RUN_COMMANDS.md`。需要一条新的真实路线时，只运行 `scripts/replay_request.py`，它使用唯一输出目录，不覆盖本轮结果。

| 用途 | 主要代码 | 说明 |
| --- | --- | --- |
| 冻结核心 | `frozen_runtime/src/` | 字节身份见49成员清单；本轮未修改 |
| 共用实验适配 | `scripts/experiment_core.py` | 调用冻结准备、绑定、求解和全路径检查，不读路线答案 |
| Q2 / Q7 当前完整驱动 | `scripts/run_entries_and_closures_v2.py` | 本轮首版实际执行代码另保留在无v2文件中；v2纠正封闭对象必须是原生步道 |
| Q2 原门再核验 | `scripts/recheck_entry_identity.py` | 当前A1用米制Source.projected；旧错误源码在audit/EXECUTED_* |
| Q2 上下文、窗口与注释 | `scripts/finish_entry_audit.py`、`complete_entry_context.py`、`annotate_target_definitions.py` | 窗口比较仍依赖两个旧固定ZIP；不改旧图或旧路线 |
| Q6 历史只读审计 | `scripts/audit_sources.py`、`recheck_grass_policy.py` | 前者需6个外部旧ZIP；后者用包内冻结源重评377段 |
| Q6 现场缺项 | `scripts/record_field_blocker.py` | 只记录真实阻断；不会生成现场照片或标签 |
| Q7 博物馆修正复测 | `scripts/retest_museum_walkway_states.py` | 本轮一次性保留首版，再重测符合源步道条件的干预；不是新默认算法 |
| Q8 小图 | `scripts/run_benchmark.py`、`benchmark_worker.py` | 4组合；原执行管理器快照在audit中 |
| Q8 合并输入 | `scripts/prepare_medium.py`、`medium_adapter.py`、`run_supplementary_benchmarks.py` | 精确原生ID/兼容缺字段合并，真实覆盖并集，派生输入已含于包 |
| Q8 Top3 | `scripts/benchmark_topk_worker.py`、`run_topk_phased_benchmark.py` | 新增Yen实验适配器；当前A2含分阶段时钟；A1有效整体计时保留secondary |
| Q8 删边 / K2 | `scripts/run_replan_benchmark.py`、`run_joint_benchmark.py`及对应worker | 删边NO_PATH保留；K2两个门都仅到门外，每请求核对缓存来源版本 |
| 统计与真实地图 | `scripts/assemble_results.py`、`build_figures.py`、`plot_performance.py` | 汇总原始观测，不生成现场真值；图像均来自实际源几何/结果 |
| 图文与完整性核验 | `scripts/check_browser.py`、`validate_delivery.py` | 作者新脚本/进程核验，不冒称独立人员 |
| 打包与干净解包 | `scripts/package_review.py`、`verify_review_zip.py` | CRC、SHA、路径检查、离线阅读及一条新的真实求路 |

`fix_*`、`prepare_phase_instrumentation.py`、`prepare_walkway_state_correction.py`、`promote_phased_top3.py` 和历史schema复查代码用于解释本轮实际纠错，不是推荐反复执行的日常入口。每个动作的来源/版本和限制见 DATA_VERSION_NOTES.md、audit/ 及逐实验原始记录。

没有常驻服务需要启动或停止。本轮未修改旧APP、历史工程或Git暂存；新Top3/K2/状态适配器没有自动合并进旧产品。
