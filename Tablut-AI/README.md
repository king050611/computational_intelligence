# JC4004 Tablut AI — 统一 Alpha-Beta

项目围绕一个增强搜索引擎、三个核心策略和一个遗传训练入口维护。Python 3.9+，全部运行功能只需标准库；在 `Tablut-AI/` 目录运行命令。

| 策略 | 用途 |
| --- | --- |
| `enhanced` | 迭代加深、完整分支Alpha-Beta、走法排序、置换走法提示；静态预算 |
| `enhanced_dynamic` | 相同搜索器，使用动态预算；正式 `TeamXX.Player()` 默认 |
| `evolutionary_dynamic` | 相同动态搜索，显式加载六特征遗传权重；研究策略，尚未证明更强 |

`random` 只作为测试、演示对手保留。First、Greedy、旧Minimax/Adaptive、线性训练、神经网络和MCTS已从当前入口移除。旧成果的归档及历史版本见[精简复盘](reports/SIMPLIFICATION_REVIEW_20261125.md)。

## 验证与人机对战

```powershell
python -m unittest discover -s tests -v
python scripts/play_cli.py --side D --strategy enhanced_dynamic --show-search
```

列A–I、行1–9，输入 `D1 C1` 走棋；支持 `help`、`moves`、`board`、`quit`。人类思考不限时，AI每局累计60秒。详见[CLI指南](docs/CLI_GUIDE.md)。

## 自动对战与棋谱

```powershell
python scripts/benchmark.py --strategy enhanced_dynamic --opponent enhanced --games 2
python scripts/replay_demo.py --strategy enhanced_dynamic --opponent random --games 2 --seed 42 --output-dir reports/replays/current_seed42
Start-Process reports/replays/current_seed42/replay.html
```

Benchmark输出统计JSON；Replay重新进行比赛，输出逐步棋谱JSON和离线HTML。它不会自动播放Benchmark的对局。更换Random种子可产生不同棋局，不能保证改变胜负。详情见[实验指南](docs/EXPERIMENT_GUIDE.md)。

## 唯一训练入口：遗传权重优化

先验证流程，再决定是否启动耗时更长的正式训练：

```powershell
python scripts/train_evolution.py --generations 1 --population 2 --elite 1 --pairs 1 --max-depth 1 --output-dir reports/training/evolution_quickstart
```

这只是低深度、小种群流程验证。正式建议配置为12个体、2精英、10代、4对开局，默认最大搜索深度4，每代96局、10代960局。内部best不等于通过独立验证的模型；正式Bot不自动读取模型。完整训练、续训、停止和留出验证见[训练指南](docs/TRAINING_GUIDE.md)。

## 文档导航

- [CLI_GUIDE](docs/CLI_GUIDE.md)：普通玩家操作。
- [EXPERIMENT_GUIDE](docs/EXPERIMENT_GUIDE.md)：配对对照、统计和回放。
- [TECHNICAL_REFERENCE](docs/TECHNICAL_REFERENCE.md)：统一搜索、特征、模型和接口。
- [TRAINING_GUIDE](docs/TRAINING_GUIDE.md)：唯一遗传训练流程。
- [DEVELOPMENT_PLAN](docs/DEVELOPMENT_PLAN.md)：已完成及尚待验证的工作。
- [reports/README](reports/README.md)：当前与历史结果索引。

课程规则、初始棋盘及官方裁判保持原样。正式组号仍需替换TeamXX，并按课程要求打包实际依赖的config/src模块。
