# 与AI下棋

安装Python 3.9+，在Tablut-AI目录启动：

```powershell
python scripts/play_cli.py
python scripts/play_cli.py --side A --strategy enhanced
python scripts/play_cli.py --side D --strategy enhanced_dynamic --show-search
```

A为攻方，先走；D为守方，帮助国王逃到边缘。列A–I、行1–9，例如 `D1 C1`。只能水平或垂直移动，不能越子；空城堡可穿越但不可停留。错误输入会重试。

| 输入 | 作用 |
| --- | --- |
| `help` | 操作说明 |
| `moves` | 所有合法动作 |
| `board` | 再次显示棋盘 |
| `quit` / Ctrl+C | 中止，不计胜负 |

默认AI为Enhanced Dynamic，另有Enhanced。`random`仅保留为测试/演示基线。人类思考不限时，AI每局累计60秒。`--show-search`展示实际目标/完成深度、节点、截止和回退；目标深度不保证完成。

只有显式使用已保存的六特征模型时，才启用遗传策略：

```powershell
python scripts/play_cli.py --side D --strategy evolutionary_dynamic --model reports/training/evolution_run/best.json --show-search
```

模型路径必须实际存在；旧线性/神经模型不兼容。普通策略不能传模型。人机模式当前不保存棋谱；逐步回放请使用[实验指南](EXPERIMENT_GUIDE.md)中的独立Demo。
