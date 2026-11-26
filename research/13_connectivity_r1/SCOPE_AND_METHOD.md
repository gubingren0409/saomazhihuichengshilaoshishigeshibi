# 本轮范围与固定输入

本轮只研究六份既有OSM裁片的显式步行面和周围源步道/相邻面的接入，不采集、不发地图API、不新增建筑/入口、不训练，不改历史工程或Git暂存。Geoapify历史服务基线没有被冒称重算。

固定基线OPEN_REVIEW_R1_FINAL_FIXED.zip SHA256：c5472838de6320d983d80e4defd448e08c017777f23bc7aa083d38e7ce10b08a。当前用户输入包c446c27ba30047b8011c08310b9c68cd914b1600b9262a4b8760bf621ee2e136；旧包外重放7285518c573051d7f620808135e767a723ea6945d0088683e81288848ce346b2，均已实际CRC/SHA核验。旧原件保持只读。

主比较B0/FROZEN_FULL_FACE、B1/SOURCE_COMPLETE、B2/EXACT_STITCH、B3/CONDITIONAL_SEAMS。各自F0/F1同图同区域，仅有限假设代价不同；接口与接缝域单列。冻结源边界P、原门/起点、用途、30米域、1米格网、障碍/权限/层级和0.25米面净空不变。探测10米，主上限2米，只有0.5/5米敏感性。

具体算法与修复见METHOD.md，实际结果见RESULTS.md，真实时间和中断/修复见PROCESS_RECORD.md。旧说明保存在audits/baseline_*.md，仅作历史依赖，不作为本轮实施结果。禁止把计算连通率、路线缩短、源面颜色或无冲突当作现场公众通行证明。
