"""Read-only MQTT, OPC UA, and Modbus telemetry clients."""

from __future__ import annotations

import asyncio
import json
import os
import ssl
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from core.storage import mock_mode, repository

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


@dataclass(frozen=True)
class IndustrialSettings:
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    mqtt_tls: bool
    opcua_endpoint: str
    modbus_host: str
    modbus_port: int
    modbus_unit_id: int

    @classmethod
    def from_environment(cls) -> IndustrialSettings:
        return cls(
            mqtt_host=os.getenv("WEG_MQTT_HOST", ""),
            mqtt_port=int(os.getenv("WEG_MQTT_PORT", "8883")),
            mqtt_username=os.getenv("WEG_MQTT_USERNAME", ""),
            mqtt_password=os.getenv("WEG_MQTT_PASSWORD", ""),
            mqtt_tls=os.getenv("WEG_MQTT_TLS", "true").casefold() == "true",
            opcua_endpoint=os.getenv("WEG_OPCUA_ENDPOINT", ""),
            modbus_host=os.getenv("WEG_MODBUS_HOST", ""),
            modbus_port=int(os.getenv("WEG_MODBUS_PORT", "502")),
            modbus_unit_id=int(os.getenv("WEG_MODBUS_UNIT_ID", "1")),
        )


def _required(value: str, setting: str) -> str:
    if not value:
        raise RuntimeError(f"{setting} is not configured in the project environment.")
    return value


async def subscribe_mqtt(topic: str) -> AsyncIterator[dict[str, Any]]:
    """Yield JSON MQTT telemetry; TLS is enabled by default."""
    if not topic or len(topic) > 512:
        raise ValueError("Provide a valid MQTT topic (up to 512 characters).")
    if mock_mode():
        reading = {
            "topic": topic,
            "payload": {
                "asset_id": "WEG-DEMO-01",
                "temperature_c": 22.4,
                "vibration_mm_s": 1.8,
                "mock": True,
            },
        }
        await repository.record_agent_log(
            "agent-23",
            "MQTT Telemetry",
            "mock_telemetry",
            json.dumps(reading, ensure_ascii=False),
        )
        yield reading
        return

    settings = IndustrialSettings.from_environment()
    host = _required(settings.mqtt_host, "WEG_MQTT_HOST")

    try:
        import aiomqtt
    except ImportError as exc:
        raise RuntimeError("Install the aiomqtt dependency to use MQTT telemetry.") from exc

    tls_context = ssl.create_default_context() if settings.mqtt_tls else None
    async with aiomqtt.Client(
        hostname=host,
        port=settings.mqtt_port,
        username=settings.mqtt_username or None,
        password=settings.mqtt_password or None,
        tls_context=tls_context,
    ) as client:
        await client.subscribe(topic)
        async for message in client.messages:
            try:
                payload = json.loads(message.payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"MQTT payload on {message.topic} is not valid UTF-8 JSON."
                ) from exc
            reading = {"topic": str(message.topic), "payload": payload}
            await repository.record_agent_log(
                "agent-23",
                "MQTT Telemetry",
                "telemetry_received",
                json.dumps(reading, ensure_ascii=False),
            )
            yield reading


async def read_opcua_node(node_id: str) -> Any:
    """Read one OPC UA node; this connector intentionally exposes no write method."""
    if not node_id or len(node_id) > 512:
        raise ValueError("Provide a valid OPC UA node id.")
    if mock_mode():
        value = {"node_id": node_id, "value": 22.4, "mock": True}
        await repository.record_agent_log(
            "agent-21",
            "OPC UA Telemetry",
            "mock_telemetry",
            json.dumps(value, ensure_ascii=False),
        )
        return value
    endpoint = _required(
        IndustrialSettings.from_environment().opcua_endpoint, "WEG_OPCUA_ENDPOINT"
    )
    try:
        from asyncua import Client
    except ImportError as exc:
        raise RuntimeError("Install the asyncua dependency to use OPC UA telemetry.") from exc

    async with Client(url=endpoint, timeout=10) as client:
        node = client.get_node(node_id)
        value = await node.read_value()
    await repository.record_agent_log(
        "agent-21",
        "OPC UA Telemetry",
        "telemetry_received",
        json.dumps({"node_id": node_id, "value": value}, ensure_ascii=False, default=str),
    )
    return value


async def read_modbus_registers(
    address: int,
    count: int,
    *,
    unit_id: int | None = None,
) -> list[int]:
    """Read Modbus holding registers without exposing a write operation."""
    settings = IndustrialSettings.from_environment()
    if address < 0 or not 1 <= count <= 125:
        raise ValueError("address must be non-negative and count must be 1-125.")
    if mock_mode():
        registers = [230 + index * 2 for index in range(count)]
        await repository.record_agent_log(
            "agent-22",
            "Modbus Telemetry",
            "mock_telemetry",
            json.dumps(
                {
                    "address": address,
                    "unit_id": unit_id or settings.modbus_unit_id,
                    "registers": registers,
                    "mock": True,
                }
            ),
        )
        return registers
    host = _required(settings.modbus_host, "WEG_MODBUS_HOST")

    try:
        from pymodbus.client import AsyncModbusTcpClient
    except ImportError as exc:
        raise RuntimeError(
            "Install the pymodbus dependency to use Modbus telemetry."
        ) from exc

    client = AsyncModbusTcpClient(host, port=settings.modbus_port, timeout=5)
    try:
        await client.connect()
        if not client.connected:
            raise ConnectionError(f"Could not connect to Modbus host {host}.")
        response = await client.read_holding_registers(
            address=address,
            count=count,
            device_id=unit_id if unit_id is not None else settings.modbus_unit_id,
        )
        if response.isError():
            raise RuntimeError(f"Modbus returned an error for address {address}.")
        registers = list(response.registers)
    finally:
        client.close()
    await repository.record_agent_log(
        "agent-22",
        "Modbus Telemetry",
        "telemetry_received",
        json.dumps(
            {
                "address": address,
                "unit_id": unit_id if unit_id is not None else settings.modbus_unit_id,
                "registers": registers,
            }
        ),
    )
    return registers
