"""Summarize only completed direction-A confirmation matches."""
from pathlib import Path
from collections import Counter
import hashlib,json,re,zipfile
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent

def describe(data):
    rows=data['results']; own=[];control=[]
    for row in rows:
        own.extend(x for x in row['search_stats'][row['our_side']] if x)
        control.extend(x for x in row['search_stats']['D' if row['our_side']=='A' else 'A'] if x)
    def search(records):
        return {'moves':len(records),'mean_depth':sum(x['completed_depth'] for x in records)/len(records),'mean_nodes':sum(x['nodes'] for x in records)/len(records),'elapsed_seconds':sum(x['elapsed_seconds'] for x in records),'fallbacks':sum(x['fallback_used'] for x in records)}
    pairs={}
    for row in rows:
        key=str(row['opening_id']);pairs.setdefault(key,[]).append({'game':row['game'],'side':row['our_side'],'winner':row['winner'],'points':row['points'],'plies':row['plies']})
    return {'standings':data['standings'],'issues':{k:sum(r[k] for r in rows) for k in ('illegal_moves','timeouts','exceptions','invalid_returns')},'max_player_seconds':max(max(r['attacker_seconds'],r['defender_seconds']) for r in rows),'own_search':search(own),'control_search':search(control),'repetition_draws':sum(r['winner']=='DRAW' and 'Repeated position' in r['log'] for r in rows),'pairs':pairs,'double_loss_pairs':[k for k,v in pairs.items() if len(v)==2 and sum(x['points'] for x in v)==0]}

def main():
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'));assert manifest['status']=='complete'
    data=json.loads((OUT/'result.json').read_text(encoding='utf-8'));summary=json.loads((OUT/'result.summary.json').read_text(encoding='utf-8'))
    old=json.loads((ROOT/'reports/experiments/evolution_quick_20261125/validation.json').read_text(encoding='utf-8'))
    metrics=describe(data);metrics['paired']=summary;metrics['previous_quick']=describe(old);metrics['manifest']=manifest
    assert data['games']==40 and all(v==0 for v in metrics['issues'].values())
    (OUT/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    row=metrics['standings']['overall'];oldrow=old['standings']['overall'];ci=summary['ci95'];rate=summary['point_rate']
    conclusion=('这20对开局中的结果支持该候选落后于手工模型，但不能推广为遗传算法整体无效。' if ci[1]<0.5 else '区间仍包含50%，尚不足以认定存在稳定劣势或优势。' if ci[0]<=0.5 else '这20对开局显示了优势迹象，但仍需全新留出验证，不能直接晋级。')
    roles='\n'.join(f"| {label} | {metrics['standings'][side]['wins']} / {metrics['standings'][side]['draws']} / {metrics['standings'][side]['losses']} | {metrics['standings'][side]['points']}/{2*metrics['standings'][side]['games']} | {metrics['standings'][side]['points']/(2*metrics['standings'][side]['games']):.2%} |" for side,label in [('attacker','我方执攻'),('defender','我方执守')])
    searchrows='\n'.join(f"| {label} | {metrics[key]['moves']} | {metrics[key]['mean_depth']:.3f} | {metrics[key]['mean_nodes']:.0f} | {metrics[key]['elapsed_seconds']:.2f} | {metrics[key]['fallbacks']} |" for key,label in [('own_search','遗传候选'),('control_search','手工对照')])
    text=f'''\n\n---

# 追加验证：20对独立开局确认（方向A）

本节为先前8局快速检查之后的独立新实验，未重新训练，未更改权重、核心算法或正式Bot。对应基准`{manifest['source_commit']}`。

## 主要结果

原候选对手工Enhanced Dynamic完成**40局：{row['wins']}胜、{row['draws']}平、{row['losses']}负，{row['points']}/80分，积分率{rate:.2%}**。按20对开局重采样10,000次得到配对95%区间**{ci[0]:.2%}–{ci[1]:.2%}**。{conclusion}

| 数据集 | 对局数 | 胜 / 平 / 负 | 积分率 |
| --- | --- | --- | --- |
| 先前4对快测，Seed85261 | 8 | {oldrow['wins']} / {oldrow['draws']} / {oldrow['losses']} | {oldrow['points']/16:.2%} |
| 本次20对确认，Seed61827 | 40 | {row['wins']} / {row['draws']} / {row['losses']} | {rate:.2%} |

两个数据集分别报告，本次区间只来自新增40局，不把不同规模数据混在一起后再挑有利结论。积分率不是胜率。4对开局得到的31.25%只是初步点估计，扩大验证后的结果可能变化。

## 控制条件与隔离

使用原candidate.json的逐字节副本，SHA256为`{manifest['candidate_sha256']}`，赛后校验原文件和副本均未改变。新开局Seed61827、20对，与8对训练开局及此前4对验证开局交集均为0，检查发生在比赛之前，见[隔离记录](experiments/evolution_confirm/split_audit.json)。

双方最大深度4、走法提示20,000、排序开启、相同六特征接口和动态时间管理、整局60秒及5秒预留；每个开局交换攻守。候选没有完成一代正式进化，这仍是原初始种群候选的确认实验，不是多代遗传训练结果。

实际命令：

```powershell
python scripts/generate_openings.py --pairs 20 --seed 61827 --output reports/experiments/evolution_confirm/openings.json
python scripts/run_experiments.py --strategy evolutionary_dynamic --model reports/experiments/evolution_confirm/candidate_snapshot.json --opponent enhanced_dynamic --openings reports/experiments/evolution_confirm/openings.json --max-depth 4 --tt-capacity 20000 --record-search --output reports/experiments/evolution_confirm/result.json
```

## 攻守与稳定性

| 身份 | 胜 / 平 / 负 | 积分 | 积分率 |
| --- | --- | --- | --- |
{roles}

非法走法{metrics['issues']['illegal_moves']}、整局超时{metrics['issues']['timeouts']}、异常{metrics['issues']['exceptions']}、非法返回{metrics['issues']['invalid_returns']}。单方整局最高累计{metrics['max_player_seconds']:.3f}秒；新增对局中重复局面平局{metrics['repetition_draws']}局。

| 搜索方 | 动作数 | 平均完成深度 | 平均节点/步 | 累计计算秒数 | 回退步数 |
| --- | --- | --- | --- | --- | --- |
{searchrows}

搜索统计来自本次真实记录；完成深度不等于目标深度，单步截止回退不等于超出整局时限。不同算法路径会造成不同局面，不能只凭节点数判断计算效率或认定失败原因。

## 结果解释与后续范围

双方换边均判负的开局编号：{', '.join(metrics['double_loss_pairs']) or '无'}。完整配对结果、时间与搜索信息见[指标JSON](experiments/evolution_confirm/metrics.json)及[原始40局记录](experiments/evolution_confirm/result.json)。本次Benchmark仍没有完整逐步棋盘，不能从汇总数据定位具体哪一步战术失误。

W4为正、W5为负与通常战略直觉存在冲突，这仍然只是研究假设。本次没有权重消融，不能把结果归因于这两个符号。约束遗传算法会改变搜索空间，可能有帮助，也可能排除有用的特征交互，需另作公平实验。

本轮只执行方向A的确认验证。没有进行方向B的符号约束改造、没有追加遗传训练、没有运行ED1–ED6，也没有自动修改正式Bot。下一步可围绕Enhanced Dynamic参数对照，或在单独开发实验中比较约束与无约束权重；不凭当前候选强制晋级，也不把一次候选实验推广为整个遗传算法无效。

完整命令及耗时见[运行清单](experiments/evolution_confirm/manifest.json)，新增40局归档见[confirmation_bundle.zip](experiments/evolution_confirm/confirmation_bundle.zip)。全部保存本地，不提交或推送Git。
'''
    report=ROOT/'reports/EVOLUTIONARY_REVIEW.md';previous=report.read_text(encoding='utf-8');assert '# 追加验证：20对独立开局确认（方向A）' not in previous
    report.write_text(previous+text,encoding='utf-8')
    files=[p for p in OUT.iterdir() if p.is_file() and p.name not in ('confirmation_bundle.zip','bundle_manifest.json')]+[report]
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files};(OUT/'bundle_manifest.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    with zipfile.ZipFile(OUT/'confirmation_bundle.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in files+[OUT/'bundle_manifest.json']:z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(OUT/'confirmation_bundle.zip') as z:
        assert z.testzip() is None
        for name,sha in hashes.items():assert hashlib.sha256(z.read(name)).hexdigest()==sha
    print('RESULT',json.dumps(row),'POINT_RATE',rate,'CI95',ci,'ISSUES',metrics['issues'])
    print('REPORT',report)
if __name__=='__main__':main()
