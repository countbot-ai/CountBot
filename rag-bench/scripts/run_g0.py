#!/usr/bin/env python3
"""G0 基线：测量 CountBot 现状 BM25 文档级检索在 60 题问题集上的表现。

口径：纯程序化打分（recall@k / MRR@10 / NDCG@10 / top1 / 注入 token 量），无 LLM 判分，可直接复现。
指标：
  - S1/S3（单文档）: recall@5/10, MRR@10, NDCG@10
  - S2（跨文档）:   全源 recall@10, primary MRR@10, 平均源覆盖率
  - S4（负样本）:   得分分布（top1 score），与非负样本对比
  - token 注入（镜像生产 top_k=3, _handle_ask 整篇拼接）: est tokens 注入量
est_tokens = chars / 1.5（CJK 近似）。
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent          # rag-bench/
REPO = Path(__file__).resolve().parents[2]              # 仓库根（含 backend/，从任意克隆位置可复现）
INDEX_PY = REPO / "backend/modules/wiki/index.py"

NO_JIEBA = "--no-jieba" in sys.argv  # 模拟生产默认环境（requirements.txt 中 jieba 被注释）

# ---- 加载 worktree 的 BM25Index（不 import 整个 backend）----
spec = importlib.util.spec_from_file_location("cb_bm25_index", INDEX_PY)
mod = importlib.util.module_from_spec(spec)
sys.modules["cb_bm25_index"] = mod
spec.loader.exec_module(mod)
BM25Index = mod.BM25Index

if NO_JIEBA:
    # 强制走降级路径（单字分词）：_jieba 为 falsy 且非 None 时 _load_jieba 直接 return
    BM25Index._jieba = False
    assert BM25Index.tokenize("测试分词") == list("测试分词"), "no-jieba mode failed"

# ---- 建索引：corpus manifest + md 文件 ----
manifest = json.loads((BENCH / "corpus/manifest.json").read_text(encoding="utf-8"))
index = BM25Index()
docs = {}  # slug -> {title, content, chars, est_tokens}
for entry in manifest:
    slug = entry["slug"]
    p = BENCH / "corpus" / f"{slug}.md"
    content = p.read_text(encoding="utf-8")
    docs[slug] = {
        "title": entry["title"],
        "content": content,
        "chars": entry["chars"],
        "est_tokens": entry["est_tokens"],
    }
    index.add_document(slug, entry["title"], content)

print(f"[index] {len(docs)} docs loaded")

questions = [json.loads(l) for l in (BENCH / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
print(f"[questions] {len(questions)} questions")

# manifest slug 不含 .md 后缀（如 core/memory）；questions.jsonl 的 source_pages 带 .md，统一去掉
def to_slug(page: str) -> str:
    return page[:-3] if page.endswith(".md") else page

for q in questions:
    q["source_pages"] = [to_slug(p) for p in q["source_pages"]]

TOP_K_EVAL = 10   # 评估口径
TOP_K_PROD = 3    # 生产口径（wiki/tool.py _handle_ask）


def est_tokens(text: str) -> int:
    return int(len(text) / 1.5)


def prod_injection(results) -> int:
    """镜像生产行为：每个命中文档全文 `### {title}\\n{content}` 拼接进 prompt。"""
    total = 0
    for slug, _score in results:
        d = docs.get(slug)
        if d:
            total += est_tokens(f"### {d['title']}\n{d['content']}")
    return total


def dcg(rels):
    return sum(r / math.log2(i + 2) for i, r in enumerate(rels))


detail = []
agg = {
    "single": {"n": 0, "rec5": 0, "rec10": 0, "mrr10": 0, "ndcg10": 0, "top1": 0},
    "semantic": {"n": 0, "rec5": 0, "rec10": 0, "mrr10": 0, "ndcg10": 0, "top1": 0},
    "needle": {"n": 0, "rec5": 0, "rec10": 0, "mrr10": 0, "ndcg10": 0, "top1": 0},
    "cross": {"n": 0, "all_source_rec10": 0, "primary_mrr10": 0, "avg_coverage": 0.0,
              "avg_sources": 0, "primary_top1": 0},
    "negative": {"n": 0, "scores": [], "returned": 0},
}

for q in questions:
    qid, qtype = q["id"], q["type"]
    eval_results = index.search(q["question"], top_k=TOP_K_EVAL)
    prod_results = index.search(q["question"], top_k=TOP_K_PROD)
    eval_slugs = [s for s, _ in eval_results]

    rec = {"id": qid, "type": qtype, "semantic": q["semantic"],
           "question": q["question"], "expected_pages": q["source_pages"],
           "top10": [{"slug": s, "score": round(sc, 3)} for s, sc in eval_results],
           "prod_top3_slugs": [s for s, _ in prod_results],
           "prod_injection_tokens": prod_injection(prod_results)}

    if qtype in ("single_doc", "needle"):
        src = q["source_pages"][0]
        if src in eval_slugs:
            rank = eval_slugs.index(src) + 1
            rec["rank"] = rank
            rec["hit"] = True
        else:
            rank = None
            rec["hit"] = False
        bucket = agg["semantic" if q["semantic"] else ("needle" if qtype == "needle" else "single")]
        bucket["n"] += 1
        if rank:
            bucket["rec5"] += 1 if rank <= 5 else 0
            bucket["rec10"] += 1
            bucket["mrr10"] += 1.0 / rank
            bucket["ndcg10"] += 1.0 / (1 + math.log2(rank))  # 单相关文档的二值 NDCG
            bucket["top1"] += 1 if rank == 1 else 0

    elif qtype == "cross_doc":
        srcs = q["source_pages"]
        hits = [s for s in srcs if s in eval_slugs]
        primary = srcs[0]
        p_rank = (eval_slugs.index(primary) + 1) if primary in eval_slugs else None
        rec["hit_sources"] = hits
        rec["missed_sources"] = [s for s in srcs if s not in hits]
        rec["primary_rank"] = p_rank
        b = agg["cross"]
        b["n"] += 1
        b["all_source_rec10"] += 1 if len(hits) == len(srcs) else 0
        b["primary_mrr10"] += (1.0 / p_rank) if p_rank else 0.0
        b["avg_coverage"] += len(hits) / len(srcs)
        b["avg_sources"] += len(srcs)
        b["primary_top1"] += 1 if p_rank == 1 else 0

    elif qtype == "negative":
        b = agg["negative"]
        b["n"] += 1
        top1_score = eval_results[0][1] if eval_results else 0.0
        b["scores"].append(round(top1_score, 3))
        b["returned"] += 1 if eval_results else 0
        rec["top1_score"] = round(top1_score, 3)
        rec["returned_any"] = bool(eval_results)

    detail.append(rec)

# ---- 负样本 vs 非负样本 top1 分数对比（S4 的核心观察）----
nonneg_top1 = []
for q, r in zip(questions, detail):
    if q["type"] != "negative" and r["top10"]:
        nonneg_top1.append(r["top10"][0]["score"])

neg_scores = agg["negative"]["scores"]

def stats(xs):
    if not xs:
        return {"n": 0}
    xs2 = sorted(xs)
    return {"n": len(xs), "mean": round(sum(xs)/len(xs), 2),
            "median": round(xs2[len(xs2)//2], 2),
            "min": round(xs2[0], 2), "max": round(xs2[-1], 2)}

# S1/S3 生产 token 注入统计（正样本部分）
inj_pos = [r["prod_injection_tokens"] for r in detail if r["type"] != "negative"]
inj_neg = [r["prod_injection_tokens"] for r in detail if r["type"] == "negative"]

summary = {}
for k in ("single", "semantic", "needle"):
    b = agg[k]
    n = b["n"] or 1
    summary[k] = {
        "n": b["n"],
        "recall@5": round(b["rec5"]/n, 3),
        "recall@10": round(b["rec10"]/n, 3),
        "MRR@10": round(b["mrr10"]/n, 3),
        "NDCG@10": round(b["ndcg10"]/n, 3),
        "top1_acc": round(b["top1"]/n, 3),
    }
b = agg["cross"]
n = b["n"] or 1
summary["cross"] = {
    "n": b["n"],
    "avg_sources_per_q": round(b["avg_sources"]/n, 2),
    "all_source_recall@10": round(b["all_source_rec10"]/n, 3),
    "primary_MRR@10": round(b["primary_mrr10"]/n, 3),
    "primary_top1": round(b["primary_top1"]/n, 3),
    "avg_source_coverage@10": round(b["avg_coverage"]/n, 3),
}
summary["negative"] = {
    "n": agg["negative"]["n"],
    "returned_any": agg["negative"]["returned"],
    "top1_score_stats": stats(neg_scores),
    "nonneg_top1_score_stats": stats(nonneg_top1),
}
summary["prod_injection"] = {
    "note": "镜像 wiki/tool.py _handle_ask: top_k=3 整篇文档拼接, est_tokens=chars/1.5",
    "positive_qs": stats(inj_pos),
    "negative_qs": stats(inj_neg),
    "corpus_total_est_tokens": sum(d["est_tokens"] for d in docs.values()),
    "top3_injection_ratio_of_corpus": round((sum(inj_pos)/len(inj_pos)) / sum(d["est_tokens"] for d in docs.values()), 4) if inj_pos else None,
}

out = {"config": {"top_k_eval": TOP_K_EVAL, "top_k_prod": TOP_K_PROD,
                  "docs": len(docs), "questions": len(questions), "no_jieba": NO_JIEBA},
       "summary": summary, "detail": detail}
(BENCH / "results").mkdir(exist_ok=True)
suffix = "-nojieba" if NO_JIEBA else ""
(BENCH / f"results/g0{suffix}-detail.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1))

# ---- 控制台快速诊断：未命中的题 ----
print("\n== misses ==")
for r in detail:
    if r["type"] in ("single_doc", "needle") and not r["hit"]:
        print(f"  MISS {r['id']}: {r['question'][:40]}... expected={r['expected_pages']}")
    elif r["type"] == "cross_doc" and r.get("missed_sources"):
        print(f"  PART {r['id']}: missed {r['missed_sources']}")
