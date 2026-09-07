#!/usr/bin/env python3
"""CRAG 端到端验证 v2：真实 LLM 全链路 + LLM judge 分点判定 + 分层归因 + pairwise 对照。

本脚本不进入 PR，属于本地验证工具。需要 OpenAI 兼容的 API 环境：

用法（在 rag-bench/scripts/ 下）：
  python3 run_crag_eval.py --base-url https://api.xxx.com/v1 \
                           --api-key sk-xxx \
                           --model gpt-4o-mini \
                           [--judge-model gpt-4o-mini] \
                           [--out ../results/crag-detail.json] [--limit 10] \
                           [--no-judge] \
                           [--baseline-json ../results/crag-detail-old.json]

v2 相对 v1 的升级（评测架构迭代）：
  1. LLM judge 消费 questions.jsonl 的 expected_points（此前标注存在但未被使用）：
     五分类 verdict = correct / partial / wrong / refused / hallucinated + 分点覆盖。
  2. 拒答判定从关键词匹配升级为 judge 判定（关键词保留为 fallback 与一致性校验，
     两者不一致率是 judge 质量的元指标）。
  3. 检索层信号：每题独立记录原始问题的 top-6 检索命中，产出误拒答归因表
     （检索 miss vs grader 误判），把"误拒答为什么发生"从猜测变成查表。
  4. pairwise 模式：--baseline-json 对比两次 v2 run 的完整回答（A/B 换序双判，
     不一致记 tie，防 position bias），Phase 1 验收"答案质量不回退"用相对比较
     而非绝对分数（小 judge 模型上绝对分数噪声大）。

前提：
  - rag-bench/corpus/ 已就绪（python3 fetch_corpus.py）
  - COUNTBOT_RAG_CHUNKS 路径由本脚本自动注入，无需手动设置
"""
import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

BENCH = Path(__file__).resolve().parent.parent
REPO = Path(__file__).resolve().parents[2]

VERDICTS = ("correct", "partial", "wrong", "refused", "hallucinated")

# [slug#section] 形态的块级引用（生成 prompt 要求的溯源格式）
CITATION_RE = re.compile(r"\[[^\[\]\n]*#[^\[\]\n]*\]")

JUDGE_PROMPT = """你是知识库问答系统的质量评估器。请根据「问题」与「参考要点」评估「系统回答」。

问题：{question}
参考要点（评分依据）：{points}
系统回答：
{answer}

判定标准：
- correct：参考要点基本全部覆盖，且无编造
- partial：覆盖了部分要点，遗漏明显
- wrong：给出了回答但与参考要点明显不符
- refused：明确表示知识库中没有相关内容 / 拒绝回答
- hallucinated：编造了参考要点中不存在的具体事实（功能、数字、命令等）

只输出一行 JSON（不要输出其他内容）：
{{"verdict": "correct|partial|wrong|refused|hallucinated", "covered": ["覆盖到的要点，可空"], "reason": "一句话理由"}}"""

PAIRWISE_PROMPT = """你是知识库问答质量评估器。对同一个问题，判断回答 A 和回答 B 哪个更好。

问题：{question}
参考要点：{points}

回答 A：
{a}

回答 B：
{b}

评判维度（按优先级）：参考要点覆盖 > 准确（无编造）> 带可溯源引用 > 简洁。
若参考要点表明该题应当拒答（如"应拒答：…"），则正确拒答的回答更好。

只输出一行 JSON（不要输出其他内容）：
{{"better": "A|B|tie", "reason": "一句话理由"}}"""


class SimpleProvider:
    """最小 OpenAI 兼容 provider：只需 chat_completion 接口"""

    def __init__(self, base_url: str, api_key: str, model: str):
        from openai import AsyncOpenAI
        # 显式超时 + 限制重试：无超时挂起的代价是整轮评测（60 题已跑完的部分
        # 全部作废）——实测过一次连接半开导致进程挂起 2 小时无进展。
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key,
                                   timeout=120.0, max_retries=1)
        self._model = model
        self.calls = 0
        self.tokens_in = 0

    async def chat_completion(self, prompt: str, max_tokens: int = 1000,
                              temperature: float = 0.3) -> str:
        self.calls += 1
        self.tokens_in += len(prompt) // 2  # 粗略估计
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""


def build_wiki_from_corpus(tmp: Path):
    """把评测语料写成 concepts/*.md（frontmatter），供 WikiTool/RagService 使用"""
    import frontmatter
    concepts = tmp / "concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((BENCH / "corpus/manifest.json").read_text(encoding="utf-8"))
    for e in manifest:
        content = (BENCH / "corpus" / f"{e['slug']}.md").read_text(encoding="utf-8")
        post = frontmatter.Post(content)
        post.metadata["title"] = e["title"]
        post.metadata["tags"] = [e.get("section", "")]
        safe_slug = e["slug"].replace("/", "__")
        (concepts / f"{safe_slug}.md").write_text(frontmatter.dumps(post), encoding="utf-8")
    return {e["slug"]: safe_slug for e in manifest}


# ────────────────────────────────────────────
# 判定组件（v1 的字符串匹配保留为 fallback / 一致性校验）
# ────────────────────────────────────────────

def detect_refusal_keyword(text: str) -> bool:
    """v1 的关键词拒答判定：CRAG 拒答文案是固定字符串，关键词命中较准，
    但换 prompt 措辞即静默失效——只作为 judge 不可用时的 fallback。"""
    return ("没有找到" in text) or ("没有相关" in text)


def detect_citation(text: str) -> bool:
    """块级引用检测：匹配 [slug#section] 溯源格式"""
    return bool(CITATION_RE.search(text))


def parse_json_loose(text: str):
    """容错解析 judge 输出中的单行 JSON（与 tool.py 的 _parse_grade 同策略）"""
    if not text:
        return None
    m = re.search(r"\{[^{}]*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


async def judge_answer(provider, question: str, points: list, answer: str):
    """LLM judge 五分类判定，消费 expected_points 标注。

    Returns: {"verdict", "covered", "reason"} 或 None（调用失败/不可解析，调用方回退关键词）。
    """
    try:
        resp = await provider.chat_completion(
            JUDGE_PROMPT.format(
                question=question,
                points="；".join(points) if points else "（无标注）",
                answer=answer,
            ),
            max_tokens=2500,  # deepseek-v4-pro 是推理模型，思考也计入预算
            temperature=0.0,
        )
    except Exception as e:
        print(f"  judge 调用失败，回退关键词判定: {e}", file=sys.stderr)
        return None
    data = parse_json_loose(resp)
    if not data or str(data.get("verdict", "")).strip().lower() not in VERDICTS:
        return None
    return {
        "verdict": str(data["verdict"]).strip().lower(),
        "covered": list(data.get("covered") or []),
        "reason": str(data.get("reason", ""))[:200],
    }


# ────────────────────────────────────────────
# 检索层信号（归因用；门禁级检索指标归 l1_eval.py，两者口径独立）
# ────────────────────────────────────────────

def retrieval_signal(tool, question: str, top_k: int = 6) -> dict:
    """原始问题一次检索的文档级命中信号。

    注意：生产 _rag_ask 在 grader 判 none 后会改写查询重试，这里记录的是
    原始问题的第一次检索——误拒答归因的正是"第一次检索就没召回"这一情形。
    """
    if tool._rag is None:
        return {"retrieved_docs": [], "chunk_ids": [], "available": False}
    try:
        # max_per_doc=0：归因口径显式化——记录"检索能力"层面的首次命中
        # （#114 之后生产 top-6 注入默认 max_per_doc=1，单文档截断会掩盖
        # 检索缺口；归因要回答的是"第一次检索是否召回"，故不限单文档）
        chunks = tool._rag.search_chunks(
            question, top_k=top_k, max_per_doc=0) or []
    except Exception as e:
        print(f"  检索信号获取失败: {e}", file=sys.stderr)
        return {"retrieved_docs": [], "chunk_ids": [], "available": False}
    return {
        "retrieved_docs": sorted({c["chunk_id"].split("#", 1)[0]
                                  for c in chunks if "#" in c.get("chunk_id", "")}),
        "chunk_ids": [c["chunk_id"] for c in chunks],
        "available": True,
    }


def expected_slugs(question: dict) -> set:
    """source_pages 去掉 .md 后的 slug；与 build_wiki_from_corpus 一致，
    把 / 替换为 __（chunk_id 前缀用的是 safe_slug），否则两边永不相交。"""
    return {p[:-3].replace("/", "__") if p.endswith(".md") else p.replace("/", "__")
            for p in question.get("source_pages", [])}


# ────────────────────────────────────────────
# pairwise 对照（--baseline-json）
# ────────────────────────────────────────────

async def judge_better(provider, question: str, points: list, a: str, b: str):
    try:
        resp = await provider.chat_completion(
            PAIRWISE_PROMPT.format(
                question=question,
                points="；".join(points) if points else "（无标注）",
                a=a,
                b=b,
            ),
            max_tokens=2500,  # 推理模型的思考计入预算，200 会被思考耗尽
            temperature=0.0,
        )
    except Exception:
        return None
    data = parse_json_loose(resp)
    if not data or str(data.get("better", "")).strip().upper() not in ("A", "B", "TIE"):
        return None
    return str(data["better"]).strip().upper()


async def run_pairwise(provider, results: list, baseline_path: Path):
    """与 baseline run 逐题 pairwise（A/B 换序双判防 position bias）。

    一致才计票（A/B 均判同一方），不一致或解析失败记 tie（保守口径）。
    要求 baseline 是 v2 格式（detail 含完整 answer 字段）。
    """
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    base = {r["id"]: r for r in payload.get("detail", []) if r.get("answer")}
    stats = {"win": 0, "loss": 0, "tie": 0, "skipped": 0}
    rows = []
    for r in results:
        b = base.get(r["id"])
        if not b or not r.get("answer"):
            stats["skipped"] += 1
            continue
        points = r.get("expected_points") or []
        v1 = await judge_better(provider, r["question"], points, r["answer"], b["answer"])
        v2 = await judge_better(provider, r["question"], points, b["answer"], r["answer"])
        if v1 == "A" and v2 == "B":
            outcome = "win"
        elif v1 == "B" and v2 == "A":
            outcome = "loss"
        else:
            outcome = "tie"
        stats[outcome] += 1
        rows.append({
            "id": r["id"], "type": r["type"], "outcome": outcome,
            "judge_a_first": v1, "judge_b_first": v2,
        })
        print(f"  [pairwise] {r['id']}: {outcome} (A先判={v1}, B先判={v2})")
    return stats, rows


# ────────────────────────────────────────────
# 汇总
# ────────────────────────────────────────────

def summarize(results: list, args, provider, judge_calls: int) -> dict:
    neg = [r for r in results if r["type"] == "negative"]
    pos = [r for r in results if r["type"] != "negative"]

    def by_verdict(rows, v):
        return sum(1 for r in rows if r.get("verdict") == v)

    # 误拒答归因：positive 却被判 refused，按"第一次检索是否命中"分流
    misref = [r for r in pos if r.get("verdict") == "refused"]
    attribution = {
        "retrieval_miss": [r["id"] for r in misref if r.get("retrieval_hit") is False],
        "grader_error": [r["id"] for r in misref if r.get("retrieval_hit") is True],
        "no_signal": [r["id"] for r in misref if r.get("retrieval_hit") is None],
    }

    judged = [r for r in results if r.get("verdict") not in (None, "unknown")]
    agree = (sum(1 for r in judged if (r["verdict"] == "refused") == r["refused_keyword"])
             / len(judged)) if judged else None

    pos_answered = [r for r in pos if r.get("verdict") != "refused"]
    return {
        "model": args.model,
        "judge_model": args.judge_model,
        "llm_calls_total": provider.calls,
        "judge_calls": judge_calls,
        "negative": {
            "n": len(neg),
            "refused": by_verdict(neg, "refused"),
            "hallucinated": by_verdict(neg, "hallucinated") + by_verdict(neg, "wrong"),
            "refusal_rate": round(by_verdict(neg, "refused") / len(neg), 4) if neg else None,
            "note": "拒答率 = 负样本被判 refused 的比例（judge 口径），期望 10/10",
        },
        "positive": {
            "n": len(pos),
            "answered": len(pos_answered),
            "verdicts": {v: by_verdict(pos, v) for v in VERDICTS},
            "quality_pass": (by_verdict(pos, "correct") + by_verdict(pos, "partial")),
            "with_citation": sum(1 for r in pos_answered if r["has_citation"]),
            "misrefusal_attribution": attribution,
            "note": "误拒答归因：retrieval_miss=第一次检索未召回（检索层问题），"
                    "grader_error=检索已命中仍拒答（编排层问题）",
        },
        "judge_keyword_agreement": round(agree, 4) if agree is not None else None,
        "judge_keyword_agreement_note": "judge 与关键词拒答判定的一致率；显著低于 1.0 时"
                                        "优先排查 judge prompt 而非系统行为",
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--judge-model", default=None,
                    help="judge 用不同模型（防同模型自评偏好）；缺省同 --model")
    ap.add_argument("--out", default=str(BENCH / "results/crag-detail.json"))
    ap.add_argument("--questions-jsonl", default=str(BENCH / "questions.jsonl"),
                    help="题目文件（默认 questions.jsonl；口语集等独立口径用）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题（调试用）")
    ap.add_argument("--no-judge", action="store_true",
                    help="跳过 judge，仅执行系统 + 关键词判定（冒烟用）")
    ap.add_argument("--baseline-json", default=None,
                    help="v2 格式的旧 run 明细，逐题 pairwise 对照（Phase 验收用）")
    args = ap.parse_args()
    if args.judge_model is None:
        args.judge_model = args.model

    provider = SimpleProvider(args.base_url, args.api_key, args.model)
    judge = provider if args.judge_model == args.model else \
        SimpleProvider(args.base_url, args.api_key, args.judge_model)

    # 注入 provider（绕过 FastAPI app.state）
    import backend.app as app_mod
    app_mod.get_shared_provider = lambda: provider

    os.environ["COUNTBOT_RAG_CHUNKS"] = "1"
    from backend.modules.wiki.tool import WikiTool

    judge_calls = 0
    with tempfile.TemporaryDirectory() as td:
        build_wiki_from_corpus(Path(td))
        tool = WikiTool(Path(td))

        questions = [json.loads(l) for l in
                     Path(args.questions_jsonl).read_text(encoding="utf-8").splitlines()
                     if l.strip()]
        if args.limit:
            questions = questions[:args.limit]

        results = []
        for i, q in enumerate(questions, 1):
            out = await tool._handle_ask(q["question"])
            sig = retrieval_signal(tool, q["question"])
            expected = expected_slugs(q)
            retrieval_hit = (bool(expected & set(sig["retrieved_docs"]))
                            if sig["available"] and expected else None)

            rec = {
                "id": q["id"], "type": q["type"], "semantic": q.get("semantic", False),
                "question": q["question"],
                "expected_points": q.get("expected_points", []),
                "answer": out,
                "refused_keyword": detect_refusal_keyword(out),
                "has_citation": detect_citation(out),
                "retrieval_hit": retrieval_hit,
                "retrieved_docs": sig["retrieved_docs"],
            }

            if args.no_judge:
                rec["verdict"] = "refused" if rec["refused_keyword"] else "unknown"
            else:
                v = await judge_answer(judge, q["question"], rec["expected_points"], out)
                judge_calls += 1
                if v:
                    rec.update(v)
                else:
                    rec["verdict"] = "refused" if rec["refused_keyword"] else "unknown"
                    rec["judge_fallback"] = True

            results.append(rec)
            verdict = rec["verdict"]
            hit = "-" if retrieval_hit is None else ("Y" if retrieval_hit else "N")
            print(f"[{i}/{len(questions)}] {q['id']} [{q['type']}] "
                  f"verdict={verdict} retrieval_hit={hit}")

    summary = summarize(results, args, provider, judge_calls)

    pairwise_block = None
    if args.baseline_json:
        print(f"\n===== pairwise 对照（vs {args.baseline_json}）=====")
        stats, rows = await run_pairwise(provider, results, Path(args.baseline_json))
        pairwise_block = {
            "baseline": args.baseline_json,
            "note": "换序双判一致才计票，不一致记 tie（防 position bias 的保守口径）",
            **stats,
            "detail": rows,
        }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"summary": summary, "pairwise": pairwise_block, "detail": results},
        ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n===== CRAG 端到端摘要（v2 judge 口径）=====")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if pairwise_block:
        print("\n===== pairwise =====")
        print(json.dumps({k: v for k, v in pairwise_block.items() if k != "detail"},
                         ensure_ascii=False, indent=1))
    print(f"\n明细已写入: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
