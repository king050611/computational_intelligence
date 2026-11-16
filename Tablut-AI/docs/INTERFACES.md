# 统一接口约定

## 数据

- Python 3.9+；坐标均为从 0 开始的 `(row, column)`。
- 外部棋盘：老师传入 `list[list[str]]`。
- 内部 Board：`tuple[tuple[str, ...], ...]`；GameState 是不可变 dataclass。
- 玩家：`A` 或 `D`，D 方同时控制 D 与 K。
- Move：`((起点行, 起点列), (终点行, 终点列))`。
- 空城堡是 X，位于 (4,4)，不得作为落点。中心初始为 K，国王离开后为 X。

## 调用接口

| 接口 | 输入 | 输出 / 契约 | 当前状态 |
| --- | --- | --- | --- |
| parse_board | 外部棋盘 | 不可变 Board；结构错误抛 ValueError | 已实现 |
| initial_state | 无 | 初始攻方回合 GameState | 已实现 |
| get_state_key | state | (board, player) | 已实现 |
| get_legal_moves | state | list[Move]，无棋可走为空列表 | 已实现 |
| is_legal_move | state, move | bool，move 使用标准 tuple | 已实现 |
| resolve_captures | 移动后的 board, destination | 捕获后的新 Board | 待 A 实现 |
| is_king_captured | 移动后的 board, destination | bool | 待 A 实现 |
| apply_move | state, move | 新 GameState，非法移动抛 ValueError | 待 A 实现 |
| get_game_result | state, history | A / D / DRAW / None | 待 A 实现 |
| minimax / alpha_beta_search | state, depth, evaluate, deadline | Move 或无棋可走时 None | 待 B 实现 |
| evaluate | state | float，越高越有利于评估函数对应方 | 待 B/C 实现 |
| choose_attacker_move / choose_defender_move | 外部棋盘 | Move 或 None | 基线已实现 |
| Player.play_attacker / play_defender | 外部棋盘 | list[list[int]] | 已对接 |

搜索中的 evaluate 固定为根节点玩家的视角：根方行动最大化，对手行动最小化。递归中不能随行动方更换评估函数，否则评分方向会冲突。

history 只包含此前已发生的状态键，不包括当前 state；当前状态键已在 history 中时才代表重复。搜索实现时也需要考虑路径上的重复，不能只比较棋盘而忽略回合。

deadline 使用 `time.perf_counter()` 的绝对值，不能混用 `time.time()`。TimeManager 应在一局内持续复用，决策后调用 record_elapsed，下一局重新创建。当前入口尚未使用该工具。

内部无合法走法返回 None；老师框架正常会先判无行动平局而不调用 Player。若调用方仍在终局调用 Player，入口会抛 ValueError，不伪造非法行动。
