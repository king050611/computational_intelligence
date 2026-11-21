# JC4004 Tablut AI v2.2

Tablut AI 使用 Adaptive Minimax + Alpha-Beta + Greedy 回退。三个核心模块位于 `src/`，参数统一放在 `config/settings.py`，正式评测入口为 `TeamXX.py`。

v2.2 第一阶段新增独立的终端人机对战入口，复用现有 AI 和老师裁判。v2.1 的搜索监控、自动实验和棋谱回放继续保留。

## 环境与验证

需要 Python 3.9+，当前运行代码只使用标准库。在 `Tablut-AI/` 目录执行：

```powershell
python --version
python -m unittest discover -s tests -v
```

老师提供的环境快照保存在 `reference/requirements.txt`，编码为 UTF-16；不需要为当前程序额外安装大型机器学习库。

## 三个运行入口

### 1. 人机对战

```powershell
python scripts/play_cli.py --side A --strategy adaptive
```

输入 `D1 C1`，表示将第1行D列的攻击棋子移到第1行C列。支持 `help`、`moves`、`board`、`quit`，大小写不敏感。若选择 `--side D`，AI 会先走；省略 `--side` 会询问你的身份。

```powershell
python scripts/play_cli.py --side D --strategy minimax --show-search
```

人类思考不计时，AI 使用原有累计时间管理；`--show-search` 显示实际目标/完成深度、节点、耗时和回退信息。人机模式当前不保存棋谱或生成 HTML。完整玩法见[人机对战指南](docs/CLI_GUIDE.md)。

### 2. 自动 AI 对战实验

```powershell
python scripts/benchmark.py --games 10
```

默认我方 Adaptive、对手 Random，每局交换攻守并创建新实例。终端显示胜平负和2/1/0积分；JSON 保存双方耗时、责任方错误和逐局日志，默认输出为 `reports/experiments/latest_v2.json`。

```powershell
python scripts/benchmark.py --strategy minimax --opponent greedy --games 10 --output reports/experiments/minimax_vs_greedy.json
python scripts/benchmark.py --strategy adaptive --opponent-file opponents/Team02.py --games 10 --output reports/experiments/vs_team02.json
```

外部对手路径是示例，需要提供真实的入口及依赖。对手须有无参 `Player()`、`play_attacker(board)`、`play_defender(board)`，返回 `[[行,列],[行,列]]`；其代码在独立进程加载以隔离同名模块，这不是安全沙箱。`--opponent` 和 `--opponent-file` 互斥，外部代码自行管理随机种子。完整步骤和结果表见[实验操作与结果验证手册](docs/EXPERIMENT_MANUAL_V2_1.md)。

### 3. 生成逐步棋谱和 HTML 回放

```powershell
python scripts/replay_demo.py --games 2
Start-Process 'reports/replays/latest/replay.html'
```

回放目录包含 `games.json` 和可离线打开的 `replay.html`，支持逐步棋盘、吃子标记、自动播放和每步搜索监控。Replay 会重新比赛，不会读取此前 benchmark 汇总结果来还原棋局，也不包含人机对战记录。

## 用不同 Seed 观察不同棋局

固定对手为 Random，分别生成两组回放：

```powershell
python scripts/replay_demo.py --games 2 --opponent random --seed 42 --output-dir reports/replays/seed42
python scripts/replay_demo.py --games 2 --opponent random --seed 100 --output-dir reports/replays/seed100
Start-Process 'reports/replays/seed42/replay.html'
Start-Process 'reports/replays/seed100/replay.html'
```

比较两个页面的同一局号，观察随机对手从哪一步选择了不同路线。每局使用基础 `seed + 局号索引`，索引从0开始；不同 Seed 通常产生不同走法，不保证胜负不同。确定性算法之间更换 Seed 通常不会改变动作；机器负载和搜索截止也可能影响复现。

独立目录方便比较，重复使用相同输出路径会覆盖原结果。`reports/experiments/*.json` 默认被 Git 忽略，分享实验时需检查结果文件是否一并提供。更多监控口径、旧棋谱兼容性和输出说明见[回放指南](docs/REPLAY_DEMO.md)。

## 算法与结果边界

普通局面目标深度2；Adaptive 在紧急局面、根分支数不超过40且本步预算充足时，最多尝试深度3。迭代加深只提交完整层结果，截止后使用已完成层或合法回退。每方正式对局累计预算60秒，预留5秒；正式 `Player()` 默认关闭搜索监控，Replay 按需打开。

`completed_depth` 只计完整扫描结束的层。一步获胜提前返回时，`target_depth=1`、`completed_depth=0`、`finish_reason=immediate_win`；这不是超时。节点数只统计 Alpha-Beta 递归，不能当成所有 Greedy 候选的总数。缺少监控的旧棋谱显示“未记录”。

历史 v2.0 验收有21项测试，v2.1 监控验收为26项，随后低风险整理增至28项；当前版本以实际运行测试命令的结果为准。历史小样本中 Adaptive 对 Random 两局全胜，对 Minimax 两局平局；这些记录不证明 Adaptive 总是更强。旧开发记录保留历史语境，不应当作当前功能清单或当前 Performance 成绩。

正式提交前需要替换 TeamXX 为课程组号，并同步脚本和测试导入，打包 `config/`、`src/` 等必要模块。算法实现和实验应能由团队解释，按课程要求记录外部代码和 AI 辅助使用情况。

## 文档导航

| 文档 | 用途 |
| --- | --- |
| [CLI_GUIDE.md](docs/CLI_GUIDE.md) | 人机模式、棋盘坐标、输入命令和错误处理 |
| [INTERFACES.md](docs/INTERFACES.md) | 状态、动作、Player、监控和 CLI 接口 |
| [REPLAY_DEMO.md](docs/REPLAY_DEMO.md) | JSON 棋谱、HTML 回放、搜索统计和历史验证 |
| [EXPERIMENT_MANUAL_V2_1.md](docs/EXPERIMENT_MANUAL_V2_1.md) | E0–E4 实验操作、变量控制、结果验证 |
| [DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) | 当前阶段、团队分工与后续任务 |
| [SETUP_LIST.md](docs/SETUP_LIST.md) | v2.0 迭代历史记录 |
