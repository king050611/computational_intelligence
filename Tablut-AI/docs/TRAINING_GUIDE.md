# 可选训练：Self-play、神经网络与模型评测

这些模块用于独立实验，不替换正式Assessment Bot。`TeamXX.Player()`保持稳定版接口，默认使用手工评估；模型由实验用StrategyBot或NeuralPlayer显式加载。原有规则、权重配置、人机CLI和Replay不因安装模型而自动切换算法。

所有命令均在 `Tablut-AI/` 目录执行。普通实验见[实验指南](EXPERIMENT_GUIDE.md)，接口和搜索口径见[技术参考](TECHNICAL_REFERENCE.md)。

## 1. 环境与验收顺序

线性训练只需标准库。神经网络训练和模型对战需NumPy：

```powershell
python --version
python -m unittest discover -s tests -p test_bot.py -v
python -m unittest discover -s tests -p test_cli.py -v
python -m unittest discover -s tests -p test_learning.py -v

# 仅使用神经网络时安装
python -m pip install -r requirements-neural.txt
python -m unittest discover -s tests -p test_neural.py -v
```

未安装NumPy时，神经网络测试明确显示Skipped；这不等于已通过神经网络验收。完整训练环境必须实际运行这些用例。默认Assessment功能和线性训练不应依赖NumPy；课程最终依赖限制仍需团队核对。

先验证有限训练、检查点、续训和模型加载，再决定是否长时间运行。下文命令是操作说明，不表示训练已取得性能提升。

## 2. 线性自博弈

`scripts/train_selfplay.py`复用现有规则和固定目标深度的Minimax。特征由国王相邻攻击者、国王逃生路线、子力差及截距组成，训练时缩放后用岭回归拟合守方视角价值；攻方使用相反分数。训练加入随机探索和历史模型对手，只保留最近三批完成对局的样本。超出步数上限的未终局对局记为truncated，不伪造平局标签。

### 新建一轮

```powershell
python scripts/train_selfplay.py --iterations 1 --train-games 8 --eval-pairs 1 --output-dir reports/training/merge_linear
```

新目录先评测并保存手写基线 `checkpoint-0000.json`，然后训练并保存 `checkpoint-0001.json`。每次保存打印路径。已有检查点的目录必须加 `--resume`，否则拒绝覆盖。

| 参数 | 含义 / 新训练默认值 |
| --- | --- |
| `--iterations` | 有限模式额外轮数，默认1，必须正数；与continuous互斥 |
| `--output-dir` | 输出目录，默认 `reports/training/default` |
| `--resume` | 从最高编号JSON继续 |
| `--seed` | 默认42，控制训练与评测随机流 |
| `--train-games` | 每轮自博弈局数，默认16 |
| `--eval-pairs` | 每个固定对手的开局对数，默认3，每个开局交换攻守 |
| `--max-plies` | 训练局半步上限，默认160；不是正式裁判的步数规则 |
| `--continuous` | 持续优化，直到STOP出现，不与iterations同时使用 |

### 续训和模型选择

```powershell
python scripts/train_selfplay.py --resume --iterations 1 --output-dir reports/training/merge_linear
```

该命令再训练一轮，例如已有0001则生成0002。续训沿用保存的配置：可显式调整新的train-games和max-plies，但不得更换seed或eval-pairs而继续比较旧的最佳成绩。

检查点的 `candidate` 是当轮候选，`best` 是固定评测套件中的历史最佳。候选总积分严格高于原最佳才晋升。评测包含Greedy/Minimax对手、固定开局、攻守互换和官方整局计时；训练局数量不等于评测局数量。

如果 `best.weights` 仍为 `null`，说明手工评估仍是历史最佳，`--model`会继续使用它，不代表模型加载失败。要测实际拟合的权重，用 `--candidate`：

```powershell
python scripts/benchmark.py --strategy adaptive --model reports/training/merge_linear/checkpoint-0001.json --candidate --opponent minimax --games 2 --output reports/experiments/linear_candidate.json
python scripts/benchmark.py --strategy minimax --model reports/training/merge_linear/checkpoint-0001.json --opponent minimax --games 2 --output reports/experiments/linear_best.json
```

`--opponent-model <JSON>`为内置对手选择检查点的best；它不能与 `--opponent-file` 同时使用。线性模型必须配合greedy/minimax/adaptive，不能配first/random。

### 可控停止

先确认短训练正常，再在原目录继续：

```powershell
python -u scripts/train_selfplay.py --resume --continuous --output-dir reports/training/merge_linear
```

持续模式每轮尝试混合拟合权重与最佳模型、以及扰动最佳权重两个候选，参数和成绩保存在 `trials`；停止文件在轮次之间检查：

```powershell
# 在另一终端执行；当前轮完成并保存后退出
New-Item -ItemType File -Path 'reports/training/merge_linear/STOP' -Force
```

下次继续前移走或删除STOP文件。线性有限模式不会用STOP中断；Ctrl+C时可从最后完整检查点恢复，未完成的一轮不算已保存。每个训练目录同时只允许一个训练进程。

## 3. 两阶段神经网络

价值网络从完整9×9棋盘及行动方预测守方价值，仍由Alpha-Beta负责选择走法。随后策略价值网络输出价值及合法动作概率，用MCTS自博弈训练。这是轻量实验实现，不应直接称为完整AlphaZero。

### 有限流程验证

```powershell
python scripts/train_neural.py --value-rounds 1 --train-games 8 --eval-pairs 1 --simulations 8 --epochs 1 --output-dir reports/training/merge_neural
```

新训练默认一轮value阶段，再进行一轮policy阶段。上述配置正常完成后应有：

```text
reports/training/merge_neural/
  checkpoint-0001.npz   # phase=value
  checkpoint-0002.npz   # phase=policy
```

神经网络脚本没有 `--iterations` 参数。有限运行由value-rounds决定新训练的value轮数，并额外执行一轮policy；检查点已超过此界限后，有限续训仍会再进行至少一轮。长期运行需显式continuous。

| 参数 | 新训练默认值 / 用途 |
| --- | --- |
| `--output-dir` | `reports/training/neural` |
| `--reference` | 可选线性JSON检查点；使用其best作为教师/比较基准，默认手工评估 |
| `--seed` | 6421，必须非负 |
| `--value-rounds` | 1 |
| `--train-games` | 12 |
| `--eval-pairs` | 3，选择集与独立评测开局各有该数量 |
| `--simulations` | 16，MCTS每次搜索最多模拟次数，仍受决策截止限制 |
| `--epochs` | 3，每轮优化轮数 |
| `--max-plies` | 120，训练局截断上限 |
| `--resume` / `--continuous` | 恢复训练 / 持续policy训练至STOP |

数值训练参数除seed外须为正。第一轮可用教师生成样本，之后加入当前模型及历史对手。没有完成对局或policy没有有效策略样本时会报错；应检查truncated数量并调整训练局数/上限，不能把空样本当作训练成功。

模型在固定选择开局中比较，每阶段首次还报告独立开局成绩；policy首次额外对比value网络。检查点记录权重、配置、phase、样本数、损失、评测及各阶段best编号。**传给benchmark的是指定文件当轮的网络**，不会自动换成metadata中的最佳轮次；要测试最佳模型，请选对应编号的文件。

### 加载value或MCTS

```powershell
python scripts/benchmark.py --neural-model reports/training/merge_neural/checkpoint-0001.npz --opponent minimax --games 2 --output reports/experiments/neural_value.json
python scripts/benchmark.py --neural-model reports/training/merge_neural/checkpoint-0002.npz --opponent minimax --games 2 --output reports/experiments/neural_mcts.json
```

benchmark从phase选择value+Minimax或policy+MCTS，模拟次数读取检查点配置；不要同时传 `--strategy` 以假定覆盖网络策略。`--model`和 `--neural-model`互斥，`--candidate`仅用于线性model。模型实验未指定output时会自动生成带基础Seed和UTC微秒时间戳的独立文件：线性或opponent-model实验使用 `selfplay_seed42_<时间戳>.json`，神经网络按phase使用 `neural_value_seed42_<时间戳>.json` 或 `neural_policy_seed42_<时间戳>.json`。无模型的普通benchmark仍写 `latest_v2.json`。报告中建议显式指定 `--output`，便于追踪参数；同一显式路径重复运行仍会覆盖。

### 续训与停止

```powershell
python -u scripts/train_neural.py --resume --continuous --output-dir reports/training/merge_neural
New-Item -ItemType File -Path 'reports/training/merge_neural/STOP' -Force
```

创建STOP需在另一终端执行，训练器在当前轮保存后退出。神经网络有限/持续模式都会在轮次之间检查STOP；继续前移走该文件。若只想有限续训，去掉continuous。

神经网络续训完全沿用保存配置，禁止再传seed、value-rounds、train-games、eval-pairs、simulations、epochs、max-plies或reference覆盖。若使用reference，其**绝对路径**保存在检查点；迁移机器时必须让原路径中的参考JSON仍可访问。当前没有续训时重新映射reference的命令，不能只复制NPZ就假定可续训。未指定reference的训练没有该路径依赖。

## 4. 检查点与文件系统

`reports/training/`已被Git忽略；分享时另行复制模型，保留实际Git SHA、Python/NumPy版本、配置及日志，不把大型训练产物加入源代码提交。JSON和NPZ不可混用；缺失、损坏或格式不兼容应先修正模型文件，再进行比赛。

两个保存器均先写同目录临时文件，再用 `os.link()`发布新的编号，避免覆盖已有检查点。因此输出目录需位于支持硬链接的文件系统（例如本机NTFS），已有目标编号不得覆盖。同步盘、网络盘或不支持硬链接的文件系统需先实际验证。仅复制 `.training.lock` 文件不代表有运行中的锁；锁由操作系统持有，不要同时启动多个写入者。

## 5. 实验结论与功能边界

训练成功、损失下降或模型被选为best，只说明对应流程或固定评测有效。棋力比较需使用未参与模型选择的对手/开局、攻守交换，分别报告成绩、累计耗时、非法动作、异常和截断率。两局加载验证不能证明训练模型强于原版。

正式Assessment仍使用原来的 `Player()`，无需模型或NumPy；线性候选通过StrategyBot进入实验，神经网络通过NeuralPlayer进入实验。当前人机CLI和Replay仍只支持原有内置策略，没有训练后神经网络的人机入口或专用回放。MCTS及持续训练属于实验功能，不能替代正式每局累计60秒与稳定性验收。
