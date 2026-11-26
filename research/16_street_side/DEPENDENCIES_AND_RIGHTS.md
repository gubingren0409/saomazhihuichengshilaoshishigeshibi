# 依赖与分发边界

- 旧Foundation固定包：PG1_FOUNDATION_REVIEW.zip，72,108,383B，SHA256 `7c9ed58766177e8906defc257555b0d7ba0d92c8e97129a691f9f6e72dffef7c`。本轮仅引用，不嵌套；封存内容不修改。
- 旧R1固定包SHA256 `d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed`；旧R2诊断包SHA256 `3988e9fba95da70dc03b8191a177740a3ccd13602019afe3765e566648b55711`。本轮没有重跑其模型、探针或全局可视图。
- 新地图和局部源派生切片来自已保存OpenStreetMap数据；保留原生ID、原始标签及来源SHA。© OpenStreetMap contributors，既有来源记录为ODbL；参见 https://www.openstreetmap.org/copyright 。本轮未重新访问许可网页；不将地图事实升级成现场通行证据。
- 候选数据合同仅引用上一轮已保存的NYC及Helsinki来源/许可观察。未把NYC默认为CC0；未把403页面摘要说成取得了许可全文；没有重新取数或转发未审核原始包。
- 新源码未选择许可证。当前ZIP为本地私有审查材料，非个人Public仓库待推的38文件清单，也未获公开批准。首次Push继续等待用户批准；不能直接上传此ZIP。
- 包内不含.env、API Key、Cookie、商业底图、模型或用户聊天凭据。PNG不嵌入字体文件。

本地路径仅用于定位原依赖；Windows路径本身不证明外部可独立复现。新三窗口图与页面可离线核查，旧原始源完整核验须取得相应固定依赖。
