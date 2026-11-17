# 2026-11-17 两局实际对战记录

本次未修改算法，使用本地 v2.0 程序实际运行 Adaptive vs Random，首局我方攻、次局我方守。

## 如何运行

PowerShell 工作目录：`D:\workstudy\大四\大四上\computational_intelligence\Tablut-AI`。

```powershell
cd 'D:\workstudy\大四\大四上\computational_intelligence\Tablut-AI'
python --version
python -m unittest discover -s tests -v
python scripts/benchmark.py --games 2 --output reports/experiments/demo_2026-11-17_two_games.json
Get-Content -LiteralPath reports/experiments/demo_2026-11-17_two_games.json -Raw
```

Python 为3.13.7；当前代码只需要标准库，没有安装额外依赖。21项测试全部通过，无跳过。比赛命令与教程的 `--games 2` 使用相同默认策略，仅增加独立输出路径，避免覆盖此前记录。

默认参数：我方 adaptive、对手 random、seed=42。两局随机对手各使用 seed=42、43；每局从初始棋盘开始，双方新建实例。自动交换攻守，由未修改的 reference/Tablut.py 判断移动、捕获、胜负、重复和每方整局60秒预算。

## 实际终端输出

```text
overall    W 2 D 0 L 0 Points 4/4
attacker   W 1 D 0 L 0 Points 2/2
defender   W 1 D 0 L 0 Points 2/2
Illegal moves / timeouts / exceptions: 0 0 0
```

## 两局详情

| 指标 | 第1局 | 第2局 |
| --- | --- | --- |
| 我方身份 | 进攻A | 防守D |
| 对手身份 | 随机防守D | 随机进攻A |
| 获胜方 | A，我方 | D，我方 |
| 总半步数 plies | 41 | 38 |
| 裁判显示轮数 | 21 | 19 |
| 我方行动次数 | 21 | 19 |
| 整局墙钟时间 | 1.025100秒 | 0.629816秒 |
| 我方累计决策时间 | 1.020566秒 | 0.625262秒 |
| 对方累计决策时间 | 0.000549秒 | 0.000784秒 |
| 我方平均单步 | 48.598毫秒 | 32.909毫秒 |
| 我方最慢单步 | 196.020毫秒 | 159.650毫秒 |
| 非法移动/超时/异常（双方合计） | 0/0/0 | 0/0/0 |

plies 是单方行动一次计1，不等同于双方各行动一次。第一局进攻方第21次行动后结束，所以只有41半步；第二局双方各19次，共38半步。墙钟时间还包括裁判和记录开销，因此略高于双方决策时间相加。

## 程序内部如何比赛

1. benchmark 读取默认策略和局数，创建我方 Player 与随机策略对象。
2. 第1局把我方传给裁判的进攻位置；第2局交换到防守位置。
3. 裁判复制棋盘，交替调用 play_attacker / play_defender。
4. 我方入口解析棋盘、计算本步预算，搜索器先扫描Greedy候选和直接获胜，再尝试深度2；符合危险、分支与预算条件时最多尝试3。
5. 递归使用固定根方评分、Alpha-Beta和路径判重；超时保留已完成层或合法回退。
6. 随机方使用独立RNG从合法走法中随机选取。裁判实际执行动作并判断终局。
7. benchmark 汇总计时、责任方错误、积分和日志，保存JSON。

## 结果说明什么

- 本次两种身份均可正常完成比赛，并击败随机合法走法基线，获得2胜、4分，样本内胜率100%。
- 本次没有因非法动作、异常或超时造成判负；我方每局累计决策时间远低于60秒预算。
- 随机方只挑合法动作，耗时远少于搜索方符合算法工作量差异；不能据此说我方实现效率最优。
- 只有两局且随机对手较弱，无法证明对其他小组或更强算法也有100%胜率，不能证明Adaptive优于Minimax或Greedy。
- 当前JSON没有逐步走法、终局棋盘或实际搜索层数；无法仅凭本记录还原完整决策过程、确认深度3是否完成，或区分防守胜利具体来自逃生还是攻击者不足两枚。运行耗时也会随机器负载和时间回退变化。

原始结果：[JSON记录](experiments/demo_2026-11-17_two_games.json)。该JSON按现有gitignore默认不纳入Git版本控制，当前文件已保存在本地。
