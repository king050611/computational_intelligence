# 技术参考：接口、搜索与数据格式

面向开发者。操作见[CLI指南](CLI_GUIDE.md)，命令见[实验指南](EXPERIMENT_GUIDE.md)，数据见[结果索引](../reports/README.md)。

## 1. 数据与规则

settings集中参数；game模拟、evaluation评分、search决策。正式入口TeamXX.Player，真实比赛由reference/Tablut.py裁判。

- Board：9×9的`tuple[tuple[str, ...], ...]`；外部列表不修改，移动返回新Board。
- 编码：A攻击者、D防守者、K国王、`.`空格、X空城堡。中心(4,4)为K或X，空城堡可穿不可停。
- player：A或D，D方控制D和K；A先行。Position为从0开始的`(row, column)`。
- Move：`((起点行,列),(终点行,列))`；正式输出转换为`[[行,列],[行,列]]`。
- CLI坐标：列A–I、行1–9；例如D1对应(0,3)，与内部坐标方向一致。

| game.py接口 | 返回及约定 |
| --- | --- |
| `parse_board(board)` | 结构校验并复制为Board；错误抛ValueError，不验证可达性 |
| `initial_board()` | 固定初始Board |
| `get_legal_moves(board, player)` | list[Move]，无合法动作时为空 |
| `apply_move(board, move, player)` | 搬动、恢复X、同时捕获后的新Board；非法动作抛ValueError |
| `check_winner(board, player, history=())` | A/D/DRAW/None；player为接下来行动方 |
| `get_state_key(board, player)` | `(Board, player)`，包含行动方 |

history只含此前状态键。国王被捕、到边缘、攻击者不足两枚决定胜负；无行动或局面重复记平局。搜索不知道完整比赛历史。

终局差异：中心国王被捕后，模拟保留X，裁判可能留下`.`；均为攻击方胜。回放保留裁判棋盘，不改写为本地表示。

## 2. 搜索与累计预算

`evaluate_attacker(board)`、`evaluate_defender(board)`高分有利于命名方；特征为国王压力、逃生路线和棋子优势，攻守权重独立。

```python
choose_move(board, player, deadline=float("inf"),
            strategy="adaptive", rng=None, stats=None)
alpha_beta(board, current_player, root_player, depth, alpha, beta,
           deadline, path=(), *, prune=True, stats=None)
```

choose_move返回Move或无动作时None。支持first/random/greedy/minimax/adaptive，random需RNG。root_player视角固定，根方最大化、对手最小化；胜负分正负十亿，平局0。path为祖先状态键tuple，不含当前节点。

搜索先扫描Greedy候选并检测直接胜利，随后迭代尝试深度2。Adaptive仅在以下条件同时满足时把目标改为3：国王存在一步直达边缘的合法动作，或相邻攻击者至少两枚；根合法走法不超过40；Greedy扫描后剩余本步预算至少0.4秒。参数来自settings，目标不保证完成。根走法按Greedy得分稳定排序。完整层才提交结果；截止返回已完成层、部分Greedy或初始合法动作。

`TimeManager(limit=60, margin=5)`每局新建并持续复用。`allocate_time(expected_moves=30)`按剩余可用预算除以预计剩余决策数；`deadline()`使用perf_counter绝对时间，`record_elapsed(elapsed)`累计耗时。递归检查截止，SearchTimeout由choose_move捕获。底层计算不可打断；正式裁判另核对每方整局60秒。

## 3. Player与搜索监控

`Player(record_search=False)`无参兼容，play_attacker/play_defender(board)返回列表动作；ENABLE_ADAPTIVE_SEARCH关闭时用minimax。实验适配器为`StrategyBot(strategy, seed, record_search=False)`。每局新建实例。

开启监控时，每步重建last_search_stats并在finally保存；Replay深拷贝避免串步。Replay自动开启，CLI通过`--show-search`开启；benchmark不存逐步统计。

| search字段 | 定义 |
| --- | --- |
| strategy | 实际调用的策略 |
| target_depth | 计划深度；First/Random为0，Greedy通常1，Minimax通常2，Adaptive最多3 |
| completed_depth | 完整扫描结束的层数，未完成首层为0 |
| nodes | 通过截止检查后进入的Alpha-Beta递归节点，含未完成迭代；不含Greedy扫描 |
| root_moves | 根节点合法动作数量 |
| urgent | 实际执行的紧急判断；未执行为null，不是false |
| timed_out | 是否达到本步截止时间 |
| fallback_used | 是否因此使用浅层或备用动作 |
| policy_reason / finish_reason | 实际触发的深度选择与停止条件，见下表 |
| elapsed_seconds | Bot入口的本次决策耗时 |

policy_reason：normal_depth（普通/固定深度）、urgent_deepening（满足深搜）、branch_limit（紧急但分支多）、insufficient_budget（紧急但预算少）、immediate_win（一步胜）、baseline（基线）。固定Minimax不执行紧急判断。

finish_reason为depth_completed（完成目标）、immediate_win（一步胜）、search_deadline（截止）、proven_terminal（已证明终局提前结束）、no_legal_moves（无行动）。

一步胜会直接返回，统计为target_depth=1、completed_depth=0、fallback_used=false；这不表示没有评估动作。目标3完成2且因search_deadline停止才是深搜截止回退；proven_terminal不等同于超时。First/Random深度0是明确基线定义，缺少数据必须为null或“未记录”。

## 4. 实验JSON与外部Bot

benchmark JSON顶层有version、strategy、opponent、seed、games、standings、our_win_rate、results。standings按overall/attacker/defender分别存games/wins/draws/losses/points，积分为胜2、平1、负0。

results逐局含game、our_side、winner（A/D/DRAW）、plies、elapsed_seconds、attacker_seconds、defender_seconds、our_mean_move_seconds、our_max_move_seconds、illegal_moves、timeouts、exceptions、issues、log、opponent_log。plies是半步数；issues按A/D存责任方、details和invalid_returns。墙钟时间含裁判开销。

benchmark的version仍是2.0标签，实验另记Git SHA及工作区状态。每局种子=基础seed+从0开始局号；外部Bot自行管理随机数。

外部Bot需无参Player及两个攻守方法。独立进程从对手目录加载并隔离同名模块，初始化限10秒，失败在开赛前报错。对局异常回传，格式错误转为负坐标非法动作并保留原值。调用与通信计时，初始化不计时。进程不是安全沙箱，只加载可信代码及齐全依赖。

## 5. 逐步Replay JSON

当前schema_version为1.1。顶层包含created_at（UTC）、coordinates、symbols、note、games。每局games[]包含game、our_side、seed、strategies（A/D）、initial_board、moves、final_board、result（winner/reason）、accepted_moves、双方累计秒数及referee_log。

| moves[]字段 | 内容 |
| --- | --- |
| ply / round | 从1开始的半步序号、双方轮次 |
| player / strategy / piece | 行动方、策略、移动棋子 |
| move / from_square / to_square | 完整动作、单独起终点；坐标均为从0开始的行列 |
| captures | 被移除棋子的piece及square列表 |
| board_before / board_after | 完整9×9棋盘；前后事件应连续 |
| accepted / status | 是否执行；played、illegal_move、timeout、exception等 |
| elapsed_seconds | 外层观察器耗时，略多于search中的入口耗时 |
| result_after | terminal、winner、next_player；终局不再有下一行动方 |
| search | 当前步统计的独立副本；缺失时null |
| error / invalid_return | 出错时的诊断信息，仅适用事件提供 |

result.reason为king_captured、king_escaped、fewer_than_two_attackers、repetition、no_legal_moves，或异常结束的timeout/exception/illegal_move。未执行动作accepted=false，棋盘保持原状。逐步result_after在官方平局时winner为null，以terminal和局级result的DRAW识别终局。

旧schema 1.0无search，显示“未记录”。HTML内嵌JSON、离线播放，不随模板或其他JSON自动更新。`write_replay(data, output)`用已有数据重新导出games.json和HTML，覆盖同名输出；无需重跑。CLI与外部Bot尚未接入Replay。

## 6. CLI接口与退出状态

CLI自行交替调用make_move/check_if_game_over。初始检查从空历史开始，加入初始棋盘+A行动的哈希，与play()起始记录一致。非法人类输入不触碰裁判计数；AI收副本，返回后核对累计60秒。

| CLI接口 | 契约 |
| --- | --- |
| parse_square(text)、parse_move(text) | 解析用户坐标；错误抛ValueError |
| format_square(square)、format_move(move) | 内部坐标转A1-I9形式 |
| display_board(board, write=print) | 输出完整ASCII棋盘 |
| read_human_move(board, side, *, input_fn=input, write=print) | 命令、合法性重试；quit返回None，EOF/中断向外传递 |
| display_search_stats(stats, write=print) | 展示可用统计，缺失不补造 |
| run_game(human_side, strategy='adaptive', seed=42, show_search=False, *, input_fn=input, write=print, game=None, ai=None) | 返回结果dict，后两个参数支持测试注入 |
| main(argv=None) | 解析参数及选择身份，返回进程退出码 |

run_game返回status/winner/reason/plies/ai_seconds。finished含官方game_over或AI判负；aborted对应quit/eof/interrupted；error对应referee_rejected_move，后两种winner=None。AI异常/非法/超时对应ai_exception/ai_illegal_move/ai_timeout，人类胜且退出码非零；普通结束和用户中止为0。

人类不限时，CLI计时不含输入和输出。人机棋谱未实现。
