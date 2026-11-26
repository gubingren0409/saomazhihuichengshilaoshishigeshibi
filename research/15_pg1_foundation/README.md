# PG1 初始基础轮本地审查入口

先看 http://127.0.0.1:53501/ ，再看FOUNDATION_REVIEW.md。六场景地图在phase1/index.html；真实候选图册在phase2/index.html。本包是私有审查实物，**不是允许上传Public的文件集合**。

## 启动和停止

在解包根目录执行：

```powershell
python -X utf8 -B scripts/serve_review.py --port 53501
```

打开上面的本机地址；前台Ctrl+C停止。若后台实例已运行，先查看 http://127.0.0.1:53501/api/health ，只有service=SMART_CITY_PG1_FOUNDATION_REVIEW时才按其pid停止；不要按模糊Python进程名停进程，也不动旧53421/31/41/51。独立解包复验用其他空闲端口。

无需互联网瓦片，但phase1交互需要本机HTTP取分文件JSON；直接file打开根HTML可看六张固定图，phase2自包含图册可直接file打开。图层切换不调用新solver，旧路线均保留历史run身份。没有在线推送接口。

## 版本与公开边界

repository/为个人仓库拟公开源码，精确38文件清单在audit/PUBLIC_FILE_INVENTORY.csv，Final Commit与Git tree在audit/ROUND_BINDING.json；git/PG1_SOURCE.bundle保留本轮本地三次提交，无旧仓库history。源码逐字节与Git blob一致；私有phase1/phase2/src是同字节生成镜像，不另作为编辑源。修改正式源码后须重建受影响产物、重新commit/封包/复验，不能继续引用旧ZIP。

首次公开Push、软件许可证、地图呈现合同、数据分组仍待G0/G1/G2批准。当前个人远程仍为空，不能冒称GitHub已经有这份源码。原件/坐标/图片/API响应/旧包不在首次公开清单。细项见repository/docs/public_release_audit.md与reviews/INDEPENDENT_REVIEW.md。

## 本地离线复验

五项新源码合成检查：

```powershell
python -X utf8 -B -m unittest discover -s repository/tests -v
python -X utf8 -B repository/tools/verify_probe_certificates.py --probe track_a/TA-PG1-01 --out delivery/author_certificate_replay.json
```

后者重验八个已保存有限图证书，新增solver=0；不是再次运行8请求。实际历史source/topology核验还需单独提供固定R1/R2 ZIP：

- R1 SHA256：d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed
- R2 SHA256：3988e9fba95da70dc03b8191a177740a3ccd13602019afe3765e566648b55711

独立脚本在reviews/src，使用PG1_REVIEW_R1_ZIP、PG1_REVIEW_R2_ZIP两个进程级变量只读定位，不更改全局环境。图册/新薄图证书可直接查看，但从raw源重新生成所有lineage仍依赖R1源码/原件/manifest，不能声称全历史自包含。完整从头重建会需要在隔离目录解包该已核验R1、提供--source-root/--runtime/--out，不在旧目录写文件；本轮未重建全局VG或104实验。

实际预算和结果见phase1/execution_receipt.json、phase2/collection_receipt.json、track_a/TA-PG1-01/registry.json及最终delivery/FINAL_STATUS.json。峰值内存未instrument；网络超时总字节UNKNOWN。独立复验、GPT审查、用户自然语言验收各有身份，整个Parent Goal并未PASS。

固定ZIP和解包回执位于delivery。回执在包外绑定实际ZIP SHA，包内STATUS/CHECKPOINT保留封包前真实时序，不循环写自己的SHA。旧服务当前可用性未确认，不以本轮新只读页面替代旧已知入口APP功能验收。
