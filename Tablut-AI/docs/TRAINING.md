# 攻方训练与独立验证

`config/roles.json` 指定 V5 攻方和冻结守方。两侧各读自己的 `models/<role>/best.json`，使用独立子进程和计时状态。守方的普通比赛配置由历史清单、模型和引擎 SHA256 固定，训练入口仅运行攻方。两侧八维特征完整保留。

从项目目录运行。训练初始权重来自 `models/attacker/best.json`。默认种群 8，精英 2，交叉概率 0.7、变异概率 0.2、Sigma 40、权重绝对值上限 1000。快筛 4 局、目标深度 3，复筛 12 局、目标深度 4。训练和复筛对手均使用冻结守方引擎，Escape、Protective、Champion、Manual 的目标权重为 30%、30%、25%、15%。整数局数用最大余数分配。复筛先按同场攻方冠军的 2:1:0 官方积分设底线，再按胜局数排名。

```powershell
python -m scripts.train
python -m scripts.train --resume
python -m scripts.train --config config/training.json --output-dir reports/training/run02
```

恢复时保持原输出目录、随机种子、开局、候选引擎和对手模型。训练用已保存合法棋谱恢复当前代，已完成代从检查点继续。修改训练参数时另起一个输出目录。各轮优胜模型留在训练目录的 `attacker_best.json`，独立验证通过后再人工更新攻方冠军及对应哈希。

可加 `--archive-to ../reference/archive/run02` 将已经结束的代及较旧检查点压缩备份。验明内容后清理工作目录中的相应原始副本，最新两个检查点与每代统计仍保留。一个归档目录对应一个训练运行。

```powershell
python -m scripts.benchmark --research --candidate-side A --pairs 16 --output reports/experiments/fixed_a
python -m scripts.benchmark --research --candidate-side D --pairs 16 --output reports/experiments/fixed_d
python -m scripts.benchmark --research --pairs 16 --output reports/experiments/swapped
python -m scripts.analyze reports/experiments/swapped --html-dir reports/experiments/swapped
```

研究模式支持显式替换引擎、模型及深度。用 `--openings FILE` 提供预留开局文件，对战前核对其与训练开局按棋盘对称去重。显式开局集会保存指纹，续跑会核对原清单。晋级看角色胜率、官方积分率和时间安全，单一对手或少量样本只能用作初筛。

## 攻方战术修复的实验开关

默认攻方使用 R0 正确性修复和原冠军权重。E1 战略排序保持关闭。可用既有 40 局棋谱重跑 6 个分歧局面的固定节点诊断。

```powershell
python -m scripts.analyze_attacker_positions
```

如需测试 R1，在固定攻方研究对局中使用 `--capture-proof`。三层先于五层，守方全部应手都必须通过，只有已证明获胜才覆盖常规 Alpha-Beta。预算取剩余单步时间的 10%、100 毫秒和 1,000 个子节点中的约束，并与常规搜索共享固定节点额度。

R2 使用 `--deepen-ties`。将原最佳与至多三个近分候选进行相同深度的完整窗口比较，尝试深度 5，低分支可尝试深度 6；候选轮未完整完成时继续采用最后已完整验证的结果。两个开关均只允许固定攻方实验，默认关闭。
