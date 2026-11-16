# JC4004 Tablut AI 基础框架

当前阶段：项目初始化、接口统一、合法走法生成、基线 Bot 对接。尚未实现独立规则引擎和 Minimax。

## 快速运行

在 PowerShell 中进入本文件所在目录，使用 Python 3.9 或以上版本：

```powershell
cd .\Tablut-AI
python -m unittest discover -s tests -v
python scripts/benchmark.py --games 2 --output reports/experiments/baseline.json
```

如果当前已经位于 `Tablut-AI`，无需再运行 `cd`。本项目基线仅使用标准库，无需安装依赖。可选创建隔离环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

没有自动安装老师环境快照中的 TensorFlow、PyTorch 等大型依赖；原始清单位于 `reference/requirements.txt`，编码为 UTF-16，供团队核对课程环境。根目录的 `requirements.txt` 表示当前项目的实际依赖，不是老师环境的副本。

## 入口

老师框架实际调用 `Player().play_attacker(board)`、`Player().play_defender(board)`。`TeamXX.py` 已实现这两个方法，返回 `[[起点行, 起点列], [终点行, 终点列]]`。获得正式组号后重命名入口，并同步脚本和测试的导入。

`Tablut.py` 和 `Team00.py` 从补充 ZIP 原样复制；`reference/` 保存完整原始副本。直接运行 `python Tablut.py` 会调用老师的人工输入示例，需要键盘输入。自动对战请使用上面的 benchmark 命令。

## 详细说明

- [搭建清单与完成边界](docs/SETUP_LIST.md)
- [模块接口与数据约定](docs/INTERFACES.md)
- [三人分工与验收计划](docs/DEVELOPMENT_PLAN.md)

目前基线 Agent 直接调用合法走法生成器。尚未完成的接口使用 `NotImplementedError`，测试占位项标为 skip，不表示规则已验收。整局对战由老师框架负责捕获和终局判断。
