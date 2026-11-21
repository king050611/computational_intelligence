# 逐步 JSON 棋谱与离线回放 Demo

这是独立回放工具。v2.1 在搜索器和策略适配器中增加可选统计接口；规则、初始棋盘、评估权重和搜索决策条件保持不变。Demo 内继承老师裁判记录实际执行结果。

## 运行

在 Tablut-AI 中执行：

```powershell
python scripts/replay_demo.py --games 2 --output-dir reports/replays/demo_2026-11-17
```

默认我方 adaptive、对手 random，seed=42，逐局交换攻守。可用 `--strategy minimax --opponent greedy` 比较其他内置策略。输出目录不指定时使用 `reports/replays/latest`；重复指定同一目录会覆盖该目录的 games.json 和 replay.html。

这会重新运行并记录比赛，不能从旧 benchmark 汇总结果中恢复以前没有记录过的走法。当前 demo 暂只支持已有五种内置策略，不包含外部 Bot 加载。

## 打开结果

- `games.json`：可用 VS Code 打开，或让其他程序读取。
- `replay.html`：双击后在浏览器离线打开，不需要服务器或联网。页面内嵌同一份 JSON，不使用 fetch。
- 页面可选择比赛、上一步/下一步、滑动选步、自动播放、查看落子前棋盘、下载JSON。
- 平局会显示“平局 / 重复局面”等实际结束原因；每局搜索汇总在选择比赛时计算，翻步只更新当前步信息。
- 展开页面底部“整局图解”，会画出初始局面和每一步落子后的棋盘。
- 绿框标记起终点、箭头显示移动方向、红叉标记本步被捕棋子位置。A蓝、D金、K红；所有坐标按[行,列]从0开始。

页面模板更新只影响之后导出的 HTML。已有回放内嵌旧版页面代码，不会自动升级；保留的 `games.json` 可通过 `write_replay()` 重新导出，无需重跑比赛或改写历史走法。

## JSON 格式

顶层包含 schema_version、created_at（UTC）、coordinates、symbols 和 games。每局包含：

| 字段 | 内容 |
| --- | --- |
| game / our_side / seed | 局号、我方攻守身份和随机种子 |
| strategies | A/D各自使用的策略 |
| initial_board | 初始9×9二维棋盘 |
| moves | 按发生顺序排列的双方行动 |
| final_board | 实际终局棋盘 |
| result | 获胜方及结束原因 |
| accepted_moves | 真正被裁判接受的动作数 |
| attacker_seconds / defender_seconds | 双方决策累计耗时 |
| referee_log | 原裁判输出 |

每步包含：

| 字段 | 内容 |
| --- | --- |
| ply / round | 半步序号、双方轮次 |
| player / strategy / piece | A或D行动方、所用策略、移动棋子ADK |
| move | [[起点行,列],[终点行,列]] |
| from_square / to_square | 起终点单独字段，便于读取 |
| elapsed_seconds | 本次决策耗时 |
| accepted / status | 是否实际执行，以及played、illegal_move、timeout、exception等状态 |
| captures | 本步被捕棋子的piece及square |
| board_before / board_after | 落子前后完整9×9棋盘 |
| result_after | 本步后是否终局、赢家、接下来行动方 |

例如本次第一局第一步，A棋子从[0,3]到[0,2]，无吃子；第二步D从[4,6]到[7,6]。完整数据含每步实际棋盘，不只是文字走法。

非法动作或超时未执行的动作会标accepted=false，落子后棋盘保持不变；异常详情保存在error。回放以实际棋盘为准，不把未执行动作画成成功移动。

## 本次验证

已记录两局：41步进攻方胜（king_captured），38步防守方胜（king_escaped）。重新用未修改的官方裁判重放全部79步，逐项核对落子前/后棋盘、动作合法性、终局时点与最终赢家，全部一致。页面JavaScript语法检查通过，已用本机Edge渲染并检查初始页面截图。

数据位于 `reports/replays/demo_2026-11-17/`，该目录同时包含离线页面和预览图。

旧schema 1.0不包含搜索监控；v2.1新记录含实际完成深度和程序触发的深度选择原因，但不包含搜索树、启发式评分或AI主观思考理由。裁判调用中增加了观察开销，故此demo耗时不应替代正式benchmark性能统计。

## v2.1 逐步搜索监控

新JSON的schema_version为1.1，每个moves事件新增search。Replay开启内置Bot监控，正式Player和普通benchmark默认关闭。每步在finally中保存独立深拷贝，异常或非法动作仍保留可用诊断；无统计时为null。旧1.0数据用新模板生成页面时正常显示“未记录”，已有旧HTML不会自动升级。

| search字段 | 口径 |
| --- | --- |
| strategy | 本步实际调用的策略 |
| target_depth | 计划深度；初始默认2，实际触发深搜后3；立即获胜为1 |
| completed_depth | 只有完整一层结束才递增；First/Random为0 |
| nodes | Alpha-Beta递归进入并通过截止检查的节点数，包括未完成迭代访问的节点，不含Greedy扫描 |
| root_moves | 当前根节点合法走法数 |
| urgent | 实际策略判断结果；未执行该检查时为null，例如Greedy、固定Minimax、直接获胜、首层超时 |
| timed_out / fallback_used | 截止中断，以及是否因此使用较浅层或备用走法 |
| policy_reason | normal_depth、urgent_deepening、branch_limit、insufficient_budget、immediate_win、baseline |
| finish_reason | depth_completed、immediate_win、search_deadline、proven_terminal、no_legal_moves |
| elapsed_seconds | Bot入口决策耗时；事件外层elapsed_seconds仍含观察包装耗时 |

直接获胜允许立刻返回，该层没有完整扫描时completed_depth=0、target_depth=1，但fallback_used=false。不能把这一0层当成Random策略；须结合strategy与finish_reason。若首层就到截止，target_depth仍为原计划2，completed_depth=0，未执行的urgent保持null。固定Minimax的normal_depth表示固定常规深度，不声称已判断局面安全。

目标3、完成2且finish_reason=search_deadline才表示深度3超时回退；proven_terminal表示已证明终局提前结束，不属于超时回退。每次行动前清空last_search_stats，监控只读取原有决策分支，不重复调用choose_move。

### 2026-11-18 实验

26项测试全部通过，保留原21项。覆盖正常/紧急/分支限制/预算限制、一步获胜、两级超时回退、基线口径、监控开关行动一致、字典副本和旧数据展示。限时测试采用模拟时钟或SearchTimeout；实战另核对全部200步棋盘快照与官方裁判一致，6局无非法动作、异常、累计超时。

| 对手 | 我方执攻 | 我方执守 | 我方完整深度2步数 | 我方一步获胜步数 | 我方递归节点总数 |
| --- | --- | --- | --- | --- | --- |
| Random | 胜，1.035秒 | 胜，0.690秒 | 38 | 2 | 22298 |
| Greedy | 胜，0.567秒 | 平，0.222秒 | 33 | 1 | 10317 |
| Minimax | 平，0.292秒 | 平，0.257秒 | 27 | 0 | 6282 |

我方全部样本均未触发目标3，也没有截止回退；紧急局面有11步因根走法数超过阈值保持深度2。这是实测结果，不调整阈值制造深度3。触发和中断深度3的控制流由模拟条件测试验证，不当作实战完成深度3的证据。

分别输出于reports/replays/depth_demo、depth_greedy、depth_minimax；每个目录均有games.json和replay.html。depth_demo/monitoring_summary.json含分局深度分布、原因、节点和时间原始汇总。

监控开销：初始棋盘Adaptive执攻，无限截止以排除超时干扰，预热后交替开关各运行10次，无回放观察器。关闭/开启中位耗时26.025/26.149毫秒，约增加0.48%；全部走法一致。短测受系统噪声影响，不能代表所有局面，也不能以Demo耗时替代正式Performance成绩。
