# PG1 Phase 1 本地审计

在父任务的只读审核服务打开 `/phase1/index.html`。不启动或停止任何历史服务。若需要独立本地预览，可在此目录执行 `python -m http.server 53471 --bind 127.0.0.1`，结束时 Ctrl+C；默认使用父任务统一的 53501 服务。

## 重放

```powershell
python src/build_audit.py --baseline <固定R1最终ZIP> --source-root <已解包R1只读根> --runtime <R1历史results和runs根> --out <新的phase1输出目录>
python src/export_current_graph.py --baseline <固定R1最终ZIP> --source-root <已解包R1只读根> --runtime <R1历史results和runs根> --out <phase1输出目录>
python src/render_maps.py --out <phase1输出目录>
```

`--baseline` 只接受最终 SHA256 `d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed` 的 ZIP。ZIP 不会被解包或修改。现有解包目录的成员 manifest 必须与固定 ZIP 相同，实际使用的源码及数据必须匹配该 manifest。历史 APP 路线必须匹配原 `formal_registry.jsonl` 中的 SHA256。

脚本只回放源对象解析与逐段语义准入，不调用 `_build_graph`、路线求解器或完整可视图。处理单场景可添加 `--scene sh-library`；输出目录必须与历史目录隔离。Python 禁止在旧源码目录产生 bytecode。

## 文件边界

自有可公开候选是 `src/build_audit.py`、`src/export_current_graph.py`、`src/render_maps.py`、`src/map.js`、`src/map.css`、`index.html` 与 `requirements.txt`。它们不包含 API key、用户目录、原始裁片或旧规划器源码；是否首次公开由父任务的精确清单与用户批准控制。

审计运行仍依赖现有授权的 R1 代码和数据。源码包装不将旧代码或数据改授许可。所有 `data/`、`maps/`、源对象 ID 索引、运行收据与本文审计证据均仅在本地审核包中交付。地图保留 © OpenStreetMap contributors / ODbL attribution；派生数据的公开发布另行许可审核。

输出中的绝对证据路径用于本地追踪，不应直接推送个人 public repo。数据集 split 为 `DEVELOPMENT_FROZEN`，G1 为 `PENDING_USER_REVIEW`。完整解释见 `audit_findings.md`。
