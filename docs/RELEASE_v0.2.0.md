# Cover Studio v0.2.0 · 专业模式 / Professional mode

本版本加入训练曲线与实时控制台。在工作台右上角打开“专业模式”，进入“训练监控”并选择任务即可使用。

- 实际 TensorBoard 指标：生成器/判别器损失、Mel/FM/KL/对抗损失、梯度和学习率，以及上游记录的 50 步均值。
- 可切换指标、指数平滑及悬停查看采样值；显示实际轮数、步数和进度。
- 实时增量日志：每 2 秒刷新，可暂停跟随、自动滚动、清空视图和下载完整日志。
- 历史任务回看、大日志限制、恢复训练重复步数及 UTF-8/部分事件写入处理。
- 中英文切换和专业模式偏好记忆。

## 更新

Git 克隆用户：关闭运行中的工作台，双击 `update.bat`，完成后运行 `start.bat`。也可以手动执行：

```powershell
git pull --ff-only
.venv/Scripts/python -m pip install -r requirements-app.lock
.venv/Scripts/python -m pip install -e . --no-deps
```

首次使用：下载并解压 `CoverStudio-v0.2.0-source.zip`，安装 Python 3.12、Git 和兼容 NVIDIA 驱动后运行 `install.bat`，再运行 `start.bat`。发布包是源码包，**不包含预装 Python 环境、模型或录音**。

## 验证范围

22 项 Python 测试与 4 项 JavaScript 测试通过。浏览器验证了双语专业模式、指标选择、曲线显示、暂停/继续日志及空状态。曲线和日志测试使用隔离的合成事件文件，没有启动真实模型训练。训练音质、收敛及显存仍需使用录音自行测试。

## English

Enable **Professional mode** in the header, then open **Training monitor** and select a job. This release adds actual TensorBoard curves with metric selection, smoothing and sample inspection; observed epoch/step/progress; and incremental live console output with pause/resume, clear view, auto-scroll and full-log downloads.

Existing Git installations: stop the running server, run `update.bat`, then `start.bat`. Fresh installations: extract the source ZIP and run `install.bat` with Python 3.12, Git and a compatible NVIDIA driver available. The source ZIP does not bundle Python environments, model weights or recordings.

Validation: 22 Python tests and 4 JavaScript tests, plus browser checks using isolated synthetic event/log fixtures. No real training or voice-quality validation was performed.
