# AI 对战、棋谱回放与实验验证

本文面向实验人员，整合自动对战、HTML 回放和 E0–E4 验证流程。人机下棋见 [CLI_GUIDE](CLI_GUIDE.md)，接口及 JSON 字段见 [TECHNICAL_REFERENCE](TECHNICAL_REFERENCE.md)，已有数据见 [结果索引](../reports/README.md)。本文的命令与待填表不是新的实验成绩。

## 1. 准备和工具区别

在 `Tablut-AI/` 目录使用 Python 3.9+，当前程序仅依赖标准库。每批实验先记录环境与代码版本，再通过测试：

```powershell
python --version
git rev-parse HEAD
git status --short
python -m unittest discover -s tests -v
```

记录实际 Python 版本、Git SHA、未提交改动和运行参数，不把不同版本的成绩混合。测试失败时先排查再比较性能；测试数量以实际输出为准。

| 入口 | 用途 | 产物 |
| --- | --- | --- |
| `benchmark.py` | 自动比赛、角色交换、积分与耗时统计 | 成绩 JSON，默认 `reports/experiments/latest_v2.json` |
| `replay_demo.py` | 重新比赛，逐步记录动作和搜索统计 | `games.json`、离线 `replay.html`，默认 `reports/replays/latest/` |
| `play_cli.py` | 人类与 AI 下棋 | 终端交互，当前不导出棋谱 |

**benchmark 不会生成或更新 HTML。** 汇总 JSON 没有完整动作，不能还原为此前比赛的回放；运行 replay 会重新比赛。打开时使用这次命令输出的具体路径，而非旧标签页或其他目录中的 HTML。

两种实验工具首局我方攻、次局我方守，交替角色，每局新建 Bot。偶数局能均衡身份。`--seed` 控制内置 Random 的随机数，每局用基础值加从0开始的局号索引；确定性策略和外部 Bot 的动作不能靠该参数强制随机化。

同一路径会覆盖已有结果，重复实验使用独立名称。`reports/experiments/*.json` 默认被 Git 忽略，交付时另行确认结果文件是否齐全。

## 2. E0：两局基准与规则核对

目标：先确认攻守均可运行，棋谱、监控与裁判执行一致。

```powershell
python scripts/benchmark.py --strategy adaptive --opponent random --games 2 --seed 42 --output reports/experiments/E0_benchmark.json
python scripts/replay_demo.py --strategy adaptive --opponent random --games 2 --seed 42 --output-dir reports/replays/E0_baseline
Start-Process 'reports/replays/E0_baseline/replay.html'
```

查看9×9棋盘、两局选择框、动作列表、翻步与自动播放、AI Search Analysis。`games.json` 与 HTML 应在同一输出目录。

已保存的[监控基准棋谱](../reports/replays/depth_demo/games.json)中，Adaptive 对 Random 的两局分别使用 Seed42、43：我方攻41步获胜（`king_captured`），我方守38步获胜（`king_escaped`），合计2胜4分。完整79步保存在 JSON，无需手工抄写。历史记录用于对照，不要求新机器的每步与其完全一致。

### 每步检查清单

以未修改的 `reference/Tablut.py` 为独立标准，不能只用自己的规则代码验证自己的输出。当前 CLI 没有额外的“一键核验全部棋谱”参数，以下是人工检查或独立验证程序应遵守的要求：

- `ply` 从1递增，A先走、A/D交替；一步指单方行动一次。
- 初始 `board_before` 与 `initial_board` 一致，此后与上一手 `board_after` 连续。
- 正常动作的 `accepted=true`；起点为本方棋子，终点为空，水平或垂直且不越子。
- 将动作交给官方裁判执行后，棋盘与 `board_after` 一致，实际移除的棋子与 `captures` 一致。
- 官方终局检查的时点、胜方、下一行动方与 `result_after`、最终 `result` 一致；验证时需同样初始化重复局面历史。
- 监控记录属于当前步，耗时非负；缺失统计为 `null` 或未记录，不能补成0。

## 3. E1：不同随机种子的稳定性

固定 Adaptive 对 Random，三个基础 Seed 各20局，每组我方执攻/执守各10局：

```powershell
python scripts/benchmark.py --strategy adaptive --opponent random --games 20 --seed 42 --output reports/experiments/E1_seed42.json
python scripts/benchmark.py --strategy adaptive --opponent random --games 20 --seed 100 --output reports/experiments/E1_seed100.json
python scripts/benchmark.py --strategy adaptive --opponent random --games 20 --seed 2026 --output reports/experiments/E1_seed2026.json
```

实际种子范围是42–61、100–119、2026–2045。检查各20局、攻守各10局、完整胜平负和耗时记录、每方累计预算60秒，以及非法动作/超时/异常的责任方。不同 Seed 通常产生不同路线，不保证胜负不同。

要直接观察两组不同路线：

```powershell
python scripts/replay_demo.py --games 2 --seed 42 --output-dir reports/replays/E1_seed42
python scripts/replay_demo.py --games 2 --seed 100 --output-dir reports/replays/E1_seed100
Start-Process 'reports/replays/E1_seed42/replay.html'
Start-Process 'reports/replays/E1_seed100/replay.html'
```

比较同一局号，保持我方身份一致，找出 Random 首次改变走法的位置。上述是新比赛，不一定逐步复现此前 benchmark 的同参数比赛。

## 4. E2：算法对照

固定 Random 对手、基础 Seed42、20局，分别测试 Greedy 和 Minimax。Adaptive 复用 E1 的 `E1_seed42.json`，无需重复相同配置：

```powershell
python scripts/benchmark.py --strategy greedy --opponent random --games 20 --seed 42 --output reports/experiments/E2_greedy.json
python scripts/benchmark.py --strategy minimax --opponent random --games 20 --seed 42 --output reports/experiments/E2_minimax.json
```

再生成直接算法对战的两局棋谱：

```powershell
python scripts/replay_demo.py --strategy adaptive --opponent greedy --games 2 --output-dir reports/replays/E2_vs_greedy
python scripts/replay_demo.py --strategy adaptive --opponent minimax --games 2 --output-dir reports/replays/E2_vs_minimax
Start-Process 'reports/replays/E2_vs_greedy/replay.html'
Start-Process 'reports/replays/E2_vs_minimax/replay.html'
```

历史[对 Greedy 回放](../reports/replays/depth_greedy/replay.html)为我方攻43步胜、我方守24步重复平局；历史[对 Minimax 回放](../reports/replays/depth_minimax/replay.html)为两局各27步重复平局。这些是参考成绩，不是新实验必然结果。

**24步停止也可能是完整终局。** Greedy攻、Adaptive守的历史第二局，第24步后的棋盘与第20步后相同，且都轮到A；裁判因此判重复平局，国王不必已逃脱或被捕。可在[完整棋谱](../reports/replays/depth_greedy/games.json)核对，回放24/24就是最后一步。

确定性算法从固定开局反复比赛可能产生相同棋谱，增加局数不等于增加独立样本。相同 Random 种子也不保证不同算法遇到完全相同的动作，因为它们产生的合法动作集合可能不同。比较时同时报告对手、种子、角色和预算，结合典型棋局解释平局或失误。

## 5. E3：实际搜索深度

```powershell
python scripts/replay_demo.py --strategy adaptive --opponent random --games 2 --seed 42 --output-dir reports/replays/E3_depth
Start-Process 'reports/replays/E3_depth/replay.html'
```

点击各步，核对策略、目标/完成深度、Alpha-Beta节点、根走法数、决策耗时、深度选择/停止原因及截止回退；展开按行动方统计查看全局分布。

| 情况 | 目标深度 | 完成深度 | 判断要点 |
| --- | --- | --- | --- |
| 普通双层搜索完成 | 2 | 2 | `depth_completed` |
| 紧急局面满足深搜条件 | 3 | 最多3 | `urgent_deepening` 表示尝试，不代表完成 |
| 深搜到截止 | 3 | 2或更浅 | `search_deadline`，使用已完成结果 |
| 直接找到一步获胜 | 1 | 0 | `immediate_win`，未扫描完整首层，不是超时 |
| First / Random | 0 | 0 | 基线，不等于缺失统计 |

`nodes` 仅统计 Alpha-Beta递归，不含 Greedy首层扫描。未提供监控的数据必须显示“未记录”。字段完整定义见[技术参考](TECHNICAL_REFERENCE.md)。

2026-11-18的历史6局监控样本没有触发目标3，也没有截止回退；11步紧急局面因根分支超过40保持深度2，详见[历史汇总](../reports/replays/depth_demo/monitoring_summary.json)。不得为了展示效果编造深度3。触发与回退的控制逻辑可先通过可控单元测试验证，另行构造的战术局面需明确标注，不能冒充正式完整比赛。

## 6. E4：真实外部 Bot

取得可信的其他小组 `Player` 文件及依赖后，把示例路径换成实际入口：

```powershell
python scripts/benchmark.py --strategy adaptive --opponent-file opponents/Team02.py --games 10 --output reports/experiments/E4_vs_team02.json
```

对手需实现无参 `Player()` 和正式攻守方法。工具独立进程加载、每局换边，记录成绩、双方累计时间和责任方错误；独立进程不是安全沙箱。`--opponent-file` 与 `--opponent` 互斥，外部随机数由对手管理。

当前 replay 只支持内置策略，外部比赛没有完整HTML棋谱，以 benchmark JSON 验收。外部异常导致的判负应单独说明，不能自动解释为我方算法更强；本地成绩不等于老师联赛成绩。

## 7. 阅读、保存与复现

- 胜平负、2/1/0积分从 `standings.overall` 读取；攻守成绩分别见 `standings.attacker/defender`。`results` 保存逐局时间、错误和日志。
- 回放的 `games.json` 保存完整状态及 `moves[].search`，不是 benchmark 格式。新棋谱schema为1.1；旧数据没有搜索字段时，新模板显示“未记录”。
- HTML内嵌生成当时的数据与页面代码，可直接离线打开，无需服务器。翻步、自动播放、前后棋盘、动作跳转和整局图解用于核查实际行动，不包含搜索树或启发式评分。
- 旧HTML不会随模板或其他JSON自动刷新。已有完整棋谱可用 `write_replay(data, output)` 配合新模板重新导出；仅有benchmark汇总则无法恢复未记录的动作。
- 当前搜索使用实际时钟截止，机器负载可能改变完成深度与走法。相同版本、种子、充足预算通常更易复现，但逐步等同历史不是所有环境的强制条件。
- 规则合法、棋盘连续、吃子/终局与老师裁判一致是强制要求；与历史棋谱的差异需要另行分析。Demo观察开销不能直接作为正式Performance证据。

## 8. 结果模板与完成标准

| 实验 | 我方 / 对手 | 局数 | 胜 / 平 / 负 | 积分率 | 执攻 / 执守胜率 |
| --- | --- | --- | --- | --- | --- |
| E1-A/B/C | Adaptive / Random Seed42、100、2026，分别填表 | 各20 | 待测 | 待测 | 待测 |
| E2-A | Greedy / Random Seed42 | 20 | 待测 | 待测 | 待测 |
| E2-B | Minimax / Random Seed42 | 20 | 待测 | 待测 | 待测 |
| E2-C/D | Adaptive / Greedy、Minimax，分别填表 | 各2 | 待测 | 待测 | 待测 |
| E4 | Adaptive / 真实外部Bot | 10 | 待测 | 待测 | 待测 |

胜率=`胜/总局数`；积分率=`(2×胜+平)/(2×总局数)`；攻守胜率分别使用对应身份局数作分母。另记录双方累计/单步耗时、非法动作/超时/异常、目标与完成深度分布、节点数和回退，附典型胜负棋谱。

第一轮完成标准：E0规则核验通过，E1三组种子、E2同条件算法对照、E3真实监控数据齐全；所有结论可追溯至版本、参数和原始结果，并解释重复平局或异常。E4按实际对手可获得情况安排。结果不同不必然失败，先核对规则，再分析随机行动、计时和环境。

## 9. 增强搜索与训练模型对照

在 Tablut-AI 目录运行，并为每次实验使用新的输出路径。

```powershell
python -m unittest discover -s tests -v
python scripts/evaluate_positions.py --positions 100 --depth 2 --seed 42 --output reports/experiments/aths/depth2_run2.json
python scripts/generate_openings.py --pairs 10 --seed 42 --output reports/experiments/aths/openings_run2.json
python scripts/run_experiments.py --strategy enhanced --opponent adaptive --openings reports/experiments/aths/openings_run2.json --output reports/experiments/aths/enhanced_run2.json
python scripts/run_experiments.py --strategy enhanced_dynamic --opponent enhanced --openings reports/experiments/aths/openings_run2.json --output reports/experiments/aths/dynamic_run2.json
```

每个开局双方交换角色，使用相同配对种子，重复历史从该开局重新开始。结果包含代码版本、开局 SHA256、环境、配置、逐局耗时与裁判日志。配对汇总按开局而非单局重采样，输出积分率及95%区间。使用 `--record-search` 另行检查实际完成深度、PV、走法提示和回退。要比较排序贡献，可用 `--tt-capacity 0` 关闭置换提示，或 `--no-ordering` 关闭实验排序。测时与监控结果应注明设置。

第一轮验证按固定深度正确性、合法对战及等时棋力依次进行。即使节点减少，排序成本也可能让单个局面变慢。默认 Bot 晋级还需要独立开局集的实测结果和团队审核。UCT、Minimax 引导的 MCTS、ATHS 路由和统计评估留作后续阶段。


线性模型、神经网络加载与评测命令见[训练指南](TRAINING_GUIDE.md)。增强搜索模型组合必须遵守[技术参考](TECHNICAL_REFERENCE.md)中的接口限制。首轮筛选数据和统一合并验收见[结果索引](../reports/README.md)。
