"""Explicit-send integration with the Meta WhatsApp Cloud API."""

from __future__ import annotations

import os
import hashlib
import hmac
from typing import Any

import httpx
from dotenv import load_dotenv

from core.storage import mock_mode, repository

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


class MetaWhatsAppClient:
    def __init__(
        self,
        *,
        access_token: str | None = None,
        phone_number_id: str | None = None,
        graph_api_version: str | None = None,
        app_secret: str | None = None,
    ) -> None:
        self._access_token = access_token or os.getenv("META_WHATSAPP_ACCESS_TOKEN", "")
        self._phone_number_id = phone_number_id or os.getenv(
            "META_WHATSAPP_PHONE_NUMBER_ID", ""
        )
        self._graph_api_version = graph_api_version or os.getenv(
            "META_GRAPH_API_VERSION", ""
        )
        self._app_secret = app_secret or os.getenv("META_WHATSAPP_APP_SECRET", "")

    def _messages_url(self) -> str:
        missing = [
            name
            for name, value in (
                ("META_WHATSAPP_ACCESS_TOKEN", self._access_token),
                ("META_WHATSAPP_PHONE_NUMBER_ID", self._phone_number_id),
                ("META_GRAPH_API_VERSION", self._graph_api_version),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing Meta WhatsApp configuration: {', '.join(missing)}.")
        return (
            f"https://graph.facebook.com/{self._graph_api_version}/"
            f"{self._phone_number_id}/messages"
        )

    async def send_text(self, recipient: str, text: str) -> dict[str, object]:
        """Send a user-approved text message to an opted-in WhatsApp recipient."""
        normalized_recipient = recipient.removeprefix("+")
        if (
            not normalized_recipient.isdigit()
            or not 8 <= len(normalized_recipient) <= 15
            or not 1 <= len(text.strip()) <= 4096
        ):
            raise ValueError("Provide a numeric E.164 recipient and 1-4096 text characters.")
        if mock_mode():
            result: dict[str, object] = {
                "mock": True,
                "messaging_product": "whatsapp",
                "messages": [{"id": "mock-whatsapp-message"}],
            }
        else:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    self._messages_url(),
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    json={
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                        "to": normalized_recipient,
                        "type": "text",
                        "text": {"preview_url": False, "body": text.strip()},
                    },
                )
                response.raise_for_status()
                result = response.json()

        message_id = None
        messages = result.get("messages")
        if isinstance(messages, list) and messages and isinstance(messages[0], dict):
            message_id = messages[0].get("id")
        await repository.record_whatsapp_message(
            "outbound", normalized_recipient, text.strip(), message_id
        )
        return result

    async def send_lead_reply_notification(
        self, recipient: str, *, lead_phone: str, message_text: str
    ) -> dict[str, object]:
        """Forward an inbound lead reply to the configured operator via an approved template."""
        normalized_recipient = recipient.removeprefix("+")
        template_name = os.getenv("META_WHATSAPP_NOTIFICATION_TEMPLATE", "")
        language = os.getenv("META_WHATSAPP_NOTIFICATION_LANGUAGE", "pt_BR")
        preview = message_text.strip().replace("\n", " ")[:900]
        if (
            not normalized_recipient.isdigit()
            or not 8 <= len(normalized_recipient) <= 15
            or not template_name
            or not 1 <= len(preview) <= 900
        ):
            raise ValueError("Operator number, approved template, and message are required.")
        if mock_mode():
            result: dict[str, object] = {
                "mock": True,
                "messaging_product": "whatsapp",
                "messages": [{"id": "mock-lead-notification"}],
            }
        else:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    self._messages_url(),
                    headers={"Authorization": f"******"},
                    json={
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                        "to": normalized_recipient,
                        "type": "template",
                        "template": {
                            "name": template_name,
                            "language": {"code": language},
                            "components": [
                                {
                                    "type": "body",
                                    "parameters": [
                                        {"type": "text", "text": lead_phone[:32]},
                                        {"type": "text", "text": preview},
                                    ],
                                }
                            ],
                        },
                    },
                )
                response.raise_for_status()
                result = response.json()
        message_id = None
        messages = result.get("messages")
        if isinstance(messages, list) and messages and isinstance(messages[0], dict):
            message_id = messages[0].get("id")
        await repository.record_whatsapp_message(
            "outbound",
            normalized_recipient,
            f"Notificação de resposta de lead {lead_phone}: {preview}",
            message_id,
        )
        return result

    async def register_lead(
        self,
        *,
        company_name: str,
        segment: str | None = None,
        email: str | None = None,
        whatsapp: str | None = None,
    ) -> dict[str, Any]:
        """Persist a lead that was collected with an appropriate lawful basis."""
        return await repository.add_lead(
            {
                "empresa_nome": company_name,
                "segmento": segment or "",
                "contato_email": email or "",
                "contato_whatsapp": whatsapp or "",
                "status_funil": "captado",
                "agente_responsavel": "agent-05",
            }
        )

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        if mock_mode() and signature == "mock-signature":
            return True
        if not self._app_secret or not signature.startswith("sha256="):
            return False
        digest = hmac.new(
            self._app_secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature[7:], digest)

    async def process_webhook(
        self, raw_body: bytes, signature: str
    ) -> list[dict[str, Any]]:
        if not self.verify_webhook_signature(raw_body, signature):
            raise PermissionError("Meta webhook signature verification failed.")
        import json

        try:
            payload = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Meta webhook body must be valid JSON.") from exc

        stored_messages: list[dict[str, Any]] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts = {
                    contact.get("wa_id"): contact
                    for contact in value.get("contacts", [])
                    if contact.get("wa_id")
                }
                for incoming in value.get("messages", []):
                    phone = incoming.get("from")
                    if not isinstance(phone, str):
                        continue
                    message_text = incoming.get("text", {}).get("body")
                    if not isinstance(message_text, str):
                        message_text = f"[WhatsApp {incoming.get('type', 'message')} recebido]"
                    contact = contacts.get(phone, {})
                    profile_name = contact.get("profile", {}).get("name")
                    await self.register_lead(
                        company_name=profile_name or phone,
                        segment="WhatsApp",
                        whatsapp=phone,
                    )
                    stored_messages.append(
                        await repository.record_whatsapp_message(
                            "inbound",
                            phone,
                            message_text,
                            incoming.get("id"),
                        )
                    )
        return stored_messages
