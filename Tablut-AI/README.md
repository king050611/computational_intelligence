# Tablut AI

JC4004 Computational Intelligence 课程的 9×9 Tablut AI。攻方先走并尝试围捕国王，守方尝试把国王走到边缘。棋子沿行或列滑动，课程裁判处理捕获、重复局面与终局。

开发配置按角色隔离。攻方使用 V5 和 V4 冠军八维权重，守方固定使用继承 V6 搜索的 D-Champion-01。两侧使用迭代加深和 Alpha-Beta，各有 60 秒总预算，默认最大深度 4。守方源码和模型进程启动前逐文件校验。课程入口 `TeamXX.Player` 保留原正式 Bot。独立引擎可通过 `TeamXX.independent_player()` 验证，完成独立验收后再决定是否替换正式入口。

在 `Tablut-AI` 目录使用 Python 3.9 或更新版本，无需第三方库。

```powershell
python -m scripts.play --side A --output reports/experiments/human.json
python -m scripts.benchmark --research --candidate-side A --pairs 2 --output reports/experiments/local_pair
python -m scripts.analyze reports/experiments/local_pair
python -m scripts.train
python -m unittest discover -s tests -v
```

人机对战输入两个棋格，例如 `D1 C1`。用 `moves` 查看合法走法、`board` 重新显示棋盘、`help` 查看命令、`quit` 结束。把 `--side` 改为 `D` 可以执守，AI 先走。加 `--show-search` 查看实际搜索深度。

- `engines/` 保存互相隔离的攻守引擎。
- `models/` 保存角色冠军权重及训练对手模型。
- `config/` 保存角色和训练配置。
- `src/` 和 `scripts/` 提供规则、对战、训练与分析工具。
- `reference/Tablut.py` 为课程裁判。

[训练与验证](docs/TRAINING.md) · [实验结论与归档恢复](reports/RESULTS.md)
