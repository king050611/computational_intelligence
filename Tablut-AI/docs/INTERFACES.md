# v2.0 接口约定

## 棋盘和规则

坐标从0开始，Move 为 `((起点行,起点列),(终点行,终点列))`，Board 为不可变 tuple。player 为 A/D，D 控制 D/K。外部列表输入不被修改。

| src/game.py 接口 | 返回 |
| --- | --- |
| parse_board(board) | 结构校验后的 Board；不校验完整可达性 |
| initial_board() | 初始 Board |
| get_legal_moves(board, player) | list[Move] |
| apply_move(board, move, player) | 执行移动及同时捕获后的新 Board；非法动作抛 ValueError |
| check_winner(board, player, history=()) | A / D / DRAW / None，player 为接下来行动方 |
| get_state_key(board, player) | (Board, player) |

history 仅含以前的状态键。中心是 K 或 X，空城堡可穿不可停。老师原件在 reference，实际比赛由它控制。

## 搜索和评分

- evaluate_attacker(board)、evaluate_defender(board)：越高越有利于函数命名的一方。
- choose_move(board, player, deadline=inf, strategy='adaptive', rng=None, stats=None)：返回 Move；无行动返回 None。
- 策略：first、random、greedy、minimax、adaptive。random 要求显式传入带种子的 RNG。
- alpha_beta(board, current_player, root_player, depth, alpha, beta, deadline, path=(), *, prune=True, stats=None)：返回根方视角分数。root_player 在整个树中固定；当前方等于根方时最大化，否则最小化。
- 终局胜负分为正负十亿，平局为0；非终局用根方的启发式评分。
- path 为祖先状态键的 tuple，包含行动方，不能含当前节点；路径重复记平局。
- stats 可选字典用于检查 completed_depth、target_depth、nodes、timed_out，不影响正式返回格式。直接发现获胜时 completed_depth=1 表示已经证明单步胜利，并非扫描了所有候选。
- 深度2/3未完成不更新最佳结果。深度1未完成则使用部分 Greedy 结果或合法默认动作。

TimeManager 仍提供 allocate_time(expected_moves=30)、deadline()、record_elapsed(elapsed)；time_exceeded 使用 perf_counter，禁止与 time.time 的绝对值混用。递归内部抛 SearchTimeout，由 choose_move 捕获用于回退。

## 正式入口

`Player()` 无参构造，每局新建。play_attacker(board)、play_defender(board) 返回 `[[行,列],[行,列]]`，并累计登记耗时。ENABLE_ADAPTIVE_SEARCH=False 时正式入口使用固定目标深度2。

## 对战记录

benchmark 的 --strategy 与 --opponent 使用上述策略名，--opponent-file 接收实际 .py 路径，二者对手参数互斥。

JSON 顶层包括 version、strategy、opponent、seed、games、standings、our_win_rate、results。standings 有 overall/attacker/defender，均含 games/wins/draws/losses/points。每局记录 our_side、winner、plies、双方秒数、我方每步平均/最大耗时、issues、总违规数、裁判日志和外部日志。issues 的 A/D 明确责任方，包含异常类型及说明、格式错误原返回值。

外部 Bot 的导入和实例化在独立进程完成，初始化限10秒，失败直接报错而不伪造比赛结果。进程内异常回传主进程供裁判判负；格式错误动作映射为负坐标动作，确保原裁判能安全拒绝。加载过程与构造耗时不算决策时间；每次调用和通信耗时计入对局时间。
