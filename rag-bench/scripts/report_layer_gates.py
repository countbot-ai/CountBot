#!/usr/bin/env python3
"""分层门禁报告：把 Phase 1 验收从"单一 hit@6"拆成可归因的两层

口径（与 l1_eval.py / work-log §4 一致）：
  qrels = source_pages 全部块 relevant（文档级到块级的自然扩张，块 id = slug#section）；
  评测只评正样本（negative 归 run_crag_eval.py）。

逐题两层归因（top6 miss 时）：
  recall_gap —— top-50 候选内没有任何 relevant 块（召回缺口：该通道"找不到"答案，
                只能靠另一路通道或查询改写/分解解决）
  rank_gap   —— top-50 内有 relevant 块但没进 top-6（排序缺口：答案已召回，
                需 rerank 精排解决，不是召回问题）

用法：
  python report_layer_gates.py --runs-dir ../results/l1-g123-bge-runs \
      --out ../results/l1-g123-bge/layer-gates.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BENCH = SCRIPT_DIR.parent
REPO_ROOT = BENCH.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from l1_eval import (  # noqa: E402
    build_chunk_index,
    build_qrels_from_questions,
    load_questions_jsonl,
)

TYPE_ORDER = ["single_doc", "cross_doc", "needle"]


def load_run_trec(path: Path) -> dict[str, list[str]]:
    """TREC run -> {qid: [docid...] 按 rank 序}"""
    out: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        out.setdefault(parts[0], []).append(parts[2])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=str(BENCH / "questions.jsonl"))
    ap.add_argument("--corpus", default=str(BENCH / "corpus"))
    ap.add_argument("--runs-dir", default=str(BENCH / "results" / "l1-g123-bge-runs"))
    ap.add_argument("--out", default=str(BENCH / "results" / "l1-g123-bge" / "layer-gates.md"))
    args = ap.parse_args()

    store = build_chunk_index(Path(args.corpus))
    questions = [q for q in load_questions_jsonl(args.questions) if q.get("dup_of") is None]
    qrels = build_qrels_from_questions(questions, store).to_dict()
    type_of = {q["id"]: q["type"] for q in questions}
    qids = list(qrels.keys())

    run_files = {p.name.split(".")[0]: p for p in Path(args.runs_dir).glob("*.trec")}
    runs = {}
    for tag in ("G1", "G2", "G3"):
        key = next((k for k in run_files if k.startswith(tag)), None)
        if key:
            runs[tag] = load_run_trec(run_files[key])

    # 逐题分析
    rows = []  # (qid, type, g1_hit, g2_hit, g3_hit, g1_gap, g2_gap, g3_gap)
    for qid in qids:
        rel = set(qrels[qid])
        info = [qid, type_of[qid]]
        for tag in ("G1", "G2", "G3"):
            r = runs.get(tag, {}).get(qid, [])
            top6, top50 = r[:6], r[:50]
            hit = bool(set(top6) & rel)
            gap = "recall" if not (set(top50) & rel) else ("rank" if not hit else "-")
            info.extend([hit, gap])
        rows.append(info)

    # 汇总表
    lines = ["# 分层门禁报告（Phase 1 检索层）", "", "- 口径：块级 qrels（source_pages → 全部块），top-6 / top-50",
             f"- 正题 {len(qids)}（已去重：排除 dup_of）；评测 run 来自 {Path(args.runs_dir).name}", ""]
    header = ["题型", "n", "G1 hit@6", "G2 hit@6", "G3 hit@6", "G1 召回缺口", "G2 召回缺口", "G3 召回缺口",
              "G1 排序缺口", "G2 排序缺口", "G3 排序缺口"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))

    # 行结构：[qid, type, g1_hit, g1_gap, g2_hit, g2_gap, g3_hit, g3_gap]
    HIT_COL = {"G1": 2, "G2": 4, "G3": 6}
    GAP_COL = {"G1": 3, "G2": 5, "G3": 7}

    def add_block(rows, label):
        n = len(rows)
        if not n:
            return
        def hit_rate(tag):
            hits = sum(1 for r in rows if r[HIT_COL[tag]])
            return f"{hits}/{n} = {hits / n:.1%}"
        def gap_count(tag, kind):
            col = GAP_COL[tag]
            return sum(1 for r in rows if r[col] == kind)
        cells = [label, str(n)] + [
            hit_rate(t) if i < 3 else str(gap_count(t, "recall") if i < 6 else gap_count(t, "rank"))
            for i, t in enumerate(["G1", "G2", "G3", "G1", "G2", "G3", "G1", "G2", "G3"])
        ]
        lines.append("| " + " | ".join(cells) + " |")

    add_block(rows, "全部")
    for t in TYPE_ORDER:
        add_block([r for r in rows if r[1] == t], t)

    # 逐题明细
    lines += ["", "## 逐题（* 表示该 run top6 命中；G 缺口：recall/rank/-）", "",
              "| qid | type | G1 | G2 | G3 | 缺口(G1→G3) |"]
    for r in rows:
        qid, tp, *rest = r
        hits = rest[0::2]
        gaps = rest[1::2]
        lines.append(f"| {qid} | {tp} | {hits[0]} | {hits[1]} | {hits[2]} | "
                     f"G1={gaps[0]} G2={gaps[1]} G3={gaps[2]} |")

    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(l for l in lines[:16]))
    print(f"\nwritten -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
