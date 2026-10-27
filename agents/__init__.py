"""Private agent definitions and runtime."""

from agents.business_agents import BUSINESS_AGENTS
from agents.industrial_agents import INDUSTRIAL_AGENTS
from agents.market_agents import MARKET_AGENTS
from agents.system_agents import SYSTEM_AGENTS
from agents.additional_agents import ADDITIONAL_AGENTS

AGENT_DEFINITIONS = (
    BUSINESS_AGENTS
    + INDUSTRIAL_AGENTS
    + SYSTEM_AGENTS
    + MARKET_AGENTS
    + ADDITIONAL_AGENTS
)

if len(AGENT_DEFINITIONS) != 43:
    raise RuntimeError("Neris requires exactly 43 configured agent definitions.")

if len({agent.id for agent in AGENT_DEFINITIONS}) != 43:
    raise RuntimeError("Agent identifiers must be unique.")

__all__ = [
    "AGENT_DEFINITIONS",
    "ADDITIONAL_AGENTS",
    "BUSINESS_AGENTS",
    "INDUSTRIAL_AGENTS",
    "MARKET_AGENTS",
    "SYSTEM_AGENTS",
]
