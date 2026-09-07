#!/usr/bin/env python3
"""生成"答案块标注"工作文件（供人工复核后落盘为块级 qrels 的收细依据）

背景：当前块级 qrels = source_pages 全部块都 relevant，
块数多的文档天然更好中 → hit@6 对"小文档"偏送分、难易失真（基线 0.82 偏高）。
业界收细做法：每题只标"真正包含答案的块"（answer chunks）。

本脚本不做主观判定，只做两件事：
  1. 逐题从 G3 混合 run 的 top 命中里，预填候选答案块（属于 source_pages 的块）；
     G3 无命中时回退 G2/G1；全部无命中 → 标 missing（这类题正是"召回缺口"，
     需要标注人从全文人工定位答案）。
  2. 输出 rag-bench/data/answer-chunk-annotations.jsonl 供人工复核：
     标注人仅需把每题 answer_chunk_ids 从候选（可增删）确认为真正的答案块。

用法：
  python gen_answer_chunk_annotations.py \
      --questions ../questions.jsonl \
      --corpus ../corpus \
      --runs ../results \
      --out ../data/answer-chunk-annotations.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BENCH = SCRIPT_DIR.parent  # rag-bench/
REPO_ROOT = BENCH.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from l1_eval import build_chunk_index, load_questions_jsonl  # noqa: E402


def load_trec(path: Path) -> dict[str, list[tuple[str, float]]]:
    """TREC run -> {qid: [(docid, score)] 按文件序（rank 列）}"""
    out: dict[str, list[tuple[str, float]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        qid, doc = parts[0], parts[2]
        out.setdefault(qid, []).append((doc, float(parts[4])))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=str(BENCH / "questions.jsonl"))
    ap.add_argument("--corpus", default=str(BENCH / "corpus"))
    ap.add_argument("--runs", default=str(BENCH / "results"),
                    help="含 G* run trec 的目录（rglob，取最新目录的同前缀 tag）")
    ap.add_argument("--out", default=str(BENCH / "data" / "answer-chunk-annotations.jsonl"))
    args = ap.parse_args()

    store = build_chunk_index(Path(args.corpus))
    cid_content = {cid: store.get_chunk(cid) for cid in store.all_chunk_ids()}

    def page_of(cid: str) -> str:
        return cid.split("#", 1)[0]

    def preview(cid: str) -> str:
        c = cid_content.get(cid)
        raw = (c or {}).get("content", "") if isinstance(c, dict) else (getattr(c, "content", "") or "")
        return raw[:120].replace("\n", " ")

    # run 文件：按 mtime 新→旧，tag 前缀 G1/G2/G3（bge 版目录比 qwen 版新，优先）
    run_files = sorted(Path(args.runs).rglob("*.trec"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    by_tag: dict[str, list[tuple[str, dict]]] = {}
    for p in run_files:
        first = p.name.split(".")[0]
        for pref in ("G1", "G2", "G3"):
            if first.startswith(pref):
                by_tag.setdefault(pref, []).append((p.name, load_trec(p)))
                break

    rows = []
    for q in load_questions_jsonl(args.questions):
        qid = q["id"]
        # source_pages 带 .md（如 core/memory.md），块 id 的 slug 前缀不带 → 归一
        pages = {p[:-3] if p.endswith(".md") else p for p in q.get("source_pages", [])}
        cand: list[str] = []
        seen: set[str] = set()
        # 全通道累积去重（G3→G2→G1 命中面从宽到窄），候选最多 8 个供人工挑
        for pref in ("G3", "G2", "G1"):
            for _, run in by_tag.get(pref, []):
                for doc, _ in run.get(qid, [])[:25]:
                    if doc in seen:
                        continue
                    seen.add(doc)
                    if page_of(doc) in pages:
                        cand.append(doc)
                if len(cand) >= 8:
                    break
            if len(cand) >= 8:
                break
        all_page_chunks = sorted(
            cid for cid in store.all_chunk_ids() if page_of(cid) in pages
        )
        rows.append({
            "id": qid,
            "type": q.get("type"),
            "dup_of": q.get("dup_of"),
            "semantic": q.get("semantic"),
            "question": q["question"],
            "source_pages": q.get("source_pages", []),
            "auto_candidates": [{"chunk_id": c, "preview": preview(c)} for c in cand[:8]],
            # 源页全部块 id（标注人挑真正答案块的完整清单，不受 run 命中限制）
            "page_chunk_ids": all_page_chunks,
            "answer_chunk_ids": None,   # ← 人工复核：确认/增删后回填（只填真正含答案的块）
            "note": "negative（无答案块，跳过）" if q.get("type") == "negative"
                    else ("missing-in-all-runs（召回缺口，需全文定位答案）" if not cand else ""),
        })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8")
    print(f"written {len(rows)} rows -> {args.out}")
    miss = [r["id"] for r in rows if not r["auto_candidates"]]
    print(f"无候选（所有 run top25 均未召回 source_pages → 召回缺口，需全文人工定位）: {len(miss)}")
    for m in miss:
        print("   ", m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
