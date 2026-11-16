# 基础框架搭建详细 List

## 1. 本次采用的材料与范围

- 以你粘贴的分层架构方案作为目录和分工依据。
- 从 `files(1).zip` 读取实际 `Tablut.py`、`Team00.py` 和环境依赖快照，以实际代码核对调用协议。
- 原 ZIP、作业 PDF 均保留在上一级目录，未修改。此次未提取或逐条核对 PDF，以下兼容性结论来自实际 Python 框架；正式规则验收仍需团队对照作业原文。
- 在当前文件夹内建立 `Tablut-AI/`，不移动用户原文件。

## 2. 完整目录

```text
Tablut-AI/
├── TeamXX.py
├── Tablut.py
├── Team00.py
├── requirements.txt
├── README.md
├── .gitignore
├── reference/
│   ├── Tablut.py
│   ├── Team00.py
│   └── requirements.txt
├── config/
│   ├── __init__.py
│   ├── rules.py
│   ├── settings.py
│   └── weights.py
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── state.py
│   │   ├── move_generator.py
│   │   ├── capture.py
│   │   ├── transition.py
│   │   └── terminal.py
│   ├── search/
│   │   ├── __init__.py
│   │   ├── minimax.py
│   │   └── time_manager.py
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── attacker_eval.py
│   │   └── defender_eval.py
│   └── agents/
│       ├── __init__.py
│       ├── attacker.py
│       └── defender.py
├── tests/
│   ├── __init__.py
│   ├── test_moves.py
│   ├── test_capture.py
│   ├── test_terminal.py
│   ├── test_search.py
│   └── test_integration.py
├── scripts/
│   └── benchmark.py
├── docs/
│   ├── SETUP_LIST.md
│   ├── INTERFACES.md
│   └── DEVELOPMENT_PLAN.md
└── reports/
    └── experiments/
        └── .gitkeep
```

## 3. 已实现的部分

| 文件 / 模块 | 已做的事情 | 用途 |
| --- | --- | --- |
| `config/rules.py` | 统一 9×9 棋盘、ADK.X 编码、方向、城堡及初始布局 | 防止三个人重复定义规则常量 |
| `config/settings.py` | 建立深度、剪枝开关、60 秒累计预算及安全余量配置 | 为后续算法提供集中调参位置，当前搜索参数未启用 |
| `config/weights.py` | 拆分攻守示例权重 | 提供配置格式，数值尚未调优，也未参与决策 |
| `state.py` | 定义不可变棋盘、Move、GameState、初始状态和状态键 | 统一模块数据，避免搜索分支误改原局面 |
| `parse_board()` | 检查尺寸、符号、X 位置及中心格；复制成 tuple | 接收老师的 list 棋盘，保持输入不变 |
| `get_state_key()` | 返回棋盘与轮到哪方的组合 | 为后续重复局面判断和缓存预留基础 |
| `move_generator.py` | 生成当前方所有横纵滑动走法，禁止越子、落在棋子或空城堡上，允许穿过空城堡 | 支撑当前基线和后续搜索 |
| `agents/` | 双方分别取稳定顺序中的第一个合法走法 | 建立可运行、可回退的最低基线 |
| `TeamXX.py` | 无参 Player、两个正式方法、tuple 到 list 的输出转换 | 对接实际老师框架 |
| `time_manager.py` | 累计耗时登记、安全余量、按预计剩余步数分配预算、单调时钟截止检测 | 提供后续搜索时间管理工具；当前基线未接入 |
| `benchmark.py` | 使用老师框架运行双方基线，自定义局数、JSON 输出、胜率、步数、总耗时、非法动作/超时/异常计数 | 冒烟验证和后续实验起点 |
| `reference/` | 保留老师三个原始文件的字节副本 | 随时核对来源，避免误改评测代码 |
| `.gitignore` | 忽略缓存、虚拟环境及生成的实验 JSON | 减少后续仓库噪声；需要提交实验时可另存或显式添加 |

`parse_board()` 只做结构检查，不检查棋子总数等完整局面合法性，允许构造稀疏测试棋盘。中心必须是 K 或 X，与老师框架的状态约定一致。

## 4. 已建立接口，但尚未实现

- `capture.py`：普通夹击、空城堡协助夹击、国王在中心/中心旁/普通位置的捕获、特殊防守棋子捕获、同时结算。
- `transition.py`：合法性检查、复制状态、搬动棋子、恢复空城堡 X、执行捕获、交换行动方。
- `terminal.py`：国王逃生/被捕、攻方少于两子、无行动平局、含行动方的局面重复平局。
- `minimax.py`：不剪枝 Minimax、Alpha-Beta、超时回退和后续优化。
- `attacker_eval.py`、`defender_eval.py`：双方特征及评分。

这些函数明确抛出 `NotImplementedError`，避免后续成员误以为调用它们已具备完整规则。当前 Agent 不调用这些待办接口，依赖老师框架执行真实对局。

## 5. 验证内容及边界

当前 unittest 共 10 项：7 项实际通过，3 项明确 skip，分别对应未完成的捕获、终局和搜索战术。已验证：

1. 初始棋盘与老师框架逐格一致，16A、8D、1K。
2. 初始局面攻守双方的完整合法走法集合，与老师框架枚举验证结果一致。
3. 空城堡可以经过但不能落入，不能斜行、原地移动或越子。
4. 状态键区分轮到哪一方。
5. 使用固定随机种子生成的可达局面，生成的走法均被老师框架接受。
6. 双方基线可以在老师框架内结束一整局，返回格式正确，不修改输入棋盘。
7. 时间管理工具能够累计消耗预算并保留余量。

三项 skip 是待办标识，尚不覆盖粘贴方案中全部 17 条验收要求。基线自对弈是确定性的，重复运行不能证明策略实力；JSON 的 elapsed_seconds 为整局墙钟耗时，尚未拆分各方每步耗时，也未实现权重组合比较。

## 6. 环境和交付状态

- 当前基线使用 Python 标准库，未安装额外依赖，未自动创建虚拟环境。
- 老师的 requirements 是 UTF-16 环境快照，保存在 reference；项目自己的 requirements 只描述当前基线需要的依赖。
- 未替你们填写正式组号、生成最终报告 PDF、创建远程仓库或提交 Git commit。
- 未在基础阶段实现搜索、启发式策略和完整规则引擎，后续按开发计划推进。
- 正式提交需要包含入口、config 和 src；算法实现后确认实际使用的库符合课程环境，并由团队按作业要求记录 AI 辅助使用情况。
