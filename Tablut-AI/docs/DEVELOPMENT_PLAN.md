# v2.2 当前进度与团队分工

## 当前交付范围

项目保留三个业务模块：game、evaluation、search。v2.0建立规则模拟、双边评分、Greedy和后续Minimax/Alpha-Beta；v2.1增加可选逐步搜索监控；之后的低风险整理减少了回放重复汇总和无引用配置定义。

v2.2第一阶段新增独立终端人机模式，工作范围为`scripts/play_cli.py`、`tests/test_cli.py`和对应文档。人类可选攻守、输入A1–I9、查看合法走法和帮助、退出游戏，并可查看AI实际搜索统计。输入先验证再交给官方裁判，人工思考不计入AI预算。

原有搜索算法、权重、初始布局、正式入口和老师裁判继续复用；本阶段没有人机JSON导出或HTML回放，不扩大核心目录。

## 三人分工

| 成员 | 主要文件 | 后续任务 |
| --- | --- | --- |
| A：规则与兼容性 | game.py、TeamXX.py、play_cli.py、测试 | 对照课程原文复核特殊捕获，核对人机回合、终局和正式组号 |
| B：搜索与计时 | search.py、settings.py、监控测试 | 分析搜索完成率和预算，复查失败棋局；以数据决定是否继续优化 |
| C：实验与体验 | evaluation.py、benchmark.py、回放与文档 | 多种子、多对手实验，试玩终端输入，整理成绩和报告材料 |

B/C共同参与规则和人机输入测试，避免规则边界工作集中给A。当前策略名称只代表不同决策方法，不承诺固定难度排名。

## 本阶段验收

1. 坐标解析、大小写、错误输入、help/moves/board/quit正常。
2. 非法人类输入不改变棋盘、回合或裁判移动计数。
3. 人类选D时AI先走；AI接收副本，每局只创建一个实例并累计时间。
4. 官方胜负与重复平局正常；退出、EOF和Ctrl+C明确中止。
5. AI异常、非法动作及累计超时明确报告，不默默执行或当作平局。
6. 原有28项测试保留，新增CLI测试后以完整unittest实际输出为准；benchmark和Replay原命令继续可运行。

在Tablut-AI目录执行：

```powershell
python -m unittest discover -s tests -v
python scripts/play_cli.py --side A --strategy adaptive
python scripts/benchmark.py --games 2
python scripts/replay_demo.py --games 2
```

交互试玩和自动测试验证用途不同；人机模式人工输入不计时，不应用其耗时冒充正式Performance成绩。

## 第二阶段及正式提交

- 人机交互稳定后，再将动作映射为现有Replay事件，复用Recorder/write_replay导出JSON和HTML，建议输出至reports/human_games。
- 扩大不同Seed与真实外部Bot样本，分别统计攻守、错误和耗时；已有小样本不能证明Adaptive总是更强。
- 继续记录目标/完成深度、节点和回退，不通过修改历史棋谱制造深度3。
- 获得正式组号后替换TeamXX并同步导入，独立目录模拟提交，检查必要模块和依赖。
- 全员理解实现并审核报告、引用和AI辅助使用记录，保证实验结论可追溯到真实数据。

原定11月完成规则与算法、12月初实验、12月7–10日报告、12月11–13日模拟提交的安排仍可参考；正式截止以课程通知为准。SETUP_LIST.md保留v2.0历史里程碑，实验操作以EXPERIMENT_MANUAL_V2_1.md为准；当前文档不声称新代码已经提交或推送GitHub。
