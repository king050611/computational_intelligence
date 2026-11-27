# 外部来源与规则审计

[WTF 分项排名](https://aagenielsen.dk/separate_ratings.php)及[历史规则](https://aagenielsen.dk/historical_hnefatafl_rules.php)可查。站方代表曾在[论坛](https://aagenielsen.dk/hnefataflforum/phpBB3/viewtopic.php?t=72)列出一份 Tablut 对局文本，但本次未能核实该链接可下载，也未核实逐步棋盘、吃子证据及研究或批量使用许可。实际导入外部对局为 0，兼容率、胜负一致率和人类对照均缺数据。后续须用有明确授权的原始导出。

历史规则与课程的重复终局不同。公开规则还应逐项核对城堡、包围及无子可动的判定。[历史规则](https://aagenielsen.dk/historical_hnefatafl_rules.php)与[Bologna 2019 竞赛资料](https://lia.disi.unibo.it/Courses/AI/fundamentalsAI2018-19/challenge/Challenge2019.pdf)都说明同名的 9×9 Tablut 不能视为规则等价，Bologna 另有营地限制。[McGill 课程项目](https://github.com/demetrios-koziris/comp-424-tablut-ai-project)和[Ashton 论文](https://www.jemne.org/issues/13/ashton.php)用作规则与实现背景。

## 导入约定

运行 python -m scripts.import_external_games INPUT.json NEW_OUTPUT。输入对象包含 source 和 games。source 包含 url、variant、year、rules_url、permission_evidence 及 research_use_authorized。只有明确验证过规则等价的来源才填 course_rules_equivalent 为 true。每局提供 game_id、initial_board、moves、result。事件提供 player（A 或 D）、move（0 基坐标或 d1-c1）、board_after 和 captures（每项为 [行,列,棋子]），result 含 winner、reason。棋谱原始文件按字节存档。文本、SGF 等其他输入需先依据来源文档转换为这个规范，保留原始记录及坐标约定。

A 类要求规则等价、完整终局和所有动作证据一致。B 类只保留首次分歧或证据缺口前已验证的起始段，课程胜负为空。C 类隔离。暂无真实平台样本，因此测试只验证本地输入、规则重放及分流机制。
