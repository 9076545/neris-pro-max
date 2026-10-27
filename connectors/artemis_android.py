"""Neris adapter for the official Google ARTEMIS remote Android SDK."""

from __future__ import annotations

import asyncio
import ipaddress
import os
from urllib.parse import urlsplit
from typing import Any


class ArtemisAndroidConnector:
    """Control an explicitly configured Artemis host; never starts device actions implicitly."""

    def __init__(self) -> None:
        self._base_url = os.getenv("ARTEMIS_BASE_URL", "").strip().rstrip("/")
        self._token = os.getenv("ARTEMIS_TOKEN", "").strip()
        self._device_serial = os.getenv("ARTEMIS_DEVICE_SERIAL", "").strip() or None
        self._profile = os.getenv("ARTEMIS_PROFILE", "flash").strip().casefold()
        self._enabled = os.getenv("NERIS_ENABLE_ARTEMIS", "false").casefold() == "true"

    def _client(self, profile: str | None = None) -> Any:
        if not self._enabled:
            raise RuntimeError("ARTEMIS integration is disabled.")
        if not self._base_url:
            raise RuntimeError("ARTEMIS_BASE_URL is not configured.")
        selected_profile = profile or self._profile
        if selected_profile not in {"flash", "pro"}:
            raise RuntimeError("ARTEMIS_PROFILE must be flash or pro.")
        parsed = urlsplit(self._base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("ARTEMIS_BASE_URL must be a valid HTTP(S) URL.")
        host = parsed.hostname.casefold()
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = host == "localhost"
        if parsed.scheme != "https" and not is_loopback:
            raise RuntimeError(
                "Remote ARTEMIS hosts require HTTPS; use a private SSH tunnel for local HTTP."
            )
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeError("ARTEMIS_BASE_URL must not contain credentials or query data.")
        if not is_loopback and not self._token:
            raise RuntimeError("ARTEMIS_TOKEN is required for a remote host.")
        try:
            from artemis_client import ArtemisClient
        except ImportError as exc:
            raise RuntimeError(
                "Install the pinned artemis-client dependency to use Android integration."
            ) from exc
        return ArtemisClient(
            self._base_url,
            token=self._token or None,
            request_timeout=30,
            poll_interval=1.0,
            device_serial=self._device_serial,
            default_profile=selected_profile,
        )

    async def list_devices(self) -> list[dict[str, object]]:
        client = self._client()
        devices = await asyncio.wait_for(client.list_devices(), timeout=20)
        return [
            {
                "serial": device.serial,
                "state": device.state,
                "model": device.model,
                "product": device.product,
                "busy": device.busy,
            }
            for device in devices
        ]

    async def run_ui_task(
        self,
        goal: str,
        *,
        device_serial: str | None,
        confirmed: bool,
        profile: str | None = None,
    ) -> dict[str, object]:
        if not confirmed:
            raise ValueError("Confirme que e proprietario ou tem autorizacao para este aparelho.")
        if not goal.strip() or len(goal) > 1200:
            raise ValueError("A tarefa precisa ter de 1 a 1200 caracteres.")
        if profile is not None and profile not in {"flash", "pro"}:
            raise ValueError("profile must be flash or pro.")
        client = self._client(profile)
        result = await asyncio.wait_for(
            client.run(
                goal.strip(),
                profile=profile or self._profile,
                device_serial=device_serial or self._device_serial,
                timeout=600,
            ),
            timeout=610,
        )
        return {
            "task_id": result.task_id,
            "status": result.status,
            "succeeded": result.succeeded,
            "device_serial": result.device_serial,
            "output": str(result.output)[:4000] if result.output is not None else None,
            "error": str(result.error)[:1000] if result.error is not None else None,
        }
