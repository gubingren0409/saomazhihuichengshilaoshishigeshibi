# R4-REV1：下一轮执行包

**先读新 Prompt，再看旧报告。这个包用于实施修订，不是让 Codex 再做一次问题复核。**

## 一、这轮改变什么

旧 R4 要求候选边先有原生步行线支持，导致有步行面却无法派生边。本轮明确替换这条限制：在源步行面、真实接点和障碍约束下，可生成身份准确的“面派生计算边”，实际用于条件寻路。

南侧检验三个原生接点如何通过广场边缘接到南门；北侧把门外可达性和入馆资格分开，约8米间隙不被直接吸附。北西门仍保留 exit 角色。

**未标记入口生成不在本轮范围。** 原门坐标不变，不把代理点当门，不新增建筑或数据采集，不调用API，不训练，不购买服务，不启动R5。

## 二、阅读与核验

1. `OSM_GEOAPIFY_R4_REV1_CODEX_PROMPT.md`（主执行依据）
2. `01_SCOPE_REPLACEMENT.md`（覆盖旧条款的逐项说明）
3. `references/review/00_R4_QUESTIONS_REVIEW.md`、`question_checks.json`、`source_code_evidence.md`
4. `INPUT_BINDINGS.json` 和 `references/frozen/` 中的两份原包
5. `02_ACCEPTANCE_CHECKLIST.md`、`references/USER_DECISIONS.md`
6. 当前适用的项目规范；`project_rules/` 仅为本对话规范的分发副本

先在解压后的本包根目录运行：

```powershell
python -X utf8 -B verify_inputs.py
```

验证程序只读检查，不安装依赖、不联网、不提取文件、不运行旧实验。

## 三、不需要再次寻找整套历史数据

`references/frozen/OSM_GEOAPIFY_R4_OPEN_REVIEW.zip` 是用户提供的旧R4实际审查包的原字节副本：有六个OSM裁片、冻结B0程序、历史路线、必要IR和旧运行记录。

`references/frozen/R4_MAP_INFORMATION_REVIEW.zip` 是上一轮GPT复核包原件，保存旧实现限制、南北门几何复算与脚本。

关键复核报告及核对图另按原字节展开到 `references/review/`，便于直接阅读。完整来源绑定见 `INPUT_BINDINGS.json`。核心离线实现不需要API Key，也不要求再次上传66MB的R3全包。

把旧R4归档解到新的只读基线副本，把开发代码放入全新的 `OSM_GEOAPIFY_R4_REV1/` 工作目录。不要覆盖原R4或在旧目录运行会覆盖输出的脚本。复核脚本中的旧容器绝对路径需要参数化，原脚本本身保留。

## 四、要交付的重点

- 真正生成的面派生边、每条边的来源/假设/障碍检查。
- 旧R4与修订机制同图对照，南门完整路线或具体断点。
- 北侧可到达的位置、未支持间隙、出口角色三者分别显示。
- 主带宽3米与1/5米敏感性、移除派生边的消融、六个既有病例回归。
- 可交互的地图审查页，支持用户直接用自然语言评价，不要求重新填评分表。
- 独立技术核验、实际解包复现和固定审查ZIP。

本包是**执行说明与冻结输入**，没有包含本轮已实现算法或新实验结果；旧图和旧收据保持历史身份。本包供用户与Codex任务交接，不代表已授权公开发布。
