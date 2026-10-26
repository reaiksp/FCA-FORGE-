# 实施记录 / Implementation status

日期：2026-10-26

## 当前交付

A（RVC / Applio）已实现为本地 Web 工作台，默认中文，支持切换英文并记住语言。覆盖素材处理与筛选、训练任务编排、模型导入/导出、歌曲分离、分段转换、混音和中间文件下载。

B（Seed-VC）未实现，由另一个 AI 后续接入；设计见 `SEED_VC_B_ARCHITECTURE_HANDOFF.md`。本次没有启动任何个人音色训练。

## 已验证

- Python 3.12.10，Windows，RTX 5080，16 GB 显存。
- RVC 和分离环境均使用 PyTorch 2.11.0+cu130；两者 CUDA 矩阵计算通过。
- RVC、HuBERT 模型类、FAISS、scikit-learn 和 audio-separator 导入通过。
- ContentVec 基础权重成功加载到 CUDA；没有执行训练。
- Applio checkout 与配置中的固定 commit 一致。
- RMVPE、ContentVec、40 kHz G/D 基础权重已下载并按固定 SHA-256 校验。
- 三个 Python 环境的 `pip check` 均无依赖冲突。
- 10 项自动测试通过：合成音频切片与静音筛除、重采样/立体声混音、防削波、时长偏差拒绝、非有限输入拒绝、任务重启恢复、无输出进程取消、API 上传/筛选/持久化、请求边界和音色包导出、上下文分段拼接。
- Python 编译与 JavaScript 语法检查通过。
- 浏览器查看了中文工作台和素材页面，验证英文切换及刷新后语言记忆；截图位于 `screenshots/`。

测试中的神经转换器使用 identity 替身，只验证拼接算法。测试与合成信号均使用隔离临时目录，不向用户数据目录写入训练素材。

## 尚未验证

按用户要求，真实训练和真实翻唱留待录音完成后自测。因此尚不能确认训练收敛、中文咬字、音色相似度、实际速度、峰值显存、最佳批大小以及整曲听感。

分离/去混响权重在首次调用时由 audio-separator 下载，尚未用真实歌曲运行。默认批大小 4、轮数 200 和 30 秒分段均是初始预设，不是实测最优值。

已完成本机安装与依赖检查，但尚未在另一台干净 Windows 机器上重装验证。源码包不包含环境、第三方 checkout、权重、录音或输出。

## 使用入口

- `start.bat`：启动服务并打开浏览器。
- `install.bat`：在另一台 Windows 机器安装组件与基础模型。
- `README.md` / `README.en.md`：中英文说明。
- `SELF_TEST_GUIDE.md`：录音完成后的自测流程。
- `scripts/package_source.py`：生成 `dist/CoverStudio-source.zip`。

仓库已初始化 Git；发布目标为 https://github.com/reaiksp/FCA-FORGE- 。个人数据与模型默认忽略，远端提交状态以 GitHub 和 Git 记录为准。

## English summary

The A workstation and orchestration are implemented, with a Chinese/English toggle. Ten synthetic/API/recovery/stitching tests pass. Both GPU environments pass CUDA matrix and import checks; ContentVec loads on CUDA, and pinned 40 kHz base models have been downloaded and hash-verified. Personal voice training and real-song conversion have deliberately not been run. Audio quality, convergence, peak memory and real throughput remain for the user's later testing. B remains a separate, unimplemented engine with a handoff design.
