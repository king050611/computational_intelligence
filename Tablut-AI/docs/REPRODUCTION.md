# 实验复现与验收

正式运行使用 `TeamXX.Player`，攻方原 V5，守方 D-Champion-01。两侧使用 V4 冠军八维权重、深度 4、60 秒累计预算和引擎独立计时。训练与论文脚本可选，正式文件清单为 `reports/submission_manifest.json`。

## 对战和录像

```powershell
python -m scripts.benchmark --research --candidate-side A --pairs 2 --output reports/experiments/check
python -m scripts.analyze reports/experiments/check --html-dir reports/experiments/check
```

用 `--openings FILE` 复用冻结开局，按原清单设置种子、引擎、模型及双方预算。原 V5 来自最终归档的 reports/v7_baseline_engine，源码与原 20 局比赛清单逐文件匹配。历史 E1、R0、R1、R2 由其 Git 源码和比赛清单复现。R0 专用测试可从 3a03c02 恢复。记录的完整搜索深度与候选限定深度分别解读。

## 恢复历史数据

从项目目录执行 `python -m zipfile -e ../reference/archive/final-research-3a03c02.zip <空白恢复目录>`，以 ZIP 内 `__archive_manifest__.json` 的逐文件 SHA256 校验。较早的资料用 `pre-cleanup-v7-701f0d0.zip`，其余历史版本可从 Git 取得。归档位置、摘要、哈希与四组图见 [实验索引](../reports/experiment_index.json)。冻结目录的哈希按原始字节校验，跨系统解包时保留源码换行原样。

## 训练复现

`python -m scripts.train` 保留最小双阶段训练。最终一轮真实配置是种群 8、精英 2、Sigma 25、快筛每候选 8 局、复筛每候选 24 局、两轮深度均 4。守方池为 Escape、Protective、Champion、Manual，比例 30/30/25/15。候选权重与变异分组在 `config/`。用 `--output-dir` 指定专用运行目录，继续当前实现启动的训练时加 `--resume`，并保持配置和源码一致。候选入场表按实际向量写入每代目录。历史训练含近重复冠军的运行结果由归档中的原检查点复现。本次发布未重跑历史训练。

## 论文数据与图表

```powershell
python -m scripts.paper_results
python -m scripts.paper_results --figures-only
```

前者从两份原始归档重新生成 CSV 和 PDF。后者只读取随项目提供的 CSV，绘图需要 Matplotlib，正式 Bot 无此依赖。各实验按对手、角色、深度及条件分开保留。历史记录缺失的字段使用 `NA`。
