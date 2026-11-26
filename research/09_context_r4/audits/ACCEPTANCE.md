# 本轮验收对照

| 要求 | 状态与证据 |
|---|---|
| 历史保护 | 通过，`input_verification.json`、`protection_after.json` |
| 隐藏、观察、评分、显示分离 | 通过，`config/methods.json`、`data/task_manifest.json`、`context_input_audit.json` |
| H0 与 H40 区分 | 四例实际校准，`e0_replay.json` 和 `runs/context_metrics.json` E0 |
| 多半径真实上下文 | 138 个规范输入全部重建，`data/context_inventory.jsonl` |
| 片段级遮蔽和外段保存 | 原图独立复算通过，`data/mask_dependency_ledger.jsonl`、`DATA_CONTRACT.md` |
| H、G、S、N 分层 | 21 个 H／G 可比正例和 4 个 N，真实 S 因无独立中性同形轮廓不适用，`neutral_shape_audit.json` 与 `semantic_contract_fixture.json` |
| M0 源码与参数 | 原始 SHA 绑定且四个原锚点路径和表面相同，`config/methods.json`、`e0_replay.json` |
| M1 实际外围证据 | 逐格独立复核及相关、无关、屏障对照，`context_feature_spatial.json`、`tests/test_context_policy.py` |
| 固定域及风险 | 面、线、风险、UNKNOWN 分层，`runs/context_metrics.csv` |
| 圈外路与局部恢复 | 各尺度无推断基线、路线长度及各段来源，`runs/context_metrics.json` |
| 读取和遮蔽隔离 | 通过应用层实际打开审计，`context_input_audit.json`、`context_isolation_probe.json` |
| 历史暴露 | 全部同源受控诊断，`STATUS.json`、`SCOPE_AND_METHOD.md` |
| 北门、南门、草地回归 | 通过，`context_north_independent.json`、`s1_regression.json` |
| 图册和可读入口 | Edge 和几何校验通过，`context_browser_check.json`、`context_visual_geometry.json` |
| 固定 ZIP 及空目录重放 | 包外最终版本收据，`delivery/replay_receipt.json` 与 `delivery/independent_package_check.json` |
| 效果边界与外部验收 | 局部证据使用和覆盖获支持，正例接通无增益，等待 GPT 和用户 |
