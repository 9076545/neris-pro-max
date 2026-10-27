"""Deterministic, aggregate Cakto-like sales data for safe local simulations."""

from __future__ import annotations

from typing import Any

from core.storage import mock_mode


class CaktoConnector:
    """Expose mock sales aggregates without pretending to call Cakto's API."""

    async def sales_metrics(self) -> dict[str, Any]:
        if not mock_mode():
            raise RuntimeError(
                "Live Cakto synchronization is not configured; provide verified "
                "sales aggregates before running pricing analysis."
            )
        return {
            "source": "Cakto (simulado)",
            "period": "ultimos_30_dias",
            "currency": "BRL",
            "product_id": "cakto-demo-product",
            "current_price": 149.90,
            "page_views": 3200,
            "purchases": 96,
            "conversion_rate": 0.03,
            "gross_revenue": 14390.40,
            "refunds": 2,
            "refund_rate": 0.0208,
        }
