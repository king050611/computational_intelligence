# JC4004 Tablut AI v2.2

Python Tablut 机器人，支持终端人机对战、自动对战实验、搜索监控和离线棋谱回放。正式评测入口为 `TeamXX.py`。

## 准备环境

安装 Python 3.9+，在 `Tablut-AI/` 目录打开终端：

```powershell
python --version
python -m unittest discover -s tests -v
```

原版机器人只使用 Python 标准库。神经网络训练、神经网络对战和相关测试需要 NumPy。`reference/requirements.txt` 是课程提供的环境快照。

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

### 生成逐步回放

```powershell
python scripts/replay_demo.py --games 2
Start-Process 'reports/replays/latest/replay.html'
```

这是重新进行的两局AI比赛，生成逐步JSON和离线HTML，并不会播放刚才benchmark或人机模式的比赛。两种工具输出的区别见[实验指南](docs/EXPERIMENT_GUIDE.md)。

## 自博弈训练

在 `Tablut-AI/` 中运行。训练使用现有规则和 Minimax，拟合国王包围压力、逃生路线、子力差和截距这四个系数。每批自博弈加入探索走法并交替安排历史对手，保留最近三批完成对局的局面。目标值按守方视角记为胜 +1、负 −1、和 0，攻方用相反的估值。达到训练步数上限但仍未结束的棋局会丢弃。

```powershell
python scripts/train_selfplay.py --iterations 2 --output-dir reports/training/my_run
python scripts/train_selfplay.py --resume --iterations 3 --output-dir reports/training/my_run
```

每轮生成一个 `checkpoint-NNNN.json`。续跑从最高编号继续，沿用训练的种子和评测设置，可通过 `--train-games` 和 `--max-plies` 调整新的训练批次。候选和历代最佳分别存于 `candidate` 和 `best`。训练用最新候选继续生成棋谱，选择模型时使用固定开局集上的 Greedy、Minimax 对手、攻守互换和裁判的整局计时。候选总积分严格超过当前最佳时才替换最佳。第零轮是原有手写估值，若它仍表现最好，`best.weights` 为 `null`。

```powershell
python scripts/benchmark.py --strategy minimax --model reports/training/my_run/checkpoint-0005.json --opponent minimax --games 10
```

`--model` 读取指定检查点的最佳估值，加 `--candidate` 可以测试该轮候选，`--opponent-model` 可为内置对手指定另一检查点。固定开局和对手用于选模型，正式比较棋力时另做独立对战，分别报告攻守成绩。学习产物保存在 `reports/training/`，需要分享时单独复制检查点。

### 持续优化

已有默认训练记录时，可以从最新检查点开启持续模式：

```powershell
python -u scripts/train_selfplay.py --resume --continuous
```

每轮先用新棋谱拟合权重，再评估两个版本。一个将拟合权重与历史最佳权重混合，另一个扰动历史最佳权重来探索新组合。混合比例和扰动幅度随轮次变化，两个候选的参数与成绩都写入检查点的 `trials`。得分更高的候选进入下一批自博弈，超过历史最佳分数时晋升。单独指定 `--output-dir` 可运行独立实验。

在另一个 PowerShell 窗口创建停止文件，训练器保存当前轮检查点后退出：

```powershell
New-Item -ItemType File -Path 'reports/training/default/STOP'
```

自定义目录时把上述路径改为该次训练的目录。下次启动前将 `STOP` 文件移出训练目录。每个训练目录由一个进程写入，进程退出后系统会释放锁。检查点的 `best` 记录固定评测集上的最高得分版本，可用 `benchmark.py --model` 做单独对战。

### 神经网络自博弈

从 GitHub 克隆后，在 `Tablut-AI/` 中运行以下命令。默认使用项目的手写估值作为初始对手和评测基线。已有线性自博弈检查点时，可加 `--reference` 并传入该 JSON 文件的路径，使用其中保存的最佳估值。

```powershell
python -m pip install numpy
python -u scripts/train_neural.py --continuous
```

第一阶段用完整的 9×9 棋盘和当前走棋方训练价值网络，并在相同深度的 Alpha–Beta 下与三特征模型比较。第二阶段从价值网络开始，用 MCTS 自博弈，把终局胜负和合法走法的访问次数一起用于训练。每个评测开局都交换攻守。每阶段首轮另有独立开局评测，训练进程在终端报告成绩和保存位置。

每轮将模型权重、训练损失、评测结果和各阶段最佳轮次写入 `reports/training/neural/checkpoint-NNNN.npz`。创建 `reports/training/neural/STOP` 可让进程保存当前轮后退出。移出该文件后，用 `python -u scripts/train_neural.py --resume --continuous` 从最近的检查点续跑。可以用以下命令单独评测某一轮，脚本会根据检查点选择 Alpha–Beta 或 MCTS。

```powershell
python scripts/benchmark.py --neural-model reports/training/neural/checkpoint-0002.npz --opponent minimax --games 2
```

## 按任务阅读

| 你想做什么 | 文档 |
| --- | --- |
| 学会与AI下棋 | [CLI_GUIDE.md](docs/CLI_GUIDE.md) |
| 更换Seed、对照算法、查看回放和验证结果 | [EXPERIMENT_GUIDE.md](docs/EXPERIMENT_GUIDE.md) |
| 理解规则模拟、搜索、接口和JSON字段 | [TECHNICAL_REFERENCE.md](docs/TECHNICAL_REFERENCE.md) |
| 查看组员分工、当前进度和后续任务 | [DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) |
| 找到已有实验数据、棋谱和截图 | [reports/README.md](reports/README.md) |

普通玩家只需先阅读人机指南。Adaptive使用Minimax、Alpha-Beta和迭代加深，但不预设它一定比其他策略更强；正式组号、提交包及课程引用要求见开发计划。
