"""WorkflowTool — exposes WorkflowEngine as a CountBot tool.

The primary Agent calls ``workflow_run`` to trigger a structured
multi-agent workflow and receives the fully compiled results when
all sub-agents have finished.
"""

from typing import Any

from backend.modules.tools.base import Tool
from backend.modules.agent.workflow import WorkflowEngine


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
        self._session_id: str | None = None
        self._cancel_token = None

    def set_session_id(self, session_id: str) -> None:
        """绑定当前会话 ID，用于实时推送 workflow 事件。"""
        self._session_id = session_id

    def set_cancel_token(self, token) -> None:
        """绑定取消令牌，用于在用户点击停止时中断工作流执行。"""
        self._cancel_token = token

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
    def parameters(self) -> dict[str, Any]:
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
                        "Pipeline/Graph: [{\"id\": str, \"role\": str, \"task\": str, \"depends\": [str]}]. "
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
                            "depends": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "IDs of slots that must complete before this one (graph only).",
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
                        "If provided, the system will load team configuration (including enable_skills setting) from the database."
                    ),
                },
            },
            "required": ["mode", "goal", "agents"],
        }

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        mode: str,
        goal: str,
        agents: list[dict],
        cross_review: bool = True,
        team_name: str | None = None,
        **kwargs: Any,
    ) -> str:
        # 确定是否启用技能系统
        enable_skills = False
        
        # 如果提供了团队名称，从数据库读取配置
        if team_name:
            try:
                from backend.database import SessionLocal
                from backend.models.agent_team import AgentTeam
                from sqlalchemy import select
                
                with SessionLocal() as session:
                    result = session.execute(
                        select(AgentTeam).where(AgentTeam.name == team_name)
                    )
                    team = result.scalar_one_or_none()
                    
                    if team:
                        enable_skills = team.enable_skills
                        from loguru import logger
                        logger.debug(f"Team '{team_name}' enable_skills={enable_skills}")
            except Exception as e:
                from loguru import logger
                logger.warning(f"Failed to load team config for '{team_name}': {e}")
        
        engine = WorkflowEngine(
            self._manager,
            session_id=self._session_id,
            cancel_token=self._cancel_token,
            skills=self._skills,  # 传递技能系统
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

