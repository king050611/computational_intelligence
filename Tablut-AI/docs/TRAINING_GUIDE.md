# 唯一训练方向：Evolutionary Enhanced Dynamic

训练程序通过官方裁判的实际对战积分优化六个评估权重。所有个体与手工Enhanced Dynamic使用同一搜索器、同一动态预算和参数；不再训练线性回归或神经网络。

## 先验证流程

```powershell
python -m unittest discover -s tests -v
python scripts/train_evolution.py --generations 1 --population 2 --elite 1 --pairs 1 --max-depth 1 --output-dir reports/training/evolution_smoke_new
```

低深度验证只检查生成个体、比赛、选择、存盘，不证明棋力提升。目录必须新建或使用--resume。

## 正式建议配置

```powershell
python -u scripts/train_evolution.py --generations 10 --population 12 --elite 2 --crossover 0.7 --mutation 0.2 --pairs 4 --seed 42 --output-dir reports/training/evolution_run
```

默认最大深度4、置换容量20,000、排序开启；变异高斯标准差80、权重边界±2000。初始化包含手工等价个体与11个扰动个体。每代所有12个体分别对Enhanced Dynamic的4对开局换边，96局/代，10代共960局；遗传实验建议值尚未调优，不是保证完成的性能指标。

每代按积分排序，保留2精英，父代从排名前半选取；以0.7概率逐基因均匀交叉，以0.2概率独立变异每个权重并裁剪到边界。每个个体重新实测，不跨代缓存适应度。Best仅在积分严格增加时更新，同分保留先前模型。

## 产物、续训及停止

- `checkpoint-0000.json`保存初始种群及配置；之后每个完整代保存一个新检查点。
- `best.json`导出当前筛选Best及模型格式，仍是训练集选择结果。
- 每次代评测使用独立尝试目录，包含个体模型、裁判JSON和日志。中断留下的尝试不作为有效检查点，下次从最后完整代恢复，旧文件保留。
- 检查点记录配置、当前提交和未提交变更、开局哈希。写入为原子发布，不能覆盖既有代。模型best导出可重建。
- 文件锁阻止同目录多个训练进程。恢复时不允许更改种群、随机种子、开局、搜索配置；更改实验请创建新目录。

```powershell
python scripts/train_evolution.py --resume --generations 2 --output-dir reports/training/evolution_run
```

`--generations`为追加代数。在运行目录创建名为`STOP`的文件，当前代完成后不启动下一代。恢复前移除STOP。Ctrl+C也可中断，恢复从最近完整检查点开始。模型赛中任意一方非法动作、非法返回、异常或超时都会使该代失败，不能借对手故障晋级。

## 独立验证与冻结

先冻结best.json的副本，再创建与训练不同Seed的30对开局，双方交换身份，测试60局：

```powershell
Copy-Item reports/training/evolution_run/best.json models/evolution_frozen.json
python scripts/generate_openings.py --pairs 30 --seed 27182 --output reports/experiments/evolution_holdout.json
python scripts/run_experiments.py --strategy evolutionary_dynamic --model models/evolution_frozen.json --opponent enhanced_dynamic --openings reports/experiments/evolution_holdout.json --output reports/experiments/evolution_holdout_result.json
```

确认目标文件尚不存在再复制，避免覆盖其他冻结模型。分别报告攻守、胜平负、积分率、配对区间及错误；最后测试不得再用于调权。若未优于Enhanced Dynamic，就保留为研究结果，正式Player仍使用手工Enhanced Dynamic。当前仓库没有已通过此流程的遗传模型。

历史线性训练报告和成果仍保留，旧源码见[归档及精简复盘](../reports/SIMPLIFICATION_REVIEW_20261125.md)。
