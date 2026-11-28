# Tablut AI

JC4004 Computational Intelligence 的 9×9 Tablut Bot。攻方先走并尝试围捕国王，守方尝试把国王走到边缘。棋子沿行或列滑动，课程裁判处理捕获、重复和终局。

正式入口是 `TeamXX.Player`。攻方采用原 V5，守方保持 D-Champion-01。两侧使用冻结的 V4 冠军八维权重、Alpha-Beta、迭代加深与自适应计时，最大完整深度 4，每方每局累计 60 秒。E1、R0、R1、R2 作为历史实验配置保留。旧入口可通过 `TeamXX.LegacyPlayer` 回退。

正式运行使用 Python 3.9+ 和标准库。提交时按 [文件清单](reports/submission_manifest.json) 保持相对目录结构。在 `Tablut-AI` 中运行：

```powershell
python -m scripts.play --side A
python -m unittest discover -s tests -v
```

人机对战输入两格坐标，例如 `D1 C1`。输入 `moves` 查看合法走法、`help` 查看命令、`quit` 退出。

[复现指南](docs/REPRODUCTION.md) · [论文实验结论](reports/RESULTS.md) · [实验数据索引](reports/experiment_index.json)
