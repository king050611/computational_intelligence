# 逐步 JSON 棋谱与离线回放 Demo

这是独立观察工具，不修改 `TeamXX.py`、`src/`、`config/` 或老师原件。新增脚本只在 demo 内继承老师裁判，观察其实际执行结果，复用现有策略适配器。

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
- 展开页面底部“整局图解”，会画出初始局面和每一步落子后的棋盘。
- 绿框标记起终点、箭头显示移动方向、红叉标记本步被捕棋子位置。A蓝、D金、K红；所有坐标按[行,列]从0开始。

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

记录与绘图不包含真实搜索深度、搜索树或AI思考理由；它用于查验“双方实际怎样走”，不能凭棋谱断言搜索为什么选择某一步。裁判调用中增加了观察开销，故此demo耗时不应替代正式benchmark性能统计。
