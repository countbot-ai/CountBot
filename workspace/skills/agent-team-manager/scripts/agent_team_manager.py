#!/usr/bin/env python3
"""多智能体团队管理工具

通过 REST API 管理 CountBot 的多智能体团队、团队成员和团队级模型配置。
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


API_BASE = "http://127.0.0.1:8000/api/agent-teams"


BUILTIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "document-analysis": {
        "name": "文档深度分析",
        "description": "理解文档 → 提取要点 → 分析问题 → 生成总结报告",
        "mode": "pipeline",
        "cross_review": False,
        "enable_skills": True,
        "is_active": True,
        "agents": [
            {
                "id": "reader",
                "role": "文档理解专家",
                "task": "通读文档，理解整体结构和核心内容",
                "system_prompt": (
                    "你是文档理解专家，擅长快速把握文档核心内容与结构。"
                    "先识别文档类型和章节关系，再提炼主题、关键概念和重点段落。"
                ),
                "depends_on": [],
            },
            {
                "id": "extractor",
                "role": "信息提取专家",
                "task": "从文档中提取关键信息、数据和观点",
                "system_prompt": (
                    "你是信息提取专家，负责抽取关键数据、核心观点、重要定义和引用来源。"
                    "输出时尽量结构化并保留上下文。"
                ),
                "depends_on": [],
            },
            {
                "id": "analyzer",
                "role": "批判性分析专家",
                "task": "分析文档的逻辑性、完整性和潜在问题",
                "system_prompt": (
                    "你是批判性分析专家，重点检查论证链、信息缺口、偏见、假设和局限性，"
                    "并提出需要进一步验证的问题。"
                ),
                "depends_on": [],
            },
            {
                "id": "summarizer",
                "role": "报告撰写专家",
                "task": "整合前序分析，生成结构化的分析报告",
                "system_prompt": (
                    "你是报告撰写专家，负责综合前面各角色输出，"
                    "形成结构清晰、重点明确、可执行的总结报告。"
                ),
                "depends_on": [],
            },
        ],
    }
}


def _api_request(method: str, path: str, data: Optional[dict] = None) -> Any:
    url = f"{API_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body_text).get("detail", body_text)
        except (json.JSONDecodeError, AttributeError):
            detail = body_text
        print(f"错误 ({exc.code}): {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"连接失败: {exc.reason}", file=sys.stderr)
        print("请确认 CountBot 后端服务正在运行", file=sys.stderr)
        sys.exit(1)


def _list_teams() -> List[dict]:
    result = _api_request("GET", "/")
    return result if isinstance(result, list) else []


def _match_single(items: List[dict], ref: str, kind: str, label_getter) -> dict:
    exact_label_matches = [item for item in items if label_getter(item) == ref]
    if len(exact_label_matches) == 1:
        return exact_label_matches[0]

    exact_id_matches = [item for item in items if item.get("id") == ref]
    if len(exact_id_matches) == 1:
        return exact_id_matches[0]

    prefix_id_matches = [item for item in items if str(item.get("id", "")).startswith(ref)]
    if len(prefix_id_matches) == 1:
        return prefix_id_matches[0]

    partial_label_matches = [item for item in items if ref in str(label_getter(item))]
    if len(partial_label_matches) == 1:
        return partial_label_matches[0]

    matches = exact_label_matches or exact_id_matches or prefix_id_matches or partial_label_matches
    if not matches:
        print(f"错误: 未找到匹配 '{ref}' 的{kind}", file=sys.stderr)
        sys.exit(1)

    print(f"错误: '{ref}' 匹配到多个{kind}:", file=sys.stderr)
    for item in matches:
        print(f"  {item.get('id', '-')[:12]}  {label_getter(item)}", file=sys.stderr)
    print("请提供更精确的名称或 ID", file=sys.stderr)
    sys.exit(1)


def _resolve_team(team_ref: str) -> dict:
    return _match_single(_list_teams(), team_ref, "团队", lambda item: item.get("name", ""))


def _get_team(team_ref: str) -> dict:
    team = _resolve_team(team_ref)
    return _api_request("GET", f"/{team['id']}")


def _resolve_member(team: dict, member_ref: str) -> dict:
    members = team.get("agents", []) or []
    return _match_single(members, member_ref, "成员", lambda item: item.get("role") or item.get("perspective") or item.get("id", ""))


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("布尔值仅支持 true/false")


def _load_json_file(path_str: str) -> Any:
    path = Path(path_str)
    if not path.exists():
        print(f"错误: 文件不存在: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"错误: JSON 格式错误: {exc}", file=sys.stderr)
        sys.exit(1)


def _normalize_agent(agent: dict) -> dict:
    data = {
        "id": str(agent.get("id", "")).strip(),
        "role": str(agent.get("role", "") or ""),
        "system_prompt": agent.get("system_prompt"),
        "task": str(agent.get("task", "") or ""),
        "perspective": agent.get("perspective"),
        "depends_on": list(agent.get("depends_on", []) or []),
        "condition": agent.get("condition"),
    }
    if data["system_prompt"] == "":
        data["system_prompt"] = None
    if data["perspective"] == "":
        data["perspective"] = None
    if not data["depends_on"]:
        data["depends_on"] = []
    if not data["condition"]:
        data["condition"] = None
    return data


def _validate_agents(mode: str, agents: List[dict]) -> None:
    ids = [str(agent.get("id", "")).strip() for agent in agents]
    if any(not agent_id for agent_id in ids):
        print("错误: 每个成员都必须有非空 id", file=sys.stderr)
        sys.exit(1)
    if len(ids) != len(set(ids)):
        print("错误: 同一团队内成员 id 必须唯一", file=sys.stderr)
        sys.exit(1)

    id_set = set(ids)
    for agent in agents:
        agent_id = agent["id"]
        depends_on = agent.get("depends_on") or []

        if mode == "graph":
            for dep in depends_on:
                if dep == agent_id:
                    print(f"错误: 成员 '{agent_id}' 不能依赖自己", file=sys.stderr)
                    sys.exit(1)
                if dep not in id_set:
                    print(f"错误: 成员 '{agent_id}' 依赖了不存在的成员 '{dep}'", file=sys.stderr)
                    sys.exit(1)

            condition = agent.get("condition")
            if condition:
                node = condition.get("node")
                if not node or node not in id_set:
                    print(f"错误: 成员 '{agent_id}' 的条件引用了不存在的节点 '{node}'", file=sys.stderr)
                    sys.exit(1)
                if condition.get("type") not in {"output_contains", "output_not_contains"}:
                    print(f"错误: 成员 '{agent_id}' 的 condition.type 无效", file=sys.stderr)
                    sys.exit(1)
        else:
            if depends_on:
                print(f"错误: 当前模式 '{mode}' 不支持 depends_on，请仅在 graph 模式使用", file=sys.stderr)
                sys.exit(1)
            if agent.get("condition"):
                print(f"错误: 当前模式 '{mode}' 不支持 condition，请仅在 graph 模式使用", file=sys.stderr)
                sys.exit(1)


def _build_condition(args) -> Optional[dict]:
    if getattr(args, "clear_condition", False):
        return None

    condition_type = getattr(args, "condition_type", None)
    condition_node = getattr(args, "condition_node", None)
    condition_text = getattr(args, "condition_text", None)

    provided = [condition_type is not None, condition_node is not None, condition_text is not None]
    if any(provided) and not all(provided):
        print("错误: condition 需要同时提供 --condition-type --condition-node --condition-text", file=sys.stderr)
        sys.exit(1)

    if not all(provided):
        return None

    return {
        "type": condition_type,
        "node": condition_node,
        "text": condition_text,
    }


def _parse_depends(depends_on: Optional[str]) -> List[str]:
    if not depends_on:
        return []
    return [item.strip() for item in depends_on.split(",") if item.strip()]


def _load_agents_input(agents_file: Optional[str], agents_json: Optional[str]) -> Optional[List[dict]]:
    raw = None
    if agents_file:
        raw = _load_json_file(agents_file)
    elif agents_json:
        try:
            raw = json.loads(agents_json)
        except json.JSONDecodeError as exc:
            print(f"错误: --agents-json 不是合法 JSON: {exc}", file=sys.stderr)
            sys.exit(1)

    if raw is None:
        return None

    if isinstance(raw, dict) and "agents" in raw:
        raw = raw["agents"]
    if not isinstance(raw, list):
        print("错误: agents 输入必须是数组，或包含 agents 数组的对象", file=sys.stderr)
        sys.exit(1)
    return [_normalize_agent(agent) for agent in raw]


def _format_team(team: dict, verbose: bool = False) -> str:
    lines = [
        f"团队: {team['name']}",
        f"ID: {team['id']}",
        f"模式: {team['mode']}",
        f"状态: {'激活' if team.get('is_active', True) else '停用'}",
        f"技能系统: {'开启' if team.get('enable_skills') else '关闭'}",
        f"自定义模型: {'是' if team.get('use_custom_model') else '否'}",
        f"成员数: {len(team.get('agents', []) or [])}",
    ]

    if team.get("mode") == "council":
        lines.append(f"交叉评审: {'开启' if team.get('cross_review', True) else '关闭'}")
    if team.get("description"):
        lines.append(f"描述: {team['description']}")

    if verbose:
        lines.append("")
        lines.append("成员:")
        agents = team.get("agents", []) or []
        if not agents:
            lines.append("  - 暂无成员")
        else:
            for agent in agents:
                title = agent.get("role") or agent.get("perspective") or agent.get("id")
                lines.append(f"  - {agent.get('id')}: {title}")
                if agent.get("task"):
                    lines.append(f"    task: {agent['task']}")
                if agent.get("system_prompt"):
                    lines.append(f"    system_prompt: {agent['system_prompt']}")
                if agent.get("perspective"):
                    lines.append(f"    perspective: {agent['perspective']}")
                if agent.get("depends_on"):
                    lines.append(f"    depends_on: {', '.join(agent['depends_on'])}")
                if agent.get("condition"):
                    cond = agent["condition"]
                    lines.append(f"    condition: {cond.get('type')} {cond.get('node')} {cond.get('text')}")
    return "\n".join(lines)


def cmd_list(_args) -> None:
    teams = _list_teams()
    if not teams:
        print("暂无多智能体团队")
        return

    print(f"共 {len(teams)} 个团队:\n")
    for index, team in enumerate(teams, 1):
        desc = (team.get("description") or "")[:40]
        if len(team.get("description") or "") > 40:
            desc += "..."
        print(f"  {index}. [{team['id'][:8]}] {team['name']}")
        print(f"     模式: {team['mode']}  成员: {len(team.get('agents', []) or [])}  状态: {'激活' if team.get('is_active', True) else '停用'}")
        print(f"     技能: {'开' if team.get('enable_skills') else '关'}  自定义模型: {'是' if team.get('use_custom_model') else '否'}")
        if desc:
            print(f"     描述: {desc}")
        print()


def cmd_info(args) -> None:
    team = _get_team(args.team_ref)
    print(_format_team(team, verbose=True))


def cmd_template_list(_args) -> None:
    print("内置模板:")
    for key, template in BUILTIN_TEMPLATES.items():
        print(f"  - {key}: {template['name']} ({template['mode']})")
        print(f"    {template.get('description', '')}")


def _build_create_payload(args) -> dict:
    payload: Dict[str, Any] = {
        "name": args.name,
        "description": args.description,
        "mode": args.mode,
        "agents": [],
        "is_active": not args.inactive,
        "cross_review": args.cross_review if args.cross_review is not None else True,
        "enable_skills": args.enable_skills,
    }

    if args.template:
        template = BUILTIN_TEMPLATES.get(args.template)
        if not template:
            print(f"错误: 不支持的模板 '{args.template}'", file=sys.stderr)
            sys.exit(1)
        payload = {
            "name": template["name"],
            "description": template.get("description"),
            "mode": template["mode"],
            "agents": copy.deepcopy(template.get("agents", [])),
            "is_active": template.get("is_active", True),
            "cross_review": template.get("cross_review", True),
            "enable_skills": template.get("enable_skills", False),
        }

    if args.name is not None:
        payload["name"] = args.name
    if args.description is not None:
        payload["description"] = args.description
    if args.mode is not None:
        payload["mode"] = args.mode
    if args.cross_review is not None:
        payload["cross_review"] = args.cross_review
    if args.enable_skills:
        payload["enable_skills"] = True
    if args.disable_skills:
        payload["enable_skills"] = False
    if args.active:
        payload["is_active"] = True
    if args.inactive:
        payload["is_active"] = False

    agents = _load_agents_input(args.agents_file, args.agents_json)
    if agents is not None:
        payload["agents"] = agents

    if not payload.get("name"):
        print("错误: 创建团队必须提供 --name，或使用带默认名称的 --template", file=sys.stderr)
        sys.exit(1)
    if not payload.get("mode"):
        print("错误: 创建团队必须提供 --mode，或使用带默认模式的 --template", file=sys.stderr)
        sys.exit(1)

    payload["agents"] = [_normalize_agent(agent) for agent in payload.get("agents", [])]
    _validate_agents(payload["mode"], payload["agents"])
    return payload


def cmd_create(args) -> None:
    payload = _build_create_payload(args)
    team = _api_request("POST", "/", payload)
    print("团队创建成功")
    print(_format_team(team, verbose=False))


def cmd_update(args) -> None:
    current = _get_team(args.team_ref)
    payload: Dict[str, Any] = {}

    if args.name is not None:
        payload["name"] = args.name
    if args.description is not None:
        payload["description"] = args.description
    if args.mode is not None:
        payload["mode"] = args.mode
    if args.cross_review is not None:
        payload["cross_review"] = args.cross_review
    if args.enable_skills:
        payload["enable_skills"] = True
    if args.disable_skills:
        payload["enable_skills"] = False
    if args.active:
        payload["is_active"] = True
    if args.inactive:
        payload["is_active"] = False

    agents = _load_agents_input(args.agents_file, args.agents_json)
    if agents is not None:
        payload["agents"] = agents

    if not payload:
        print("错误: 至少需要提供一个要修改的字段", file=sys.stderr)
        sys.exit(1)

    mode = payload.get("mode", current["mode"])
    future_agents = payload.get("agents", current.get("agents", []) or [])
    future_agents = [_normalize_agent(agent) for agent in future_agents]
    _validate_agents(mode, future_agents)
    if "agents" in payload:
        payload["agents"] = future_agents

    team = _api_request("PUT", f"/{current['id']}", payload)
    print("团队已更新")
    print(_format_team(team, verbose=False))


def cmd_delete(args) -> None:
    team = _resolve_team(args.team_ref)
    _api_request("DELETE", f"/{team['id']}")
    print(f"已删除团队: {team['name']} ({team['id'][:8]})")


def cmd_member_list(args) -> None:
    team = _get_team(args.team_ref)
    agents = team.get("agents", []) or []
    if not agents:
        print(f"团队 [{team['name']}] 暂无成员")
        return

    print(f"团队 [{team['name']}] 共 {len(agents)} 个成员:\n")
    for index, agent in enumerate(agents, 1):
        print(f"  {index}. {agent['id']}  {agent.get('role') or agent.get('perspective') or '-'}")
        if agent.get("task"):
            print(f"     task: {agent['task']}")
        if agent.get("system_prompt"):
            print(f"     system_prompt: {agent['system_prompt']}")
        if agent.get("perspective"):
            print(f"     perspective: {agent['perspective']}")
        if agent.get("depends_on"):
            print(f"     depends_on: {', '.join(agent['depends_on'])}")
        if agent.get("condition"):
            cond = agent["condition"]
            print(f"     condition: {cond.get('type')} {cond.get('node')} {cond.get('text')}")
        print()


def _save_agents(team: dict, agents: List[dict]) -> dict:
    mode = team["mode"]
    normalized = [_normalize_agent(agent) for agent in agents]
    _validate_agents(mode, normalized)
    return _api_request("PUT", f"/{team['id']}", {"agents": normalized})


def cmd_member_add(args) -> None:
    team = _get_team(args.team_ref)
    agents = team.get("agents", []) or []

    if any(agent.get("id") == args.id for agent in agents):
        print(f"错误: 成员 id '{args.id}' 已存在", file=sys.stderr)
        sys.exit(1)

    agent = _normalize_agent({
        "id": args.id,
        "role": args.role or "",
        "system_prompt": args.system_prompt,
        "task": args.task or "",
        "perspective": args.perspective,
        "depends_on": [] if args.clear_depends_on else _parse_depends(args.depends_on),
        "condition": _build_condition(args),
    })

    updated = _save_agents(team, agents + [agent])
    print(f"已添加成员到团队 [{updated['name']}]: {agent['id']}")


def cmd_member_update(args) -> None:
    team = _get_team(args.team_ref)
    agents = team.get("agents", []) or []
    member = _resolve_member(team, args.member_ref)

    updated_agents: List[dict] = []
    for agent in agents:
        if agent.get("id") != member.get("id"):
            updated_agents.append(agent)
            continue

        next_agent = _normalize_agent(agent)
        if args.new_id is not None:
            next_agent["id"] = args.new_id
        if args.role is not None:
            next_agent["role"] = args.role
        if args.task is not None:
            next_agent["task"] = args.task
        if args.system_prompt is not None:
            next_agent["system_prompt"] = args.system_prompt or None
        if args.perspective is not None:
            next_agent["perspective"] = args.perspective or None
        if args.clear_depends_on:
            next_agent["depends_on"] = []
        elif args.depends_on is not None:
            next_agent["depends_on"] = _parse_depends(args.depends_on)

        if args.clear_condition:
            next_agent["condition"] = None
        else:
            new_condition = _build_condition(args)
            if new_condition is not None:
                next_agent["condition"] = new_condition

        updated_agents.append(next_agent)

    if args.new_id is not None:
        old_id = member["id"]
        for agent in updated_agents:
            depends_on = agent.get("depends_on") or []
            agent["depends_on"] = [args.new_id if dep == old_id else dep for dep in depends_on]
            condition = agent.get("condition")
            if condition and condition.get("node") == old_id:
                condition["node"] = args.new_id

    updated = _save_agents(team, updated_agents)
    print(f"已更新团队 [{updated['name']}] 的成员: {member['id']}")


def cmd_member_delete(args) -> None:
    team = _get_team(args.team_ref)
    member = _resolve_member(team, args.member_ref)
    target_id = member["id"]
    next_agents = []

    for agent in team.get("agents", []) or []:
        if agent.get("id") == target_id:
            continue
        normalized = _normalize_agent(agent)
        normalized["depends_on"] = [dep for dep in normalized.get("depends_on", []) if dep != target_id]
        condition = normalized.get("condition")
        if condition and condition.get("node") == target_id:
            normalized["condition"] = None
        next_agents.append(normalized)

    updated = _save_agents(team, next_agents)
    print(f"已从团队 [{updated['name']}] 删除成员: {target_id}")


def cmd_config(args) -> None:
    team = _resolve_team(args.team_ref)
    result = _api_request("GET", f"/{team['id']}/config")

    print(f"团队: {team['name']}")
    print(f"团队 ID: {team['id']}")
    print(f"使用自定义模型: {'是' if result.get('use_custom_model') else '否'}")
    print("")
    print("当前有效配置:")
    for key, value in result.get("model_settings", {}).items():
        masked = "***" if key == "api_key" and value else value
        print(f"  {key}: {masked}")
    print("")
    print("全局默认:")
    for key, value in result.get("global_defaults", {}).items():
        masked = "***" if key == "api_key" and value else value
        print(f"  {key}: {masked}")


def cmd_config_set(args) -> None:
    team = _resolve_team(args.team_ref)
    payload: Dict[str, Any] = {}
    for key in ("provider", "model", "api_key", "api_base"):
        value = getattr(args, key)
        if value is not None:
            payload[key] = value
    if args.temperature is not None:
        payload["temperature"] = args.temperature
    if args.max_tokens is not None:
        payload["max_tokens"] = args.max_tokens

    if not payload:
        print("错误: 至少需要提供一个模型配置字段", file=sys.stderr)
        sys.exit(1)

    result = _api_request("PUT", f"/{team['id']}/config", payload)
    print(result.get("message", "团队模型配置已更新"))


def cmd_config_reset(args) -> None:
    team = _resolve_team(args.team_ref)
    result = _api_request("DELETE", f"/{team['id']}/config")
    print(result.get("message", "团队模型配置已重置"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CountBot 多智能体团队管理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    sub.add_parser("list", help="列出所有团队")

    p_info = sub.add_parser("info", help="查看团队详情")
    p_info.add_argument("team_ref", help="团队名称、完整 ID 或 ID 前缀")

    sub.add_parser("template-list", help="列出内置模板")

    p_create = sub.add_parser("create", help="创建团队")
    p_create.add_argument("--name", help="团队名称")
    p_create.add_argument("--description", help="团队描述")
    p_create.add_argument("--mode", choices=["pipeline", "graph", "council"], help="协作模式")
    p_create.add_argument("--template", choices=sorted(BUILTIN_TEMPLATES.keys()), help="按内置模板创建")
    p_create.add_argument("--agents-file", help="成员 JSON 文件路径")
    p_create.add_argument("--agents-json", help="成员 JSON 字符串")
    p_create.add_argument("--cross-review", dest="cross_review", action="store_true", default=None, help="开启交叉评审（Council）")
    p_create.add_argument("--no-cross-review", dest="cross_review", action="store_false", help="关闭交叉评审（Council）")
    p_create.add_argument("--enable-skills", action="store_true", help="开启技能系统")
    p_create.add_argument("--disable-skills", action="store_true", help="关闭技能系统")
    p_create.add_argument("--active", action="store_true", help="激活团队")
    p_create.add_argument("--inactive", action="store_true", help="创建为停用状态")

    p_update = sub.add_parser("update", help="修改团队")
    p_update.add_argument("team_ref", help="团队名称、完整 ID 或 ID 前缀")
    p_update.add_argument("--name", help="新团队名称")
    p_update.add_argument("--description", help="新团队描述")
    p_update.add_argument("--mode", choices=["pipeline", "graph", "council"], help="新协作模式")
    p_update.add_argument("--agents-file", help="用 JSON 文件整体覆盖成员")
    p_update.add_argument("--agents-json", help="用 JSON 字符串整体覆盖成员")
    p_update.add_argument("--cross-review", dest="cross_review", action="store_true", default=None, help="开启交叉评审（Council）")
    p_update.add_argument("--no-cross-review", dest="cross_review", action="store_false", help="关闭交叉评审（Council）")
    p_update.add_argument("--enable-skills", action="store_true", help="开启技能系统")
    p_update.add_argument("--disable-skills", action="store_true", help="关闭技能系统")
    p_update.add_argument("--active", action="store_true", help="激活团队")
    p_update.add_argument("--inactive", action="store_true", help="停用团队")

    p_delete = sub.add_parser("delete", help="删除团队")
    p_delete.add_argument("team_ref", help="团队名称、完整 ID 或 ID 前缀")

    p_member_list = sub.add_parser("member-list", help="列出团队成员")
    p_member_list.add_argument("team_ref", help="团队名称、完整 ID 或 ID 前缀")

    p_member_add = sub.add_parser("member-add", help="添加团队成员")
    p_member_add.add_argument("team_ref", help="团队名称、完整 ID 或 ID 前缀")
    p_member_add.add_argument("--id", required=True, help="成员 ID")
    p_member_add.add_argument("--role", help="角色名")
    p_member_add.add_argument("--task", help="角色任务")
    p_member_add.add_argument("--system-prompt", help="系统提示词")
    p_member_add.add_argument("--perspective", help="视角标签（Council）")
    p_member_add.add_argument("--depends-on", help="依赖成员 ID，多个用逗号分隔（Graph）")
    p_member_add.add_argument("--clear-depends-on", action="store_true", help="清空依赖")
    p_member_add.add_argument("--condition-type", choices=["output_contains", "output_not_contains"], help="条件类型（Graph）")
    p_member_add.add_argument("--condition-node", help="条件引用节点（Graph）")
    p_member_add.add_argument("--condition-text", help="条件匹配文本（Graph）")
    p_member_add.add_argument("--clear-condition", action="store_true", help="清空条件")

    p_member_update = sub.add_parser("member-update", help="修改团队成员")
    p_member_update.add_argument("team_ref", help="团队名称、完整 ID 或 ID 前缀")
    p_member_update.add_argument("member_ref", help="成员 ID、角色名或 ID 前缀")
    p_member_update.add_argument("--new-id", help="新成员 ID")
    p_member_update.add_argument("--role", help="新角色名")
    p_member_update.add_argument("--task", help="新任务")
    p_member_update.add_argument("--system-prompt", help="新系统提示词")
    p_member_update.add_argument("--perspective", help="新视角标签")
    p_member_update.add_argument("--depends-on", help="新的依赖成员 ID，多个用逗号分隔")
    p_member_update.add_argument("--clear-depends-on", action="store_true", help="清空依赖")
    p_member_update.add_argument("--condition-type", choices=["output_contains", "output_not_contains"], help="条件类型")
    p_member_update.add_argument("--condition-node", help="条件引用节点")
    p_member_update.add_argument("--condition-text", help="条件匹配文本")
    p_member_update.add_argument("--clear-condition", action="store_true", help="清空条件")

    p_member_delete = sub.add_parser("member-delete", help="删除团队成员")
    p_member_delete.add_argument("team_ref", help="团队名称、完整 ID 或 ID 前缀")
    p_member_delete.add_argument("member_ref", help="成员 ID、角色名或 ID 前缀")

    p_config = sub.add_parser("config", help="查看团队模型配置")
    p_config.add_argument("team_ref", help="团队名称、完整 ID 或 ID 前缀")

    p_config_set = sub.add_parser("config-set", help="设置团队模型配置")
    p_config_set.add_argument("team_ref", help="团队名称、完整 ID 或 ID 前缀")
    p_config_set.add_argument("--provider", help="模型服务商")
    p_config_set.add_argument("--model", help="模型名称")
    p_config_set.add_argument("--temperature", type=float, help="温度")
    p_config_set.add_argument("--max-tokens", type=int, help="最大输出 token")
    p_config_set.add_argument("--api-key", help="专属 API Key")
    p_config_set.add_argument("--api-base", help="专属 API Base URL")

    p_config_reset = sub.add_parser("config-reset", help="重置团队模型配置")
    p_config_reset.add_argument("team_ref", help="团队名称、完整 ID 或 ID 前缀")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "list": cmd_list,
        "info": cmd_info,
        "template-list": cmd_template_list,
        "create": cmd_create,
        "update": cmd_update,
        "delete": cmd_delete,
        "member-list": cmd_member_list,
        "member-add": cmd_member_add,
        "member-update": cmd_member_update,
        "member-delete": cmd_member_delete,
        "config": cmd_config,
        "config-set": cmd_config_set,
        "config-reset": cmd_config_reset,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
