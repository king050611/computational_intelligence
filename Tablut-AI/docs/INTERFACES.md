# 轻量版接口约定

## 数据约定

- 坐标从 0 开始，形式为 (row, column)。
- Board 是 tuple[tuple[str,...],...]；外部 list 棋盘可以传入函数，输出的新棋盘使用 tuple。
- Move 是 ((起点行,起点列),(终点行,终点列))。
- player 为 A 或 D；D 同时控制 D 和 K。编码使用 A、D、K、.、X。
- 已取消旧版 GameState 类、Agent 层及 core 子包，所有调用直接传 board、player。

## 对外函数

| 模块 / 函数 | 参数 | 返回 |
| --- | --- | --- |
| game.parse_board | board | 检查尺寸和编码后复制为 Board，错误抛 ValueError |
| game.initial_board | 无 | 标准初始 Board |
| game.get_legal_moves | board, player | list[Move]，无走法时为空列表 |
| game.apply_move | board, move, player | 捕获后的新 Board，非法 move 抛 ValueError |
| game.check_winner | board, player, history=() | A / D / DRAW / None，player 是接下来行动方 |
| game.get_state_key | board, player | (Board, player) |
| evaluation.evaluate_attacker | board | 越大越有利于 A 的分数 |
| evaluation.evaluate_defender | board | 越大越有利于 D 的分数 |
| search.choose_move | board, player, deadline=inf, strategy='greedy', rng=None | Move，无行动返回 None |
| TeamXX.Player.play_attacker / play_defender | board | list[list[int]] |

parse_board 做结构检查，允许稀疏测试局面；它不验证棋子数量或完整局面可达性。空中心使用 X，国王在中心时使用 K。

history 仅包含此前状态键，不包含当前状态；相同棋盘但行动方不同不算重复。check_winner 为无副作用函数，不会自动追加历史。

choose_move 默认固定顺序遍历，评分相同保留先遇到的动作。获胜优先，失利最差，平局记 0。first 用于复现旧基线；random 要求传入已设种子的 random.Random。终局应先由比赛控制器判断，避免请求无走法的 Player。

## 时间接口

TimeManager.allocate_time(expected_moves=30) 返回本步可用秒数，deadline() 返回 perf_counter 绝对截止时间，record_elapsed() 登记实际耗时。time_exceeded(deadline) 使用同一单调时钟。

Player 已集成预算管理；每局创建新实例，不跨局复用累计时钟。输入棋盘不被修改。策略为软截止：在候选走法之间检查时间，截止后仍返回合法回退。
