# 数据版本与纠错身份

- Q2入口身份主表和9条主请求使用米制坐标，一直保留。补充审计A0误把Source.coord经纬度当米：其3条上下文PASS和3条身份FAIL均失效，字节与源码仍在；当前使用entry_constraint_context_A1.csv及outputs/identity_recheck_A1.json。Q2_SUPERSESSION_MAP记录对应关系，不把审计器错误算入口错误。
- Q6初次审计器字段错误和8个聚合schema假FAIL保留；A3改为INCONCLUSIVE，没有改原算法/旧值。
- Q7首版博物馆封闭了residential道路轴，19行作为secondary压力测试；A1按源标签关闭footway。图书馆原19行合格，主表38行。两版干预不同，不能称方法优化。原始raw包含所有版本。
- Q8 A0暖机/正式ID碰撞，38条记录整批不用于主计时，3个独立暖机输出无法恢复。主小图A1不包含A0。Top3首版43次有效整体计时保留secondary；A2同图同算法补阶段时钟作为主版，不按快慢选留。
- K2、Top3、状态注入、合并输入是本轮新增实验适配器，不是冻结APP已部署的产品功能。旧核心、源对象坐标/标签及历史报告未修改。
