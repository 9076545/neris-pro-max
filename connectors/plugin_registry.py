"""Allowlisted server-side connector catalog without exposing credential values."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PluginDefinition:
    id: str
    name: str
    description: str
    required_settings: tuple[str, ...]
    access: str


PLUGIN_DEFINITIONS = (
    PluginDefinition(
        "meta-whatsapp",
        "Meta WhatsApp",
        "Recebe webhooks assinados e envia mensagens explicitamente aprovadas.",
        (
            "META_WHATSAPP_ACCESS_TOKEN",
            "META_WHATSAPP_PHONE_NUMBER_ID",
            "META_WHATSAPP_APP_SECRET",
        ),
        "webhook-and-explicit-send",
    ),
    PluginDefinition(
        "shopify",
        "Shopify",
        "Consulta catalogo e pedidos; ajustes de estoque exigem chamada administrativa.",
        ("SHOPIFY_SHOP_DOMAIN", "SHOPIFY_ADMIN_ACCESS_TOKEN"),
        "read-with-explicit-write",
    ),
    PluginDefinition(
        "industrial-iot",
        "WEG / Industrial IoT",
        "Leitura de telemetria MQTT, OPC UA e Modbus; sem comandos de controle.",
        ("WEG_MQTT_HOST", "WEG_OPCUA_ENDPOINT", "WEG_MODBUS_HOST"),
        "read-only",
    ),
    PluginDefinition(
        "nexus-plus",
        "Nexus Plus Graph RAG",
        "Consulta o endpoint WebSocket remoto somente quando configurado.",
        ("NEXUS_PLUS_WS_URL", "NEXUS_PLUS_SYNC_TOKEN"),
        "query-only",
    ),
    PluginDefinition(
        "android-artemis",
        "ARTEMIS Android",
        "Executa testes de interface explicitamente aprovados em dispositivos Android conectados.",
        ("NERIS_ENABLE_ARTEMIS", "ARTEMIS_BASE_URL", "ARTEMIS_TOKEN"),
        "explicit-user-approved-device-testing",
    ),
)


def plugin_status() -> list[dict[str, object]]:
    result = []
    for plugin in PLUGIN_DEFINITIONS:
        missing = [
            setting
            for setting in plugin.required_settings
            if (
                not os.getenv(setting, "").strip()
                or (
                    setting == "NERIS_ENABLE_ARTEMIS"
                    and os.getenv(setting, "").casefold() != "true"
                )
            )
        ]
        result.append(
            {
                "id": plugin.id,
                "name": plugin.name,
                "description": plugin.description,
                "access": plugin.access,
                "connected": not missing,
                "missing_settings": missing,
                "credential_handling": "server-side-only",
            }
        )
    return result
