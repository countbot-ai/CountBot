# 分层门禁报告（Phase 1 检索层）

- 口径：块级 qrels（source_pages → 全部块），top-6 / top-50
- 正题 49（已去重：排除 dup_of）；评测 run 来自 l1-g123-bge-runs

| 题型 | n | G1 hit@6 | G2 hit@6 | G3 hit@6 | G1 召回缺口 | G2 召回缺口 | G3 召回缺口 | G1 排序缺口 | G2 排序缺口 | G3 排序缺口 |
|---|---|---|---|---|---|---|---|---|---|---|
| 全部 | 49 | 41/49 = 83.7% | 43/49 = 87.8% | 40/49 = 81.6% | 4 | 0 | 0 | 4 | 6 | 9 |
| single_doc | 25 | 19/25 = 76.0% | 19/25 = 76.0% | 18/25 = 72.0% | 3 | 0 | 0 | 3 | 6 | 7 |
| cross_doc | 15 | 13/15 = 86.7% | 15/15 = 100.0% | 13/15 = 86.7% | 1 | 0 | 0 | 1 | 0 | 2 |
| needle | 9 | 9/9 = 100.0% | 9/9 = 100.0% | 9/9 = 100.0% | 0 | 0 | 0 | 0 | 0 | 0 |

## 逐题（* 表示该 run top6 命中；G 缺口：recall/rank/-）

| qid | type | G1 | G2 | G3 | 缺口(G1→G3) |
| S1-01 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-02 | single_doc | False | True | False | G1=recall G2=- G3=rank |
| S1-03 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-04 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-05 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-06 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-07 | single_doc | True | False | False | G1=- G2=rank G3=rank |
| S1-08 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-09 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-10 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-11 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-12 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-13 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-14 | single_doc | False | True | True | G1=rank G2=- G3=- |
| S1-15 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-16 | single_doc | False | False | False | G1=recall G2=rank G3=rank |
| S1-17 | single_doc | False | False | False | G1=recall G2=rank G3=rank |
| S1-18 | single_doc | False | False | False | G1=rank G2=rank G3=rank |
| S1-19 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-20 | single_doc | True | False | True | G1=- G2=rank G3=- |
| S1-21 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-22 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-23 | single_doc | False | True | False | G1=rank G2=- G3=rank |
| S1-24 | single_doc | True | True | True | G1=- G2=- G3=- |
| S1-25 | single_doc | True | False | False | G1=- G2=rank G3=rank |
| S2-01 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-02 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-03 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-04 | cross_doc | False | True | False | G1=rank G2=- G3=rank |
| S2-05 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-06 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-07 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-08 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-09 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-10 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-11 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-12 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-13 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S2-14 | cross_doc | False | True | False | G1=recall G2=- G3=rank |
| S2-15 | cross_doc | True | True | True | G1=- G2=- G3=- |
| S3-01 | needle | True | True | True | G1=- G2=- G3=- |
| S3-02 | needle | True | True | True | G1=- G2=- G3=- |
| S3-03 | needle | True | True | True | G1=- G2=- G3=- |
| S3-04 | needle | True | True | True | G1=- G2=- G3=- |
| S3-05 | needle | True | True | True | G1=- G2=- G3=- |
| S3-06 | needle | True | True | True | G1=- G2=- G3=- |
| S3-08 | needle | True | True | True | G1=- G2=- G3=- |
| S3-09 | needle | True | True | True | G1=- G2=- G3=- |
| S3-10 | needle | True | True | True | G1=- G2=- G3=- |
