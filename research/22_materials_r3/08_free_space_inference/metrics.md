# F0/F1：未知事实与条件规划许可分开

F0先排除共同已知限制，再允许剩余局部未知空间条件参与求路。F1与F0同区域、节点、边和接口，只对假设段采用有限额外成本。

- M1-C_valid_reached：20 query；口径：33 positive queries
- M1-C_area_covered：36.644381346279644 m²；口径：7 area references /3996.534424703586 m²
- M1-C_area_total：3996.534424703586 m²；口径：7 area references
- M1-C_line_covered：34.99989425733953 m；口径：14 line references /215.76619820972144 m
- M1-C_line_total：215.76619820972144 m；口径：14 line references
- M1-C_unverified_remaining：66.85938348054503 m²；口径：7 area references; reference-outside unconfirmed expansion
- M1-C_outside_only：5 queries；口径：33 positive queries
- M1-C_conflict_queries：0 queries；口径：33 positive queries
- F0_valid_reached：26 query；口径：33 positive queries
- F0_area_covered：3996.5344247022063 m²；口径：7 area references /3996.534424703586 m²
- F0_area_total：3996.534424703586 m²；口径：7 area references
- F0_line_covered：157.86236770923733 m；口径：14 line references /215.76619820972144 m
- F0_line_total：215.76619820972144 m；口径：14 line references
- F0_unverified_remaining：10278.986186267939 m²；口径：7 area references; reference-outside unconfirmed expansion
- F0_outside_only：1 queries；口径：33 positive queries
- F0_conflict_queries：0 queries；口径：33 positive queries
- F1_valid_reached：26 query；口径：33 positive queries
- F1_area_covered：3996.5344247022063 m²；口径：7 area references /3996.534424703586 m²
- F1_area_total：3996.534424703586 m²；口径：7 area references
- F1_line_covered：157.86236770923733 m；口径：14 line references /215.76619820972144 m
- F1_line_total：215.76619820972144 m；口径：14 line references
- F1_unverified_remaining：10278.986186267939 m²；口径：7 area references; reference-outside unconfirmed expansion
- F1_outside_only：1 queries；口径：33 positive queries
- F1_conflict_queries：0 queries；口径：33 positive queries
- F0_added_vs_M1_C：6 query；口径：33 positive queries
- F0_lost_vs_M1_C：0 query；口径：33 positive queries
- F0_paired_length_m：710.4225331225492 m；口径：26 same reached positive queries
- F0_paired_assumed_m：348.91836225742145 m；口径：26 same reached positive queries
- F0_paired_native_m：311.429671008158 m；口径：26 same reached positive queries
- F0_paired_mapped_area_derived_m：50.07449985696984 m；口径：26 same reached positive queries
- F0_paired_cost：710.4225331225492 weighted metre；口径：26 same reached positive queries
- F1_added_vs_M1_C：6 query；口径：33 positive queries
- F1_lost_vs_M1_C：0 query；口径：33 positive queries
- F1_paired_length_m：715.0972545159681 m；口径：26 same reached positive queries
- F1_paired_assumed_m：324.2709853786829 m；口径：26 same reached positive queries
- F1_paired_native_m：340.7517692803154 m；口径：26 same reached positive queries
- F1_paired_mapped_area_derived_m：50.07449985696984 m；口径：26 same reached positive queries
- F1_paired_cost：1039.368239894651 weighted metre；口径：26 same reached positive queries
- F1_minus_F0_geometry_m：4.674721393418849 m；口径：26 same reached positive queries
- F0_minus_F1_hypothesis_m：24.647376878738555 m；口径：26 same reached positive queries
- R0_private_wrongly_admitted_area：128.38855916051605 m²；口径：W7a6b5a10076_G_080 within D30; historical R0 only
- R1_private_assumed_overlap：0.0 m²；口径：W7a6b5a10076_G_080 within D30; final R1
- R1_private_restricted_area：128.38855916082926 m²；口径：W7a6b5a10076_G_080 within D30; final R1

限制：同一主批33正例从20到26，新增6失去0；F0/F1可达集合相同。七面参考外10278.99平方米仅未获参考证实，不自动算全错；8障碍查询6合法绕行、2不通，已知冲突0。七正例仍失败。旧private漏导已修，不能用旧07图作当前成果。
