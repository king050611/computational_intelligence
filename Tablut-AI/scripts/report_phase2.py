"""Summarize Phase 2 pilot evidence without pooling timing modes."""
from collections import Counter, defaultdict
import json
from pathlib import Path

from scripts.build_strategy_dataset import read_rows, symmetry


def main():
    data = Path("data/positions/phase2")
    stats = json.loads((data/"metrics.json").read_bytes())
    cases={s:read_rows(data/f"{s}_positions.jsonl") for s in ("development","regression","holdout")}
    seen_boards=set()
    seen_games=set()
    for split,rows in cases.items():
        boards={symmetry(r["board"],r["side"]) for r in rows}
        games={r["game_id"] for r in rows}
        assert len(boards)==len(rows) and not boards&seen_boards and not games&seen_games,split
        seen_boards|=boards
        seen_games|=games
    c=stats["categories"]
    games=read_rows(data/"exact_games.jsonl")
    new=[g for g in games if "/phase2_pilot/" in g["game_id"]]
    assert len(new)==8
    endings=defaultdict(Counter)
    for g in games:
        endings[g.get("mode","historical")][g["termination"] or "unknown"]+=1
    table="\n".join(f"| {mode} | {sum(tally.values())} | {tally.get('A',0)} | {tally.get('D',0)} | {tally.get('DRAW',0)} |"
                    for mode,tally in stats["modes"].items())
    splits="、".join(f"{s} {len(rows)}" for s,rows in cases.items())
    output=Path("reports/external_analysis")
    (output/"phase2_report.md").write_text(f"""
# V6 Phase 2 战略数据试验

## 来源和适用范围

外部对局导入数为 0。官网曾发布棋谱下载线索，本次无法核实下载、逐步证据及研究许可，因此暂停外部样本获取。按方案转入内部数据建设。B 类数据只能进入来源隔离的战略参考，现为空。规则及输入约定见[来源审计](source_reliability_report.md)。

内部核心数据集汇总 Phase 1 的完整记录及本轮新增 8 局，按行动与原始计时排查副本，再逐步复验新增棋谱。规则、正式 Bot 和遗传训练保持现状。实际复验拒绝数为 {len(stats['rejected'])}。

| 组别 | 局数 | 攻方胜 | 守方胜 | 平 |
| --- | ---: | ---: | ---: | ---: |
{table}

本轮每种模式 2 对开局并交换角色。选用迁移后的 V4 冠军对手工权重，标准模式深度上限 4，研究模式上限 5 且每步固定上限 30,000 搜索节点，仍有整局时间保护。研究模式单列。其余跨版本及深度组合仍待扩充。每局含前后棋盘、吃子、搜索得分、实际深度、节点、用时、可用时钟估计和记录到的主路径。重复历史可由初始棋盘和动作序列还原。

## 攻守与和棋证据

对局库的终局类型（按组）为 {dict(endings)}。攻方以规则确认的围捕终结为主要证据。守方则以规则确认的边缘逃生为证据。去重后的关键局面包含 {c.get('king_captured',0)} 个围捕终结、{c.get('king_escaped',0)} 个逃生终结、{c.get('avoidable_mate_in_one',0)} 个存在安全一手替代的直接败局。可验证的首要研究对象是遗漏下一手终结，而连续封锁、牺牲突破等长期模式仍需更大的样本。参考评价特征分布见[指标](../../data/positions/phase2/metrics.json)。

按课程规则区分重复终局及其他平局。保留的局面中主动重复 {c.get('active_repeat',0)} 个、被动重复 {c.get('passive_repeat',0)} 个。安全替代经过一步应手检查，未来仍可能失败，因此不能将它标为可强制转胜。人类对照和由此衍生的战略归因等待授权样本。

## 划分与复现

Phase 1 留出文件原样保留，并预留其来源棋局的镜像和旋转局面。Phase 2 以对局哈希按 70/15/15 分桶，再以八种棋盘对称及行动方全局去重。小样本的实际关键局面数为 {splits}。每条保存原始历史、实际走法、合法走法、V6 深度 4 建议和高预算参考结果。两个建议都有截止记录，启发式结果只作为分析证据。

产物位于 [规则兼容对局库](../../data/positions/phase2/exact_games.jsonl)、[标准限时回放](../../data/internal/standard_games/phase2_pilot/replay.html) 和 [高预算回放](../../data/internal/high_budget_games/phase2_pilot/replay.html)。用 python -m scripts.build_strategy_dataset --output NEW_OUTPUT 可重建数据集。授权 A 类导入结果可通过 --external 加入。
""".strip()+"\n",encoding="utf-8")
    print("Phase 2:",stats["games"],"games;",len(new),"fresh games;",splits)


if __name__=="__main__":
    main()
