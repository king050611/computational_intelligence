# JC4004 Tablut AI v2.0

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
