# 统一搜索与数据接口

## 规则与正式入口

`game.py`和`reference/Tablut.py`保持原样。棋盘9×9，内部不可变元组；A攻、D守、K国王、X空城堡。Move为`((row,col),(row,col))`，正式Player返回两个坐标列表。`get_state_key`同时包含棋盘与接下来行动方；重复历史只包含此前状态。

`TeamXX.Player(record_search=False)`继承统一适配器，默认enhanced_dynamic，不读取模型文件；每局创建新实例。CLI、Benchmark和Replay均使用`ExperimentalPlayer(strategy, evaluator=None, options=None, opening=None, record_search=False, seed=42)`。只有evolutionary_dynamic要求evaluator，其余策略拒绝注入。Random仅测试用途。

## 一个搜索器

`choose_enhanced(board, side, *, deadline, soft_deadline=None, history=(), evaluator=None, stats=None, options=None)`处理全部正式策略。根方视角固定、终局优先判定、Alpha-Beta完整分支、从一层迭代加深，未完成的层不会覆盖已完成结果；零预算返回合法备用动作。

`EnhancedSearch.visit`同时支持手工评估和六特征权重。置换表只存深度和走法提示，不缓存分数；当前重复历史始终重新判断。排序使用国王逃生、PV/提示、潜在吃子、killer及history分数，不能删除合法分支。表容量默认20,000，单次决策隔离。固定深度无计时对照应得到相同分数，最优并列走法允许不同。

`SearchOptions(max_depth=4, tt_capacity=20000, order_moves=True)`来自config/experimental.py，是未完成调参的现有默认值。Enhanced使用TimeManager按剩余预算分配；两个Dynamic版本使用相同AdaptiveTimeManager：整局60秒、5秒余量、单步上限4秒、软截止为额度80%，并按剩余步数与紧急程度分配。底层Python操作不能硬抢占，裁判独立检查累计60秒。

## 六特征及评估

模型采用守方视角`sum(w[i]*f[i])`，攻方取负；终局由搜索处理，不用启发式代替胜负。六个特征顺序固定：

| 特征 | 实现 |
| --- | --- |
| 国王包围压力 | 邻接攻击者数 / 4 |
| 直接逃生路线 | 国王可一步合法到达边缘的方向数 / 4 |
| 加权子力差 | (A数量 − 2×普通D数量) / 16 |
| 距离边缘 | min(row,col,8-row,8-col) / 4 |
| 国王行动力 | 国王合法目的地数量 / 16 |
| 逃生通道封锁 | 四条射线上第一个阻挡子为A时累加1/距离，再除4 |

封锁特征区分阻挡距离，不等同于“1−逃生路线”。三个策略均走同一个六特征提取和加权接口，默认使用手工初始化权重；E2不会因两方走不同特征提取代码而混入额外差异。初始化权重`(-400,600,-160,0,0,0)`与原三特征手工评分等价；新增特征初始权重为零，训练后才可能改变。权重有界，终局±十亿始终由规则优先处理。所有新特征的棋力收益仍待消融验证。

模型JSON须包含`schema_version=1`、`model_type=evolutionary_dynamic`、完全一致的六个features名称及六个有限weights，绝对值不超过10,000。旧四权重模型和神经检查点会被拒绝，不能默默回退成手工评估。

## 监控与结果

适配器每步重建last_search_stats；字段包括strategy、budget_seconds、elapsed_seconds、target_depth、completed_depth、nodes、cutoffs、tt_hint_hits、root_moves、pv、score、timed_out、fallback_used、finish_reason。Random深度和节点为0。Replay深拷贝，历史旧字段缺失时显示未记录。

Benchmark结果包括standings的overall/attacker/defender、逐局用时和责任方错误、opening_id、seed、积分、可选search_stats；manifest保存提交SHA、未提交变更、配置、环境、开局SHA256和模型SHA256。Replay schema1.1保存完整每步棋盘及事件，HTML内嵌JSON、可离线打开。历史schema仍可读取，旧数据不会被新算法改写。

遗传训练机制、续训约束和最终留出见[训练指南](TRAINING_GUIDE.md)。
