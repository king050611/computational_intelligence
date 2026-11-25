# 实验结果与棋谱索引

这里保存实际运行产物；如何运行实验见[实验指南](../docs/EXPERIMENT_GUIDE.md)，字段定义见[技术参考](../docs/TECHNICAL_REFERENCE.md)。原有JSON、HTML、截图及样例代码继续保留；可选训练集成的新验收记录见下方。

## 文件在哪里

| 位置 | 内容与注意事项 |
| --- | --- |
| `experiments/*.json` | benchmark胜平负、积分、逐局时间与错误日志；多数默认不受Git跟踪，仅本地存在 |
| `replays/<实验名>/games.json` | 初始棋盘、每步动作/捕获/前后棋盘、终局，以及新格式的search统计 |
| `replays/<实验名>/replay.html` | 内嵌该次数据和页面代码的离线回放，不会随新比赛或新模板自动更新 |
| `replays/*/*.png` | 历史截图；静态图片不替代完整棋谱 |
| `experiments/tmp_opponent/TeamYY.py` | 外部加载验收使用的随机样例，不是其他小组的真实参赛Bot |

`latest`只是默认输出名，不保证它比所有独立实验目录都新。相同输出路径会被后一次运行覆盖。当前人机CLI没有棋谱导出；`human_games/`仅是后续建议目录。

## 已保存回放

下列链接指向现有文件。历史结果用于核对，不表示相同参数在所有机器上必然逐步复现，也不代表重新测量的成绩。

| 实验目录 | 棋谱 / 回放 | 历史结果（我方Adaptive，先攻后守） |
| --- | --- | --- |
| demo_2026-11-17 | [JSON](replays/demo_2026-11-17/games.json) · [HTML](replays/demo_2026-11-17/replay.html) · [截图](replays/demo_2026-11-17/preview.png) | 41步攻胜、38步守胜；早期格式不含逐步搜索监控 |
| depth_demo | [JSON](replays/depth_demo/games.json) · [HTML](replays/depth_demo/replay.html) · [监控汇总](replays/depth_demo/monitoring_summary.json) | 对Random：2胜；国王被捕/国王逃生 |
| depth_greedy | [JSON](replays/depth_greedy/games.json) · [HTML](replays/depth_greedy/replay.html) | 对Greedy：43步攻胜、24步重复平局 |
| depth_minimax | [JSON](replays/depth_minimax/games.json) · [HTML](replays/depth_minimax/replay.html) | 对Minimax：27步平、27步平 |
| E0_baseline | [JSON](replays/E0_baseline/games.json) · [HTML](replays/E0_baseline/replay.html) | 后续基准复现材料 |
| E1_seed42 / E1_seed100 | [Seed42](replays/E1_seed42/replay.html) · [Seed100](replays/E1_seed100/replay.html) | 比较同一局号的随机对手轨迹 |
| E2_vs_greedy / E2_vs_minimax | [对Greedy](replays/E2_vs_greedy/replay.html) · [对Minimax](replays/E2_vs_minimax/replay.html) | 后续算法对照材料 |

`depth_demo`、`depth_greedy`、`depth_minimax`这6局历史监控中，我方98步完整完成深度2，3步直接获胜提前返回；没有目标深度3或截止回退。11步紧急局面因根分支超过阈值而保持深度2。具体分局节点、原因和耗时以监控汇总为准，小样本不能证明Adaptive比其他策略更强。

本地另有 `experiments/demo_2026-11-17_two_games.json`、`v2_*.json`、`E0_benchmark.json`、`E1_seed*.json` 等文件，按实际存在情况查看；不要把历史schema标签当作代码提交版本。

## 保存与分享

记录实际Git SHA、工作区状态、Python版本、命令、Seed、攻守和输出路径。`experiments/*.json`被现有忽略规则排除，分享时单独打包或有选择地加入版本管理；不能因网页链接存在就假定本地未跟踪数据已上传。HTML应下载后用浏览器离线打开，在GitHub上查看源码不等同于播放。

benchmark汇总没有完整走法，不能还原成棋谱；replay_demo会重新比赛。保留的games.json可用现有write_replay函数重新导出新模板，不需要改变历史动作。操作方法见实验指南。

## 文档迁移记录

| 已合并的旧说明 | 现在的位置 |
| --- | --- |
| `docs/EXPERIMENT_MANUAL_V2_1.md`、`docs/REPLAY_DEMO.md` | [实验指南](../docs/EXPERIMENT_GUIDE.md)的操作与验证，[技术参考](../docs/TECHNICAL_REFERENCE.md)的数据口径 |
| `docs/INTERFACES.md`、`docs/SETUP_LIST.md` | [技术参考](../docs/TECHNICAL_REFERENCE.md)的架构、接口和边界，[开发计划](../docs/DEVELOPMENT_PLAN.md)的进度 |
| `reports/demo_2026-11-17_two_games.md` | 本页历史结果索引；完整结果与棋谱文件继续保留 |

旧版说明仍可通过Git历史查阅；不再保留第二套重复说明入口。

## 2026-11-25：可选训练集成验收

稳定基准为 `b51abfd`，已保存在远端 `backup/main-before-neural` 与 `v2.2-stable` 标签。正式TeamXX、游戏规则、手写评估、配置、裁判、CLI和Replay均与基准一致。NumPy仅用于明确启用的神经模块；原命令无需模型。

- Python 3.13.7、NumPy 2.3.5：66项测试全部通过；独立无NumPy环境：59项通过、7项神经测试明确跳过。
- 新增稳定搜索基准包含28组走法/完整统计、8组Alpha-Beta评分/节点/判重，以及超时回退和模型损坏检查。
- 合并前后各10局Adaptive对Random，均10胜，逐局胜方与行动次数一致；后10局无非法动作、超时、异常，单方累计耗时最大约1.231秒。
- 无NumPy环境实跑双边CLI及79步Replay通过。线性训练8局有7局完成、1局截断；续训8局全部完成，候选未超过上一轮时保留历史最佳。
- 神经训练完成value及policy阶段，分别产生295和267个样本，各1局截断；STOP后恢复并再保存policy检查点成功。Windows本机硬链接检查点保存可用。

| 加载对照（每组2局，对手Minimax） | 我方胜 / 平 / 负 | 错误、超时、非法动作 |
| --- | --- | --- |
| 线性best + Adaptive | 0 / 2 / 0 | 0 |
| 线性candidate + Minimax | 0 / 2 / 0 | 0 |
| 价值网络 + Alpha-Beta | 0 / 1 / 1 | 0 |
| 策略价值网络 + MCTS | 0 / 0 / 2 | 0 |

这是流程与兼容性验收，不证明模型更强；当前短训练的神经模型没有优势，默认机器人不切换模型。原始JSON在本地 `experiments/pre_merge.json`、`post_merge.json`、`linear_*_smoke.json`、`neural_*_smoke_test.json`；检查点在被忽略的 `training/merge_linear/` 和 `training/merge_neural/`，不进入源码提交。重跑步骤见[训练指南](../docs/TRAINING_GUIDE.md)。
