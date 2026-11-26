# 固定回归的可移植入口与数据角色

APP实际求路使用包内六份冻结地图和已标步行面依赖，不需要旧Windows工程路径、基线ZIP或下列stage操作。

固定历史比较需要唯一的最终修复版基线包，SHA256必须为：
`1d4110a76d0e5006f5c518366d82d6fb1aa98c8e46bac6956b2b0dbd91ccc77a`。
它是独立只读依赖；本轮没有把1213成员历史包再次嵌套分发，也没有把只有个人Windows路径的引用写成完全自包含。

## 选择性准备

在当前新工程根目录运行，`--baseline-zip`指向上述固定包：

```powershell
python -X utf8 -B scripts/stage_regression_inputs.py --baseline-zip "基线包的实际路径/OPEN_REVIEW.zip" --destination runtime/regression_baseline
```

脚本先核验外层SHA与每个选中成员清单哈希，再只准备25个固定父任务的观测、查询、参考、约束及比较所需字段。旧预测只提取路线作为**新计算结束后的历史比较**；七失败的四父任务另外保存F0表面/图供诊断。受控参考没有进入worker。唯一的嵌套读取是指定mask ledger，不递归展开旧工程。

主面板stage实测186文件、14,633,333字节，包含源成员与派生摘取身份的 `STAGING_MANIFEST.json`。这个数量不等于主实验样本数。

## 重新执行主回归

```powershell
python -X utf8 -B scripts/run_regression.py --baseline runtime/regression_baseline --run-name replay_main --unified-guards
```

`data/benchmark_guards`是本轮统一负向限制导出的固定输入。若要从已有源地图重导，使用stage内mask ledger；只读ID来排除隐藏对象，不按隐藏形状裁切：

```powershell
python -X utf8 -B scripts/run_regression.py --baseline runtime/regression_baseline --prepare-guards runtime/regression_baseline/data/mask_dependency_ledger.jsonl
```

先导出后求路；不要修改或覆盖已封存运行。新的 `--run-name` 将生成独立目录。`--ids`只用于指定故障/复现回归，不能据此改主面板25父任务、41查询分母。

worker只得到观测、独立负向guard、配置及代码绑定。表面冻结后才读取固定query；没有提供reference、完整正向原图或旧route答案。进程内文件打开审核并非操作系统安全沙箱。

## 北门八查询与南门旧起点

旧北门合同比APP大，另需59MB旧观测、87MB route-only原生/面图；默认stage不复制它们。明确要重放时对新空目录使用 `--include-natural`，然后：

```powershell
python -X utf8 -B scripts/regress_natural.py --baseline runtime/regression_baseline_natural
python -X utf8 -B scripts/regress_source_route.py --run-name SOUTH_source_new_replay
```

北门使用经source/config/code绑定的旧M1观测分类缓存；局部F0/F1区域、图与路径均真实重算。原native/面图仅在冻结表面后读取，不是路线答案。南门脚本用当前统一source graph及同一solver重算历史起点，不计新增APP验收样本。

## 本次真实运行与计数

- `R1_cold`：四失败父任务的先导冷回归，9查询×3，验证绑定修复未违规放行楼梯端点。
- `R2_unified`：25父任务、41固定查询×3方法，123次routing函数评估；其中122次进入图搜索，M1-C/图书馆一次因端点未绑定提前拒绝。
- `NORTH_regression`：旧8查询×3方法，24次求路；不能混作8个新建筑或APP新起点。
- `SOUTH_source_R0` / `SOUTH_source_R1`：历史source-only南门查询，版本保留和最终复验分开。
- `R3_staging_smoke`：验证选择性stage的真实worker启动，重复固定任务不冒充新增样本。

个别旧输出字段 `actual_solver_calls` 原本计routing函数评估。保留原worker记录，并在summary及作者审计中新增 `query_evaluation_count`、`actual_graph_search_count`，不得把提前拒绝写成执行过图搜索。

作者核对见 `AUDIT/regression_author_checks.json`；独立审核者另有自己的范围记录。全部是已有暴露地图的同源工程/受控回归，不能当新盲测、公众通行保证或现场到门成功率。
