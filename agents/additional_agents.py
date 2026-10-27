"""Definitions for agents 40-43, derived from their delivered modules."""

from __future__ import annotations

import json
from pathlib import Path

from agents.base import AgentDefinition
from neris_agentes.agente40_whatsapp import AGENTE_40
from neris_agentes.agente42_crescimento import AGENTE_42
from neris_agentes.agente43_capital_giro import AGENTE_43

SKILL_ENTENDIMENTO_SETOR_PATH = (
    Path(__file__).resolve().parent.parent
    / "neris_agentes"
    / "skill-entendimento-setor.json"
)
with SKILL_ENTENDIMENTO_SETOR_PATH.open(encoding="utf-8") as skill_file:
    SKILL_ENTENDIMENTO_SETOR = json.load(skill_file)

def _load_agent_definition(filename: str) -> dict[str, object]:
    path = Path(__file__).resolve().parent.parent / "neris_agentes" / filename
    with path.open(encoding="utf-8") as definition_file:
        definition = json.load(definition_file)
    if not isinstance(definition, dict):
        raise RuntimeError(f"Invalid agent definition: {filename}")
    return definition


AGENT40_JSON = _load_agent_definition("agente40_whatsapp.json")
AGENT41_JSON = _load_agent_definition("agente41_auditor.json")
AGENT40_SYSTEM_INSTRUCTION = (
    str(AGENT40_JSON["system_prompt"])
    + " Skill de entendimento do setor: "
    + json.dumps(SKILL_ENTENDIMENTO_SETOR, ensure_ascii=False)
)

ADDITIONAL_AGENTS = (
    AgentDefinition(
        str(AGENT40_JSON["id"]),
        str(AGENT40_JSON["nome"]),
        AGENT40_SYSTEM_INSTRUCTION,
    ),
    AgentDefinition(
        str(AGENT41_JSON["id"]),
        str(AGENT41_JSON["nome"]),
        str(AGENT41_JSON["system_prompt"]),
    ),
    AgentDefinition(
        f"agent-{AGENTE_42['numero']:02}",
        AGENTE_42["nome"],
        "Analise crescimento, funil, campanhas, leads e conteúdo usando somente "
        "dados fornecidos. Explique métricas e premissas; conteúdo e follow-up são "
        "rascunhos. Nunca publique, envie mensagens em massa ou altere orçamento.",
    ),
    AgentDefinition(
        f"agent-{AGENTE_43['numero']:02}",
        AGENTE_43["nome"],
        "Analise capital de giro e cálculos financeiros com transparência sobre "
        "premissas e limitações. Não ofereça recomendação de investimento, crédito "
        "ou captação; encaminhe decisões a profissional habilitado.",
    ),
)

PENDING_INTEGRATION_AGENT_IDS = frozenset({"agent-40"})

if [agent.id for agent in ADDITIONAL_AGENTS] != [
    "agent-40",
    "agent-41",
    "agent-42",
    "agent-43",
]:
    raise RuntimeError("Additional agent IDs must be numbered 40 through 43.")

if AGENTE_40.get("status") != "pendente_integracao":
    raise RuntimeError("WhatsApp agent 40 must remain pending integration.")

if (
    AGENT40_JSON.get("numero") != 40
    or AGENT41_JSON.get("numero") != 41
    or AGENT40_JSON.get("status") != "pendente_integracao"
):
    raise RuntimeError("Agent 40 and 41 JSON metadata does not match the reserved registry IDs.")
