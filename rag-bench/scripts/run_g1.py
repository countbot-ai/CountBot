"""G1 实验：分块索引（本 PR）在同一批 60 题上与 G0 的 before/after 对比

与 run_g0.py 同一把尺子（同题、同语料、同指标口径），仅检索单元不同：
G0 = 文档级 BM25（整篇检索，改前），G1 = 分块级 BM25（backend/modules/rag，改后）。

输出：results/g1-detail.json + 控制台对比摘要。
"""

import json
import math
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent
REPO = Path(__file__).resolve().parents[2]              # 仓库根（含 backend/，从任意克隆位置可复现）

sys.path.insert(0, str(REPO))

from backend.modules.rag.stores import ChunkedBM25Index  # noqa: E402

TOP_K_EVAL = 10      # 评估口径
TOP_K_PROD = 6        # 生产镜像：ask 注入的块数（G0 生产是 top3 整篇）

def est_tokens(text: str) -> int:
    return int(len(text) / 1.5)

def load_questions():
    qs = [json.loads(l) for l in (BENCH / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    for q in qs:
        q["expected_pages"] = [p.replace(".md", "") for p in q["source_pages"]]
    return qs

def build_index():
    store = ChunkedBM25Index()
    manifest = json.load(open(BENCH / "corpus/manifest.json", encoding="utf-8"))
    for e in manifest:
        content = (BENCH / "corpus" / f"{e['slug']}.md").read_text(encoding="utf-8")
        store.add_document(e["slug"], e["title"], content, [e.get("section", "")])
    return store, len(manifest)

def main():
    questions = load_questions()
    print(f"[questions] {len(questions)}")
    store, n_docs = build_index()
    n_chunks = store.stats()["total_chunks"]
    print(f"[index] {n_docs} docs -> {n_chunks} chunks")

    detail = []
    for q in questions:
        results = store.search_chunks(q["question"], top_k=TOP_K_EVAL)
        top_slugs = [r["slug"] for r in results]

        # 生产镜像：top6 块注入（口径与 G0 相同的 header+content）
        prod = store.search_chunks(q["question"], top_k=TOP_K_PROD)
        prod_injection = sum(est_tokens(f"### {r['doc_title']} › {r['section']}\n{r['content']}") for r in prod)
        prod_slugs = [r["slug"] for r in prod]

        rec = {
            "id": q["id"],
            "type": q["type"],
            "semantic": q.get("semantic", False),
            "question": q["question"],
            "expected_pages": q["expected_pages"],
            "top10": [{"chunk_id": r["chunk_id"], "slug": r["slug"], "score": r["score"]} for r in results],
            "prod_top6_slugs": prod_slugs,
            "prod_top6_chunks": [r["chunk_id"] for r in prod],
            "prod_injection_tokens": prod_injection,
        }

        if q["type"] == "negative":
            rec["top1_score"] = results[0]["score"] if results else 0.0
        else:
            exp = q["expected_pages"]
            # 文档级命中（去重后按首次出现位置）
            first_rank = None
            for i, s in enumerate(top_slugs):
                if s in exp:
                    first_rank = i + 1
                    break
            rec["first_rank"] = first_rank
            rec["hit"] = first_rank is not None
            rec["all_source_hit"] = all(s in top_slugs for s in exp)
            # 生产口径命中：期望文档出现在注入的 top6 块中
            rec["prod_hit"] = any(s in prod_slugs for s in exp)
            # 跨文档：生产覆盖的源比例
            rec["prod_source_coverage"] = len([s for s in exp if s in prod_slugs]) / len(exp)
        detail.append(rec)

    # ---------- 汇总 ----------
    def group(pred):
        return [r for r in detail if pred(r)]

    summary = {}
    for name, rs in [
        ("S1 直接", lambda: group(lambda r: r["type"] == "single_doc" and not r["semantic"])),
        ("S1 语义", lambda: group(lambda r: r["type"] == "single_doc" and r["semantic"])),
        ("S3 针", lambda: group(lambda r: r["type"] == "needle")),
        ("S2 跨文档", lambda: group(lambda r: r["type"] == "cross_doc")),
    ]:
        rows = rs()
        n = len(rows)
        r5 = sum(1 for r in rows if r.get("first_rank") and r["first_rank"] <= 5)
        r10 = sum(1 for r in rows if r.get("first_rank") and r["first_rank"] <= 10)
        mrr = sum(1.0 / r["first_rank"] for r in rows if r.get("first_rank")) / n
        top1 = sum(1 for r in rows if r.get("first_rank") == 1) / n
        # NDCG@10（文档级，单相关文档：1/log2(rank+1)）
        ndcg = sum(1.0 / math.log2(r["first_rank"] + 1) for r in rows if r.get("first_rank")) / n
        inj = [r["prod_injection_tokens"] for r in rows]
        prod_hit = sum(1 for r in rows if r.get("prod_hit"))
        summary[name] = {
            "n": n, "recall@5": r5 / n, "recall@10": r10 / n, "MRR@10": mrr,
            "NDCG@10": ndcg, "top1": top1,
            "prod_hit@6": prod_hit / n,
            "prod_injection_mean": sum(inj) / n, "prod_injection_max": max(inj),
        }
        if name == "S2 跨文档":
            summary[name]["all_source_hit@10"] = sum(1 for r in rows if r.get("all_source_hit")) / n
            summary[name]["prod_source_coverage"] = sum(r["prod_source_coverage"] for r in rows) / n

    neg = group(lambda r: r["type"] == "negative")
    summary["S4 负样本"] = {
        "n": len(neg),
        "returned": sum(1 for r in neg if r["top10"]) / len(neg),
        "prod_injection_mean": sum(r["prod_injection_tokens"] for r in neg) / len(neg),
        "top1_score_max": max((r["top1_score"] for r in neg), default=0.0),
    }

    # 正样本总体注入（M1 验收：token 下降 >= 70%）
    pos = [r for r in detail if r["type"] != "negative"]
    summary["正样本总体"] = {
        "n": len(pos),
        "prod_injection_mean": sum(r["prod_injection_tokens"] for r in pos) / len(pos),
        "prod_injection_max": max(r["prod_injection_tokens"] for r in pos),
        "prod_hit@6": sum(1 for r in pos if r["prod_hit"]) / len(pos),
    }

    out = {"config": {"top_k_eval": TOP_K_EVAL, "top_k_prod": TOP_K_PROD,
                      "docs": n_docs, "chunks": n_chunks, "questions": len(questions)},
           "summary": summary, "detail": detail}
    (BENCH / "results/g1-detail.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n===== G1 分块索引摘要 =====")
    for name, s in summary.items():
        print(f"\n{name} (n={s['n']})")
        for k, v in s.items():
            if k != "n":
                print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")

if __name__ == "__main__":
    main()
