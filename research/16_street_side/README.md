# PG1-RESUME-STREET-SIDE-R1

本轮为原PG1的有限续执行，非重新启动父Goal。旧38文件、3134c0ea68e00871ed6dc86ca7bc905071449dae及历史封存包只读；只有旧delivery目录新增FINAL_STATUS.json和RECOVERY_REPORT.md。首次Push、许可证选择、取新数据、分组冻结及Blind均未授权或执行。

先看[index.html](index.html)的真实地图与R0/R1/R2对照，或本机服务 `http://127.0.0.1:53511/`。三个窗口按源结构预锁定；每窗两查询。本页显示真实保存结果，不冒称点击后重新求路。

## 运行与停止

在本目录运行：

```powershell
python -X utf8 -B scripts/serve_review.py --port 53511
```

前台服务按Ctrl+C停止。本次实际隐藏进程身份见audit/service_identity.json，仅停止这一实例可用 `Stop-Process -Id 99416`。未终止任何旧服务或无关进程。

无需服务也可直接打开index.html；它内嵌本轮真实地图数据，依赖本地maps/viewer.js及CSS。旧六场景链接需服务和原固定Foundation ZIP；新包不重复嵌入旧72MB包。

无求路的干净重建核验：

```powershell
python -X utf8 -B scripts/street_side.py verify-graphs
```

它从包内三个源派生切片重建九张图，并与保存图比较，不发起新的正式查询、不依赖全城图或网络。本次干净重放环境为Windows；锁定表内使用Windows相对路径，未验证Linux路径兼容。正式运行记录见audit/experiment_registry.jsonl；修复与首跑历史均保留。`run`命令检测已有注册表后拒绝覆盖，不能把重复求路藏成核验。

新图不是实测人行道恢复。标签与缺标侧向表示均为带road_id/side/level身份的逻辑通道；4m显示偏移标为SCHEMATIC，不是道路宽度、净空或步行精度。原生步道控制使用源折线。不同侧不凭路口自动合并，不强制闭环；不把原有广场改成必须绕边走。

## 可复现范围

包内有本轮代码、三个局部源派生输入、九张图、查询证书、图册、合同和审核。原始六份全裁片、完整旧模型/面路由器及旧独立复验依赖按SHA引用；不是整个历史工程完全离线自包含。新局部图可独立重建；原始源→切片、旧业务路线和旧交付链的复核需要原固定依赖。

作者与独立角色的检查均不代替GPT审核和用户自然语言视觉验收。候选方法不默认升级，父Goal未完成。
