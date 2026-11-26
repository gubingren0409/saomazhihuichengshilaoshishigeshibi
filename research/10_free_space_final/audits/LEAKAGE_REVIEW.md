# 输入与评价隔离：R1

独立审查者 `/root/free_evaluation`。固定obs、参考、query、30米域和1米格网逐文件哈希对照。模型初始运行的实际打开日志有reference及提前query拒读探针，区域先冻结后读query；应用层审计不冒称操作系统沙箱。

V3预测guard只补完整独立private停车面geometry/tag/source ID，不含隐藏footway正例、node/member数组、reference或query。其源身份不在hidden/removed目标中；未使用参考轮廓刻孔。可见native精确边界例外仅从同observed已有弧导出，W7当前此类例外为0。完整源footway共边registry属于数据/评价角色，未整份喂给预测。

北门和W7纯分类缓存仅obs SHA、原分类源码/配置字节绑定和M0/M1区域，不含旧routes/query/reference/readlog/features。W7复用首次同masked观测实际分类结果，未重新执行分类器；补negative guard后重新冻结两共同区域，再读原query。不是新盲测。

北门route-only续算确读旧prediction整份元数据，原分类日志只是继承证据，本次actual read_bytes另列；旧routes只用于历史对账，源码和当前区域/图/query父SHA已独立核对。最终ZIP从纯输入缓存冷重放另核，不将续算冒充observed-only新分类执行。

R0所有失败、partial、unsafe和计数误估保留；R1修复及实际范围见 `private_guard_v3_independent_input_review.json`、`free_independent_checks.json`、`closed_access_D30_independent.json`、`independent_budget_FINAL_R1.json`。未新下载地图、调用地图API、训练模型或生成未登记入口。
