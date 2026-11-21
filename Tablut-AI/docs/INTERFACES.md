# v2.2 接口约定

## 棋盘和规则

内部坐标从0开始，Move 为 `((起点行,起点列),(终点行,终点列))`，Board 为不可变 tuple。player 为 A/D，D控制 D/K。传给正式AI的外部列表棋盘不应被修改。

| `src/game.py` 接口 | 返回 |
| --- | --- |
| `parse_board(board)` | 结构校验后的Board；不校验完整可达性 |
| `initial_board()` | 初始Board |
| `get_legal_moves(board, player)` | `list[Move]` |
| `apply_move(board, move, player)` | 移动及同时捕获后的新Board；非法动作抛ValueError |
| `check_winner(board, player, history=())` | A / D / DRAW / None，player为接下来行动方 |
| `get_state_key(board, player)` | `(Board, player)` |

history仅含此前状态键。中心是K或X，空城堡可穿不可停。老师原件保存在reference；自动比赛和人机模式均由官方裁判执行真实动作，自己的规则引擎用于搜索模拟及合法行动生成。

## 搜索和评分

- `evaluate_attacker(board)`、`evaluate_defender(board)`：越高越有利于函数命名的一方。
- `choose_move(board, player, deadline=inf, strategy='adaptive', rng=None, stats=None)`：返回Move，无行动时None。
- 策略为first、random、greedy、minimax、adaptive；random要求显式传入带种子的RNG。
- `alpha_beta(board, current_player, root_player, depth, alpha, beta, deadline, path=(), *, prune=True, stats=None)`：返回固定根方视角分数。当前方等于根方时最大化，否则最小化。
- 终局胜负分为正负十亿，平局为0；非终局使用根方启发式评分。
- path为祖先状态键tuple，含行动方，不含当前节点；路径重复记平局。真实跨回合历史仍由官方裁判判定。
- 迭代加深只在完整完成一层后更新最佳结果；未完成第一层时可返回部分Greedy结果或默认合法行动。

TimeManager提供`allocate_time(expected_moves=30)`、`deadline()`、`record_elapsed(elapsed)`；截止绝对值与`time_exceeded()`均使用perf_counter，不能混用time.time。内部SearchTimeout由choose_move捕获并回退。

## 正式Player与可选监控

`Player(record_search=False)`保持默认无参兼容，每局重新创建。`play_attacker(board)`、`play_defender(board)`返回`[[行,列],[行,列]]`，并累计登记AI耗时。ENABLE_ADAPTIVE_SEARCH=False时入口使用固定目标深度2。

监控开启时，每步先清空旧记录，把新字典传给choose_move，在finally中保存`last_search_stats`与耗时。`StrategyBot(strategy, seed, record_search=False)`提供同一监控约定。正式比赛默认关闭监控，Replay自动打开；CLI仅在`--show-search`时打开。

| 统计字段 | 口径 |
| --- | --- |
| target_depth | 计划深度，直接获胜时为1 |
| completed_depth | 完整扫描结束的层数；First/Random为0 |
| nodes | Alpha-Beta递归通过截止检查后访问的节点数，包含未完成迭代节点，不含Greedy首层扫描 |
| root_moves | 根节点合法行动数量 |
| urgent | 实际执行的紧急判断结果；未执行时为null |
| policy_reason / finish_reason | 实际触发的深度选择条件、搜索结束原因 |
| timed_out / fallback_used | 是否截止中断、是否因此使用浅层或备用结果 |
| elapsed_seconds | Bot入口本次决策耗时 |

直接发现一步获胜时，`target_depth=1`、`completed_depth=0`、`finish_reason=immediate_win`、`fallback_used=false`，并不声称已扫描完整首层。缺少监控的旧棋谱为未记录，不补造0。

## 人机CLI

入口为`scripts/play_cli.py`，仅负责输入、展示和回合控制，复用正式Player、StrategyBot和官方Tablut。用户坐标为A1–I9：字母是列，数字是行，例如D1对应内部(0,3)。

| CLI接口 | 用途 |
| --- | --- |
| `parse_square(text)` | A1–I9转为(row,column)，格式错误抛ValueError |
| `parse_move(text)` | 两个空格分隔坐标转为Move |
| `format_square(position)` / `format_move(move)` | 内部坐标格式化为人类输入形式 |
| `display_board(board, write=print)` | 输出完整棋盘及坐标 |
| `read_human_move(board, side, *, input_fn=input, write=print)` | 处理help/moves/board/quit与合法性重试 |
| `run_game(human_side, strategy='adaptive', seed=42, show_search=False, *, input_fn=input, write=print, game=None, ai=None)` | 控制独立人机对战，返回结束状态字典；game/ai供可控测试注入 |
| `display_search_stats(stats, write=print)` | 输出监控字段；缺失统计显示未记录 |
| `main(argv=None)` | 参数解析、可选选边提示及退出码 |

run_game返回status、winner、reason等信息；status为finished/aborted/error，正常赢家为A/D/DRAW，中止或内部错误的winner为None。game_over表示官方终局；quit、eof、interrupted表示主动或输入中止；ai_exception、ai_illegal_move、ai_timeout表示AI判负，人类获胜，CLI以非零退出码提示失败；referee_rejected_move表示官方裁判拒绝了预验证动作，程序中止并报告内部一致性错误。

人类输入先用get_legal_moves验证，非法输入不调用make_move，不改变棋盘或裁判计数。每局初始化官方重复局面历史，A先行；每个执行动作之后调用官方check_if_game_over，不能漏掉重复判定或把quit当平局。AI接收棋盘副本，人类思考不计时，AI整局仍有60秒累计预算。

第一阶段无保存棋谱接口，不强制改动现有Replay schema，也不提供外部Bot人机选项。

## 实验与回放输出

benchmark的`--strategy`和`--opponent`使用内置策略名，`--opponent-file`接收真实.py路径；对手参数互斥。JSON含version、strategy、opponent、seed、games、standings、our_win_rate和results。standings有overall/attacker/defender，均含games/wins/draws/losses/points；issues按A/D记录错误责任方。

外部Bot在独立进程导入和实例化，初始化限10秒；构造失败在开赛前报错。进程内异常回传供裁判判负，格式错误动作转换为负坐标动作以便原裁判安全拒绝。每次调用和通信耗时计入对局时间。

v2.1及之后新Replay JSON的schema_version为1.1，逐步统计保存在`games[].moves[].search`，每步深拷贝；旧数据缺失字段显示未记录。普通benchmark的version目前仍为2.0输出标签，应结合实际Git SHA记录代码版本。当前人机模式不生成这些文件。
