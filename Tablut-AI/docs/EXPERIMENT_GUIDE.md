# 对照实验与回放

所有命令在Tablut-AI运行。先运行 `python -m unittest discover -s tests -v`。当前仅维护enhanced、enhanced_dynamic、evolutionary_dynamic三个策略，random为测试基线。算法和模型格式见[技术参考](TECHNICAL_REFERENCE.md)。

## 配对正式实验

每组30对开局、60局，交换攻守，重复历史从给定开局重新开始。请使用新的输出路径，程序拒绝覆盖既有实验。

```powershell
python scripts/generate_openings.py --pairs 30 --seed 31415 --output reports/experiments/current_selection.json
python scripts/run_experiments.py --strategy enhanced_dynamic --opponent enhanced --openings reports/experiments/current_selection.json --output reports/experiments/E1_dynamic_enhanced.json
python scripts/run_experiments.py --strategy evolutionary_dynamic --model reports/training/evolution_run/best.json --opponent enhanced_dynamic --openings reports/experiments/current_selection.json --output reports/experiments/E2_evolution_dynamic.json
python scripts/run_experiments.py --strategy evolutionary_dynamic --model reports/training/evolution_run/best.json --opponent enhanced --openings reports/experiments/current_selection.json --output reports/experiments/E3_evolution_enhanced.json
```

E2两方采用相同搜索器、动态时间管理及参数，主要变量是评估权重。`--max-depth`、`--tt-capacity`、`--no-ordering`对本次全部内置搜索方生效，不能据这组命令声称只改变了单方深度。参数消融使用同一开局集，之后生成新的留出集验证，不能把筛选集当作最终测试。

`run_experiments.py`同时输出 `.summary.json`：按开局重采样10,000次，报告2/1/0积分率和配对95%区间。还需检查逐局攻守、非法动作、超时、异常及非法返回。进程抢占会影响实际完成深度，训练与正式计时对战不要同时运行。

## 不同种子与实际动作

```powershell
python scripts/replay_demo.py --games 2 --seed 42 --opponent random --output-dir reports/replays/seed42_new
python scripts/replay_demo.py --games 2 --seed 100 --opponent random --output-dir reports/replays/seed100_new
```

分别打开新目录的 `replay.html`。HTML内嵌生成时的数据；旧HTML不会随其他JSON更新。`games.json`记录每步前后棋盘、走法、吃子、搜索统计和终局。重复局面是合法完整终局，走到最后一步不等于必须捕获或逃生。Random种子影响对手选择，确定性搜索也会受实际计时影响。

遗传回放在同一命令中指定 `--strategy evolutionary_dynamic --model <六特征模型>`；遗传对手指定 `--opponent evolutionary_dynamic --opponent-model <模型>`。正式测时使用Benchmark，回放观测有额外开销。

## 搜索正确性与外部对手

```powershell
python scripts/evaluate_positions.py --positions 100 --depth 2 --seed 42 --output reports/experiments/fixed_depth_new.json
python scripts/benchmark.py --strategy enhanced_dynamic --opponent-file opponents/Team02.py --games 10 --output reports/experiments/external_new.json
```

固定深度工具比较同一引擎的无排序、排序、排序加提示分数；测试另有独立穷举oracle。冷表实验不一定显示提示的独立收益。外部Player在独立进程加载，需实现老师的攻守方法；这不是安全沙箱。外部结果不等于老师正式联赛。

原始输出保存到用户指定路径，缺省Benchmark生成唯一时间戳文件。历史版本结果继续保留在[结果索引](../reports/README.md)，不能当作本轮重新测量。
