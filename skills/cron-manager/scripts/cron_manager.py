#!/usr/bin/env python3
"""定时任务管理工具

通过 REST API 管理 CountBot 定时任务的完整 CRUD 操作。
支持创建、查看、修改、删除、启用/禁用、手动触发、验证表达式。
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
import urllib.parse

# API 基础地址
API_BASE = "http://127.0.0.1:8000/api/cron"

# 内置任务前缀
BUILTIN_PREFIX = "builtin:"


def _api_request(method: str, path: str, data: dict | None = None) -> dict:
    """发送 API 请求"""
    url = f"{API_BASE}{path}"
    headers = {"Content-Type": "application/json"}

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            detail = json.loads(body).get("detail", body)
        except (json.JSONDecodeError, AttributeError):
            detail = body
        print(f"错误 ({e.code}): {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"连接失败: {e.reason}", file=sys.stderr)
        print("请确认 CountBot 后端服务正在运行", file=sys.stderr)
        sys.exit(1)


def _find_job_id(partial_id: str) -> str:
    """通过前缀匹配找到完整的 job_id（排除内置任务）"""
    result = _api_request("GET", "/jobs")
    jobs = result.get("jobs", [])

    # 排除内置任务
    user_jobs = [j for j in jobs if not j["id"].startswith(BUILTIN_PREFIX)]
    matches = [j for j in user_jobs if j["id"].startswith(partial_id)]

    if len(matches) == 0:
        # 检查是否匹配到了内置任务
        builtin_match = [j for j in jobs if j["id"].startswith(partial_id) and j["id"].startswith(BUILTIN_PREFIX)]
        if builtin_match:
            print(f"错误: [{builtin_match[0]['name']}] 是内置系统任务，不可操作", file=sys.stderr)
            sys.exit(1)
        print(f"错误: 未找到匹配 '{partial_id}' 的任务", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"错误: '{partial_id}' 匹配到多个任务:", file=sys.stderr)
        for m in matches:
            print(f"  {m['id'][:8]}  {m['name']}", file=sys.stderr)
        print("请提供更长的 ID 前缀", file=sys.stderr)
        sys.exit(1)
    return matches[0]["id"]


def _format_job(job: dict, verbose: bool = False) -> str:
    """格式化任务信息"""
    lines = []
    status = "启用" if job["enabled"] else "禁用"

    lines.append(f"任务: {job['name']}")
    lines.append(f"ID: {job['id']}")
    lines.append(f"Cron: {job['schedule']}")
    lines.append(f"状态: {status}")

    if verbose:
        lines.append(f"消息: {job['message']}")
    else:
        msg = job["message"]
        lines.append(f"消息: {msg[:80]}{'...' if len(msg) > 80 else ''}")

    if job.get("channel"):
        deliver = "是" if job.get("deliver_response") else "否"
        lines.append(f"渠道: {job['channel']}:{job.get('chat_id', '')}")
        lines.append(f"投递结果: {deliver}")

    if job.get("next_run"):
        lines.append(f"下次运行: {job['next_run']}")
    if job.get("last_run"):
        lines.append(f"上次运行: {job['last_run']}")
    if job.get("last_status"):
        lines.append(f"上次状态: {job['last_status']}")
    if job.get("run_count"):
        lines.append(f"执行次数: {job['run_count']} (失败: {job.get('error_count', 0)})")

    return "\n".join(lines)


def cmd_list(args):
    """列出所有定时任务（不显示内置系统任务）"""
    result = _api_request("GET", "/jobs")
    jobs = result.get("jobs", [])

    # 完全过滤掉内置任务
    user_jobs = [j for j in jobs if not j["id"].startswith(BUILTIN_PREFIX)]

    if not user_jobs:
        print("暂无定时任务")
        return

    print(f"共 {len(user_jobs)} 个定时任务:\n")
    for i, job in enumerate(user_jobs, 1):
        status = "启用" if job["enabled"] else "禁用"
        channel = job.get("channel") or "-"
        next_run = (job.get("next_run") or "-")[:19]
        msg = job["message"][:40] + ("..." if len(job["message"]) > 40 else "")
        print(f"  {i}. [{job['id'][:8]}] {job['name']}")
        print(f"     Cron: {job['schedule']}  状态: {status}  渠道: {channel}")
        print(f"     消息: {msg}")
        print(f"     下次运行: {next_run}")
        print()


def cmd_info(args):
    """查看任务详情"""
    job_id = _find_job_id(args.job_id)
    result = _api_request("GET", f"/jobs/{job_id}")
    job = result.get("job", result)
    print(_format_job(job, verbose=True))

    # 显示完整响应和错误
    last_resp = result.get("last_response")
    last_err = result.get("last_error")
    if last_resp:
        print(f"\n上次响应:\n{last_resp[:500]}")
    if last_err:
        print(f"\n上次错误:\n{last_err[:500]}")


def cmd_create(args):
    """创建定时任务"""
    if not args.name:
        print("错误: --name 是必需的", file=sys.stderr)
        sys.exit(1)
    if not args.schedule:
        print("错误: --schedule 是必需的", file=sys.stderr)
        sys.exit(1)
    if not args.message:
        print("错误: --message 是必需的", file=sys.stderr)
        sys.exit(1)

    # 先验证表达式
    validate_result = _api_request("POST", "/validate", {"schedule": args.schedule})
    if not validate_result.get("valid"):
        print(f"错误: 无效的 Cron 表达式 '{args.schedule}'", file=sys.stderr)
        sys.exit(1)

    payload = {
        "name": args.name,
        "schedule": args.schedule,
        "message": args.message,
        "enabled": True,
    }

    if args.channel:
        payload["channel"] = args.channel
    if args.chat_id:
        payload["chat_id"] = args.chat_id
    if args.deliver:
        if not args.channel or not args.chat_id:
            print("错误: --deliver 需要同时指定 --channel 和 --chat-id", file=sys.stderr)
            sys.exit(1)
        payload["deliver_response"] = True

    result = _api_request("POST", "/jobs", payload)
    job = result.get("job", result)

    print(f"任务创建成功")
    print(f"ID: {job['id']}")
    print(f"名称: {job['name']}")
    print(f"Cron: {job['schedule']}")
    if job.get("next_run"):
        print(f"下次运行: {job['next_run']}")
    if job.get("channel"):
        print(f"投递渠道: {job['channel']}:{job.get('chat_id', '')}")


def cmd_update(args):
    """修改任务"""
    job_id = _find_job_id(args.job_id)

    payload = {}
    if args.name is not None:
        payload["name"] = args.name
    if args.schedule is not None:
        # 先验证
        validate_result = _api_request("POST", "/validate", {"schedule": args.schedule})
        if not validate_result.get("valid"):
            print(f"错误: 无效的 Cron 表达式 '{args.schedule}'", file=sys.stderr)
            sys.exit(1)
        payload["schedule"] = args.schedule
    if args.message is not None:
        payload["message"] = args.message
    if args.channel is not None:
        payload["channel"] = args.channel
    if args.chat_id is not None:
        payload["chat_id"] = args.chat_id
    if args.deliver is not None:
        payload["deliver_response"] = args.deliver
    if args.enabled is not None:
        payload["enabled"] = args.enabled

    if not payload:
        print("错误: 至少需要指定一个要修改的字段", file=sys.stderr)
        sys.exit(1)

    result = _api_request("PUT", f"/jobs/{job_id}", payload)
    job = result.get("job", result)
    print(f"任务已更新: {job['name']}")
    print(f"Cron: {job['schedule']}")
    if job.get("next_run"):
        print(f"下次运行: {job['next_run']}")


def cmd_delete(args):
    """删除任务"""
    job_id = _find_job_id(args.job_id)

    # 先获取任务名称
    info = _api_request("GET", f"/jobs/{job_id}")
    job = info.get("job", info)
    job_name = job.get("name", job_id)

    _api_request("DELETE", f"/jobs/{job_id}")
    print(f"已删除任务: {job_name} ({job_id[:8]})")


def cmd_enable(args):
    """启用任务"""
    job_id = _find_job_id(args.job_id)
    result = _api_request("PUT", f"/jobs/{job_id}", {"enabled": True})
    job = result.get("job", result)
    print(f"已启用任务: {job['name']}")
    if job.get("next_run"):
        print(f"下次运行: {job['next_run']}")


def cmd_disable(args):
    """禁用任务"""
    job_id = _find_job_id(args.job_id)
    result = _api_request("PUT", f"/jobs/{job_id}", {"enabled": False})
    job = result.get("job", result)
    print(f"已禁用任务: {job['name']}")


def cmd_run(args):
    """手动触发执行"""
    job_id = _find_job_id(args.job_id)
    result = _api_request("POST", f"/jobs/{job_id}/run")
    print(result.get("message", "已提交执行"))


def cmd_validate(args):
    """验证 Cron 表达式"""
    result = _api_request("POST", "/validate", {"schedule": args.expression})
    if result.get("valid"):
        print(f"表达式有效: {args.expression}")
        if result.get("description"):
            print(f"含义: {result['description']}")
        if result.get("next_run"):
            print(f"下次运行: {result['next_run']}")
    else:
        print(f"表达式无效: {args.expression}", file=sys.stderr)
        sys.exit(1)


# ============================================================================
# 会话管理命令（直接操作数据库）
# ============================================================================

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "countbot.db"


def _get_db():
    """获取数据库连接"""
    if not DB_PATH.exists():
        print(f"错误: 数据库文件不存在: {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _get_session_name(job: dict) -> str:
    """获取任务关联的会话名称"""
    channel = job.get("channel")
    chat_id = job.get("chat_id")
    return f"{channel}:{chat_id}" if channel and chat_id else f"cron:{job['id']}"


def _find_session(db, session_name: str):
    """查找会话"""
    return db.execute(
        "SELECT id, name, created_at FROM sessions WHERE name = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (session_name,)
    ).fetchone()


def cmd_messages(args):
    """查看指定任务会话的最近消息"""
    # 先通过 API 获取任务信息
    job_id = _find_job_id(args.job_id)
    result = _api_request("GET", f"/jobs/{job_id}")
    job = result.get("job", result)
    session_name = _get_session_name(job)

    db = _get_db()
    try:
        session = _find_session(db, session_name)
        if not session:
            print("无关联会话（任务可能尚未执行过）")
            return

        messages = db.execute(
            "SELECT role, content, created_at FROM messages "
            "WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session["id"], args.limit)
        ).fetchall()

        if not messages:
            print("会话中无消息")
            return

        print(f"任务 [{job['name']}] 最近 {len(messages)} 条消息:\n")
        for msg in reversed(messages):
            role = "用户" if msg["role"] == "user" else "AI"
            content = msg["content"][:200]
            if len(msg["content"]) > 200:
                content += "..."
            print(f"[{msg['created_at']}] {role}: {content}")
            print()
    finally:
        db.close()


def cmd_clean(args):
    """清理指定任务会话的历史消息"""
    job_id = _find_job_id(args.job_id)
    result = _api_request("GET", f"/jobs/{job_id}")
    job = result.get("job", result)
    session_name = _get_session_name(job)

    db = _get_db()
    try:
        session = _find_session(db, session_name)
        if not session:
            print("无关联会话，无需清理")
            return

        session_id = session["id"]
        total = db.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
            (session_id,)
        ).fetchone()["cnt"]

        if total == 0:
            print("会话中无消息，无需清理")
            return

        keep = args.keep
        if keep >= total:
            print(f"当前共 {total} 条消息，保留数 {keep} >= 总数，无需清理")
            return

        if keep > 0:
            keep_ids = db.execute(
                "SELECT id FROM messages WHERE session_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (session_id, keep)
            ).fetchall()
            keep_id_set = [r["id"] for r in keep_ids]
            placeholders = ",".join(["?"] * len(keep_id_set))
            deleted = db.execute(
                f"DELETE FROM messages WHERE session_id = ? AND id NOT IN ({placeholders})",
                [session_id] + keep_id_set
            ).rowcount
        else:
            deleted = db.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (session_id,)
            ).rowcount

        db.commit()
        print(f"已清理任务 [{job['name']}] 的 {deleted} 条消息，保留 {keep} 条")
    finally:
        db.close()


def cmd_reset(args):
    """重置任务会话（删除会话及所有消息）"""
    job_id = _find_job_id(args.job_id)
    result = _api_request("GET", f"/jobs/{job_id}")
    job = result.get("job", result)
    session_name = _get_session_name(job)

    db = _get_db()
    try:
        session = _find_session(db, session_name)
        if not session:
            print("无关联会话，无需重置")
            return

        session_id = session["id"]
        msg_deleted = db.execute(
            "DELETE FROM messages WHERE session_id = ?",
            (session_id,)
        ).rowcount
        db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        db.commit()

        print(f"已重置任务 [{job['name']}] 的会话，删除 {msg_deleted} 条消息")
        print("下次任务执行时将自动创建新会话")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="CountBot 定时任务管理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # list
    sub.add_parser("list", help="列出所有定时任务")

    # info
    p_info = sub.add_parser("info", help="查看任务详情")
    p_info.add_argument("job_id", help="任务ID（支持前缀匹配）")

    # create
    p_create = sub.add_parser("create", help="创建定时任务")
    p_create.add_argument("--name", required=True, help="任务名称")
    p_create.add_argument("--schedule", required=True, help="Cron 表达式")
    p_create.add_argument("--message", required=True, help="执行时发送给 AI 的消息")
    p_create.add_argument("--channel", help="投递渠道 (feishu/telegram/dingtalk/wechat/qq)")
    p_create.add_argument("--chat-id", help="投递目标 ID")
    p_create.add_argument("--deliver", action="store_true", help="是否投递结果到渠道")

    # update
    p_update = sub.add_parser("update", help="修改任务")
    p_update.add_argument("job_id", help="任务ID")
    p_update.add_argument("--name", help="新名称")
    p_update.add_argument("--schedule", help="新 Cron 表达式")
    p_update.add_argument("--message", help="新执行消息")
    p_update.add_argument("--channel", help="新投递渠道")
    p_update.add_argument("--chat-id", help="新投递目标 ID")
    p_update.add_argument("--deliver", type=lambda x: x.lower() in ("true", "1", "yes"),
                          default=None, help="是否投递结果 (true/false)")
    p_update.add_argument("--enabled", type=lambda x: x.lower() in ("true", "1", "yes"),
                          default=None, help="是否启用 (true/false)")

    # delete
    p_delete = sub.add_parser("delete", help="删除任务")
    p_delete.add_argument("job_id", help="任务ID")

    # enable
    p_enable = sub.add_parser("enable", help="启用任务")
    p_enable.add_argument("job_id", help="任务ID")

    # disable
    p_disable = sub.add_parser("disable", help="禁用任务")
    p_disable.add_argument("job_id", help="任务ID")

    # run
    p_run = sub.add_parser("run", help="手动触发执行")
    p_run.add_argument("job_id", help="任务ID")

    # validate
    p_validate = sub.add_parser("validate", help="验证 Cron 表达式")
    p_validate.add_argument("expression", help="Cron 表达式")

    # messages (会话管理)
    p_msg = sub.add_parser("messages", help="查看任务会话消息")
    p_msg.add_argument("job_id", help="任务ID")
    p_msg.add_argument("--limit", type=int, default=20, help="显示条数（默认20）")

    # clean (会话管理)
    p_clean = sub.add_parser("clean", help="清理任务会话消息")
    p_clean.add_argument("job_id", help="任务ID")
    p_clean.add_argument("--keep", type=int, default=10, help="保留最近N条（默认10）")

    # reset (会话管理)
    p_reset = sub.add_parser("reset", help="重置任务会话")
    p_reset.add_argument("job_id", help="任务ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "list": cmd_list,
        "info": cmd_info,
        "create": cmd_create,
        "update": cmd_update,
        "delete": cmd_delete,
        "enable": cmd_enable,
        "disable": cmd_disable,
        "run": cmd_run,
        "validate": cmd_validate,
        "messages": cmd_messages,
        "clean": cmd_clean,
        "reset": cmd_reset,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
