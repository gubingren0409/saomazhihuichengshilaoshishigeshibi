# 街区侧R0/R1/R2：逻辑侧别与条件通道

R0沿用道路轴/共享街道；R1/R2才分别保留road_id+side+level逻辑身份，R2进一步增加条件缺标侧道。

24次尝试含6成本修复重测，22实际求解，最终矩阵18；R0两条ZERO_LENGTH_COLLAPSED_SIDE_ALIAS仍不是合法过街。4米偏移SCHEMATIC，缺真实侧向位置/物理平行去重/同侧广场接口验证；原生窗不是博物馆到门任务。

材料身份：SUPPLEMENTARY_RESEARCH / LATER_EXPLORATION。本轮没有重算路线。
