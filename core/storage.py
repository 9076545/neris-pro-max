"""Supabase persistence with an explicit, process-local development mock."""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


def mock_mode() -> bool:
    return os.getenv("NERIS_MOCK_MODE", "false").casefold() == "true"


class SupabaseRepository:
    """Store backend data with a service-role client; public clients never use it."""

    def __init__(self) -> None:
        self._client: Any | None = None
        self._client_lock = threading.Lock()
        self._mock_lock = asyncio.Lock()
        self._logs: list[dict[str, Any]] = []
        self._leads: list[dict[str, Any]] = []
        self._memories: list[dict[str, Any]] = []
        self._whatsapp_messages: list[dict[str, Any]] = []
        self._shopify_inventory: dict[str, dict[str, Any]] = {}
        self._users: dict[str, dict[str, Any]] = {}

    def _service_client(self) -> Any:
        if self._client is not None:
            return self._client
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            raise RuntimeError(
                f"SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured in "
                f"{os.path.join(PROJECT_ROOT, '.env')}."
            )
        with self._client_lock:
            if self._client is None:
                try:
                    from supabase import create_client
                except ImportError as exc:
                    raise RuntimeError(
                        "Install supabase-py to connect to the Supabase database."
                    ) from exc
                self._client = create_client(url, key)
        return self._client

    async def record_agent_log(
        self,
        agent_id: str,
        agent_name: str,
        status: str,
        log_text: str,
    ) -> dict[str, Any]:
        record = {
            "agente_id": agent_id,
            "nome_agente": agent_name,
            "status_acao": status,
            "log_texto": log_text,
        }
        if mock_mode():
            async with self._mock_lock:
                stored = {
                    **record,
                    "id": len(self._logs) + 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                self._logs.append(stored)
                return stored
        response = await asyncio.to_thread(
            lambda: self._service_client()
            .table("logs_agentes")
            .insert(record)
            .execute()
        )
        return response.data[0]

    async def recent_agent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500.")
        if mock_mode():
            async with self._mock_lock:
                return list(reversed(self._logs[-limit:]))
        response = await asyncio.to_thread(
            lambda: self._service_client()
            .table("logs_agentes")
            .select("id,agente_id,nome_agente,status_acao,log_texto,created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data

    async def add_lead(self, lead: dict[str, Any]) -> dict[str, Any]:
        required_fields = ("empresa_nome",)
        if any(not lead.get(field, "").strip() for field in required_fields):
            raise ValueError("empresa_nome is required.")
        record = {
            field: value
            for field, value in lead.items()
            if field
            in {
                "empresa_nome",
                "segmento",
                "contato_email",
                "contato_whatsapp",
                "status_funil",
                "agente_responsavel",
                "consentimento_contato",
                "consentimento_em",
                "owner_user_id",
            }
        }
        if mock_mode():
            async with self._mock_lock:
                stored = {
                    **record,
                    "id": len(self._leads) + 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                self._leads.append(stored)
                return stored
        response = await asyncio.to_thread(
            lambda: self._service_client()
            .table("leads_prospeccao")
            .insert(record)
            .execute()
        )
        return response.data[0]

    async def recent_leads(self, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500.")
        if mock_mode():
            async with self._mock_lock:
                personal_leads = [
                    item for item in self._leads if item.get("owner_user_id") is None
                ]
                return list(reversed(personal_leads[-limit:]))
        response = await asyncio.to_thread(
            lambda: self._service_client()
            .table("leads_prospeccao")
            .select(
                "id,empresa_nome,segmento,contato_email,contato_whatsapp,"
                "status_funil,agente_responsavel,created_at"
                ",consentimento_contato,consentimento_em"
            )
            .is_("owner_user_id", "null")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data

    async def customer_leads(
        self, owner_user_id: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200.")
        if mock_mode():
            async with self._mock_lock:
                return list(
                    reversed(
                        [
                            item
                            for item in self._leads
                            if item.get("owner_user_id") == owner_user_id
                        ][-limit:]
                    )
                )
        response = await asyncio.to_thread(
            lambda: self._service_client()
            .table("leads_prospeccao")
            .select(
                "id,empresa_nome,segmento,contato_email,contato_whatsapp,"
                "status_funil,agente_responsavel,created_at"
            )
            .eq("owner_user_id", owner_user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data

    async def add_customer_lead(
        self, owner_user_id: str, lead: dict[str, Any]
    ) -> dict[str, Any]:
        record = {
            **lead,
            "owner_user_id": owner_user_id,
            "status_funil": "captado",
            "agente_responsavel": "agent-37",
        }
        if mock_mode():
            async with self._mock_lock:
                stored = {
                    **record,
                    "id": len(self._leads) + 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                self._leads.append(stored)
                return stored
        response = await asyncio.to_thread(
            lambda: self._service_client()
            .table("leads_prospeccao")
            .insert(record)
            .execute()
        )
        return response.data[0]

    async def customer_lead(
        self, owner_user_id: str, lead_id: int
    ) -> dict[str, Any] | None:
        if mock_mode():
            async with self._mock_lock:
                return next(
                    (
                        item
                        for item in self._leads
                        if item.get("id") == lead_id
                        and item.get("owner_user_id") == owner_user_id
                    ),
                    None,
                )
        response = await asyncio.to_thread(
            lambda: self._service_client()
            .table("leads_prospeccao")
            .select(
                "id,empresa_nome,segmento,contato_email,contato_whatsapp,"
                "status_funil,agente_responsavel,created_at"
            )
            .eq("owner_user_id", owner_user_id)
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    async def record_whatsapp_message(
        self,
        direction: str,
        phone: str,
        message: str,
        meta_message_id: str | None = None,
    ) -> dict[str, Any]:
        if direction not in {"inbound", "outbound"} or not phone or not message:
            raise ValueError("A message direction, phone number, and text are required.")
        record = {
            "direcao": direction,
            "contato_whatsapp": phone,
            "mensagem": message,
            "meta_message_id": meta_message_id,
        }
        if mock_mode():
            async with self._mock_lock:
                stored = {
                    **record,
                    "id": len(self._whatsapp_messages) + 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                self._whatsapp_messages.append(stored)
                return stored
        response = await asyncio.to_thread(
            lambda: self._service_client()
            .table("mensagens_whatsapp")
            .insert(record)
            .execute()
        )
        return response.data[0]

    async def upsert_shopify_inventory(
        self, products: list[dict[str, Any]]
    ) -> int:
        records = [
            {
                "product_gid": product["id"],
                "titulo": product["title"],
                "status": product["status"],
                "total_inventory": product["totalInventory"],
                "sincronizado_em": datetime.now(timezone.utc).isoformat(),
            }
            for product in products
        ]
        if not records:
            return 0
        if mock_mode():
            async with self._mock_lock:
                self._shopify_inventory.update(
                    {record["product_gid"]: record for record in records}
                )
            return len(records)
        response = await asyncio.to_thread(
            lambda: self._service_client()
            .table("inventario_shopify")
            .upsert(records, on_conflict="product_gid")
            .execute()
        )
        return len(response.data)

    async def add_memory(
        self, context: str, content: str, embedding: list[float]
    ) -> dict[str, Any]:
        if not content.strip() or len(embedding) != 1536:
            raise ValueError("Memory content and a 1536-dimensional embedding are required.")
        record = {"contexto": context, "conteudo": content, "vetor_embedding": embedding}
        if mock_mode():
            async with self._mock_lock:
                stored = {
                    **record,
                    "id": len(self._memories) + 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                self._memories.append(stored)
                return stored
        vector_literal = "[" + ",".join(format(value, ".9g") for value in embedding) + "]"
        response = await asyncio.to_thread(
            lambda: self._service_client()
            .table("memoria_ia")
            .insert(
                {
                    "contexto": context,
                    "conteudo": content,
                    "vetor_embedding": vector_literal,
                }
            )
            .execute()
        )
        return response.data[0]

    async def search_memories(
        self,
        embedding: list[float],
        *,
        limit: int = 5,
        context: str | None = None,
    ) -> list[dict[str, Any]]:
        if len(embedding) != 1536 or not 1 <= limit <= 50:
            raise ValueError("A 1536-dimensional vector and limit 1-50 are required.")
        if mock_mode():
            async with self._mock_lock:
                candidates = self._memories
                if context:
                    candidates = [item for item in candidates if item["contexto"] == context]
                ranked = sorted(
                    (
                        (
                            sum(a * b for a, b in zip(embedding, item["vetor_embedding"])),
                            item,
                        )
                        for item in candidates
                    ),
                    key=lambda pair: pair[0],
                    reverse=True,
                )
                return [
                    {
                        "id": item["id"],
                        "contexto": item["contexto"],
                        "conteudo": item["conteudo"],
                        "similarity": score,
                    }
                    for score, item in ranked[:limit]
                ]

        vector_literal = "[" + ",".join(format(value, ".9g") for value in embedding) + "]"
        response = await asyncio.to_thread(
            lambda: self._service_client()
            .rpc(
                "match_memoria_ia",
                {
                    "query_embedding": vector_literal,
                    "match_count": limit,
                    "filter_context": context,
                },
            )
            .execute()
        )
        return response.data

    async def verify_user_and_append_chat(
        self, access_token: str, turn: dict[str, Any]
    ) -> str:
        if mock_mode():
            prefix, _, user_id = access_token.partition(":")
            if prefix != "mock-user":
                raise PermissionError("Use a mock-user:<uuid> bearer token in mock mode.")
            try:
                user_id = str(uuid.UUID(user_id))
            except ValueError as exc:
                raise PermissionError("The mock user token is invalid.") from exc
            async with self._mock_lock:
                user = self._users.setdefault(
                    user_id,
                    {"id": user_id, "plano": "Neris 3.5", "historico_chat": []},
                )
                user["historico_chat"].append(turn)
            return user_id

        url = os.getenv("SUPABASE_URL", "")
        anon_key = os.getenv("SUPABASE_ANON_KEY", "")
        if not url or not anon_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be configured.")

        def verify() -> str:
            try:
                from supabase import create_client
            except ImportError as exc:
                raise RuntimeError("Install supabase-py to verify Supabase users.") from exc
            user_client = create_client(url, anon_key)
            user_response = user_client.auth.get_user(access_token)
            user = getattr(user_response, "user", None)
            user_id = getattr(user, "id", None)
            if not user_id:
                raise PermissionError("Supabase rejected the user access token.")
            user_client.postgrest.auth(access_token)
            result = (
                user_client.rpc(
                    "append_neris_chat_turn",
                    {"target_user_id": user_id, "chat_turn": turn},
                ).execute()
            )
            if not result.data:
                raise RuntimeError("Supabase did not persist the chat turn.")
            return str(user_id)

        return await asyncio.to_thread(verify)

    async def authenticated_user_profile(self, access_token: str) -> dict[str, Any]:
        if mock_mode():
            prefix, _, user_id = access_token.partition(":")
            if prefix != "mock-user":
                raise PermissionError("Use a mock-user:<uuid> bearer token in mock mode.")
            try:
                user_id = str(uuid.UUID(user_id))
            except ValueError as exc:
                raise PermissionError("The mock user token is invalid.") from exc
            async with self._mock_lock:
                user = self._users.setdefault(
                    user_id,
                    {"id": user_id, "plano": "Neris 3.5", "historico_chat": []},
                )
                return {
                    "id": user["id"],
                    "plano": user.get("plano", "Neris 3.5"),
                    "status_assinatura": user.get("status_assinatura", "ativo"),
                }

        url = os.getenv("SUPABASE_URL", "")
        anon_key = os.getenv("SUPABASE_ANON_KEY", "")
        if not url or not anon_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be configured.")

        def read_profile() -> dict[str, Any]:
            try:
                from supabase import create_client
            except ImportError as exc:
                raise RuntimeError("Install supabase-py to authenticate project users.") from exc
            user_client = create_client(url, anon_key)
            user_response = user_client.auth.get_user(access_token)
            user = getattr(user_response, "user", None)
            user_id = getattr(user, "id", None)
            if not user_id:
                raise PermissionError("Supabase rejected the user access token.")
            user_client.postgrest.auth(access_token)
            response = (
                user_client.table("usuarios_saas")
                .select("id,plano,status_assinatura")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            if not response.data:
                raise PermissionError("The authenticated SaaS profile was not found.")
            return response.data[0]

        return await asyncio.to_thread(read_profile)


repository = SupabaseRepository()
