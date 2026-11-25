# ATHS 第一轮：增强 Alpha-Beta 与动态计时

基线为 `b51abfd09192698f3fc2e2650d913448f4406aec`，本地备份分支为 `backup/main-before-aths`。新增策略在 Benchmark 中显式选择，正式 Assessment 入口仍使用原来的 Adaptive，同时沿用原版规则、评分及课程裁判。

| 策略 | 搜索与时间控制 |
| --- | --- |
| adaptive | 原有搜索与静态预算 |
| enhanced | 全宽 Alpha-Beta 迭代加深，默认最多四层，沿用旧预算分配方式 |
| enhanced_dynamic | 相同搜索，按剩余时长、己方已走次数与局面风险分配预算 |

搜索保持根方评分，遇到终局先按规则计分。排序优先检查国王逃生、上一层及置换表提示、潜在捕获和剪枝历史，保留全部合法分支。每次决策至多缓存 20,000 个走法提示。相同棋盘可能对应不同历史，因此置换表只提示走法，每次仍按当前历史判重。战术诊断可确认立即胜和安全应对，预算不足给出未知状态。动态计时使用原有低成本紧急判断调整预算。

动态计时从适配器入口开始计量。每次预算取按预计剩余己方行动数分配的额度、剩余总预算的20%及4秒中的最小值。软截止为该额度的80%，在两层之间检查。硬截止在递归和局面计算前后检查。未完成的层不会覆盖上一个完整结果，零预算走有效的合法回退。课程裁判仍独立执行整局60秒时限。所有初始参数都是实验值。

## 复现

在 Tablut-AI 目录运行，并为每次实验使用新的输出路径。

```powershell
python -m unittest discover -s tests -v
python scripts/evaluate_positions.py --positions 100 --depth 2 --seed 42 --output reports/experiments/aths/depth2_run2.json
python scripts/generate_openings.py --pairs 10 --seed 42 --output reports/experiments/aths/openings_run2.json
python scripts/run_experiments.py --strategy enhanced --opponent adaptive --openings reports/experiments/aths/openings_run2.json --output reports/experiments/aths/enhanced_run2.json
python scripts/run_experiments.py --strategy enhanced_dynamic --opponent enhanced --openings reports/experiments/aths/openings_run2.json --output reports/experiments/aths/dynamic_run2.json
```

每个开局双方交换角色，使用相同配对种子，重复历史从该开局重新开始。结果包含代码版本、开局 SHA256、环境、配置、逐局耗时与裁判日志。配对汇总按开局而非单局重采样，输出积分率及95%区间。使用 `--record-search` 另行检查实际完成深度、PV、走法提示和回退。要比较排序贡献，可用 `--tt-capacity 0` 关闭置换提示，或 `--no-ordering` 关闭实验排序。测时与监控结果应注明设置。

第一轮验证按固定深度正确性、合法对战及等时棋力依次进行。即使节点减少，排序成本也可能让单个局面变慢。默认 Bot 晋级还需要独立开局集的实测结果和团队审核。UCT、Minimax 引导的 MCTS、ATHS 路由和统计评估留作后续阶段。

## 首轮筛选结果

- 纯标准库环境通过全部56项测试，包含原有46项。原版 Adaptive 对 Random 10胜，对 Minimax 10平，两组均无违规。
- 固定深度2的100个可达局面和深度3的8个局面全部评分一致。深度2从86,185节点减至31,618节点，合计约7.04秒降至3.26秒；仍有39个局面的提示排序版本比原版慢。深度3从139,901减至54,662节点，合计约9.85秒降至4.34秒。此对照从冷表开始，排序和排序加提示两组节点数相同，尚无置换提示的独立收益证据。
- `enhanced` 对 `adaptive` 在 Seed 42 的10对开局中取得15胜、2平、3负，攻方17/20分、守方15/20分。总积分率80%，按开局配对的 bootstrap 95%区间为62.5%–95.0%。20局的非法走法、超时、异常和非法返回均为0，单方累计墙钟用时最高约28.36秒。

原始数据在本地 `reports/experiments/aths/`。该目录也保存合并前基准及实际找到的6份训练检查点的校验归档。这些数据用于首轮筛选，正式替换仍需独立留出开局验证。
