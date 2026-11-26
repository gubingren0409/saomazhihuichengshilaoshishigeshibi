# 已知门原型、动态适配器与冷热性能

旧固定APP通过CLI、HTTP、网页调用共同内核；已有新请求和分段来源实物可核验。本轮只收录当时响应、源码与截图。

- SMALL_FROZEN_LIBRARY_ONLY HOT_PROCESS p95_ms：106.45105500734644 ms；口径：30次正式观测
- SMALL_FROZEN_LIBRARY_ONLY HOT_PROCESS max_ms：112.3953999922378 ms；口径：30次正式观测
- SMALL_FROZEN_LIBRARY_ONLY COLD_PROCESS p95_ms：35529.50160000255 ms；口径：10次正式观测
- SMALL_FROZEN_LIBRARY_ONLY COLD_PROCESS max_ms：35617.34880000586 ms；口径：10次正式观测
- SMALL_FROZEN_MUSEUM_TWO_DOORS HOT_PROCESS p95_ms：6229.083730002458 ms；口径：10次正式观测
- SMALL_FROZEN_MUSEUM_TWO_DOORS HOT_PROCESS max_ms：6324.5956000027945 ms；口径：10次正式观测
- SMALL_FROZEN_MUSEUM_TWO_DOORS COLD_PROCESS p95_ms：350142.49998499214 ms；口径：10次正式观测
- SMALL_FROZEN_MUSEUM_TWO_DOORS COLD_PROCESS max_ms：350561.0578999913 ms；口径：10次正式观测
- 状态适配器PASS：18 请求；口径：36适配器请求
- 状态适配器NO_PATH：18 请求；口径：36适配器请求
- 主状态适配器请求：36 请求；口径：2场景×6状态×3重复
- 原Python接口关闭负控FAIL：2 请求；口径：2条主原接口负控均FAIL
- 原APP合法功能请求：8 次；口径：13固定功能验收请求，不是13个独立场地
- 原APP拒绝请求：5 次；口径：13固定功能验收请求，不是13个独立场地
- 原APP实际图搜索：8 次；口径：13固定功能验收请求，不是13个独立场地

限制：原APP、Q7新状态适配器、Q8性能适配器分开。36适配器请求18PASS18NO_PATH；原Python P.plan关闭负控2FAIL，未测试HTTP动态接口。冷启动与热内核成对展示，不是实时动态导航已经部署。
