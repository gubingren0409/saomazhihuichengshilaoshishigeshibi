# 最终浏览器核验的测试脚本修复

2026-11-11 第一次最终26案例浏览器核验完成 file/HTTP 交互后，在连续截图的同一 `#compare` URL 上触发 `assert not ref-toggle.checked`。前一张图主动开启了参考，而相同URL的 `goto` 不会创建新文档或触发hashchange，因此保留用户开关状态。页面行为正常，错误是测试把同页导航当成首次打开。

修复限于 `scripts/check_free_visuals.py`：需要验证初始默认状态且目标URL已是当前URL时，实际 `reload` 新文档，再检查参考默认关闭。没有放宽默认关闭检查，没有修改区域、路线、参考、地图页面或算法。随后完整重跑最终浏览器和六图导出；结果以 `visual_browser_check.json` 为准。
