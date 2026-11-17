#!/usr/bin/env python3
"""对比 topup/stat、翻页全量与首页三种口径的今日充值数值。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PAGE_SIZE = 100
MAX_PAGES = 200  # 护栏：单日订单不该超过 2 万条，超出直接报错而不是无限翻页


def _request(base: str, key: str, path: str, params: dict, user_id: str) -> dict:
    """GET 管理面接口并返回 data 节点。"""
    url = f"{base.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "New-Api-User": str(user_id or "1"),
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:200]
        raise RuntimeError(f"{path} HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{path} 连接失败: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} 返回的不是 JSON: {exc}") from exc

    if not payload.get("success", True):
        raise RuntimeError(f"{path} 返回失败: {payload.get('message')}")
    return payload.get("data") or {}


def _day_window(day: dt.date) -> tuple[int, int]:
    start = dt.datetime.combine(day, dt.time.min)
    end = start + dt.timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def _effective_end(t1: int) -> int:
    """统计窗口结束时间取 min(次日 0 点, 当前时刻)。"""
    return min(t1, int(dt.datetime.now().timestamp()))


def _scan_all_topups(base: str, key: str, user_id: str, t0: int, t1: int) -> dict:
    """翻页扫到窗口之外为止，按 create_time 精确归日。"""
    records: list[dict] = []
    page = 1
    while page <= MAX_PAGES:
        data = _request(
            base,
            key,
            "/api/user/topup",
            {"p": page, "page_size": PAGE_SIZE, "start_timestamp": t0, "end_timestamp": t1},
            user_id,
        )
        items = data.get("items") or []
        if not items:
            break
        records.extend(items)
        # 接口按时间倒序，最后一条早于窗口起点就无需再翻
        oldest = items[-1].get("create_time") or 0
        if len(items) < PAGE_SIZE or oldest < t0:
            break
        page += 1
    else:
        raise RuntimeError(f"翻页超过 {MAX_PAGES} 页仍未结束，疑似接口未按时间窗过滤")

    today = [
        r for r in records
        if t0 <= int(r.get("create_time") or 0) < t1 and (r.get("status") or "success") == "success"
    ]
    today_pending = [
        r for r in records
        if t0 <= int(r.get("create_time") or 0) < t1 and (r.get("status") or "") == "pending"
    ]
    return {
        "pages": page,
        "scanned": len(records),
        "count": len(today),
        "money": round(sum(float(r.get("money") or 0) for r in today), 2),
        "pending": len(today_pending),
    }


def _first_page_topups(base: str, key: str, user_id: str, t0: int, t1: int) -> dict:
    """复现「只取第一页」的口径，用来解释错误数字从哪来。"""
    data = _request(
        base,
        key,
        "/api/user/topup",
        {"p": 1, "page_size": PAGE_SIZE, "start_timestamp": t0, "end_timestamp": t1},
        user_id,
    )
    items = data.get("items") or []
    in_window = [r for r in items if t0 <= int(r.get("create_time") or 0) < t1]
    oldest = min((int(r.get("create_time") or 0) for r in items), default=0)
    return {
        "count": len(items),
        "money": round(sum(float(r.get("money") or 0) for r in items), 2),
        "in_window": len(in_window),
        "oldest_date": dt.datetime.fromtimestamp(oldest).date().isoformat() if oldest else "-",
        "spans_multiple_days": bool(oldest and oldest < t0),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="今日充值数值溯源（topup/stat vs 翻页 vs 首页）")
    parser.add_argument("--date", help="统计日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON")
    args = parser.parse_args(argv)

    base = os.environ.get("NEWAPI_BASE_URL", "").strip()
    key = os.environ.get("NEWAPI_ADMIN_KEY", "").strip()
    user_id = os.environ.get("NEWAPI_USER_ID", "1").strip() or "1"
    if not base or not key:
        print("缺少凭证：请设置 NEWAPI_BASE_URL 与 NEWAPI_ADMIN_KEY 环境变量", file=sys.stderr)
        return 2

    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    t0, t1 = _day_window(day)
    # 结束时间收敛到当前时刻：传未来时间可能直接返回 0
    api_end = _effective_end(t1)

    stat = _request(
        base, key, "/api/user/topup/stat",
        {"start_timestamp": t0, "end_timestamp": api_end}, user_id,
    ).get("summary") or {}
    stat_count = int(stat.get("total_count") or 0)
    stat_money = round(float(stat.get("total_money") or 0), 2)

    scanned = _scan_all_topups(base, key, user_id, t0, api_end)
    first_page = _first_page_topups(base, key, user_id, t0, api_end)

    verdict = "OK" if (stat_count, stat_money) == (scanned["count"], scanned["money"]) else "MISMATCH"
    result = {
        "date": day.isoformat(),
        "verdict": verdict,
        "authoritative": {
            "source": "/api/user/topup/stat",
            "count": stat_count,
            "money": stat_money,
            "user_count": stat.get("user_count"),
            "new_user_number": stat.get("new_user_number"),
        },
        "recount": {
            "source": "/api/user/topup (all pages)",
            "count": scanned["count"],
            "money": scanned["money"],
            "scanned_records": scanned["scanned"],
            "pages": scanned["pages"],
            "pending": scanned["pending"],
        },
        "naive_first_page": {
            "source": "/api/user/topup (p=1 only)",
            "count": first_page["count"],
            "money": first_page["money"],
            "in_window": first_page["in_window"],
            "oldest_date": first_page["oldest_date"],
            "spans_multiple_days": first_page["spans_multiple_days"],
        },
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if verdict == "OK" else 1

    print(f"日期 {day.isoformat()}")
    print(f"  权威口径  /api/user/topup/stat   {stat_count:>5} 笔  {stat_money:>12.2f}")
    print(f"  独立复算  翻页全量 {scanned['pages']} 页        {scanned['count']:>5} 笔  "
          f"{scanned['money']:>12.2f}   (扫描 {scanned['scanned']} 条，pending {scanned['pending']})")
    print(f"  错误口径  只看第 1 页(100)      {first_page['count']:>5} 笔  "
          f"{first_page['money']:>12.2f}   (其中当天 {first_page['in_window']} 条，"
          f"最旧 {first_page['oldest_date']})")

    if first_page["spans_multiple_days"]:
        print("\n注意：第一页已经跨天，直接用首页条数当「今日笔数」必然偏大——"
              "应该用 topup/stat 或翻页复算的口径。")

    if verdict == "OK":
        print("\n结论：两种正确口径一致，数据可信。")
        return 0

    print("\n结论：口径不一致，请以 /api/user/topup/stat 为准并检查翻页过滤条件。")
    print(f"  笔数差 {scanned['count'] - stat_count:+d}，金额差 {scanned['money'] - stat_money:+.2f}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f"执行失败：{exc}", file=sys.stderr)
        sys.exit(3)
