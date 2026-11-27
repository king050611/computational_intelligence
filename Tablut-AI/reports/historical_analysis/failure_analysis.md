# 败局分析

有 496 局我方失败缺少可复验棋谱，战术原因记为 Unknown。完整棋谱核对了错失一步获胜、败方最后一次行动，以及当时是否存在能避开下一步即败的合法替代。早期指前 19 半步，中局指 20 至 59 半步，其后归为残局。下表列出关键局面数据集中保留的已证实失误。历史统计覆盖所有完整棋谱，数据集另按棋盘去除跨集合重复。

| 对局 ID | 半步 | 行动方 | 分类 | 合法替代数 |
| --- | ---: | --- | --- | ---: |
| 0063e55beccc3e3070abb7c3:1 | 14 | D | avoidable_mate_in_one, first_proven_error_in_checks | 35 |
| d6feba789d3b1b9154d9aff0:1 | 12 | D | avoidable_mate_in_one, first_proven_error_in_checks | 3 |
| 69984d08df9b29cc2bde4ab4:1 | 14 | D | avoidable_mate_in_one, first_proven_error_in_checks | 35 |
| 60c6ed9d342f8e49903d9eb7:2 | 37 | A | avoidable_mate_in_one, first_proven_error_in_checks | 2 |
| ffbf19195ee90f99950fab4c:2 | 37 | A | avoidable_mate_in_one, first_proven_error_in_checks | 2 |
| e8e715ca62a31ce30ff2e7cd:2 | 37 | A | avoidable_mate_in_one, first_proven_error_in_checks | 2 |
| ffbf19195ee90f99950fab4c:1 | 40 | D | avoidable_mate_in_one, first_proven_error_in_checks | 10 |
| e8e715ca62a31ce30ff2e7cd:1 | 40 | D | avoidable_mate_in_one, first_proven_error_in_checks | 10 |
| 0063e55beccc3e3070abb7c3:2 | 7 | A | avoidable_mate_in_one, first_proven_error_in_checks | 2 |
| 870d15ff34236b9a0fdbf1c0:1 | 42 | D | avoidable_mate_in_one, first_proven_error_in_checks | 1 |
| d6feba789d3b1b9154d9aff0:2 | 23 | A | avoidable_mate_in_one, first_proven_error_in_checks | 3 |

局面原始选择、评分、替代走法和历史位于 data/positions。参考搜索注明时间、节点预算和实际完成深度。缺乏证据的评价失误、深度不足和缓存历史成因仍为 Unknown。见 [统计](root_cause_statistics.csv)。
