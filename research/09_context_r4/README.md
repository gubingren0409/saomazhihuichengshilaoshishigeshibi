# R4-WALKABILITY-R4-CONTEXT 审查入口

- [离线交互地图](visuals/index.html)
- [实验结果](RESULTS.md)
- [范围、方法和隔离](SCOPE_AND_METHOD.md)
- [自然语言验收说明](USER_REVIEW_NOTES.md)

如 Codex 内无法打开本地 HTML，解包后在项目目录运行 `python -X utf8 -B scripts/serve_review.py`，使用终端打印的本机地址。服务仅监听 127.0.0.1，自动选端口。前台按 Ctrl+C 退出。静态 SVG/PNG 位于 `visuals/figures`。

`input_contract` 包含原附包合同、完整 R3 固定包及原校验器。使用 Python 3.12 和 `requirements.txt` 中的依赖。需要重新展开原始冻结依赖时，运行 `python -X utf8 -B scripts/stage_frozen.py`。已展开源数据和临时运行目录不随包重复分发。

固定包样例复现使用 `python -X utf8 -B scripts/replay_context.py <OPEN_REVIEW.zip> <新目录> --browser '<本机Edge路径>'`。样例复现覆盖三个 G 任务和一个真实障碍反例，完整实验逐任务结果在包内另附。
