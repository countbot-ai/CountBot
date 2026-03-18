"""WorkflowTool — exposes WorkflowEngine as a CountBot tool.

The primary Agent calls ``workflow_run`` to trigger a structured
multi-agent workflow and receives the fully compiled results when
all sub-agents have finished.
"""

import contextvars
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.database import SessionLocal
from backend.models.session import Session
from backend.modules.agent.workflow import WorkflowEngine
from backend.modules.config.loader import config_loader
from backend.modules.session.runtime_config import (
    build_session_model_override,
    resolve_session_runtime_config,
)
from backend.modules.tools.base import Tool


_event_callback_context: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "workflow_tool_event_callback",
    default=None,
)


class WorkflowTool(Tool):
    """Run a structured multi-agent workflow.

    Supports three modes:

    * **pipeline** — sequential stages; each agent receives the accumulated
      outputs of all previous stages as context.
    * **graph** — dependency-DAG; agents whose dependencies are satisfied
      are dispatched in parallel automatically.
    * **council** — multi-perspective deliberation; all members analyse the
      question in parallel (round 1), then cross-review each other's
      positions (round 2), with a final compiled synthesis.
    """

    def __init__(self, subagent_manager, skills=None) -> None:
        self._manager = subagent_manager
        self._skills = skills  # 技能系统实例
        self._session_id: Optional[str] = None
        self._cancel_token = None

    def set_session_id(self, session_id: str) -> None:
        """绑定当前会话 ID，用于实时推送 workflow 事件。"""
        self._session_id = session_id

    def set_cancel_token(self, token) -> None:
        """绑定取消令牌，用于在用户点击停止时中断工作流执行。"""
        self._cancel_token = token

    def set_event_callback(self, callback) -> None:
        """绑定当前异步上下文的工作流事件回调。"""
        _event_callback_context.set(callback)

    def _load_session_model_override(self) -> Optional[Dict[str, Any]]:
        """加载会话级模型覆盖，供工作流子代理继承。"""
        if not self._session_id:
            return None

        try:
            with SessionLocal() as session:
                db_session = session.get(Session, self._session_id)
                if not db_session or not db_session.use_custom_config:
                    return None

                runtime_config = resolve_session_runtime_config(config_loader.config, db_session)
                model_override = build_session_model_override(runtime_config)
                if model_override:
                    logger.info(
                        "Workflow tool inherited session model config: {}/{} (session={})",
                        runtime_config.provider_name,
                        runtime_config.model_name,
                        self._session_id,
                    )
                return model_override
        except Exception as exc:
            logger.warning(
                f"Failed to load session model override for workflow tool: {exc}"
            )
            return None

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "workflow_run"

    @property
    def description(self) -> str:
        return (
            "Run a structured multi-agent workflow and return the compiled results. "
            "Use 'pipeline' for sequential stages where each agent builds on previous outputs. "
            "Use 'graph' for dependency-based parallel execution across independent workstreams. "
            "Use 'council' for multi-perspective analysis: "
            "  - cross_review=True (default): members analyse independently, then cross-review each other's positions. "
            "  - cross_review=False: members analyse independently without cross-review. "
            "Each agent is a fully autonomous sub-agent with access to all standard tools."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["pipeline", "graph", "council"],
                    "description": (
                        "Execution mode: "
                        "'pipeline' (sequential), "
                        "'graph' (dependency DAG with parallel dispatch), "
                        "'council' (multi-perspective deliberation)."
                    ),
                },
                "goal": {
                    "type": "string",
                    "description": (
                        "Overall goal or question driving the workflow. "
                        "For council mode this is the question put to all members."
                    ),
                },
                "agents": {
                    "type": "array",
                    "description": (
                        "Agent definitions. "
                        "Pipeline/Graph: [{\"id\": str, \"role\": str, \"task\": str, \"depends_on\": [str]}]. "
                        "Council: [{\"id\": str, \"perspective\": str}]."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Unique identifier for this agent slot.",
                            },
                            "role": {
                                "type": "string",
                                "description": "Agent role label (pipeline / graph modes).",
                            },
                            "task": {
                                "type": "string",
                                "description": "Specific task assigned to this agent (pipeline / graph).",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "IDs of slots that must complete before this one (graph only). Also accepts 'depends' for backward compatibility.",
                            },
                            "perspective": {
                                "type": "string",
                                "description": "Analytical perspective / role for council members.",
                            },
                        },
                    },
                },
                "cross_review": {
                    "type": "boolean",
                    "description": (
                        "Council mode only: enable cross-review between members. "
                        "True (default) = members review each other's positions in round 2. "
                        "False = members work independently without cross-review."
                    ),
                    "default": True,
                },
                "team_name": {
                    "type": "string",
                    "description": (
                        "Optional: name of a predefined team to use. "
                        "If provided, the system will load the complete team configuration "
                        "(mode, agents, cross_review, enable_skills) from the database."
                    ),
                },
            },
            "required": ["goal"],
        }

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        mode: Optional[str] = None,
        goal: str = "",
        agents: Optional[List[dict]] = None,
        cross_review: bool = True,
        team_name: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        agents = agents or []

        if not goal:
            return "Error: 'goal' must be provided."

        if not team_name and not agents:
            return "Error: either 'team_name' or 'agents' must be provided."

        # 确定是否启用技能系统和团队模型配置
        enable_skills = False
        team_model_config = None

        # 如果提供了团队名称，从数据库读取配置
        if team_name:
            try:
                import json
                from backend.database import SessionLocal
                from backend.models.agent_team import AgentTeam
                from sqlalchemy import select

                with SessionLocal() as session:
                    result = session.execute(
                        select(AgentTeam).where(AgentTeam.name == team_name)
                    )
                    team = result.scalar_one_or_none()

                    if team is None:
                        return f"Error: predefined team '{team_name}' was not found."

                    mode = team.mode
                    agents = team.agents or []
                    cross_review = team.cross_review
                    enable_skills = team.enable_skills
                    
                    # 加载团队模型配置
                    if team.use_custom_model and team.team_model_config:
                        try:
                            team_model_config = json.loads(team.team_model_config)
                            logger.info(f"Loaded custom model config for team '{team_name}' (id={team.id})")
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse team model config for '{team_name}'")
                    
                    logger.info(
                        "Loaded predefined team '{}' (id={}) with mode={}, agents={}, cross_review={}, enable_skills={}, custom_model={}",
                        team_name,
                        team.id,
                        mode,
                        len(agents),
                        cross_review,
                        enable_skills,
                        team_model_config is not None,
                    )
            except Exception as e:
                logger.warning(f"Failed to load team config for '{team_name}': {e}")
                return f"Error: failed to load predefined team '{team_name}': {str(e)}"

        # 团队专属模型优先；仅在团队未配置时才回退继承会话级模型。
        if team_model_config is None:
            team_model_config = self._load_session_model_override()

        if mode is None:
            return "Error: 'mode' must be provided when using custom agents."

        engine = WorkflowEngine(
            self._manager,
            session_id=self._session_id,
            cancel_token=self._cancel_token,
            skills=self._skills,  # 传递技能系统
            team_model_config=team_model_config,  # 传递团队模型配置
            event_callback=_event_callback_context.get(),
        )

        if mode == "pipeline":
            return await engine.run_pipeline(goal, agents, enable_skills=enable_skills)
        elif mode == "graph":
            return await engine.run_graph(goal, agents, enable_skills=enable_skills)
        elif mode == "council":
            return await engine.run_council(goal, agents, cross_review=cross_review, enable_skills=enable_skills)
        else:
            return (
                f"Error: unknown workflow mode '{mode}'. "
                "Valid choices are: pipeline, graph, council."
            )
