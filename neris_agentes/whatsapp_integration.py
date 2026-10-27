"""Safe dispatch helpers for the pending WhatsApp agent integration."""

from __future__ import annotations

import json
import time
from typing import Any

from agents import AGENT_DEFINITIONS
from agents.additional_agents import AGENT40_SYSTEM_INSTRUCTION
from neris_agentes.agente40_whatsapp import (
    CachePerfil,
    Empresa,
    classificar_setor,
    montar_payload_texto,
    resolver_empresa,
    rotear,
)

PROFILE_CACHE = CachePerfil(ttl_segundos=24 * 60 * 60)
ROUTE_TO_AGENT = {
    "humano": "agent-17",
    "cancelamento": "agent-13",
    "agendamento": "agent-17",
    "preco": "agent-12",
    "atendimento_geral": "agent-17",
}
AGENTS_BY_ID = {agent.id: agent for agent in AGENT_DEFINITIONS}


def specialist_for_message(message: str) -> str:
    """Resolve a single existing specialist ID for the agent-40 route result."""
    route = rotear(message)
    return ROUTE_TO_AGENT[route]


def is_within_reply_window(timestamp: Any, now: float | None = None) -> bool:
    if not isinstance(timestamp, (str, int)) or not str(timestamp).isdigit():
        return False
    received_at = int(timestamp)
    current_time = time.time() if now is None else now
    age = current_time - received_at
    return 0 <= age <= 24 * 60 * 60


async def respond_to_inbound_message(
    message: dict[str, Any],
    *,
    runtime: Any,
    whatsapp_client: Any,
    cache: CachePerfil = PROFILE_CACHE,
) -> dict[str, str]:
    sender = message.get("de")
    phone_id = message.get("phone_id")
    text = message.get("texto")
    if not all(isinstance(value, str) and value.strip() for value in (sender, phone_id, text)):
        return {"status": "skipped"}
    if not is_within_reply_window(message.get("timestamp")):
        return {"status": "outside_reply_window"}

    route = rotear(text)
    specialist_id = ROUTE_TO_AGENT[route]
    profile = cache.obter(sender) or {}
    company_profile = profile.get("empresa")
    if not isinstance(company_profile, dict):
        resolver_empresa(
            [],
            ja_perguntou=profile.get("identificacao_perguntada") is True,
        )
        if profile.get("identificacao_perguntada") is not True:
            profile["identificacao_perguntada"] = True
            cache.guardar(sender, profile)
            response_text = (
                "Para entender seu contexto, qual é o nome da sua empresa "
                "e em qual segmento ela atua?"
            )
            payload = montar_payload_texto(sender, response_text)
            await whatsapp_client.send_text(
                payload["to"],
                payload["text"]["body"],
            )
            return {"status": "identification_requested"}

        candidate = Empresa(
            id=sender,
            nome=text[:160],
            descricao=text,
            phone_id=phone_id,
        )
        resolution = resolver_empresa(
            [candidate],
            resposta_cliente=text,
            ja_perguntou=True,
        )
        if resolution.acao != "ok" or resolution.empresa is None:
            return {"status": "company_unresolved"}
        company_profile = {
            "id": resolution.empresa.id,
            "nome": resolution.empresa.nome,
            "descricao": resolution.empresa.descricao,
            "phone_id": resolution.empresa.phone_id,
        }
        profile["empresa"] = company_profile

    company = Empresa(
        id=str(company_profile["id"]),
        nome=str(company_profile["nome"]),
        descricao=str(company_profile["descricao"]),
        phone_id=str(company_profile["phone_id"]),
    )
    resolution = resolver_empresa([company], ja_perguntou=True)
    if resolution.acao != "ok" or resolution.empresa is None:
        return {"status": "company_unresolved"}

    sector = classificar_setor(f"{company.descricao}\n{text}")
    profile["setor"] = sector
    cache.guardar(sender, profile)

    specialist = AGENTS_BY_ID[specialist_id]
    user_data = {
        "empresa": company_profile,
        "setor_classificado": sector,
        "rota": route,
        "mensagem_cliente_nao_confiavel": text,
    }
    response_text = await runtime.submit(
        specialist_id,
        json.dumps(user_data, ensure_ascii=False),
        max_tokens=320,
        system_instruction=(
            specialist.system_instruction
            + "\n\nContexto do agente 40: "
            + AGENT40_SYSTEM_INSTRUCTION
        ),
    )
    payload = montar_payload_texto(sender, response_text)
    await whatsapp_client.send_text(
        payload["to"],
        payload["text"]["body"],
    )
    return {"status": "replied", "agent_id": specialist_id}
