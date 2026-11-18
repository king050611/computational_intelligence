# JC4004 Tablut AI v2.1

保持轻量结构：统一配置 `config/settings.py`，三个核心模块 `src/game.py`、`src/evaluation.py`、`src/search.py`，正式入口 `TeamXX.py`。只使用 Python 标准库，Python 3.9+。

正式 Bot 使用 **Adaptive Minimax + Alpha-Beta + Greedy 回退**。由老师原版 `reference/Tablut.py` 负责实际比赛。

## 测试与对战

在本目录执行：

```powershell
python -m unittest discover -s tests -v
python scripts/benchmark.py --games 10
```

算法对照与外部小组对战：

```powershell
python scripts/benchmark.py --strategy minimax --opponent greedy --games 10 --output reports/experiments/minimax_vs_greedy.json
python scripts/benchmark.py --strategy adaptive --opponent minimax --games 10 --output reports/experiments/adaptive_vs_minimax.json
python scripts/benchmark.py --opponent-file opponents/Team02.py --games 10 --output reports/experiments/vs_team02.json
```

最后一条需先放入真实对手文件及其依赖。可选策略：first、random、greedy、minimax、adaptive。默认我方 adaptive，对手 random；`--opponent` 与 `--opponent-file` 互斥。`--seed` 控制内置随机基线。每局创建新实例，首局我方攻、次局我方守，依次交替；需要角色均衡时用偶数局。

终端显示整体、执攻、执守的胜平负与积分（胜2、平1、负0）。JSON 保存逐局结果、双方累计耗时、我方每步平均/最大耗时、按责任方分类的非法动作/超时/异常及日志。未指定 `--output` 时写入 `reports/experiments/latest_v2.json`；出现违规时仍保存记录，并以非零退出码结束。

## 方案A：多场景 AI 对战与实验验证

通过**更换随机种子和对手策略**，观察 Adaptive 面对不同棋局时的表现。沿用正式规则、固定初始棋盘和现有 AI 算法，无需增加 Python 代码。

以下命令均在 `Tablut-AI/` 目录运行。环境要求为 Python 3.9+ 和标准库；首次运行先执行 `python --version`，并通过上面的单元测试。

### 1. 先用不同 Seed 生成棋谱，直观看到不同棋局

分别运行两组比赛，每组两局，自动交换我方攻守身份：

```powershell
python scripts/replay_demo.py --strategy adaptive --opponent random --games 2 --seed 42 --output-dir reports/replays/seed42
python scripts/replay_demo.py --strategy adaptive --opponent random --games 2 --seed 100 --output-dir reports/replays/seed100
```

生成后，双击对应目录中的 `replay.html`，或在 PowerShell 中打开：

```powershell
Start-Process 'reports/replays/seed42/replay.html'
Start-Process 'reports/replays/seed100/replay.html'
```

页面支持上一手/下一手、自动播放、跳转指定步数，以及展开整局逐步棋盘图解。每组目录还包含 `games.json`，记录双方移动、吃子、移动前后棋盘和最终结果。建议对比两个页面的**同一局号**，确保我方身份一致，再观察随机对手从哪一步开始走出不同路线。

要查看第三组棋局，可改用 `--seed 2026 --output-dir reports/replays/seed2026`。每个 Seed 使用独立输出目录，便于并排比较；重复使用同一目录会覆盖其中的 JSON 和 HTML。

**Seed 如何起作用：**它控制 Random 对手的随机选择；每局实际使用 `seed + 局号索引`，索引从0开始。例如 `--seed 42 --games 2` 使用42和43，`--seed 100 --games 2` 使用100和101。不同种子通常产生不同走法，但不保证胜负不同，也不保证每一步都不同。

回放会重新运行比赛，并非读取此前 benchmark 的汇总结果。相同种子固定的是随机序列；机器负载和搜索截止回退仍可能影响我方动作，因此不承诺跨运行棋谱完全一致。v2.1 新生成的回放同时展示目标/完成深度、递归节点、截止回退及程序实际触发的原因；旧棋谱未提供的统计显示“未记录”。内部启发式评分尚未记录。更多字段说明见[棋谱 Demo 文档](docs/REPLAY_DEMO.md)。

### 2. 用三组种子统计比赛表现

固定我方 Adaptive、对手 Random，每组10局，分别保存结果：

```powershell
python scripts/benchmark.py --strategy adaptive --opponent random --games 10 --seed 42 --output reports/experiments/seed42.json
python scripts/benchmark.py --strategy adaptive --opponent random --games 10 --seed 100 --output reports/experiments/seed100.json
python scripts/benchmark.py --strategy adaptive --opponent random --games 10 --seed 2026 --output reports/experiments/seed2026.json
```

三组实际种子范围分别为42–51、100–109和2026–2035，每组我方执攻5局、执守5局。在 VS Code 中打开三个 JSON，比对 `standings.overall`、`standings.attacker`、`standings.defender` 和 `results` 中的逐局耗时及错误记录。

即使三组全部获胜，也可能对应不同的行动轨迹；本实验检验的是面对不同对手走法时的表现，不要求刻意产生不同胜负。

### 3. 更换对手算法

```powershell
python scripts/benchmark.py --strategy adaptive --opponent greedy --games 10 --output reports/experiments/adaptive_vs_greedy.json
python scripts/benchmark.py --strategy adaptive --opponent minimax --games 10 --output reports/experiments/adaptive_vs_minimax.json
python scripts/benchmark.py --strategy minimax --opponent greedy --games 10 --output reports/experiments/minimax_vs_greedy.json
```

Greedy、Minimax 和 Adaptive 主要采用确定性决策。双方都使用这些算法时，更换 Seed 通常不会改变走法；重复同一初始局面的比赛也不等于增加了独立样本。应结合不同对手及典型棋局分析表现，搜索计时引起的变化也需区别看待。

取得其他小组的入口文件和依赖后，可使用外部对战命令：

```powershell
python scripts/benchmark.py --strategy adaptive --opponent-file opponents/Team02.py --games 10 --output reports/experiments/vs_team02.json
```

该路径仅为示例，需换成实际文件。对手须实现正式 `Player` 接口；具体加载约定见下方“外部 Bot”。外部 Bot 自行管理随机数，不能假定本工具的 `--seed` 会控制它。本地成绩也不等于课程正式联赛成绩。

### 4. 记录结果与判断结论

下表是填写模板，所有数字须来自实际运行的 JSON；“待测”不表示已有实验成绩。

| 实验 | 我方 | 对手 | 基础 Seed | 胜 | 平 | 负 | 积分 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | Adaptive | Random | 42 | 待测 | 待测 | 待测 | 待测 |
| B | Adaptive | Random | 100 | 待测 | 待测 | 待测 | 待测 |
| C | Adaptive | Random | 2026 | 待测 | 待测 | 待测 | 待测 |
| D | Adaptive | Greedy | 不影响确定性策略 | 待测 | 待测 | 待测 | 待测 |
| E | Adaptive | Minimax | 不影响确定性策略 | 待测 | 待测 | 待测 | 待测 |
| F | Minimax | Greedy | 不影响确定性策略 | 待测 | 待测 | 待测 | 待测 |
| G | Adaptive | 外部 Bot | 视对手而定 | 待测 | 待测 | 待测 | 待测 |

除总胜平负和2/1/0积分外，还应记录攻守分别的成绩、双方累计计算时间、非法移动、超时和异常次数，并保存典型胜负棋谱。`reports/experiments/*.json` 按当前 Git 忽略规则默认只保存在本地，分享实验时需一并提供结果文件。

建议先观察两组回放，再跑三组随机对手实验，最后进行算法对照。由此得到不同棋局的棋谱、比赛统计和课程报告可引用的真实数据。v2.1 已记录 `target_depth`、`completed_depth`、递归节点及超时回退，可在新生成的回放中核对是否实际触发深度3；不能由策略名称推断每步深度。

## 搜索行为

1. 先进行一层 Greedy，优先直接获胜，同时保留合法回退。
2. minimax 目标固定为深度2，使用 Alpha-Beta；截止前未完成则回退。
3. adaptive 在正常局面同样尝试深度2；国王存在直达边缘通道或相邻攻击者至少2枚，且根分支不超过40、剩余本步预算至少0.4秒时，最多尝试深度3。
4. 迭代加深只提交完整层结果，递归中检查截止时间。若一层也未完成，返回已评分候选中最佳走法，或初始合法走法。
5. 分数始终从根方视角计算；路径中相同棋盘和行动方再次出现记平局。老师仅传棋盘，真实跨回合重复仍由裁判最终判定。

每局每方累计60秒，预留5秒；按预计剩余30次决策分配当前可用预算。每局重新创建 Player。截止检测是协作式的，单次移动模拟/评估不可中途打断；有安全余量并进行实战耗时验证。

## 外部 Bot

对手须有无参 `Player()`、`play_attacker(board)`、`play_defender(board)`，返回 `[[行,列],[行,列]]`。外部 Bot 在独立进程加载，工作目录为其文件所在目录，可加载随附依赖，并隔离同名 src/config 模块缓存；首次加载限10秒。每步通过进程通信，裁判累计时间包含通信开销，外部进程失去响应会终止并记录错误。

仅加载可信代码。独立进程用于避免导入冲突和停止挂起程序，**不构成安全沙箱**。外部构造/导入错误会在开赛前报错；对局中的异常和错误返回会计入记录。格式错误会转为可被原裁判安全拒绝的非法动作，并保留原返回值。

## 验证与局限

21项规则回归及 v2 搜索/外部加载测试全部通过，参见 tests/test_bot.py。实际冒烟记录：外部随机测试 Bot 10局，10胜；Minimax 对 Greedy 2局，1胜1平；Adaptive 对 Minimax 2局，2平。均无非法动作、超时、异常。外部测试 Bot 是接口验收样例，不代表其他小组实力；小规模、固定种子结果不足以证明新版本更强。

正式组号尚需替换 TeamXX，并同步测试/脚本导入。提交包含 config、src。原老师文件位于 reference，原始环境快照为 UTF-16；当前项目无需第三方依赖，未修改老师原件。

[详细迭代清单](docs/SETUP_LIST.md) · [接口约定](docs/INTERFACES.md) · [分工与后续计划](docs/DEVELOPMENT_PLAN.md)


逐步棋谱与离线棋盘回放（独立 Demo）：[使用说明](docs/REPLAY_DEMO.md)。运行 python scripts/replay_demo.py --games 2，即可导出每步 JSON 与可翻步的离线页面。

## v2.1：逐步搜索监控

正式 `Player()` 与普通 benchmark 默认关闭监控；`Player(record_search=True)` 和 `StrategyBot(..., record_search=True)` 可打开。Replay 自动开启并保存每步独立统计，JSON schema_version 为1.1。

```powershell
python scripts/replay_demo.py --strategy adaptive --opponent random --games 2 --seed 42 --output-dir reports/replays/depth_demo
Start-Process 'reports/replays/depth_demo/replay.html'
```

右侧 AI Search Analysis 随选中步切换，显示目标/完整完成深度、Alpha-Beta递归节点、根走法数量、决策时间、深度选择/停止原因、是否截止回退；可展开按行动方统计。节点不含Greedy扫描。First/Random深度为0；缺失统计为null。“直接获胜”未扫描完整一层时completed_depth为0、target_depth为1、finish_reason为immediate_win，不表示未评估动作或超时。

本轮26项测试通过，6局带监控比赛无非法动作、异常或累计超时。真实样本没有触发深度3：普通局面或紧急局面分支过多均保持深度2，未修改参数来制造深搜。详见[监控口径和实验数据](docs/REPLAY_DEMO.md#v21-逐步搜索监控)。
