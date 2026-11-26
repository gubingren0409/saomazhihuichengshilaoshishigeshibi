# 运行与复验边界

实际演示为只读路线诊断，不是新的在线求路APP。解包根目录运行：

```powershell
python -X utf8 -B scripts/serve_review.py --port 53451
```

打开http://127.0.0.1:53451/，前台Ctrl+C停止。若本轮后台服务已在运行，先GET http://127.0.0.1:53451/api/health，确认service为PED_AREA_CONNECTIVITY_R2_DIAGNOSIS，再停止该JSON中对应pid；不要按模糊Python进程名停止，也不影响旧53421/53431/53441。改用其他空闲端口可查看解包目录的独立版本。

无需原R1 ZIP即可查看包内HTML、四图、CSV与薄图距离证书。要独立核验原始坐标/来源、旧32响应和原图归属，另提供R1固定ZIP（SHA d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed）。假设下载的R2包位于delivery/OPEN_REVIEW.zip：

```powershell
python -X utf8 -B src/independent_archive_replay.py --archive delivery/OPEN_REVIEW.zip --baseline "<R1固定ZIP绝对路径>" --extract-to delivery/clean_replay --receipt delivery/independent_unpack_receipt.json
```

目标解包目录必须为空；脚本拒绝覆盖已有复验目录。它校验CRC、成员安全及全部内容SHA，使用单独原始R1来源复查，并重放有限图的完整距离/分量/归属/反事实/替代几何证书，额外APP solver与SSSP均为0。输出JSON含实际检查与未覆盖范围，不替代真实浏览器和现场核验。

```powershell
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B src/independent_graph_certificates.py
```

前者8项合成诊断测试，后者在给定薄图上检查全部距离证书，均不是重新跑8正式求路。本轮正式8调用已经在runs/和solver_registry中固定；不要再次运行diagnose.py来假称增加了独立测试。原始图构建、来源约束和所有潜在端点附着的连续域最优性不属于这次证书证明。

实际用到的环境版本见requirements.txt；网页是自包含HTML/gzip，无外部瓦片/字体/CDN依赖。Python复验需相应本机库，未打包Python解释器。没有复制整个R1工程或旧大数据，本包不是全历史自包含环境。
