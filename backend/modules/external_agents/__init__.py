"""External coding agent integration layer."""

from backend.modules.external_agents.base import (
    ExternalAgentProfile,
    ExternalAgentRequest,
    ExternalAgentResult,
)
from backend.modules.external_agents.registry import ExternalAgentRegistry

__all__ = [
    "ExternalAgentProfile",
    "ExternalAgentRequest",
    "ExternalAgentResult",
    "ExternalAgentRegistry",
]
