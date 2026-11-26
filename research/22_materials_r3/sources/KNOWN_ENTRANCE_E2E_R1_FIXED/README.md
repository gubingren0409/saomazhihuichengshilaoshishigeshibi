# 已知登记门末段规划 · 实际计算原型

本工程使用已冻结的六个上海 OSM 裁片及 R4-REV1 步行面派生边。页面的“计算”按钮调用本地 HTTP 服务，HTTP 与 CLI 共用 `src.planner.plan`，不读取历史路线答案。

## 打开与停止

在本工程目录打开 PowerShell：

```powershell
python -X utf8 -B scripts/serve_app.py --port 53421
```

打开终端返回的 `http://127.0.0.1:53421/`。端口已占用时会返回另一个可用端口；准确地址、PID 位于 `runs/service.json`。只监听本机，前台终端可 Ctrl+C 停止，另一终端也可运行：

```powershell
python -X utf8 -B scripts/serve_app.py --stop
```

停止命令仅向该工程记录的本地服务发送 PID 校验后的停止请求，不终止其他项目进程。直接双击 HTML 只能看到“需要启动本地服务”，不能代替求路。

## 实际运行入口

```powershell
python -X utf8 -B scripts/plan.py --list
python -X utf8 -B scripts/plan.py --request runs/acceptance/minimal_request.json --output runs/my_new_cli_request.json
python -X utf8 -B scripts/prepare_scenes.py
python -X utf8 -B -m unittest discover -s tests
python -X utf8 -B scripts/run_regression.py --baseline data/regression_baseline --run-name replay_main --unified-guards
```

可在 JSON 中更换同一现有场景的合法 `start_id`、登记 `door_id` 和 F0/F1；新运行会产生新的 run_id 和 solver 记录。页面提供真实原生网络节点列表，不支持任意自由坐标吸附。`start_xy` 如提供，必须与对应原节点坐标一致。

本机已安装的运行依赖为 networkx、shapely、pyproj；测试与资源记录可用 psutil，浏览器验收使用 Playwright + Edge。依赖准确版本由 `AUDIT/environment.json` 记录。没有在本轮下载或全局安装包，没有外部地图请求。解包后 APP 的原源、派生边与源码均在包内；历史来源路径仅作追溯，不是运行依赖。

## 结果与诊断

- 主页面：实际选择场景、原生起点、原登记门、用途和 F0/F1 后计算。
- `/diagnostics`：七条失败、草地中原生步道、权限面和车道宽度限制；诊断展示与实时计算分开。
- `runs/acceptance/app_acceptance.csv`：本轮固定应用请求逐项结果。
- `FAILURE_DIAGNOSIS.csv`：四父任务的七条失败；不是七个建筑或七个门。
- `runs/benchmark/R2_unified/summary.json` 与 `AUDIT/regression_author_checks.json`：固定回归及实际图搜索次数。
- `AUDIT/independent*`：不同实际上下文的独立核验及范围。

## 方法与边界

F0 在原门心30米有效范围内排除已知限制，将普通缺标残余空间作为条件可行假设。F1 使用完全相同的区域、节点、边和接口，仅把假设段长度代价乘2。160米是局部观测域；前段使用冻结裁片内可用源网络。区域不因起点或最终路线改变。

三个登记门分别为博物馆 main、北侧 exit、图书馆 yes，涉及两栋建筑；其余四目标楼没有可用登记门。exit 可用于到门外诊断，`ENTER_BUILDING` 会拒绝。main/yes 的入馆角色通过只代表地图登记角色适用，不保证当下公众可进入。

路线始终到原登记门坐标，未移动门或生成入口。蓝色为原生源线，青色为已标步行面派生，橙色为条件假设。米制路线导出显式标记 EPSG:32651，不能当作无 CRS 的 WGS84 GeoJSON 使用。零宽道路中心线不等于车行道边界；未知障碍、高差、权限、开放时间和现场可走性仍未知。

## 可复现范围与轻量依赖

APP 实际求路不需要原 Windows 工程或旧模型。主受控回归随包保留必要观测、查询、共同负向限制与运行记录；worker 在区域冻结后才读查询，不读参考或旧答案。完整历史 NORTH 输入及旧指标比较依赖外置的最终 FREE-SPACE-R1 包：SHA256 `1d4110a76d0e5006f5c518366d82d6fb1aa98c8e46bac6956b2b0dbd91ccc77a`。它未重复嵌入本包，详见阶段整理与 manifest；不要把 APP 自包含误说成全部历史实验均无外部依赖。

地图数据 © OpenStreetMap contributors，ODbL。面派生边是对已有地图步行面进行的计算，不是实走轨迹。作者、内部独立审核、GPT外审、用户自然语言验收、现场验证与课程提交分别记录；本轮完成后等待审核，不启动下一阶段。

## 最终审查版本

请使用 `delivery/OPEN_REVIEW_R1_FIXED.zip` 及绑定该SHA的独立解包回执。首 `OPEN_REVIEW.zip` 保留为日志覆盖缺陷的失败历史，不能作为最终通过包。最终状态在包外 `delivery/FINAL_STATUS.json`；包内状态是封包时待最终验证的快照。
