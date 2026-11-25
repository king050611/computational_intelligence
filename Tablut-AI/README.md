# JC4004 Tablut AI v2.2

Python Tablut 机器人，支持终端人机对战、自动对战实验、搜索监控和离线棋谱回放。正式评测入口为 `TeamXX.py`。

## 准备环境

安装 Python 3.9+，在 `Tablut-AI/` 目录打开终端：

```powershell
python --version
python -m unittest discover -s tests -v
```

原版机器人和线性自博弈只使用 Python 标准库。神经网络训练、神经网络模型对战需要额外安装 `requirements-neural.txt`；未安装NumPy时相关测试会明确跳过。`reference/requirements.txt` 是课程提供的环境快照，不是默认运行的必装依赖。

## 三个入口

### 与 AI 下棋

```powershell
python scripts/play_cli.py
```

按提示选 A（进攻，先走）或 D（防守，AI先走）。输入 `D1 C1` 将D列第1行的棋子移到C列第1行；输入 `help` 查看命令。

```powershell
python scripts/play_cli.py --side A --strategy random
python scripts/play_cli.py --side D --strategy adaptive --show-search
```

人类思考不限时，AI累计预算60秒。人机模式尚不保存棋谱或生成回放。完整操作见[人机对战指南](docs/CLI_GUIDE.md)。

### 自动 AI 对战

```powershell
python scripts/benchmark.py --games 10
```

默认 Adaptive 对 Random，逐局交换攻守；输出胜平负、积分和JSON统计。实验命令、不同Seed及外部Bot加载见[实验指南](docs/EXPERIMENT_GUIDE.md)。

增强搜索可通过 `--strategy enhanced` 或 `--strategy enhanced_dynamic` 选择。固定深度对照、配对开局和动态计时的复现命令见[实验指南](docs/EXPERIMENT_GUIDE.md)。

### 生成逐步回放

```powershell
python scripts/replay_demo.py --games 2
Start-Process 'reports/replays/latest/replay.html'
```

这是重新进行的两局AI比赛，生成逐步JSON和离线HTML，并不会播放刚才benchmark或人机模式的比赛。两种工具输出的区别见[实验指南](docs/EXPERIMENT_GUIDE.md)。

## 可选：机器学习训练

正式 `Player()`、人机模式、默认自动对战和回放仍使用原有手工评估与搜索，不需要模型文件或 NumPy。线性自博弈可学习三个棋局特征的权重；神经网络扩展提供价值网络+Alpha-Beta，以及策略价值网络+MCTS。它们是按需启用的实验功能，尚不能据训练成功就认定比原版更强。

先做有限轮次的线性流程验证：

```powershell
python scripts/train_selfplay.py --iterations 1 --train-games 8 --eval-pairs 1 --output-dir reports/training/merge_linear
```

仅使用神经网络功能时安装额外依赖：

```powershell
python -m pip install -r requirements-neural.txt
```

训练、续训、候选/最佳模型、两阶段神经网络、停止和单独评测命令统一见[训练指南](docs/TRAINING_GUIDE.md)。训练产物保存在被Git忽略的 `reports/training/`；当前CLI和Replay尚未接入训练后的神经网络。

## 按任务阅读

| 你想做什么 | 文档 |
| --- | --- |
| 学会与AI下棋 | [CLI_GUIDE.md](docs/CLI_GUIDE.md) |
| 更换Seed、对照算法、查看回放和验证结果 | [EXPERIMENT_GUIDE.md](docs/EXPERIMENT_GUIDE.md) |
| 可选线性自博弈、神经网络训练和模型评测 | [TRAINING_GUIDE.md](docs/TRAINING_GUIDE.md) |
| 理解规则模拟、搜索、接口和JSON字段 | [TECHNICAL_REFERENCE.md](docs/TECHNICAL_REFERENCE.md) |
| 查看组员分工、当前进度和后续任务 | [DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) |
| 找到已有实验数据、棋谱和截图 | [reports/README.md](reports/README.md) |

普通玩家只需先阅读人机指南。Adaptive使用Minimax、Alpha-Beta和迭代加深，但不预设它一定比其他策略更强；正式组号、提交包及课程引用要求见开发计划。
