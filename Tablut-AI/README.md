# JC4004 Tablut AI：轻量版

项目使用 `config/settings.py` 管理配置，核心业务仅有 `src/game.py`、`src/evaluation.py` 和 `src/search.py`，由 `TeamXX.py` 对接老师框架。

当前已实现完整移动模拟、普通及特殊捕获、终局判断、双方启发式评分和一层贪心选择。尚未实现 Minimax、Alpha-Beta 或迭代加深。

## 运行

进入本目录后运行（Python 3.9+，仅标准库）：

```powershell
python -m unittest discover -s tests -v
python scripts/benchmark.py --games 10
```

对比其他基线并保存记录：

```powershell
python scripts/benchmark.py --games 10 --opponent first --output reports/experiments/greedy_vs_first.json
python scripts/benchmark.py --games 10 --opponent random --seed 42 --output reports/experiments/greedy_vs_random.json
```

脚本默认以贪心策略对抗固定种子的随机策略，并逐局交换攻守；还支持 first、greedy 对手。输出胜率、双方累计耗时、贪心每步平均/最大耗时及违规计数。样本规模和基线强度有限，不能等同于正式比赛实力。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| config/settings.py | 游戏常量、预算、双方权重；深度和剪枝参数暂留作升级配置 |
| src/game.py | 不可变棋盘、合法移动、移动捕获模拟、胜负和平局判断 |
| src/evaluation.py | 各方三个特征：国王周围攻击者、直接逃生走法、棋子优势 |
| src/search.py | 贪心选择、实验基线、累计预算工具和截止检测 |
| TeamXX.py | 无参 Player，正式攻守接口、输出转换、累计计时 |
| tests/test_bot.py | 规则、策略、兼容性与预算测试 |
| scripts/benchmark.py | 通过老师框架比较不同策略 |
| reference/ | 老师提供的三个原始文件，保持原样 |
| docs/ | 重构清单、接口和后续分工 |
| reports/experiments/ | 实验结果，不是最终报告 |

老师实际调用 `Player.play_attacker(board)` 和 `Player.play_defender(board)`，返回 `[[行,列],[行,列]]`。每局须创建新的 Player，获得正式组号后将 TeamXX 改名，并同步测试和脚本中的导入。最终提交必须包含 config 和 src。

原根目录的 Tablut.py 和 Team00.py 重复副本已移除，统一保留于 reference。直接运行老师的 `reference/Tablut.py` 会进入人工输入示例；自动对战请用 benchmark。

原依赖快照保存在 `reference/requirements.txt`（UTF-16）；根 requirements 仅说明本项目目前无需第三方依赖。未安装大型课程环境依赖。

详细信息：[重构 List](docs/SETUP_LIST.md)、[接口约定](docs/INTERFACES.md)、[后续计划](docs/DEVELOPMENT_PLAN.md)。
