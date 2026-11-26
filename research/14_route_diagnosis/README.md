# R2路线诊断审查入口

打开 http://127.0.0.1:53451/ 查看四个固定业务任务。离线可打开visuals/index.html：源背景与诊断payload内嵌，不调用外部地图。选择卡片、F0/F1、B0/B1/B2/B3，切换5/10/20米诊断走廊与图层，点选面/接口查看分量、采用与未采用理由，再查看有限替代线。诊断走廊不是新可行域。

这是只读诊断器：主线是R1保存路线；替代分析来自R2实际8次求解。界面切换不会偷偷新增求路或冒称当前实时运行。

在本目录运行：

```powershell
python -X utf8 -B scripts/serve_review.py --port 53451
```

前台服务用Ctrl+C停止；已运行后台服务先从/api/health确认service=PED_AREA_CONNECTIVITY_R2_DIAGNOSIS再按其pid停止。不要停止旧53421/53431/53441。运行与证书复验入口见src/diagnose.py、src/certificates.py与src/independent*.py；不得无意重复8正式求解。requirements.txt记录实际环境版本，不代表本轮安装了软件。

本包为增量诊断，完整原始R1固定包不重复内嵌；从源重建需要另行提供R1 ZIP，SHA256必须是d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed。新薄图、证书、结果、地图和必要源码在包内；不宣称整个历史自包含。原图数据© OpenStreetMap contributors · ODbL，frozen 2026-11-08T21:21:00Z，计算EPSG:32651米。

ROUTE_DIAGNOSIS.md解释四条路线；BUSINESS_ROUTE_OPPORTUNITY.md列替代和反事实；COMPONENT_LINEAGE.md解释分量。三份根CSV为完整逐对象证据。audits/INDEPENDENT_REVIEW.md记录真实独立范围；最终固定ZIP的解包回执放包外，绑定其SHA。包内候选状态保留封包前时序，用户验收和现场验证仍待定。
