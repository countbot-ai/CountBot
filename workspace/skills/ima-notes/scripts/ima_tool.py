#!/usr/bin/env python3
"""IMA notes-only CLI."""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ima_client import load_skill_config, post_json, require_credentials


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


class IMAApiError(RuntimeError):
    def __init__(self, endpoint: str, retcode: int, errmsg: str, data: Dict[str, Any]) -> None:
        self.endpoint = endpoint
        self.retcode = retcode
        self.errmsg = errmsg
        self.data = data
        super().__init__(f"{endpoint} failed: retcode={retcode} errmsg={errmsg}")


def repair_mojibake(text: str) -> str:
    if not text:
        return text
    for source_encoding in ("gbk", "gb18030"):
        try:
            candidate = text.encode(source_encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if candidate and candidate != text:
            return candidate
    return text


def unwrap_response(result: Dict[str, Any]) -> tuple[bool, int, str, Dict[str, Any]]:
    if "retcode" in result:
        retcode = int(result.get("retcode", -1))
        errmsg = repair_mojibake(str(result.get("errmsg", "")))
        data = result.get("data", {}) or {}
        return retcode == 0, retcode, errmsg, data if isinstance(data, dict) else {"value": data}
    if "code" in result and "msg" in result:
        code = int(result.get("code", -1))
        msg = repair_mojibake(str(result.get("msg", "")))
        data = result.get("data", {}) or {}
        return code == 0, code, msg, data if isinstance(data, dict) else {"value": data}
    return True, 0, "", result or {}


def api_call(endpoint: str, payload: Dict[str, Any], *, config: Dict[str, Any]) -> Dict[str, Any]:
    result = post_json(endpoint, payload, config=config)
    ok, retcode, errmsg, data = unwrap_response(result)
    if not ok:
        raise IMAApiError(endpoint, retcode, errmsg, data)
    return data


def print_output(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, str):
        print(payload)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def join_keywords(query: Optional[str], keywords: Sequence[str]) -> List[str]:
    result: List[str] = []
    if query and query.strip():
        result.append(query.strip())
    for keyword in keywords:
        value = keyword.strip()
        if not value:
            continue
        parts = [item.strip() for item in value.replace("，", " ").replace("；", " ").replace(",", " ").split() if item.strip()]
        result.extend(parts or [value])
    deduped: List[str] = []
    seen = set()
    for item in result:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def get_text_input(
    *,
    content: Optional[str],
    content_file: Optional[str],
    use_stdin: bool,
) -> str:
    provided = sum(1 for value in [content is not None, content_file is not None, use_stdin] if value)
    if provided != 1:
        raise ValueError("Exactly one of --content, --content-file, or --stdin must be provided.")
    if content is not None:
        return content
    if content_file is not None:
        return Path(content_file).expanduser().resolve().read_text(encoding="utf-8")
    return sys.stdin.read()


def prepare_markdown(title: Optional[str], content: str) -> str:
    cleaned = content.strip()
    if title:
        heading = f"# {title.strip()}"
        if cleaned.startswith("# "):
            return cleaned
        return f"{heading}\n\n{cleaned}".strip()
    return cleaned


def resolve_note_doc_id(
    *,
    config: Dict[str, Any],
    doc_id: str = "",
    title: str = "",
    search_type: int = 0,
) -> str:
    if doc_id.strip():
        return doc_id.strip()
    title = title.strip()
    if not title:
        raise ValueError("Use --doc-id or --title to specify the target note.")
    data = api_call(
        "openapi/note/v1/search_note_book",
        {
            "search_type": search_type,
            "query_info": {"title": title} if search_type == 0 else {"content": title},
            "start": 0,
            "end": 10,
        },
        config=config,
    )
    docs = list(data.get("docs", []) or [])
    exact_matches = []
    for item in docs:
        basic_info = item.get("doc", {}).get("basic_info", {})
        if str(basic_info.get("title", "")).strip().lower() == title.lower():
            exact_matches.append(item)
    matches = exact_matches or docs
    if len(matches) == 1:
        return str(matches[0].get("doc", {}).get("basic_info", {}).get("docid", ""))
    if not matches:
        raise ValueError(f"No note matched: {title}")
    names = ", ".join(str(item.get("doc", {}).get("basic_info", {}).get("title", "")) for item in matches[:10])
    raise ValueError(f"Note title is ambiguous: {title}. Candidates: {names}")


def render_note_search_results(items: Sequence[Dict[str, Any]]) -> str:
    lines = [f"笔记数量: {len(items)}"]
    for item in items:
        basic_info = item.get("doc", {}).get("basic_info", {})
        lines.append(f"- {basic_info.get('title', '')} ({basic_info.get('docid', '')})")
        summary = str(basic_info.get("summary", "")).strip()
        if summary:
            lines.append(f"  摘要: {summary[:180]}")
    return "\n".join(lines)


def command_test(args: argparse.Namespace, config: Dict[str, Any]) -> Dict[str, Any]:
    require_credentials(config)
    tests: List[Dict[str, Any]] = []

    def run(name: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = post_json(endpoint, payload, config=config)
        ok, retcode, errmsg, data = unwrap_response(result)
        item = {
            "name": name,
            "endpoint": endpoint,
            "ok": ok,
            "retcode": retcode,
            "errmsg": errmsg,
            "data": data,
        }
        tests.append(item)
        return item

    note_search = run(
        "search_notes",
        "openapi/note/v1/search_note_book",
        {"search_type": 0, "query_info": {"title": args.note_query}, "start": 0, "end": 5},
    )
    run("list_note_folders", "openapi/note/v1/list_note_folder_by_cursor", {"cursor": "0", "limit": 10})

    doc_id = ""
    if note_search["ok"]:
        docs = note_search["data"].get("docs", []) or []
        if docs:
            doc_id = str(docs[0].get("doc", {}).get("basic_info", {}).get("docid", ""))
    if doc_id:
        run("read_note", "openapi/note/v1/get_doc_content", {"doc_id": doc_id, "target_content_format": 0})

    note_write: Optional[Dict[str, Any]] = None
    note_append: Optional[Dict[str, Any]] = None
    if args.write_note_test:
        title = args.write_note_title or f"CountBot IMA CLI Test {time.strftime('%Y-%m-%d %H:%M:%S')}"
        content = prepare_markdown(title, args.write_note_content)
        note_write = run(
            "create_note",
            "openapi/note/v1/import_doc",
            {"content_format": 1, "content": content},
        )
        created_doc_id = str(note_write["data"].get("doc_id", ""))
        if created_doc_id:
            note_append = run(
                "append_note",
                "openapi/note/v1/append_doc",
                {
                    "doc_id": created_doc_id,
                    "content_format": 1,
                    "content": args.write_note_append_content,
                },
            )

    passed = sum(1 for item in tests if item["ok"])
    return {
        "config_path": config["config_path"],
        "base_url": config["base_url"],
        "passed": passed,
        "total": len(tests),
        "all_passed": passed == len(tests),
        "tests": tests,
        "write_note_enabled": args.write_note_test,
        "write_note_result": note_write,
        "append_note_result": note_append,
        "effective_note_query": args.note_query,
    }


def command_list_note_folders(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    payload = api_call(
        "openapi/note/v1/list_note_folder_by_cursor",
        {"cursor": args.cursor, "limit": args.limit},
        config=config,
    )
    result = {
        "cursor": args.cursor,
        "items": payload.get("note_book_folders", []),
        "next_cursor": payload.get("next_cursor", ""),
        "is_end": payload.get("is_end", True),
    }
    if args.json:
        return result
    lines = [f"笔记本数量: {len(result['items'])}"]
    for item in result["items"]:
        basic_info = item.get("folder", {}).get("basic_info", {})
        lines.append(f"- {basic_info.get('folder_name', '')} ({basic_info.get('folder_id', '')})")
    return "\n".join(lines)


def command_list_notes(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    payload = api_call(
        "openapi/note/v1/list_note_by_folder_id",
        {"folder_id": args.folder_id or "", "cursor": args.cursor, "limit": args.limit},
        config=config,
    )
    result = {
        "folder_id": args.folder_id or "",
        "items": payload.get("note_book_list", []),
        "next_cursor": payload.get("next_cursor", ""),
        "is_end": payload.get("is_end", True),
    }
    if args.json:
        return result
    lines = [f"笔记数量: {len(result['items'])}"]
    for item in result["items"]:
        basic_info = item.get("basic_info", {}).get("basic_info", {})
        lines.append(f"- {basic_info.get('title', '')} ({basic_info.get('docid', '')})")
    return "\n".join(lines)


def command_search_notes(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    queries = join_keywords(args.query, args.keyword)
    if not queries:
        raise ValueError("Use --query or one or more --keyword values.")
    groups: List[Dict[str, Any]] = []
    for query in queries:
        payload = api_call(
            "openapi/note/v1/search_note_book",
            {
                "search_type": 1 if args.search_field == "content" else 0,
                "query_info": {"content": query} if args.search_field == "content" else {"title": query},
                "start": 0,
                "end": args.limit,
            },
            config=config,
        )
        groups.append(
            {
                "query": query,
                "search_field": args.search_field,
                "total_hit_num": payload.get("total_hit_num", "0"),
                "items": list(payload.get("docs", []) or []),
            }
        )
    result = {"groups": groups}
    if args.json:
        return result
    lines: List[str] = []
    for group in groups:
        lines.append(f"关键词: {group['query']} ({group['search_field']})")
        lines.append(render_note_search_results(group["items"]))
    return "\n".join(lines)


def command_read_note(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    doc_id = resolve_note_doc_id(
        config=config,
        doc_id=args.doc_id or "",
        title=args.title or "",
        search_type=1 if args.search_field == "content" else 0,
    )
    payload = api_call(
        "openapi/note/v1/get_doc_content",
        {"doc_id": doc_id, "target_content_format": 0},
        config=config,
    )
    result = {"doc_id": doc_id, "content": payload.get("content", "")}
    if args.json:
        return result
    return str(result["content"])


def command_create_note(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    content = prepare_markdown(
        args.title,
        get_text_input(content=args.content, content_file=args.content_file, use_stdin=args.stdin),
    )
    request_payload: Dict[str, Any] = {"content_format": 1, "content": content}
    if args.folder_id:
        request_payload["folder_id"] = args.folder_id
    payload = api_call("openapi/note/v1/import_doc", request_payload, config=config)
    result = {"doc_id": payload.get("doc_id", ""), "title": args.title or "", "folder_id": args.folder_id or ""}
    if args.json:
        return result
    return f"新建笔记成功: {result['doc_id']}"


def command_append_note(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    doc_id = resolve_note_doc_id(config=config, doc_id=args.doc_id or "", title=args.title or "")
    content = get_text_input(content=args.content, content_file=args.content_file, use_stdin=args.stdin).strip()
    payload = api_call(
        "openapi/note/v1/append_doc",
        {"doc_id": doc_id, "content_format": 1, "content": content},
        config=config,
    )
    result = {"doc_id": payload.get("doc_id", doc_id)}
    if args.json:
        return result
    return f"追加笔记成功: {result['doc_id']}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IMA note CLI")
    parser.add_argument("--config", help="Optional path to config.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def with_json(subparser: argparse.ArgumentParser) -> argparse.ArgumentParser:
        subparser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
        return subparser

    test_parser = with_json(subparsers.add_parser("test", help="Run integrated connectivity checks"))
    test_parser.add_argument("--note-query", default="a", help="Keyword used for note search test")
    test_parser.add_argument("--write-note-test", action="store_true", help="Create and append a temporary test note")
    test_parser.add_argument("--write-note-title", default="", help="Custom title used when --write-note-test is enabled")
    test_parser.add_argument("--write-note-content", default="这是一条由 CountBot IMA CLI 自动创建的测试笔记。", help="Initial markdown body for the write-note test")
    test_parser.add_argument("--write-note-append-content", default="\n\n追加测试内容：IMA CLI append note 验证。", help="Append body used for the write-note test")

    list_note_folders = with_json(subparsers.add_parser("list-note-folders", help="List note folders"))
    list_note_folders.add_argument("--cursor", default="0", help="Pagination cursor")
    list_note_folders.add_argument("--limit", type=int, default=20, help="Maximum number of folders to return")

    list_notes = with_json(subparsers.add_parser("list-notes", help="List notes in a folder"))
    list_notes.add_argument("--folder-id", default="", help="Optional note folder ID")
    list_notes.add_argument("--cursor", default="", help="Pagination cursor")
    list_notes.add_argument("--limit", type=int, default=20, help="Maximum number of notes to return")

    search_notes = with_json(subparsers.add_parser("search-notes", help="Search notes by title or content"))
    search_notes.add_argument("--query", default="", help='Single combined query, for example "运营 周报"')
    search_notes.add_argument("--keyword", action="append", default=[], help='Repeatable keyword. `--keyword "运营 复盘 周报"` 会自动拆成多个关键词分别搜索')
    search_notes.add_argument("--search-field", choices=["title", "content"], default="title", help="Choose whether to search note titles or note content")
    search_notes.add_argument("--limit", type=int, default=10, help="Maximum number of notes returned per query")

    read_note = with_json(subparsers.add_parser("read-note", help="Read the plain-text body of a note"))
    read_note.add_argument("--doc-id", default="", help="Target note doc_id")
    read_note.add_argument("--title", default="", help="Resolve note by unique title")
    read_note.add_argument("--search-field", choices=["title", "content"], default="title", help="How --title is matched before reading")

    create_note = with_json(subparsers.add_parser("create-note", help="Create a new note from Markdown"))
    create_note.add_argument("--title", default="", help="Optional title. If provided, it is converted into a Markdown H1 heading")
    create_note.add_argument("--content", default=None, help="Inline Markdown content")
    create_note.add_argument("--content-file", default=None, help="Read Markdown content from a UTF-8 file")
    create_note.add_argument("--stdin", action="store_true", help="Read Markdown content from standard input")
    create_note.add_argument("--folder-id", default="", help="Optional note folder ID")

    append_note = with_json(subparsers.add_parser("append-note", help="Append Markdown content to an existing note"))
    append_note.add_argument("--doc-id", default="", help="Target note doc_id")
    append_note.add_argument("--title", default="", help="Resolve note by unique title")
    append_note.add_argument("--content", default=None, help="Inline Markdown content")
    append_note.add_argument("--content-file", default=None, help="Read Markdown content from a UTF-8 file")
    append_note.add_argument("--stdin", action="store_true", help="Read Markdown content from standard input")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_skill_config(args.config)

    handlers = {
        "test": command_test,
        "list-note-folders": command_list_note_folders,
        "list-notes": command_list_notes,
        "search-notes": command_search_notes,
        "read-note": command_read_note,
        "create-note": command_create_note,
        "append-note": command_append_note,
    }

    try:
        result = handlers[args.command](args, config)
        print_output(result, as_json=bool(getattr(args, "json", False)))
    except Exception as exc:
        if bool(getattr(args, "json", False)):
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
