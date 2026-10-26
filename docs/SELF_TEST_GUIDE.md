# 自测指南 / Self-test guide

目前没有执行真实音色训练。下面的步骤供录好素材后自行验收。

## 录音准备 / Recording

- 使用同一人的清晰录音，优先歌声，覆盖舒适音区和少量高低音、长音、气声及不同辅音。
- 使用无损文件。避免削波、强混响、叠唱和降噪造成的金属音。素材清洗后的试听优先于处理步骤数量。
- 项目建议先整理 30–60 分钟有效素材。可先用更少素材验证流程，不能据此保证最终质量。
- 对有伴奏的录音启用人声分离；已有干声时直接处理。去混响可能损伤尾音，应试听后决定是否启用。

Use consistent, clean recordings from one person, preferably singing across a comfortable range. Lossless audio is preferred. Avoid clipping, strong reverb and layered vocals. The suggested 30–60 minutes is a project starting point, not a guaranteed quality threshold. Review cleaning results by ear.

## 首次测试 / First run

1. 运行环境检查，确认 RVC 和分离环境检查通过。
2. 先上传一小段素材，在素材管理中确认切片可播放、标记合理，并保存筛选结果。
3. 先做少量轮数以确认训练/索引链路能完成，再根据试听决定正式训练参数。批大小 4 尚未实测；显存不足时从 1–2 起步。
4. 训练结束后确认音色库出现新模型，任务产物中有推理权重。不要将 `G_*.pth` / `D_*.pth` 训练状态当成推理音色导入。
5. 用一段约 15–30 秒、与训练素材不同的中文歌曲试转。先保留原调，再调整检索比例和保护参数。
6. 对比源人声与转换干声，检查咬字、目标音色相似度、原唱残留、气声、破音和高音。混音响度应一致，避免“更响”被误认为“更好”。
7. 检查整曲接缝和尾音，并试听最终混音。若最终混音失败，已完成的分离人声/转换干声仍应可以下载。

Run diagnostics, prepare a small dataset, review clips, and explicitly start a short training run to validate the chain before committing to a longer run. Import inference exports, not raw G/D training checkpoints. Test a separate short Chinese excerpt before a whole song, compare at similar loudness, and listen for diction, identity, source leakage, breaths, high notes and joins.

## 故障定位 / Troubleshooting

| 现象 / Symptom | 处理 / Action |
|---|---|
| 只有界面可用 / UI only | 运行 `scripts/setup.ps1 -Engine -Separator -Models`，再检查环境报告。 |
| 显存不足 / GPU OOM | 关闭占用显存的程序；减小批大小后新建训练任务，或缩短翻唱分段。 |
| 特征提取失败 / Feature extraction fails | 查看引擎日志，检查模型下载、素材可读性和片段长度。 |
| 下载失败 / Download fails | 检查到模型源的网络连接后重试；基础 RVC 下载支持断点与哈希校验。 |
| 服务重启 / Restart | 在任务页手动恢复；不会自动启动训练。 |
| 混音时长不匹配 / Duration mismatch | 使用同一歌曲版本的伴奏和人声；当前不会静默拉伸时间来掩盖偏差。 |

每次报告问题时附上任务 ID、阶段、引擎日志和环境报告。不要把私有录音或模型直接提交到源码仓库。

When reporting a problem, include the job ID, failing stage, worker log and environment report. Keep private recordings and voice models outside the source repository.
