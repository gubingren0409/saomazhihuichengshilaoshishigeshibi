# 完整步行面最短穿行：实际运行入口

本工程独立于旧APP，使用同一批六份冻结OSM裁片。新接口不调用外部地图API，不修改旧模型、入口或历史结果。

在 PowerShell 中进入本目录，然后运行：

```powershell
python -X utf8 -B scripts/serve_app.py --port 53431
```

打开 <http://127.0.0.1:53431/>。保留该窗口，服务只监听本机。若端口已占用，准确URL写在 `runs/service.json` 和启动输出中；同工程服务已启动时不会再起第二个。

六组固定结果图册也可在同一服务打开 <http://127.0.0.1:53431/review>，避免Codex对本地HTML预览的限制。断开服务后仍可直接打开本目录`index.html`和`visuals/`中的图片。

选择场景、登记门、合法起点、用途和F0/F1；选择“新：完整合法步行面”，点击“计算本次路线”。“同起点同门：旧／新真实对比”实际提交两次求解，在同一底图叠加结果。可切换全程、整块步行面、门前视野，以及接点/旧带/原生步道/限制面。点击对象查看原生ID、来源及约束，导出当前JSON或GeoJSON。

北门为 `entrance=exit`：可选择“接近门外”，不能作为入馆入口。加载时切换方法、用途或面路由不会取消地图请求；加载失败有重试按钮。冷启动预处理可能持续数分钟，随后同图请求使用有来源/代码版本绑定的预处理缓存，每次路线仍重新求解。

从另一个PowerShell窗口进入同目录，停止本工程服务：

```powershell
python -X utf8 -B scripts/serve_app.py --stop
```

这不会停止旧53421服务。不要用关闭全部Python进程的方法停服务。

CLI使用同一内核：

```powershell
python -X utf8 -B scripts/plan.py --request data/example_request.json --area-routing FULL_FACE --output runs/manual_result.json
python -X utf8 -B -m unittest discover -s tests -v
```

运行依赖见 `requirements.txt`；本机已具备。本ZIP包含APP所需原始裁片、新源码及派生结果，不含虚拟环境、字体或旧历史工程全集。离线审查打开 `index.html`，静态图在 `visuals/`。静态页明确为真实结果展示，不冒充交互求路APP。

`input_contract/`保留本轮原始任务与来源说明，供核对授权范围；其中所述内嵌旧基线ZIP只在用户原输入包中，最终交付不再重复打包。该旧包SHA256及成员核验回执已保存。重做旧包核验或运行`run_matrix.py`的旧答案比较需另行提供同一固定包；启动本次APP、测试和干净新请求不需要它。

阅读 `SCOPE_AND_METHOD.md` 和 `RESULTS.md` 判断最优性、来源和现场边界。用户验收及现场通行验证尚未完成。
