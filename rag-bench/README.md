# rag-bench — CountBot Wiki RAG 评测台

> 单一事实来源：所有指标数字以 `results/` 下的存档为准；口径以 `eval_config.yaml` 为准（改指标/改 k 值/换数据集都在那里改，实验卡片引用其版本号）。

## 目录结构

```
rag-bench/
├── questions.jsonl          # 术语集 60 题（S1 单文档25 / S2 跨文档15 / S3 针题10 / S4 负样本10）
├── questions-fuzzy.jsonl    # 口语集 30 题（cross_doc 15 / needle 10 / single_doc 5，刻意规避文档术语）
├── eval_config.yaml         # 评测口径（指标、k 值、数据集、门禁、provenance 要求）
├── requirements-eval.txt    # 评测专用依赖（ranx 等，不并入主 requirements.txt）
├── corpus/                  # 评测语料（fetch_corpus.py 可重抓，不入库）
├── data/                    # qrels（TREC）+ 落盘 runs（免重嵌重分析）
├── results/                 # 评测存档（每个 json/md 都对应一次可复现运行）
└── scripts/
    ├── fetch_corpus.py              # 抓取 countbot.cn/docs 全量 52 页
    ├── l1_eval.py                   # L1 检索评测：G1 BM25 / G2 纯向量 / G3 混合 / G4 混合+重排
    ├── run_crag_eval.py             # L2 端到端：v2 LLM judge（五分类）+ 拒答归因 + pairwise
    ├── run_g0.py / run_g1.py        # M0/M1 时期的文档级 vs 分块级对照（历史存档）
    ├── report_layer_gates.py        # 分层门禁报告（召回缺口 vs 排序缺口）
    └── gen_answer_chunk_annotations.py  # 答案块标注工作文件（qrels 收细用）
```

## 快速复用（三个场景）

### ① 检索层指标（程序化打分，零 LLM 成本，CI 可回归）

```bash
pip install -r requirements-eval.txt
python3 scripts/fetch_corpus.py

# 术语集：G1 基线 vs G4（混合+重排）
export COUNTBOT_RAG_EMBEDDING_BASE_URL=... COUNTBOT_RAG_EMBEDDING_API_KEY=...
export COUNTBOT_RAG_RERANK_BASE_URL=...     COUNTBOT_RAG_RERANK_API_KEY=...
python3 scripts/l1_eval.py --chunk-run G1 --rerank-run G4 --out results/l1-p2-rerank

# 口语集：三档递进（G1/G3/G4）
python3 scripts/l1_eval.py --chunk-run G1 --hybrid-run G3 --rerank-run G4 \
    --questions-jsonl ../questions-fuzzy.jsonl --out results/l1-fuzzy-bge
```

### ② 端到端（需要 LLM：被测模型 + judge 模型，建议 judge ≠ 被测）

```bash
# 基线存档（首次，产出 pairwise 对照锚点）
python3 scripts/run_crag_eval.py --base-url ... --api-key ... \
    --model <被测> --judge-model <judge> \
    --out ../results/crag-detail-v2-<tag>-baseline.json

# 对照运行（改检索配置后，pairwise 对照基线）
COUNTBOT_RAG_HYBRID=1 COUNTBOT_RAG_RERANK=1 ... python3 scripts/run_crag_eval.py \
    --baseline-json ../results/crag-detail-v2-<tag>-baseline.json \
    --out ../results/crag-detail-v2-<tag>-new.json
```

### ③ 已有 TREC runs 的免重嵌分析

```bash
python3 scripts/l1_eval.py --qrels <qrels.trec> --run TAG=path/to/run.trec
python3 scripts/report_layer_gates.py   # 召回缺口 vs 排序缺口分层归因
```

## 结果数字速查（明细见 results/ 各 summary.md）

| 指标 | G1 BM25 | G4 混合+重排 |
|---|---|---|
| 术语集 Hit@6 / MRR@6 | 0.8200 / 0.6473 | **0.9000 / 0.7000** |
| 口语集 Hit@6 / MRR@6 | 0.3333 / 0.1867 | **0.8333 / 0.5194** |
| 口语集端到端拒答率（正样本） | 57% | **3%** |
| 负样本拒答（防幻觉） | 10/10 | **10/10 不回退** |

## 评测纪律（踩坑换来，沿用至今）

1. **judge 模型与数据集版本一旦固定，跨 run 不可换**（provenance 必填，见 eval_config.yaml）；
2. **分数阈值类门控上线前必须做正负样本分离度冒烟**（置信门控因此被证伪禁用——负样本话题匹配块 rerank 分 0.9933 高于正样本 0.9046）；
3. **评测脚本必须有读超时**（无超时挂起 2 小时让已完成的 20 题全部作废过一次）；
4. **推理型 judge 的思考计入 max_tokens**（预算不足时 content 为空静默回退）；
5. **一次只改一处**（单变量原则），before/after 跑同一批题；
6. **门禁不达标即回退/记录**，"停在某一级也是有效结论"。
