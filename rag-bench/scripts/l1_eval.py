#!/usr/bin/env python3
"""L1 检索组件评测 —— ranx 驱动的程序化打分

对应用途：
  L1 检索组件测试（G0–G3 对照）；外部公开中文基准（C-MTEB）的 L1 部分作旁证

设计原则：
  1. 程序化打分，不依赖 LLM judge —— 最可复现
  2. 单变量对比：一次只改一处，before/after 跑同一批题
  3. 口径集中固化在脚本内（指标定义、k 值、qrels 构造方式），实验卡片引用版本号保证可比

与 run_g0.py / run_g1.py 的分工：
  run_g*.py   —— 自建 60 题在自建语料上的 G 轮次实验（主论据）
  l1_eval.py  —— 公开中文基准（C-MTEB 等）上的横向对照（外部旁证，非门禁）

用法：
  # 对比多个 run
  python l1_eval.py --qrels ../data/qrels.txt --run G1=../data/g1.txt --run G2=../data/g2.txt

  # 从 CountBot 现役 BM25 索引直接生成 run 并评测
  # （语料 JSONL 每行含 id/title/content/tags，可由 C-MTEB corpus 转换得到）
  python l1_eval.py --qrels ../data/qrels.txt --bm25-corpus ../data/corpus.jsonl \
                    --queries ../data/queries.json --tag G1

  # 自检（合成数据，验证环境与脚本可用）
  python l1_eval.py --self-test

数据格式（TREC）：
  qrels: <qid> <iteration> <docid> <relevance>
  run  : <qid> Q0 <docid> <rank> <score> <tag>

注：本脚本默认对接文档级 BM25Index（wiki/index.py）。
块级 ChunkedBM25Index（G1+ 轮次）由 --chunk-run 驱动：
  python l1_eval.py --chunk-run G1 --write-qrels ../data/qrels-chunk.txt
qrels 由 questions.jsonl 的 source_pages 映射构造（Phase 1 任务 1），
每题 relevant = 其源文档 slug 的全部 chunk_id（文档级到块级的自然扩张）。
G2 向量 / G3 混合轮次在此之上新增对应 build_*_run 函数，
口径（top_k=50、阈值绕过、同一 qrels）保持与本文件一致。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

try:
    from ranx import Qrels, Run  # noqa: F401（仅用于块级 run/qrels 的内存构建，统计已纯 Python 化）
except ImportError:
    sys.exit(
        "缺少 ranx。请安装评测依赖（不并入主 requirements.txt）：\n"
        "  pip install -r rag-bench/requirements-eval.txt"
    )

DEFAULT_METRICS = ["ndcg@10", "recall@50", "mrr@10", "map@10"]
# 块级轮次（G1+）口径：对齐生产 ask 注入的 top-6（Phase 1 任务 1）
CHUNK_METRICS = ["hit_rate@6", "mrr@6", "recall@6"]
SCRIPT_DIR = Path(__file__).resolve().parent
BENCH = SCRIPT_DIR.parent          # rag-bench/
REPO_ROOT = BENCH.parent           # countbot-rag 仓库根


# ────────────────────────────────────────────
# 数据加载
# ────────────────────────────────────────────

def parse_trec_plain(path: str | Path, kind: str = "run") -> dict[str, dict[str, float]]:
    """纯 Python 解析 TREC 文件 → {qid: {doc: score}}

    绕开 ranx 0.3.21 的 Qrels/Run.from_file：其内部用 numba typed dict，纯 Python 层
    遍历（.items()/to_dict()）在大规模或中文 doc key 上实测抛 KeyError（2026-09-05），
    本脚本的所有统计一律基于本函数输出的普通 dict，与 ranx 内部实现解耦。
    kind="run"  取第 5 列分数：qid Q0 doc rank score tag
    kind="qrels" 取第 4 列等级：qid 0 doc grade
    """
    out: dict[str, dict[str, float]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < (5 if kind == "run" else 4):
            continue
        qid, doc = parts[0], parts[2]
        val = float(parts[4] if kind == "run" else parts[3])
        out.setdefault(qid, {})[doc] = val
    return out


def parse_run_specs(specs: list[str]) -> dict[str, dict[str, float]]:
    """解析 TAG=path 形式的 run 参数，返回 {tag: plain run dict}"""
    runs: dict[str, dict[str, float]] = {}
    for spec in specs:
        if "=" not in spec:
            sys.exit(f"run 参数格式应为 TAG=path，收到：{spec}")
        tag, path = spec.split("=", 1)
        runs[tag.strip()] = parse_trec_plain(path.strip())
    return runs


# ────────────────────────────────────────────
# 与 CountBot 现役代码对接
# ────────────────────────────────────────────

def load_bm25_index_class():
    """动态加载 backend/modules/wiki/index.py 的 BM25Index

    用 importlib 而非 from backend...import，避免触发 backend 包的其他依赖，
    也避免评测脚本被后端包结构变动牵连。
    """
    index_py = REPO_ROOT / "backend" / "modules" / "wiki" / "index.py"
    if not index_py.exists():
        sys.exit(f"未找到 BM25 实现：{index_py}")
    spec = importlib.util.spec_from_file_location("cb_bm25", index_py)
    if spec is None or spec.loader is None:
        sys.exit(f"无法加载模块：{index_py}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BM25Index


def check_jieba() -> None:
    """jieba 是可选依赖，缺失会让基线测到'单字分词'而非线上真实行为

    对应 archive/primer.md §2.7：主 requirements.txt 中 jieba 被注释，
    --no-jieba 对照组已实测 recall@5 0.80 → 0.53 的差距。
    """
    try:
        import jieba  # noqa: F401
    except ImportError:
        print(
            "⚠️  未安装 jieba。BM25Index 将回退为单字分词，"
            "测出来的基线不代表线上真实行为（见 archive/primer.md §2.7）。\n"
            "   修复：pip install -r rag-bench/requirements-eval.txt",
            file=sys.stderr,
        )


def build_bm25_run(
    corpus_path: str | Path,
    queries: dict[str, str],
    top_k: int = 50,
    bypass_threshold: bool = True,
    name: str = "bm25",
) -> Run:
    """用 CountBot 现役 BM25Index 生成 TREC run

    ⚠️ 关键：BM25Index.search() 内置两重结果过滤——
        相对阈值 score >= max_score * min_score_ratio(默认 0.3)
        绝对阈值 score >= SCORE_THRESHOLD(默认 0.5)
       这会让 top_k=50 常常只返回个位数结果。
       若不绕过，recall@50 会被严重低估，测到的是"阈值行为"而非"检索能力"，
       基线数据将不可信。

    bypass_threshold=True 时把两重阈值置 0，取完整排序。

    已知限制：绕过阈值后，候选集仍只包含"至少命中一个查询 token"的文档。
    零词重叠文档 BM25 无法召回——这是词法检索的固有上限，
    也正是 G2 向量需要证明的增量空间（语义鸿沟，archive/primer.md §2.3）。
    """
    BM25Index = load_bm25_index_class()
    check_jieba()

    index = BM25Index()
    if bypass_threshold:
        # 实例属性覆盖类常量，仅影响本次评测
        index.SCORE_THRESHOLD = 0.0

    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            doc = json.loads(line)
            index.add_document(
                doc_id=str(doc["id"]),
                title=doc.get("title", ""),
                content=doc.get("content", ""),
                tags=doc.get("tags", []),
            )

    run = Run()
    run.name = name
    min_ratio = 0.0 if bypass_threshold else 0.3
    for qid, query in queries.items():
        results = index.search(query, top_k=top_k, min_score_ratio=min_ratio)
        for doc_id, score in results:
            run.add_score(str(qid), str(doc_id), float(score))

    return run


# ────────────────────────────────────────────
# 块级（G1+ 轮次）：ChunkedBM25Index + 自建 60 题
# ────────────────────────────────────────────

def build_chunk_index(corpus_dir: str | Path):
    """从 rag-bench/corpus 建 ChunkedBM25Index

    与 run_g1.py 完全同口径：manifest 的原始 slug（如 core/memory）直接作为
    文档标识——questions.jsonl 的 source_pages 去 .md 后与之精确相等，
    这是块级 qrels 映射成立的前提（已核实，见 implementation-plan §2）。
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from backend.modules.rag.stores import ChunkedBM25Index  # noqa: E402

    corpus = Path(corpus_dir)
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    store = ChunkedBM25Index()
    for e in manifest:
        content = (corpus / f"{e['slug']}.md").read_text(encoding="utf-8")
        store.add_document(e["slug"], e["title"], content, [e.get("section", "")])
    return store


def load_questions_jsonl(path: str | Path) -> list[dict]:
    """读自建 60 题（rag-bench/questions.jsonl）"""
    return [
        json.loads(l)
        for l in Path(path).read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]


def build_qrels_from_questions(questions: list[dict], store) -> Qrels:
    """块级 qrels：每题 relevant = source_pages 各 slug 的全部 chunk_id

    映射规则：source_pages（core/memory.md）去 .md == manifest slug ==
    ChunkedBM25Index 的文档标识 → 该文档的每个 chunk 都算相关（文档级
    标注的自然块级扩张，不做节级人工标注）。

    negative 题无 source_pages，不进入 qrels（拒答行为的评测归
    run_crag_eval.py，不与检索指标混流）。
    """
    qrels = Qrels()
    missing: list[tuple[str, str]] = []
    for q in questions:
        if q.get("type") == "negative":
            continue
        for page in q.get("source_pages", []):
            slug = page[:-3] if page.endswith(".md") else page
            chunk_ids = store._slug_registry.get(slug, {}).get("chunk_ids", [])
            if not chunk_ids:
                missing.append((q["id"], slug))
                continue
            for cid in chunk_ids:
                qrels.add_score(q["id"], cid, 1)
    if missing:
        print(
            f"⚠️  {len(missing)} 个 (题目, slug) 在索引中无对应 chunk：{missing[:5]}",
            file=sys.stderr,
        )
    return qrels


def write_qrels_trec(qrels: dict[str, dict[str, float]], path: str | Path) -> None:
    """qrels 落盘为 TREC 格式（<qid> 0 <chunk_id> 1），供复现与其他 run 对照（输入普通 dict）"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for qid in sorted(qrels):
            for cid in sorted(qrels[qid]):
                f.write(f"{qid} 0 {cid} {int(qrels[qid][cid])}\n")


def build_chunk_run(
    store,
    queries: dict[str, str],
    top_k: int = 50,
    bypass_threshold: bool = True,
    name: str = "G1-chunk",
) -> Run:
    """用 ChunkedBM25Index 生成块级 TREC run

    阈值绕过口径与 build_bm25_run 一致（SCORE_THRESHOLD / min_score_ratio
    双双置 0），否则 recall 类指标测到的是"阈值行为"而非"检索能力"。
    top_k 默认 50：对齐 HybridRetriever 的候选池深度（BM25 top-50 → 精排 top-6），
    6 以内的指标（hit_rate@6 / mrr@6 / recall@6）不受深度影响。
    """
    check_jieba()
    if bypass_threshold:
        store._bm25.SCORE_THRESHOLD = 0.0

    run = Run()
    run.name = name
    min_ratio = 0.0 if bypass_threshold else 0.3
    for qid, query in queries.items():
        for chunk_id, score in store.search(query, top_k=top_k, min_score_ratio=min_ratio):
            run.add_score(str(qid), str(chunk_id), float(score))

    return run


def build_vector_run(
    corpus_dir: str | Path,
    queries: dict[str, str],
    mode: str = "hybrid",
    top_k: int = 50,
    name: str | None = None,
) -> Run:
    """G2 纯向量 / G3 混合（RRF） / G4 重排块级 run（需 COUNTBOT_RAG_EMBEDDING_* 环境变量）

    嵌入文本组装与生产一致（service.chunk_embedding_text），保证向量空间可比。
    G2 = Dense 单通道排序（停级条款的判定依据）；
    G3 = HybridRetriever 双通道融合（与生产 search_chunks 同一条代码路径）；
    G4 = G3 候选 top-50 → RerankerClient 精排 top-6（与生产 _rag_ask 同一条
    精排路径；Phase 2 门禁"rerank 后 Hit@6 ≥90% / MRR 相对 +20%"的判定依据，
    需额外配置 COUNTBOT_RAG_RERANK_*）。
    """
    import asyncio

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from backend.modules.rag.embeddings import build_embedding_client
    from backend.modules.rag.retriever import HybridRetriever
    from backend.modules.rag.service import chunk_embedding_text
    from backend.modules.rag.stores import VectorStore

    if mode not in ("dense", "hybrid", "rerank"):
        sys.exit(f"mode 必须是 dense|hybrid|rerank，收到：{mode}")

    embedder = build_embedding_client()
    if embedder is None:
        sys.exit("未配置 COUNTBOT_RAG_EMBEDDING_BASE_URL / API_KEY，无法构建向量 run")

    store = build_chunk_index(corpus_dir)
    check_jieba()

    # 全量块嵌入（EmbeddingClient 内部按 ≤16 切批）
    pairs = [(cid, chunk_embedding_text(c))
             for cid in store.all_chunk_ids() if (c := store.get_chunk(cid))]
    print(f"[vector-run] embedding {len(pairs)} chunks ({mode})...")
    vectors = asyncio.run(embedder.embed_texts([t for _, t in pairs]))

    vs = VectorStore()
    for (cid, _), vec in zip(pairs, vectors):
        vs.add(cid, vec)

    run = Run()
    run.name = name or {"dense": "G2-dense", "hybrid": "G3-hybrid", "rerank": "G4-rerank"}[mode]
    if mode == "dense":
        for qid, query in queries.items():
            qvec = asyncio.run(embedder.embed_query(query))
            for cid, score in vs.search(qvec, top_k=top_k):
                run.add_score(str(qid), str(cid), float(score))
    else:
        retriever = HybridRetriever(store, vs, embedder, candidate_k=top_k)
        reranker = None
        if mode == "rerank":
            from backend.modules.rag.reranker import build_reranker
            reranker = build_reranker()
            if reranker is None:
                sys.exit("未配置 COUNTBOT_RAG_RERANK_BASE_URL / API_KEY，无法构建 rerank run")
        for qid, query in queries.items():
            candidates = asyncio.run(retriever.search(query, top_k=top_k))
            # rerank 返回已按相关性截断的 top_n（默认 6）；未启用 rerank 时为 RRF 全序
            results = (asyncio.run(reranker.rerank(query, candidates))
                       if reranker is not None else candidates)
            for rank, c in enumerate(results, 1):
                # 已按相关性降序，转成递减分数保持名次
                run.add_score(str(qid), str(c["chunk_id"]), float(top_k - rank))
    return run


def save_runs_trec(runs: dict[str, dict[str, float]], out_dir: Path) -> None:
    """把各 run 落盘为 TREC 格式（qid Q0 docid rank score runtag），输入普通 dict

    run 只存在于内存，评测进程退出即丢；落盘后任何口径的事后分析
    （按题型/文档子集切分）都能免重嵌重跑直接进行。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for tag, run in runs.items():
        lines = []
        for qid, doc_scores in run.items():
            scored = sorted(doc_scores.items(), key=lambda kv: kv[1], reverse=True)
            for rank, (doc, score) in enumerate(scored, 1):
                lines.append(f"{qid} Q0 {doc} {rank} {score:.6f} {tag}")
        path = out_dir / f"{tag}.trec"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[runs] saved {path} ({len(lines)} lines)")


def per_type_summary(qrels: dict[str, dict[str, float]],
                     runs: dict[str, dict[str, float]],
                     qtype_map: dict[str, str]) -> dict:
    """按题型分组统计 hit_rate@6 / mrr@6（仅正样本题型），返回 {type: {tag: {n, hit@6, mrr@6}}}

    门禁 1 的判定口径依赖本函数：needle+cross_doc 合并池 = 两型 n 与命中数直接相加。
    输入均为普通 dict（ranx typed dict 的 Python 层遍历不稳定，见 parse_trec_plain 注释）。
    """
    types = sorted({t for t in qtype_map.values() if t != "negative"})
    out: dict = {}
    for t in types:
        qids = [q for q, tt in qtype_map.items() if tt == t]
        out[t] = {}
        for tag, run in runs.items():
            hits = 0
            rr_sum = 0.0
            for qid in qids:
                rel = {d for d, g in qrels.get(qid, {}).items() if g and g > 0}
                ranked = _ranked_docs(run.get(qid, {}))[:6]
                hit = next((i for i, d in enumerate(ranked, 1) if d in rel), None)
                if hit is not None:
                    hits += 1
                    rr_sum += 1.0 / hit
            n = len(qids)
            out[t][tag] = {"n": n,
                           "hit_rate@6": (hits / n) if n else 0.0,
                           "mrr@6": (rr_sum / n) if n else 0.0}
    return out


def print_per_type(per_type: dict, runs: dict[str, Run]) -> None:
    """打印题型分表：每个题型一行一个 run 的 hit_rate@6/mrr@6"""
    tags = list(runs)
    if len(tags) == 1:
        header = "| 题型 | n | hit_rate@6 | mrr@6 |"
        sep = "|---|---|---|---|"
        for t, rows in per_type.items():
            r = rows[tags[0]]
            print(header)
            print(sep)
            print(f"| {t} | {r['n']} | {r['hit_rate@6']:.4f} | {r['mrr@6']:.4f} |")
        return
    header = "| run | " + " | ".join(t for t in per_type) + " |"
    sep = "|" + "---|" * (len(per_type) + 1)
    print("\n按题型分表（hit_rate@6，括号内 mrr@6）：")
    print(header)
    print(sep)
    for tag in tags:
        cells = []
        for t, rows in per_type.items():
            r = rows[tag]
            cells.append(f"{r['hit_rate@6']:.4f} ({r['mrr@6']:.4f})")
        print(f"| {tag} | " + " | ".join(cells) + " |")


# ────────────────────────────────────────────
# 评测与对比
# ────────────────────────────────────────────

def metric_at_single(metric: str, ranked: list[str], rel: set[str]) -> float:
    """单个 query 的 @k 指标值（ranked 已按分数降序，rel = 相关 doc 集合）

    实现 hit_rate@k / mrr@k / recall@k / ndcg@k（k 缺失视为不截断）。
    rel 只按 grade>0 判相关（块级 qrels grade 均为 1）。
    """
    k = None
    if "@" in metric:
        metric, ks = metric.rsplit("@", 1)
        k = int(ks)
    if k is not None:
        ranked = ranked[:k]
    if metric == "hit_rate":
        return 1.0 if any(d in rel for d in ranked) else 0.0
    if metric == "mrr":
        for i, d in enumerate(ranked, 1):
            if d in rel:
                return 1.0 / i
        return 0.0
    if metric == "recall":
        return sum(1 for d in ranked if d in rel) / len(rel) if rel else 0.0
    if metric == "ndcg":
        dcg = sum(1.0 / math.log2(i + 2) for i, d in enumerate(ranked) if d in rel)
        ideal = sum(1.0 / math.log2(i + 2)
                    for i in range(min(len(rel), len(ranked))))
        return dcg / ideal if ideal else 0.0
    if metric == "map":
        # AP@k = Σ(命中位置 P@r) / min(|rel|, k)，再对 query 平均
        ap, hits = 0.0, 0
        for i, d in enumerate(ranked, 1):
            if d in rel:
                hits += 1
                ap += hits / i
        denom = min(len(rel), len(ranked))
        return ap / denom if denom else 0.0
    raise NotImplementedError(f"手工统计暂未实现指标：{metric}")


def _ranked_docs(doc_scores: dict) -> list[str]:
    """按分数降序返回 doc 列表"""
    return [d for d, _ in sorted(doc_scores.items(), key=lambda kv: kv[1], reverse=True)]


def summarize(qrels: dict[str, dict[str, float]],
              runs: dict[str, dict[str, float]],
              metrics: list[str]) -> dict:
    """各 run 的指标汇总，返回 {tag: {metric: value}}

    纯 Python 实现（按 qrels∩run 的公共 qid 平均），替代 ranx compare/evaluate——
    ranx 0.3.21 的 numba typed dict 在纯 Python 层遍历不稳定（2026-09-05 实测
    KeyError/TypingError），指标公式见 metric_at_single。
    """
    out: dict[str, dict[str, float]] = {}
    for tag, run in runs.items():
        qids = sorted(set(qrels) & set(run))
        n = len(qids)
        scores = {m: 0.0 for m in metrics}
        for qid in qids:
            rel = {d for d, g in qrels[qid].items() if g and g > 0}
            ranked = _ranked_docs(run[qid])
            for m in metrics:
                scores[m] += metric_at_single(m, ranked, rel)
        out[tag] = {m: (s / n if n else 0.0) for m, s in scores.items()}
    return out


def per_query_diff(
    qrels: dict[str, dict[str, float]],
    baseline: dict[str, dict[str, float]],
    target: dict[str, dict[str, float]],
    metrics: list[str],
    main_metric: str = "ndcg@10",
) -> list[dict]:
    """逐 query 对比，识别变好 / 变坏的题目（实验卡片"变好变坏"栏）

    纯 Python 实现（metric_at_single），输入普通 dict。对 24K 量级查询仍建议抽样。
    """
    diffs: list[dict] = []
    query_ids = sorted(set(qrels) & set(baseline) & set(target))
    for qid in query_ids:
        rel = {d for d, g in qrels[qid].items() if g and g > 0}
        before = metric_at_single(main_metric, _ranked_docs(baseline[qid]), rel)
        after = metric_at_single(main_metric, _ranked_docs(target[qid]), rel)
        diffs.append(
            {
                "query_id": qid,
                "before": round(before, 4),
                "after": round(after, 4),
                "delta": round(after - before, 4),
            }
        )
    diffs.sort(key=lambda r: r["delta"])
    return diffs


# ────────────────────────────────────────────
# 输出
# ────────────────────────────────────────────

def write_report(out_dir: Path, summary: dict, diff: list[dict] | None, metrics: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = ["# L1 检索评测报告", "", f"- 指标口径：{', '.join(metrics)}", ""]
    header = "| run | " + " | ".join(metrics) + " |"
    lines += [header, "|" + "---|" * (len(metrics) + 1)]
    for tag, scores in summary.items():
        cells = []
        for m in metrics:
            val = scores.get(m)
            cells.append(f"{val:.4f}" if isinstance(val, (int, float)) else "-")
        lines.append(f"| {tag} | " + " | ".join(cells) + " |")
    lines.append("")

    if diff:
        better = [d for d in diff if d["delta"] > 0.001]
        worse = [d for d in diff if d["delta"] < -0.001]
        lines += [
            "## 变好 / 变坏",
            "",
            f"- 变好：{len(better)} 题",
            f"- 变坏：{len(worse)} 题（须逐条说明原因或记为已知限制）",
            "",
        ]
        if worse:
            lines += ["### 变坏明细（最严重 20 条）", "", "| query | before | after | delta |", "|---|---|---|---|"]
            for d in worse[:20]:
                lines.append(f"| {d['query_id']} | {d['before']} | {d['after']} | {d['delta']} |")
            lines.append("")

    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    if diff:
        import csv

        with open(out_dir / "diff.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["query_id", "before", "after", "delta"])
            writer.writeheader()
            writer.writerows(diff)

    print("\n".join(lines))
    print(f"\n报告已写入：{out_dir}")


# ────────────────────────────────────────────
# 自检
# ────────────────────────────────────────────

def self_test() -> int:
    """用合成数据跑通全流程，验证环境与脚本可用（不需要下载数据集）"""
    import tempfile

    print("运行自检：构造 20 个查询 × 200 篇文档的合成数据...\n")

    # 全流程已纯 Python 化（普通 dict），自检直接构造 dict，不再经过 ranx 对象
    qrels: dict[str, dict[str, float]] = {}
    base_run: dict[str, dict[str, float]] = {}
    good_run: dict[str, dict[str, float]] = {}

    for q in range(20):
        qid = f"q{q}"
        gold = f"d{q}"
        qrels.setdefault(qid, {})[gold] = 1.0

        # 基线：黄金文档排在第 8 位（次优基线）
        base_run[qid] = {f"d{(q + i) % 200}": 50.0 - rank
                         for rank, i in enumerate(range(50))
                         if f"d{(q + i) % 200}" != gold}
        base_run[qid][gold] = 50.0 - 7
        # 改进后：黄金文档排在第 1 位
        good_run[qid] = dict(base_run[qid])
        good_run[qid][gold] = 100.0

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "report"
        summary = summarize(qrels, {"G0": base_run, "G1": good_run}, DEFAULT_METRICS)
        diff = per_query_diff(qrels, base_run, good_run, DEFAULT_METRICS)
        write_report(out_dir, summary, diff, DEFAULT_METRICS)

    better = sum(1 for d in diff if d["delta"] > 0.001)
    worse = sum(1 for d in diff if d["delta"] < -0.001)
    ok = better == 20 and worse == 0
    print(f"\n自检结论：{'通过' if ok else '失败'}（变好 {better} / 变坏 {worse}，期望 20 / 0）")
    if not ok:
        print("  ↑ 若为 0/0，通常是 ranx 版本 API 差异，请核对指标名与 ranx 版本")
    return 0 if ok else 1


# ────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="L1 检索组件评测（ranx）")
    parser.add_argument("--qrels", help="qrels 文件路径（TREC 格式）；--chunk-run 模式可省略，自动构造")
    parser.add_argument("--run", action="append", default=[], metavar="TAG=PATH",
                        help="run 文件，可重复：--run G1=data/g1.txt --run G2=data/g2.txt")
    parser.add_argument("--bm25-corpus", metavar="JSONL",
                        help="语料 JSONL（每行含 id/title/content/tags），用现役 BM25 生成 run")
    parser.add_argument("--queries", metavar="JSON", help='查询文件 {qid: query}，配合 --bm25-corpus')
    parser.add_argument("--tag", default="G1", help="--bm25-corpus 生成的 run 名称")
    parser.add_argument("--chunk-run", metavar="TAG",
                        help="块级模式：用 ChunkedBM25Index（--corpus）对自建 60 题生成 run 并评测，"
                             "qrels 由 questions.jsonl 自动构造")
    parser.add_argument("--dense-run", metavar="TAG",
                        help="G2 纯向量 run（需 COUNTBOT_RAG_EMBEDDING_* 环境变量），停级条款判定用")
    parser.add_argument("--hybrid-run", metavar="TAG",
                        help="G3 混合 run（BM25+Dense RRF，生产同路径），Phase 1 门禁用")
    parser.add_argument("--rerank-run", metavar="TAG",
                        help="G4 重排 run（G3 候选 top-50 → reranker 精排 top-6，生产 _rag_ask 同路径），"
                             "Phase 2 门禁用；需 COUNTBOT_RAG_RERANK_* 环境变量")
    parser.add_argument("--corpus", default=str(BENCH / "corpus"),
                        help="块级模式语料目录（含 manifest.json），默认 rag-bench/corpus")
    parser.add_argument("--questions-jsonl", default=str(BENCH / "questions.jsonl"),
                        help="自建题目文件，默认 rag-bench/questions.jsonl")
    parser.add_argument("--write-qrels", metavar="PATH",
                        help="把块级 qrels 写成 TREC 文件（供复现与其他 G 轮次对照）")
    parser.add_argument("--write-runs", metavar="DIR",
                        help="把各 run 落盘为 TREC 文件到 DIR（事后按题型/子集分析的免重嵌前提）")
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--keep-threshold", action="store_true",
                        help="保留 BM25 内置阈值（默认绕过，详见 build_bm25_run 文档字符串）")
    parser.add_argument("--metrics", default=None,
                        help="逗号分隔指标；默认按模式取（文档级 ndcg@10,recall@50,mrr@10,map@10；"
                             f"块级 {','.join(CHUNK_METRICS)}）")
    parser.add_argument("--baseline", help="对照基线 tag，用于逐 query 变好变坏分析")
    parser.add_argument("--out", default=str(BENCH / "results" / "l1"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    runs = parse_run_specs(args.run)

    qrels = None
    qtype_map = None
    vector_mode = args.dense_run or args.hybrid_run or args.rerank_run
    corpus_mode = args.chunk_run or vector_mode
    if corpus_mode:
        store = build_chunk_index(args.corpus)
        questions = load_questions_jsonl(args.questions_jsonl)
        # 检索指标只评正样本：negative 题无 relevant chunk（拒答归 run_crag_eval.py）
        queries = {q["id"]: q["question"] for q in questions if q["type"] != "negative"}
        qtype_map = {q["id"]: q["type"] for q in questions}
        # ranx 内存对象（add_score 构建）的 to_dict() 安全；文件输入走 parse_trec_plain
        qrels = build_qrels_from_questions(questions, store).to_dict()
        if args.write_qrels:
            write_qrels_trec(qrels, args.write_qrels)
        if args.chunk_run:
            runs[args.chunk_run] = build_chunk_run(
                store, queries, top_k=args.top_k,
                bypass_threshold=not args.keep_threshold, name=args.chunk_run,
            ).to_dict()
        if args.dense_run:
            runs[args.dense_run] = build_vector_run(
                args.corpus, queries, mode="dense", top_k=args.top_k, name=args.dense_run,
            ).to_dict()
        if args.hybrid_run:
            runs[args.hybrid_run] = build_vector_run(
                args.corpus, queries, mode="hybrid", top_k=args.top_k, name=args.hybrid_run,
            ).to_dict()
        if args.rerank_run:
            runs[args.rerank_run] = build_vector_run(
                args.corpus, queries, mode="rerank", top_k=args.top_k, name=args.rerank_run,
            ).to_dict()
    elif args.qrels:
        qrels = parse_trec_plain(args.qrels, kind="qrels")

    if qrels is None:
        parser.error("需要 --qrels、--chunk-run / --dense-run / --hybrid-run 或 --self-test 之一")

    # --run + --qrels 的事后分析路径：qtype_map 从题目文件补全（只保留 qrels 里真实存在的
    # qid，避免文档级 qrels 下注入不匹配的 60 题映射导致按题型分表全零的误导输出）。
    if qtype_map is None and args.qrels:
        qtype_map = {q["id"]: q["type"] for q in load_questions_jsonl(args.questions_jsonl)
                     if q["id"] in qrels}

    if args.bm25_corpus:
        if not args.queries:
            parser.error("--bm25-corpus 需要配合 --queries")
        queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
        runs[args.tag] = build_bm25_run(
            args.bm25_corpus,
            queries,
            top_k=args.top_k,
            bypass_threshold=not args.keep_threshold,
            name=args.tag,
        ).to_dict()

    if not runs:
        parser.error("没有可评测的 run，用 --run / --bm25-corpus / --chunk-run 提供")

    metrics = (
        [m.strip() for m in args.metrics.split(",") if m.strip()]
        if args.metrics
        else (CHUNK_METRICS if corpus_mode else DEFAULT_METRICS)
    )
    summary = summarize(qrels, runs, metrics)

    diff = None
    if args.baseline and args.baseline in runs and len(runs) > 1:
        others = [t for t in runs if t != args.baseline]
        # 主指标取本 run 的第一个指标（块级=hit_rate@6），不要用默认 ndcg@10
        diff = per_query_diff(qrels, runs[args.baseline], runs[others[0]], metrics,
                              main_metric=metrics[0])

    if args.write_runs:
        save_runs_trec(runs, Path(args.write_runs))

    if qtype_map and len(runs) >= 2:
        per_type = per_type_summary(qrels, runs, qtype_map)
        print_per_type(per_type, runs)

    write_report(Path(args.out), summary, diff, metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
