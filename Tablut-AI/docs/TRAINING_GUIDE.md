# Evolutionary Dynamic V2训练指南

V2继续只训练六个评估权重，不新增策略。正式`TeamXX.py`默认手工Enhanced Dynamic，遗传训练不在比赛中执行，也不自动替换正式模型。原V1检查点和实验数据保留，但V1不得续训进V2。

## V3：权重唯一种群与多样性复筛（当前训练机制）

V3只改训练机制，不改棋盘规则、搜索器、六特征、时间公式和正式入口。相对V2的三处变化：

1. **权重唯一种群**：`initial_population`/`next_population` 按六项权重的精确数值去重，重复个体先重新变异（至少一个基因有效变化），超过 `--dedup-attempts` 次仍重复则报错停止，不再无限循环。手工基线、前代冠军和精英始终保留；三者权重相同时合并为一个个体。
2. **权重唯一复筛**：`select_finalists` 的四个名额依次为手工基线、前代冠军、快筛最高的新候选、多样性候选，任何名额都不接受重复权重。基线与冠军重合时释放名额并按快筛顺序补位；有效候选不足 `finalists` 时中止该代，不用重复权重凑数。多样性候选只在快筛排名前半段里按归一化欧氏距离 `sqrt(Σ((w_i−best_i)/bound)²)` 选取，避免选出排名靠后但距离最远的个体。
3. **历史权重热启动**：`--initial-model <六特征模型>` 或 `--initial-checkpoint <旧检查点>`（互斥）把既有冠军写入新种群并设为初始历史对手/强制复筛候选，同时记录文件哈希、来源代数与权重。它只迁移权重，不继承旧适应度、旧排名或旧对局，也不绕过源码哈希校验：新运行使用新目录和新源码哈希，`--resume` 不允许重新播种。

热启动与复筛名额的命令示例（V3第一轮，8个体/快筛32局/复筛48局）：

```powershell
python scripts/train_evolution.py --generations 1 --population 8 --elite 2 --finalists 4 --quick-pairs 2 --quick-depth 2 --final-pairs 6 --max-depth 4 --tt-capacity 20000 --win-reward 3 --constrained --bound 1000 --seed 42 --initial-model reports/training/v2_champion_archive/v2_g1_best.json --output-dir reports/training/evolution_v3_run
```

检查点在V2字段外新增 `initial_weights`、`initial_weights_source`（来源类型、路径、SHA256、权重）、`population_stats`（size/distinct/duplicates）、`population_retention`（基线与前代冠军是否保留）、`record_search`，以及每个候选的 `statistics`（总分、攻守分项、官方积分率、平均/最大耗时、平均完成深度）和 `screening.finalist_selection`（入选原因、快筛排名、与冠军距离）。`--record-search` 只为统计增加逐决策记录，不改变搜索与时间分配。

V3首轮仍只跑一代，不自动追加代数；结论必须结合独立留出对局，内部best不等于通过验证的棋力。

## V4：先提搜索效率，再谈训练规模

V4的前提结论来自V3：**同一权重跨运行的复筛得分可在12/24–16/24之间漂移，候选间差距只有2–8分**，而深度2快筛与深度4复筛的排名相关为0。因此V4先把单节点成本降下来、把评估样本加上去，再用遗传训练调权重。

### 搜索层改动（`src/game.py`、`src/enhanced_search.py`、`src/transposition.py`）

| 原实现 | V4 |
| --- | --- |
| `apply_move` 用 `move in get_legal_moves(...)` 校验，每节点重复生成全部走法 | `is_legal_move` 只检查路径（O(路径长度)），坏路径立即返回 |
| 终局判定的“无合法走法”也生成全部走法 | `has_any_move` 只找第一条可走路径 |
| 特征里的“逃生路线”生成守方全部走法 | `get_piece_moves` 只生成国王自己的走法 |
| 置换表只存深度+走法提示 | 增加分数缓存：深度、EXACT/LOWER/UPPER、分数、走法，LRU 上限 `--tt-capacity` |
| 排序项包含“相邻敌人集合”，每节点额外 O(81) 扫描 | 去掉该项，排序只用 根优先 > 王逃生 > 置换走法 > killer > history |

分数缓存有三条硬约束，违反任一条都会导致错误搜索结果，测试里有对应用例：

1. 上下界必须与**进入节点时的原始窗口**比较（`alpha_start`/`beta_start`），不能用循环中被抬高的 alpha；
2. 只有**整个子树没有出现重复局面**时才写入（重复和棋的分数依赖祖先历史，不能复用）；
3. 节点本身若已在 `history` 中，直接返回和棋分数，不查表。

### 固定节点预算（实验用）

`SearchOptions(node_budget=N)` 或 `python scripts/benchmark.py --node-budget N` 让每步在固定节点数处停止，用于消去 CPU 负载与墙钟分配的影响；此时战术诊断也改为按生成子节点数（`max_nodes=200`）而不是 10ms 计时，保证同局面同结果。**正式比赛仍使用 60 秒墙钟**，节点预算只用于对照实验，并且必须再用真实限时对局验证。

### 训练配置

| 参数 | V3 | V4 |
| --- | --- | --- |
| 快筛深度 / 开局对 | 2 / 2 | 3 / 2 |
| 复筛开局对 / 局数 | 6 / 12 | **15 / 30** |
| 每代总局数 | 80 | **152**（32 快筛 + 120 复筛） |
| 多样性门槛 | 仅快筛前半段名次窗口 | 额外要求快筛适应度 ≥ 手工基线 − `diversity_margin`（默认 0.10） |

快筛深度取 3 的依据：深度 2 下双方都近乎盲目，实测出现单局 2000+ 步、单方 55 秒的无效漫游；深度 3 单步约 0.2–0.3 秒，成本可接受且行为稳定。

```powershell
python scripts/train_evolution.py --generations 1 --population 8 --elite 2 --finalists 4 `
  --quick-pairs 2 --quick-depth 3 --final-pairs 15 --max-depth 4 --tt-capacity 20000 `
  --win-reward 3 --constrained --bound 1000 --seed 42 `
  --initial-model reports/training/evolution_v3_run/best.json --record-search `
  --output-dir reports/training/evolution_v4_run
```

V3冠军权重等于手工基线，因此这次热启动等价于把手工基线设为历史冠军：复筛的“基线”和“前代冠军”两格合并，**释放出一个名额给新候选**，符合V4“多评估新权重”的目标。

## V5：围绕冠军的精细训练与正式验证

V5的第一轮（P0）只做核实与验证，不改引擎：

1. **冠军核实**：`best.json`、`screening.quick_trials[i]`、`trials[i]`、`population[i]` 四处必须给出同一权重向量，并记录 SHA256。
   注意各代都从 `i0` 开始编号，**V3 的 i7 与 V4 的 i7 不是同一个体**，引用时必须带版本。
2. **置换表跨历史测试**：`tests/test_transposition_v5.py` 比较“开缓存/关缓存”在真实对局线上的固定深度分数、
   无关历史、重复根键、浅层预热与必胜分命中。修改终局分值（如胜利距离）后必须重跑。
3. **正式验证**：60 局（30 对全新开局）对**完整冻结的旧引擎**，而不是只冻结 `TeamXX.py`：

```powershell
python scripts/benchmark.py --strategy evolutionary_dynamic `
  --model reports/training/v4_champion_archive/best.json `
  --opponent-file reports/training/v3_baseline_archive/engine/TeamXX.py `
  --openings reports/experiments/evolution_v5_formal_validation_20261129/openings.json `
  --max-depth 4 --tt-capacity 20000 --seed 20261129 --record-search `
  --output reports/experiments/evolution_v5_formal_validation_20261129/v4_champion_vs_v3_formal_60.json
```

`--opponent-file` 会在独立进程里按它自己的 `src/`、`config/` 加载对照 Bot，因此搜索器、时间管理、规则模块都是旧版原件；
加载前应核对归档里的逐文件 SHA256。

晋级判定（三者缺一不可）：官方积分率≥55%、配对95%区间下限>50%、独立验证≥60局，且零违规。
**只有训练权重与引擎配置同时冻结后跑的正式验证才算数**；引擎改动后旧验证结果作废。

### V5 Phase 6 精细训练配置

以经验证的冠军为中心做小步变异，而不是重新做大幅度随机搜索：

| 参数 | V4 | V5 精细训练 |
| --- | --- | --- |
| 初始化 | 手工权重 | `--initial-model` 指向已归档冠军 |
| sigma | 80 | **40**（`--sigma`），对照组仍用 80 |
| mutation | 0.2 | 0.2 |
| quick_pairs | 2 | **4**（64 局快筛） |
| final_pairs | 15 | 15（120 局复筛） |
| seed | 42 | **43**（换训练开局与种群抽样，降低过拟合） |
| 每代局数 | 152 | **184** |

```powershell
python scripts/train_evolution.py --generations 1 --population 8 --elite 2 --finalists 4 `
  --quick-pairs 4 --quick-depth 3 --final-pairs 15 --max-depth 4 --tt-capacity 20000 `
  --win-reward 3 --constrained --bound 1000 --sigma 40 --seed 43 `
  --initial-model reports/training/v4_champion_archive/best.json --record-search `
  --output-dir reports/training/evolution_v5_run
```

`--max-depth` 同时作用于训练中的内置对手，因此换深度会改变整条评测环境；冠军的深度必须由对照实验（同一冻结对手、
同一开局、40 局一组）决定，不能直接假设“越深越强”。

### V5 训练侧新增开关

| 开关 | 默认 | 作用 |
| --- | --- | --- |
| `--attacker-game-weight` | 1.0 | 训练适应度里执攻局的权重；1.0/1.0 与原有 3:1:0 完全等价 |
| `--defender-game-weight` | 1.0 | 执守局权重；两者不能同时为 0 |
| `--sigma` | 80 | 冠军附近的精细训练用 40；仍以 80 为对照 |

权重只改变**训练期的候选排序**，官方 2:1:0 积分与裁判规则不受影响。例如攻方是最大损失源时可用
`--attacker-game-weight 2 --defender-game-weight 1`，让攻方局面在适应度里占更大比重。

特征与模型结构：V5 起为**八特征 / schema 2**；`schema_version=1` 的六权重模型仍可加载并自动补两个 0
（`load_evaluator` 标记 `migrated=True`），因此旧的 V4 冠军可以直接用 `--initial-model` 热启动，
落盘时自动升级为 schema 2。


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
