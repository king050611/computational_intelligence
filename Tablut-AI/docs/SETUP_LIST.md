# 轻量化重构 List

本文描述当前实现，替代旧版基础框架清单。

## 1. 结构迁移

| 旧文件 | 新位置 | 结果 |
| --- | --- | --- |
| config/rules.py、settings.py、weights.py | config/settings.py | 合并常量、配置、权重，删除重复文件 |
| core/state.py、move_generator.py | src/game.py | 复用棋盘解析和合法走法，取消 GameState 类，直接传 board 和 player |
| core/capture.py、transition.py、terminal.py | src/game.py | 实现原占位功能，删除旧目录 |
| evaluation/attacker_eval.py、defender_eval.py | src/evaluation.py | 实现两个评分函数 |
| search/minimax.py、time_manager.py | src/search.py | 保留累计计时，贪心选择替代未实现的搜索占位 |
| agents/attacker.py、defender.py | TeamXX.py + src/search.py | 删除 agents 层；入口调用统一 choose_move |
| tests/test_*.py | tests/test_bot.py | 合并并替换 skip 占位，现有 11 项真实测试 |
| 根 Tablut.py、Team00.py | reference/ | 删除重复副本，测试与实验从 reference 导入 |

## 2. 已完成的实际功能

1. 移动：横纵滑动、不越子、空城堡可穿过不可落入。
2. 捕获：普通夹击、空城堡协助、中心国王四面围捕、城堡旁国王剩余三面围捕、其他位置两面夹击。
3. 特殊捕获：中心国王被三名攻击者包围时，第四面防守棋子可被夹击。
4. 同时结算：先读取移动后的棋盘收集被捕棋子，再统一移除；不立即反吃移动方。
5. 状态：内部 tuple 棋盘，移动不修改输入；国王离开中心恢复 X，中心国王被捕后同样保留 X。
6. 终局：国王到边缘、国王消失、攻击者少于两枚、无行动平局、含行动方的重复局面。
7. 评分：双方各使用国王周围攻击者数量、直接逃生走法数量和棋子优势三个特征。权重尚未调优。
8. 决策：逐个模拟合法移动，优先获胜结果，再按自身评分择优；超时返回当前最佳合法走法。
9. 时间：Player 每局持有一个累计计时器，预留 5 秒，按预计剩余 30 次决策分配可用时间。单个候选内部不会中断，属于软截止；当前棋盘规模下已验证无超时。
10. 实验：可比较 first、random、greedy，交换攻守并记录双方耗时、每步平均/最大耗时及异常计数。

## 3. 验证结果

- 重构前：10 项旧测试，7 通过、3 跳过。
- 重构后：11 项测试全部通过，无跳过。
- 初始双方完整合法走法集合与老师框架一致。
- 固定随机种子的可达局面中，逐个合法动作的模拟棋盘与老师框架一致。
- 独立用例覆盖特殊国王捕获、空城堡、同时捕获、直接获胜、平局、评分变化、输入不变和预算回退。
- 10 局 greedy 对 random，seed=42，交换攻守：贪心方 10 胜，非法动作/异常/超时均为 0。记录位于 reports/experiments/greedy_vs_random.json。
- 这些验证不是对所有可能局面的穷举，也不能代表对强对手的性能。

## 4. 保留与限制

- 原始 ZIP、PDF、reference 原件均未修改。规则实现依据老师 Python 框架及用户方案，未重新逐页核对 PDF。
- 老师在中心国王被捕后会留下 '.'，本地引擎将其规范为 X；两者均已终局，不影响实际对局。其他已测试的非终局转换保持一致。
- 搜索只做一层贪心，未加入 Minimax/Alpha-Beta。settings 中 SEARCH_DEPTH 和两个优化开关暂不参与执行。
- 搜索自身不保存跨回合历史；实际比赛重复局面由老师框架判定，check_winner 支持显式传入历史。
- 当前仍保留 docs 和实验记录目录，用于保持已有文档与结果；没有生成最终报告。
- 旧版 Git 回退点为 f55940d（first commit）。创建 refactor/lightweight 分支因 .git 写入权限未成功，当前修改仍位于 main 的工作区，未创建新 commit 或推送。
