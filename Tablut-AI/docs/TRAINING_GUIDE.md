# Evolutionary Dynamic V2训练指南

V2继续只训练六个评估权重，不新增策略。正式`TeamXX.py`默认手工Enhanced Dynamic，遗传训练不在比赛中执行，也不自动替换正式模型。原V1检查点和实验数据保留，但V1不得续训进V2。

## 先验证，再跑一整代

```powershell
python -m unittest discover -s tests -v
python scripts/train_evolution.py --generations 1 --population 2 --elite 1 --finalists 2 --quick-pairs 1 --quick-depth 1 --final-pairs 1 --max-depth 1 --output-dir reports/training/evolution_v2_smoke_new
python scripts/train_evolution.py --generations 1 --population 8 --elite 2 --finalists 4 --quick-pairs 2 --quick-depth 2 --final-pairs 6 --max-depth 4 --win-reward 3 --constrained --bound 1000 --output-dir reports/training/evolution_v2_run
```

流程验证8局；完整一代32局低深度快筛、48局高深度复筛，共80局（无故障时），不自动跑3代。低深度筛选不替代正式评测，不能保证不会淘汰适合高深度的个体。

## 胜利导向与硬约束

训练排名使用`(3×胜+平)/(3×局数)`；同分依次比较实际胜率、负局率，不奖励更短计算时间。`--win-reward 2`或`5`可用于未来受控比较，本轮默认3。Benchmark官方积分始终2:1:0，必须同时报告实际胜率、官方积分率及攻守表现。

候选自己的非法动作、非法返回、异常或累计用时超过60秒会被淘汰，不以故障负局继续拟合。对手或运行环境故障使该次实验无效，最多重试一次；重复失败中止本代，不能从对手故障获利。手工对照或必要的前代精英无法安全复核时，不发布该代结果。

## 约束和两阶段筛选

默认种群8、精英2、交叉0.7、每基因变异0.2、高斯标准差80，边界±1000。W1/W3/W4/W6限负，W2/W5限正，允许零；`--unconstrained`关闭符号约束，其余条件应保持一致。约束是可检验的战略先验，不保证提高棋力。

每代在相同快筛开局上评估所有8个体。复筛保留4个体，其中必须包含手工基准及前一代冠军（如果不同），剩余名额按快筛排名填充。新种群保留精英并通过交叉/变异补足8个体，始终保留手工基准。

第一代没有历史冠军时，对手为Enhanced Dynamic与Enhanced，按2:1配额分配；6对复筛为4对Dynamic、2对Enhanced。后续目标为Dynamic50%、Enhanced25%、前代冠军25%，按完整开局配对进行最大余数取整；6对无法精确各25%，实际配额写入检查点。同一代同一阶段所有候选使用相同开局和对手安排，双方角色交换。

前代冠军先冻结为本代历史对手，且作为候选在本代复筛。对手池改变后，旧代分数不能直接用于晋级，当前best必须依据本代复筛重新选择，分数不保证单调上升。记录所有筛选和复筛原始结果，避免只展示历史最高值。

## 检查点、恢复及停止

- V2检查点schema为2，模型文件仍是六特征模型schema1，可由现有Benchmark/CLI/Replay加载。
- 记录配置、源码哈希、提交SHA、未提交状态，以及相互隔离的快筛/复筛开局哈希。
- `checkpoint-0000.json`保存初始种群；每个完整代原子发布新检查点，`best.json`导出当代筛选冠军。
- 同目录文件锁防止多进程写入。中断后仅恢复最近完整代，未完成尝试保留而不复用；不宣称已完成未落盘的代数。
- 恢复禁止更改遗传参数、对手池规则、筛选配置、开局或运行源码。新实验使用新目录。

```powershell
python scripts/train_evolution.py --resume --generations 1 --output-dir reports/training/evolution_v2_run
```

建立运行目录中的`STOP`文件，当前代完成后不再开始新代；恢复前移除STOP。只有用户决定继续时才增加代数，不自动启动长训练。

## 战术与时间

共享搜索器只在紧急局面中分配最多10毫秒、且不超过剩余单步预算5%的战术诊断。已确认的一步胜利可以直接返回；完整确认的安全应对只调整搜索顺序，仍保留全部合法走法。诊断未完成时明确记unknown，不把未知当安全，也不禁止按规则重复求和。

终局保持±十亿；权重不能覆盖真实胜负。战术直接胜利的`completed_depth`为0，因为未执行完整Alpha-Beta层，`finish_reason=tactical_win`区分该情形。整局60秒、5秒余量、单步4秒及软截止80%的公式未改变；这些边界不能替代实际长局验证，也不构成绝对不超时保证。

## 独立性能验证

训练最佳只说明内部适应度较好。模型冻结后使用不同Seed的新开局，检查与两套训练开局无重复，再对手工Enhanced Dynamic配对测试。先做少量性能初探，正式晋级至少另需30对60局、官方积分率≥55%、配对区间下限>50%、无违规，并分别报告攻守。低深度约束/无约束流程测试不是正式棋力比较。

模型不能因3:1:0适应度较高而自动晋级；尤其要检查增加胜局是否伴随过多败局和官方积分下降。正式默认不加载研究权重。
