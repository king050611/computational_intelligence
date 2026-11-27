"""Produce the Phase 1 review from collected games and the timed validation."""
from collections import Counter
import json
from pathlib import Path
from random import Random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark import standings

OUT = ROOT/"reports/historical_analysis"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

def write(name, text):
    (OUT/name).write_text(text.strip()+"\n", encoding="utf-8")

def outcome(row):
    return "平" if row["winner"]=="DRAW" else "胜" if row["winner"]==row["our_side"] else "负"

def main():
    corpus=read(OUT/"dataset_manifest.json")
    pos=read(OUT/"position_metrics.json")
    match_dir=OUT/"paired_validation"
    names={"draw_v5_order":"V5 同分降序", "draw_v6_order":"V6 和棋策略",
           "feature_full":"W7/W8 均启用", "feature_without_w7":"W7 置零", "feature_without_w8":"W8 置零"}
    games={name:read_rows(match_dir/f"{name}.jsonl") for name in names}
    assert all(len(rows)==(8 if name.startswith("draw") else 4) for name,rows in games.items())
    metrics={}
    for name,rows in games.items():
        table=standings(rows)
        total=table["overall"]
        metrics[name]=dict(standings=table, rate=total["points"]/(2*total["games"]),
                           repeat=sum(r["result"]["reason"]=="repetition" for r in rows),
                           faults=sum(r["fault"] for r in rows),
                           max_seconds=max(max(r["attacker_seconds"],r["defender_seconds"]) for r in rows))
    old,new=({(g["opening_id"],g["our_side"]):g for g in games[name]} for name in list(names)[:2])
    assert old.keys()==new.keys()
    turns=Counter((outcome(old[k]),outcome(new[k])) for k in old)
    deltas=[sum(new[i,s]["points"]-old[i,s]["points"] for s in ("A","D"))/4 for i in sorted({i for i,_ in old})]
    rng=Random(42)
    samples=sorted(sum(rng.choices(deltas,k=len(deltas)))/len(deltas) for _ in range(10_000))
    gain=sum(deltas)/len(deltas)
    ci=[samples[250],samples[9750]]
    evidence=(turns["平","胜"]>turns["平","负"] and gain>0 and
              metrics["draw_v6_order"]["standings"]["overall"]["losses"]<=
              metrics["draw_v5_order"]["standings"]["overall"]["losses"])
    decision=("此次观察到值得扩大验证的信号，策略保留为显式选项。" if evidence else
              "本轮结果不足以支持默认启用 V6 和棋策略，保留为显式实验选项。")
    (match_dir/"metrics.json").write_text(json.dumps(dict(
        matches=metrics, transition={a+"→"+b:n for (a,b),n in turns.items()},
        paired_point_rate_change=gain, exploratory_ci95=ci), ensure_ascii=False, indent=2), encoding="utf-8")
    ver="\n".join(f"| {v} | {q.get('complete',0)} | {q.get('summary_only',0)} | {q.get('invalid',0)} |"
                  for v,q in corpus["version_quality"].items())
    write("data_quality_report.md",f"""
# 历史数据质量

扫描训练、实验、回放、检查点、日志和 ZIP 归档，共 {len(corpus['source_inventory'])} 个本地来源（含 Git 对象历史）。按赛程时间戳和完整逐局内容归并了 {corpus['copied_game_rows']} 条副本记录。{len(corpus['partial_logs'])} 个只留下部分日志的批次保留在数据清单中。论文 RAR 目录只有 PDF。原始文件完整保留。

| 版本 | 完整棋谱 | 仅赛果或搜索统计 | 无效 |
| --- | ---: | ---: | ---: |
{ver}

完整棋谱逐步复验合法性、棋盘及终局。缺少权重、提交哈希、逐步得分或搜索深度的字段留空。算法版本来自明确的实验目录标识，线性和早期日志单列，Benchmark schema 不作为算法版本。训练记录能匹配检查点时标记已归档，已中止的批次单列。见 [数据清单](dataset_manifest.json)、[对局 JSONL](historical_games.jsonl) 和 [跨版本分层表](version_comparison.csv)。
""")
    table=[]
    for name,m in metrics.items():
        t=m["standings"]["overall"]; a=m["standings"]["attacker"]; d=m["standings"]["defender"]
        table.append(f"| {names[name]} | {t['wins']}/{t['draws']}/{t['losses']} | {m['rate']:.1%} | "
                     f"{a['points']}/{2*a['games']} | {d['points']}/{2*d['games']} | {m['repeat']} | {m['max_seconds']:.2f} | {m['faults']} |")
    types=pos["drawn_positions"]; cat=pos["categories"]
    write("draw_analysis.md",f"""
# 和棋分析与策略对照

历史完整棋谱中查到主动重复 {cat.get('active_repeat',0)} 例、被动重复 {cat.get('passive_repeat',0)} 例。以迁移后的 V4 权重和 ±25 分静态阈值区分，优势代理 {types.get('advantage_proxy',0)} 局、均势代理 {types.get('balanced_proxy',0)} 局、劣势代理 {types.get('disadvantage_proxy',0)} 局。代理只说明局面静态评分的位置。仅有赛果的重复和棋不能确定由哪一方触发。

V6 在优势局面限时验证对手的一步重复应手，并据此优先搜索重复风险较低的走法。原始极小极大评分和胜利距离决定棋力选择。劣势时优先搜索已确认的重复求和。保留全部合法走法，重复按裁判记零分，未完成扫描有独立标记。

| 实验 | 胜/平/负 | 2:1:0 积分率 | 攻方积分 | 守方积分 | 重复和棋 | 最高单方秒数 | 违规局 |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: |
{chr(10).join(table)}

前两组采用共同修复后的深度 4 搜索、迁移 V4 权重、相同的 4 对全新开局和同一个对手。只切换和棋排序。对应同开局同角色的 **平转胜 {turns['平','胜']} 局、平转负 {turns['平','负']} 局**。积分率差 {gain:+.1%}，按开局配对重采样区间 {ci[0]:+.1%} 至 {ci[1]:+.1%}。{decision}

后三组是另一套 2 对开局上的特征消融。W7/W8 的 −80 是预设探测权重。完整与单项归零各赛 4 局，样本不足以确认特征的棋力贡献。所有对战沿用官方 60 秒规则，程序保存每步棋盘、时间和评估统计。见 [逐局指标](paired_validation/metrics.json)、[原排序棋谱](paired_validation/draw_v5_order/replay.html) 和 [V6 棋谱](paired_validation/draw_v6_order/replay.html)。
""")
    cases=[]
    for split in ("development","regression","holdout"):
        cases.extend(read_rows(ROOT/f"data/positions/{split}_positions.jsonl"))
    examples="\n".join(f"| {c['game_id']} | {c['ply']} | {c['side']} | {', '.join(c['categories'])} | {len(c['alternatives'])} |"
                        for c in cases if "first_proven_error_in_checks" in c["categories"])
    write("failure_analysis.md",f"""
# 败局分析

有 {pos['unknown_summary_losses']} 局我方失败缺少可复验棋谱，战术原因记为 Unknown。完整棋谱核对了错失一步获胜、败方最后一次行动，以及当时是否存在能避开下一步即败的合法替代。早期指前 19 半步，中局指 20 至 59 半步，其后归为残局。下表列出关键局面数据集中保留的已证实失误。历史统计覆盖所有完整棋谱，数据集另按棋盘去除跨集合重复。

| 对局 ID | 半步 | 行动方 | 分类 | 合法替代数 |
| --- | ---: | --- | --- | ---: |
{examples or '| — | — | — | 未发现 | — |'}

局面原始选择、评分、替代走法和历史位于 data/positions。参考搜索注明时间、节点预算和实际完成深度。缺乏证据的评价失误、深度不足和缓存历史成因仍为 Unknown。见 [统计](root_cause_statistics.csv)。
""")
    patterns="\n".join(f"| {name} | {p['n']} | " + " | ".join(f"{p['mean_features'][i]:.3f}" for i in (0,1,4,5,7)) + " |"
                       for name,p in pos["winning_patterns"].items())
    write("winning_patterns.md",f"""
# 获胜棋谱

| 终结方式 | 例数 | 包围压力 | 直接逃生 | 国王行动力 | 通道封锁 | 一步捕获威胁 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{patterns}

均值取终结走法前的局面。围捕通过规则模拟确认走子与支援，逃生通过合法边缘落点确认。只有记录了真实完成深度的旧棋谱才计入深度证据。由于 V1–V5 主实验缺逐步棋盘，无法将历史胜局战术归因到具体版本的权重。见 [局面统计](position_metrics.json)。
""")
    write("optimisation_priorities.md",f"""
# 优化优先级

1. 修复跨历史缓存。冻结 V5 在同一棋盘先得到并缓存 50 分，再换成会重复的历史时仍返回 50 分。关闭缓存得到正确的 0 分。V6 用完整祖先状态集合约束分数缓存。
2. 修复全面封锁时的逃生距离与城堡周边一步围捕识别，保留真实胜负和 60 秒边界。
3. 按和棋转换评估搜索优先级。{decision}
4. W7/W8 小样本消融已运行。完整棋力验证仍是开启遗传训练的前置条件。
""")
    splits="\n".join(f"| {k} | {m['positions']} | {m['games']} | {m['references']} |" for k,m in pos["splits"].items())
    q=corpus["quality"]
    depth_samples=[]
    opened=set()
    depth_root=ROOT/"reports/experiments/v5_depth_study_20261130"
    for result in sorted(depth_root.glob("*depth[456].json")):
        payload=read(result)
        stats=payload["standings"]["overall"]
        metadata=payload["manifest"]
        opened.add((metadata["openings_sha256"],metadata["model_sha256"]["model"],payload["opponent"]))
        depth_samples.append(f"| {metadata['options']['max_depth']} | {stats['wins']}/{stats['draws']}/{stats['losses']} | {stats['points']/(2*stats['games']):.1%} |")
    assert len(opened)<=1
    depth_table="\n".join(depth_samples)
    write("historical_analysis_report.md",f"""
# V6 Phase 1 历史棋谱与和棋策略

V5 自 ff7e4c5 冻结。V3/V4 对照源码保留校验信息。V4 冠军六权重原样迁移到 Schema 2，W7/W8 初始化为零。见 [冻结清单](frozen_baselines.json)。

去重后有 **{q.get('complete',0)} 局完整棋谱、{q.get('summary_only',0)} 局仅有赛果或搜索统计、{q.get('invalid',0)} 局无效**，另存 {len(corpus['partial_logs'])} 个未完成日志批次。分析按对手、搜索配置、阶段和攻守分层。V1–V5 主实验缺少完整棋谱，战术错误率和优势转化率不能可靠跨版本比较。见 [数据质量](data_quality_report.md) 和 [版本对照](version_comparison.csv)。

| 局面划分 | 记录数 | 来源局数 | 较高预算参考 |
| --- | ---: | ---: | ---: |
{splits}

开发、回归和历史留出按对局分组，并清除跨集合重复的棋盘与行动方。计时对照另外生成全新开局。见 [败局](failure_analysis.md)、[和棋](draw_analysis.md)、[胜局](winning_patterns.md) 和 [优先级](optimisation_priorities.md)。

## 历史深度对照

V5 存档中深度 4、5、6 各 40 局使用相同开局文件、相同冠军和相同冻结 V3 对手。该组的深度 5 积分最高，深度 6 回落，说明增加上限未必改善实际计时成绩。

| 深度上限 | 胜/平/负 | 官方积分率 |
| --- | --- | ---: |
{depth_table}

完成 28 局计时对照，包括 16 局和棋策略比较及 12 局两项特征消融。{decision} 遗传训练继续等待独立棋力收益证据。完整回归测试见 [测试日志](tests.log)，实验开关和复现方法见 [实验指南](../../docs/EXPERIMENT_GUIDE.md)。
""")
    print(json.dumps(dict(metrics=metrics,gain=gain,ci=ci,transitions={a+"→"+b:n for (a,b),n in turns.items()}),ensure_ascii=True))

if __name__=="__main__":
    main()
