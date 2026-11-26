# Smart City Walkability Foundation

Project: 面向复杂建筑的目的地接入关系补全与可靠到达点选择。

Canonical repository: https://github.com/gubingren0409/saomazhihuichengshilaoshishigeshibi

PG1 is a staged parent goal. This bootstrap covers historical handover, six-scene source-to-render map fidelity, a bounded non-campus dataset discovery, and development-only algorithm continuity. G0/G1/G2 are awaiting GPT and user review. No blind split is frozen, no blind experiment is authorized, and the initial public push requires the user's approval of the exact file inventory.

The known-entrance scope preserves registered identities and distinguishes approaching an exit from entering a building. Native, mapped-face-derived and conditional path segments have different evidence. A finite-graph route is not proof of present physical/public access.

Code is versioned here; raw inputs and local review maps remain external, SHA-bound dependencies. No credentials, raw map extracts, private coordinates, imagery, large caches or historical archives belong in this bootstrap. See `docs/round_delivery_protocol.md`, `docs/public_release_audit.md`, and `docs/project_status.md`.

Run the synthetic checks from this directory:

```powershell
python -X utf8 -B -m unittest discover -s tests -v
```

The development probe uses an explicitly supplied, SHA-checked historical archive. It does not download maps, fit a model, generate entrances, change constraints or consult blind data. Actual local commands and private output manifests are delivered in the round review packet.

## 渐进层次与当前公开范围

- [1. 早期问题与跨域证据边界](docs/progress/01_historical_scope.md)
- [2. 可步行空间机制逐步改进](docs/progress/02_walkable_space.md)
- [3. 探索、系统集成与材料交接](docs/progress/03_exploration_and_handoff.md)
- [4. 固定审核证据SHA索引](docs/progress/04_frozen_evidence_index.md)

提交记录区分工程基础与后补历史文档；这些新提交不是历史实验发生时的原始commit。全部历史算法尚未迁入，原始数据/私有包和凭据不公开。未代选新的开源许可证。
