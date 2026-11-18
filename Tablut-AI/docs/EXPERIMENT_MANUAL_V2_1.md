# JC4004 Tablut AI v2.1 — 实验操作与结果验证手册

**项目：** Computational Intelligence — Tablut AI  
**实验版本：** v2.1  
**基准 Git Commit：** `ee2743a603d59851b36d9fb949abb3b4fe73769b`  
**实验环境：** Windows / PowerShell / Python 3.9+  
**实验目标：** 验证 AI 的合法性、稳定性、算法性能、动态搜索行为及对战能力。


> 使用说明：本文是实验操作手册，记录的历史成绩与“待测”实验分别标明。新增本文不代表已执行其中所有实验。所有命令从 `Tablut-AI/` 目录运行。
>
> 版本核对：编写本文时，本地 HEAD 与上述基准提交一致。普通 benchmark 的 JSON 顶层 `version` 目前仍为 `2.0`，这是脚本保留的输出标签；v2.1 回放的 `schema_version` 为 `1.1`。应以实际 Git SHA、工作区状态和运行参数标识实验代码，不能只凭 JSON 的版本标签判断。
>
> 数据保存：同一路径再次运行会覆盖原输出，重复实验请使用不同文件名或目录。`reports/experiments/*.json` 被现有 `.gitignore` 忽略，保存、分享或提交实验材料时需要单独检查这些结果是否包含在内。
>
> 工具边界：benchmark 保存成绩汇总，默认关闭搜索监控；replay_demo 会重新进行比赛并开启监控，生成新的逐步棋谱，不会把此前 benchmark 结果转换成回放。下面的逐步核对要求是验收清单，当前命令没有额外的“自动验证全部棋谱”开关。

## 1. 实验目标与内容

本项目使用 Adaptive Minimax + Alpha-Beta + Greedy Fallback 作为主要决策算法。

实验阶段不再以实现功能为主，而是使用实际比赛数据回答以下问题：

1. 程序能否稳定完成比赛？
2. 对不同随机种子和对手，AI 是否能正确行动？
3. Minimax 是否比 Greedy 更有竞争力？
4. Adaptive 是否比固定深度 Minimax 更有效？
5. Adaptive 在哪些局面调整搜索深度？
6. 每一步的棋谱、吃子、胜负判定是否与老师的 `Tablut.py` 一致？

实验分为：

| 编号 | 实验名称 | 主要产物 |
|---|---|---|
| E0 | 环境、规则与基准棋谱复现 | 测试结果、两局棋谱 |
| E1 | 多随机种子稳定性实验 | 胜率、积分、耗时 JSON |
| E2 | 不同算法的对照实验 | Greedy / Minimax / Adaptive 比较 |
| E3 | 逐步搜索深度验证 | 每步搜索统计、HTML 回放 |
| E4 | 外部 Bot 对战 | 实际对手成绩（条件允许时） |

---

## 2. 环境准备

### Step 1 — 进入项目目录

打开 VS Code 的 PowerShell 终端：

```powershell
cd 'D:\workstudy\大四\大四上\computational_intelligence\Tablut-AI'
```

检查 Python：

```powershell
python --version
```

此前记录使用 Python 3.13.7。新实验需要记录实际运行的 Python 版本。

### Step 2 — 记录代码版本

```powershell
git rev-parse HEAD
git status --short
```

推荐使用 v2.1 基准提交进行第一轮实验。如果已经有新提交，记录其 SHA；不要把不同算法版本的结果混在一起。

### Step 3 — 运行自动化测试

```powershell
python -m unittest discover -s tests -v
```

**预期：**

```text
Ran 26 tests in ...
OK
```

如果失败，先检查具体测试，不要直接进入后续性能比较。

---

# 实验 E0：基准比赛与完整棋谱验证

## 3. 实验目的

使用已有的随机对手基准，确认：

- 进攻、防守两种身份能够正常比赛。
- 官方裁判正确执行所有行动。
- 回放系统记录了每一步。
- 每一步搜索数据与行动对应。
- 能复现或对照仓库中的历史棋谱。

## 4. 实验步骤

### Step 1 — 运行两局比赛

```powershell
python scripts/benchmark.py --strategy adaptive --opponent random --games 2 --seed 42 --output reports/experiments/E0_benchmark.json
```

### Step 2 — 生成逐步棋谱

```powershell
python scripts/replay_demo.py --strategy adaptive --opponent random --games 2 --seed 42 --output-dir reports/replays/E0_baseline
```

### Step 3 — 打开 HTML 回放

```powershell
Start-Process 'reports/replays/E0_baseline/replay.html'
```

应该看到：

- 9×9棋盘。
- 两局比赛选择框。
- 上一步、下一步和自动播放。
- 双方逐步行动列表。
- AI Search Analysis 搜索统计面板。

### Step 4 — 检查输出文件

```text
reports/
├── experiments/
│   └── E0_benchmark.json
└── replays/
    └── E0_baseline/
        ├── games.json
        └── replay.html
```

## 5. E0 历史基准结果

根据本地仓库已核对的历史棋谱 [`reports/replays/depth_demo/games.json`](../reports/replays/depth_demo/games.json)：

| 项目 | 第一局 | 第二局 |
|---|---|---|
| 我方身份 | Attacker | Defender |
| 对手 | Random | Random |
| Seed | 42 | 43 |
| 行动总数 | 41 | 38 |
| 获胜方 | A | D |
| 我方结果 | 胜 | 胜 |
| 结束原因 | king_captured | king_escaped |
| 完整深度2行动 | 20 | 18 |
| 一步获胜提前返回 | 1 | 1 |
| 完整深度3行动 | 0 | 0 |
| 截止回退 | 0 | 0 |

两局合计为 **2胜0平0负，4/4分**。

这些是已经记录的历史结果。新的运行如果发生走法差异，需要进一步核对时间截止、运行环境以及算法版本，不能仅凭结果不同就断定代码错误。

---

## 6. E0 每一步棋谱的预期

棋谱中每个 `move` 都表示：

`[[起点行, 起点列], [终点行, 终点列]]`

坐标从0开始。

### 第一局：Adaptive 攻击 Random

以下是仓库现有棋谱中的前六步：

| 半步 | 行动方 | 起点 → 终点 | 预期 |
|---|---|---|---|
| 1 | A | (0,3) → (0,2) | 正常移动，无吃子 |
| 2 | D | (4,6) → (7,6) | 正常移动，无吃子 |
| 3 | A | (0,2) → (0,1) | 正常移动，无吃子 |
| 4 | D | (2,4) → (2,8) | 正常移动，无吃子 |
| 5 | A | (1,4) → (1,8) | 捕获 D，位置(2,8) |
| 6 | D | (3,4) → (1,4) | 正常移动，无吃子 |

**终局预期：**

第41步，A 从 `(4,8)` 移动到 `(4,5)`，国王在 `(4,4)` 被捕获。

结果：

```text
winner: A
reason: king_captured
accepted_moves: 41
```

### 第二局：Random 攻击 Adaptive

| 半步 | 行动方 | 起点 → 终点 | 预期 |
|---|---|---|---|
| 1 | A | (0,3) → (2,3) | 正常移动，无吃子 |
| 2 | D | (4,2) → (2,2) | 捕获 A，位置(2,3) |
| 3 | A | (4,1) → (7,1) | 正常移动，无吃子 |
| 4 | D | (2,2) → (1,2) | 正常移动，无吃子 |
| 5 | A | (3,0) → (3,1) | 正常移动，无吃子 |
| 6 | D | (1,2) → (0,2) | 正常移动，无吃子 |

**终局预期：**

第38步，国王 K 从 `(4,4)` 移动至 `(0,4)`，到达棋盘边缘。

```text
winner: D
reason: king_escaped
accepted_moves: 38
```

以上只列出便于人工核对的关键行动。**完整79步的历史预期均存放于仓库现有的 [`depth_demo/games.json`](../reports/replays/depth_demo/games.json)，可以逐步对照，不需要人工重新抄写。**

---

## 7. 每一步棋谱必须检查的内容

不论是 E0 还是之后的实验，每个行动都应满足以下标准：

| 检查字段 | 验证规则 |
|---|---|
| `ply` | 从1开始，依次递增 |
| `player` | A、D交替，A先行动 |
| `board_before` | 等于上一步执行后的棋盘 |
| `move` | 起点有己方棋子，终点合法 |
| `accepted` | 正常比赛中为true |
| `board_after` | 与官方裁判执行结果完全相同 |
| `captures` | 与实际被移除棋子一致 |
| `result_after` | 与实际胜负和下一行动方一致 |
| `search` | 与当前行动对应，不串步 |
| `elapsed_seconds` | 非负，记录真实耗时 |

特别注意：

**棋谱中的每一步，是单方行动一次，不是双方各行动一次。**

例如第41步通常表示本局发生了41次单方落子。

### 对棋盘状态的验证

每一步应依次确认：

1. 当前 `board_before` 与前一步 `board_after` 连续。
2. 起点原本存在本方棋子。
3. 终点原本是普通空格。
4. 棋子沿横向或纵向移动，没有跳过棋子。
5. 吃子后，指定棋子从棋盘消失。
6. 如果到达终局，胜负原因和棋盘一致。

自动验证时必须以未修改的老师 `reference/Tablut.py` 为标准，而不是只用自己的 `src/game.py` 检查自己的结果。

---

# 实验 E1：多随机种子稳定性实验

## 8. 实验目的

验证 Adaptive 面对不同 Random 行动序列时的胜率、稳定性和运行时间。

## 9. 实验步骤

选择三个独立基础 Seed，每组20局：

```powershell
python scripts/benchmark.py --strategy adaptive --opponent random --games 20 --seed 42 --output reports/experiments/E1_seed42.json
```

```powershell
python scripts/benchmark.py --strategy adaptive --opponent random --games 20 --seed 100 --output reports/experiments/E1_seed100.json
```

```powershell
python scripts/benchmark.py --strategy adaptive --opponent random --games 20 --seed 2026 --output reports/experiments/E1_seed2026.json
```

每组我方执攻10局、执守10局。

## 10. 预期结果与验收

**固定要求：**

- JSON 中记录20局结果。
- 攻守各10局。
- 每局都有胜方或平局结果。
- 每局都有正确的累计时间。
- 我方没有非法走法、异常或累计超时。
- 每方每局决策时间不超过60秒。

**不固定的结果：**

- 最终胜局数。
- 每局行动次数。
- 每局具体走法。
- 平均决策耗时。
- 总积分。

不同 Seed 通常会产生不同的随机走法，但不保证胜负不同。

### 结果填写表

| Seed | 胜 | 平 | 负 | 积分/40 | 我方执攻胜率 | 我方执守胜率 |
|---|---|---|---|---|---|---|
| 42 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |
| 100 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |
| 2026 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |

### E1 棋谱预期

在 E1 中不应该规定所有比赛必须出现同样的行动序列。

为了验证棋局多样性，可以另外生成两个 Seed 的回放：

```powershell
python scripts/replay_demo.py --games 2 --seed 42 --output-dir reports/replays/E1_seed42
python scripts/replay_demo.py --games 2 --seed 100 --output-dir reports/replays/E1_seed100
```

打开两个回放页面，比较两组**第一局**的逐步棋谱，观察 Random 从哪一步开始选择不同的行动。

不同 Seed 对应的棋谱不同是正常的；但所有实际执行行动仍必须通过官方规则验证。

---

# 实验 E2：算法对照实验

## 11. 实验目的

验证 Greedy、Minimax 和 Adaptive 的竞争表现。

## 12. 实验步骤

先固定 Random 对手、Seed42和20局：

**Greedy：**

```powershell
python scripts/benchmark.py --strategy greedy --opponent random --games 20 --seed 42 --output reports/experiments/E2_greedy.json
```

**Minimax：**

```powershell
python scripts/benchmark.py --strategy minimax --opponent random --games 20 --seed 42 --output reports/experiments/E2_minimax.json
```

**Adaptive：**

可以直接复用实验E1的 `E1_seed42.json`，无需重复运行完全相同的配置。

再进行直接算法对战：

```powershell
python scripts/replay_demo.py --strategy adaptive --opponent greedy --games 2 --output-dir reports/replays/E2_vs_greedy
```

```powershell
python scripts/replay_demo.py --strategy adaptive --opponent minimax --games 2 --output-dir reports/replays/E2_vs_minimax
```

## 13. 已知历史结果参考

本地仓库已保存以下两组回放：[对 Greedy](../reports/replays/depth_greedy/replay.html)、[对 Minimax](../reports/replays/depth_minimax/replay.html)：

| 对手 | 第一局（我方攻） | 第二局（我方守） |
|---|---|---|
| Greedy | 43步，A获胜 | 24步，平局 |
| Minimax | 27步，平局 | 27步，平局 |

对应终局：

- vs Greedy 第1局：`king_captured`
- vs Greedy 第2局：`repetition`
- vs Minimax 两局：`repetition`

这些是历史基准结果，不代表新实验必须产生相同结果。

### 棋谱检查

在 vs Greedy 的回放中，历史记录第1步 A 从 `(0,3)` 到 `(0,2)`，第2步 D 从 `(2,4)` 到 `(2,3)`。

在 vs Minimax 的回放中，历史记录前两步也是：

- A `(0,3)` → `(0,2)`
- D `(2,4)` → `(2,3)`

后续应继续按 `games.json` 验证全部行动，重点观察什么时候出现重复棋局，并确认裁判在正确的时点终止比赛。

**实验结论不能只写“Adaptive 比 Minimax 更好”。** 如果两者平局，应当如实报告，并通过后续战术局面测试分析原因。

---

# 实验 E3：逐步搜索深度验证

## 14. 实验目的

检查 Adaptive 是否根据当前棋局动态调整搜索深度，并计算相关成本。

## 15. 实验步骤

使用已有 v2.1 回放脚本：

```powershell
python scripts/replay_demo.py --strategy adaptive --opponent random --games 2 --seed 42 --output-dir reports/replays/E3_depth
```

打开：

```powershell
Start-Process 'reports/replays/E3_depth/replay.html'
```

在 AI Search Analysis 面板中逐步查看：

- Strategy
- Target Depth
- Completed Depth
- Search Nodes
- Root Moves
- Policy Reason
- Finish Reason
- Timeout / Fallback

## 16. 搜索统计预期

| 情况 | 目标深度 | 完成深度 | 解释 |
|---|---:|---:|---|
| 正常局面，深度2完成 | 2 | 2 | 正常 Minimax |
| 紧急局面满足深搜条件 | 3 | 最多3 | 尝试加深搜索 |
| 深度3中途截止 | 3 | 2或更浅 | 使用已完成结果 |
| 直接发现一步获胜 | 1 | 0 | 提前获胜，没有完整扫描首层 |
| Random | 0 | 0 | 随机基线 |

`nodes` 只包括 Alpha-Beta 递归节点，不包含 Greedy 的首层候选扫描。

### 当前真实基准

仓库此前6局监控记录显示：

- 全部未触发目标深度3。
- 没有搜索截止回退。
- 正常完成的 Adaptive 搜索主要为深度2。
- 已有11步紧急局面因为根节点合法走法超过40而没有加深。

这是允许出现的真实结果，不能为了展示动态效果而修改棋谱。

如果需要验证目标深度3及回退机制，先使用现有单元测试验证控制逻辑，再从有代表性的真实或构造棋局中研究触发条件，并明确标记这些是战术测试而非完整正式比赛。

---

# 实验 E4：真实外部 Bot 对战

## 17. 实验目的

评估 AI 面对其他小组独立实现的策略时的竞争能力。

## 18. 实验步骤

将获得授权共享的对手文件及依赖放入独立文件夹。例如：

```text
Tablut-AI/
└── opponents/
    └── Team02.py
```

执行：

```powershell
python scripts/benchmark.py --strategy adaptive --opponent-file opponents/Team02.py --games 10 --output reports/experiments/E4_vs_team02.json
```

### 验收标准

- 对手 `Player()` 可以正常加载。
- 每局成功交换攻守。
- 正确记录我方胜平负和2/1/0积分。
- 正确记录双方累计时间。
- 非法动作、异常和超时应被完整记录。
- 如果出现异常，检查具体责任方，不能把对手程序出错自动理解为自己的算法更强。

当前 `replay_demo.py` 只支持内置策略，尚不能直接生成外部 Bot 对战的完整 HTML 回放。

因此 E4 以 `benchmark.py` 输出的 JSON 为主要验收材料。要增加真实对手的逐步回放，需要另行扩展工具。

---

# 19. 实验结果验证的两种等级

建议把所有实验验证分成两个等级。

### A. 强制通过：规则与数据一致性

无论使用什么 Seed 或算法，都应该满足：

- 每一步移动合法。
- 每一步棋盘连续。
- 吃子与官方裁判一致。
- 终局结果与官方判定一致。
- 搜索统计有正确的语义。
- 不会出现非法移动、异常、累计超时。

这是程序正确性的验收依据。

### B. 基准比较：棋谱是否与历史一致

使用历史回放作为参考，比较：

- 每一步行动是否相同。
- 第一次出现不同走法的位置。
- 被捕棋子是否相同。
- 行动总数是否相同。
- 最终胜方是否相同。

对于相同的代码版本、种子和充足预算，棋谱通常应该具有较高可复现性。

但当前程序使用实际运行时间进行截止判断，机器负载可能使搜索提前回退，因此不能将“与历史每一步完全相同”设为所有环境下的强制验收条件。

---

# 20. 实验结果记录模板

完成全部实验后，整理以下表格。

| 实验 | 算法 | 对手 | 局数 | 胜 | 平 | 负 | 积分率 |
|---|---|---|---:|---|---|---|---|
| E1-A | Adaptive | Random Seed42 | 20 | 待测 | 待测 | 待测 | 待测 |
| E1-B | Adaptive | Random Seed100 | 20 | 待测 | 待测 | 待测 | 待测 |
| E1-C | Adaptive | Random Seed2026 | 20 | 待测 | 待测 | 待测 | 待测 |
| E2-A | Greedy | Random Seed42 | 20 | 待测 | 待测 | 待测 | 待测 |
| E2-B | Minimax | Random Seed42 | 20 | 待测 | 待测 | 待测 | 待测 |
| E2-C | Adaptive | Greedy | 2 | 待测 | 待测 | 待测 | 待测 |
| E2-D | Adaptive | Minimax | 2 | 待测 | 待测 | 待测 | 待测 |
| E4 | Adaptive | External Bot | 10 | 待测 | 待测 | 待测 | 待测 |

同时保存3类实验成果：

**比赛成绩：** 结果 JSON、胜率、积分率、攻守成绩。

**逐步棋谱：** `games.json`、`replay.html`、典型吃子及终局截图。

**搜索统计：** 目标/完成深度分布、节点数量、耗时、回退和深度选择原因。

积分率计算为 `(2 × 胜局数 + 平局数) / (2 × 总局数)`；胜率计算为 `胜局数 / 总局数`。攻守胜率分别使用对应身份的局数作分母。普通 benchmark 可从 `standings.overall`、`standings.attacker`、`standings.defender` 读取成绩；逐步搜索统计位于回放 `games[].moves[].search`，不能把未记录数据补成0。

最终需要使用真实数据解释算法优势与局限，而不是仅仅展示全胜结果。

---

# 21. 实验完成判定

满足以下条件，可以认为第一轮实验完成：

- E0 规则和棋谱验收通过。
- E1 完成三组不同 Seed 的稳定性实验。
- E2 完成 Greedy、Minimax、Adaptive 的公平比较。
- E3 得到了真实逐步搜索统计，并说明深度3是否触发。
- 所有结果有明确代码版本、参数、Seed 和输出路径。
- 所有关键结论都能追溯到原始 JSON 或 HTML 棋谱。
- 对出现的重复对局、平局及异常给出解释。

E4 真实小组对战可根据对方代码可获得情况安排。

**最重要的原则：实际记录与预期不同，并不必然表示实验失败。先判断差异是否违反官方规则，再分析随机走法、搜索截止和运行环境的影响。**
