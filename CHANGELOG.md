# Changelog / 更新日志

## v0.2.0 — 2026-10-27

- 新增可切换的专业模式，保留中英文与浏览器偏好记忆。
- 新增训练监控页，读取实际 TensorBoard 事件中的 17 种损失、梯度和学习率指标；支持指标切换、指数平滑、悬停采样值及训练轮数/步数/进度。
- 新增增量实时控制台，可监控训练、素材处理与翻唱任务，支持暂停/恢复跟随、清空本地视图、自动滚动和下载完整日志。
- 兼容训练恢复后重复步数、未完成写入的事件文件、UTF-8 分段及大日志；限制缓存与曲线点数，缺失数据时显示空状态。
- 新增 `update.bat`，更新代码和应用依赖，不移除本地模型或录音。
- 新增 TensorBoard 读取与前端曲线测试；22 项 Python 测试和 4 项 JavaScript 测试通过。

验证使用隔离的合成 TensorBoard 事件与日志，**没有启动真实训练或宣称训练音质已通过验收**。

### English

- Added a persistent bilingual Professional mode and a dedicated training monitor.
- Read actual TensorBoard loss, gradient and learning-rate events with metric selection, EMA smoothing, sample inspection and observed epoch/step/progress.
- Added incremental read-only live consoles for all job types, with pause/resume, clear view, auto-scroll and complete log downloads.
- Handle resumed steps, partial writes, Unicode boundaries and bounded logs/event caches. Missing real metrics remain empty.
- Added `update.bat` for code and application-dependency updates while retaining local models and recordings.
- Validation: 22 Python tests and 4 JavaScript tests; isolated synthetic event/log fixtures only. No real model training was run.

## v0.1.0 — 2026-10-26

Initial bilingual local RVC workstation: dataset preparation/review, training orchestration, voice import/export, source separation, conversion, mixing and durable tasks. Source was published before formal versioned releases were introduced.
