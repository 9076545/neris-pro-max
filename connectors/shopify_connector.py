"""Read-only Shopify Admin GraphQL client."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from dotenv import load_dotenv

from core.storage import mock_mode, repository

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


class ShopifyConnector:
    def __init__(
        self,
        *,
        shop_domain: str | None = None,
        access_token: str | None = None,
        api_version: str | None = None,
    ) -> None:
        self._shop_domain = (shop_domain or os.getenv("SHOPIFY_SHOP_DOMAIN", "")).strip()
        self._access_token = access_token or os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "")
        self._api_version = api_version or os.getenv("SHOPIFY_API_VERSION", "")

    def _graphql_url(self) -> str:
        domain = self._shop_domain.removeprefix("https://").removeprefix("http://").rstrip("/")
        if (
            not domain.endswith(".myshopify.com")
            or "/" in domain
            or not self._access_token
            or not self._api_version
        ):
            raise RuntimeError(
                "Set SHOPIFY_SHOP_DOMAIN (.myshopify.com), SHOPIFY_ADMIN_ACCESS_TOKEN, "
                "and SHOPIFY_API_VERSION."
            )
        return f"https://{domain}/admin/api/{self._api_version}/graphql.json"

    async def _query(
        self, query: str, variables: dict[str, object] | None = None
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self._graphql_url(),
                headers={
                    "X-Shopify-Access-Token": self._access_token,
                    "Content-Type": "application/json",
                },
                json={"query": query, "variables": variables or {}},
            )
            response.raise_for_status()
            payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(f"Shopify GraphQL errors: {payload['errors']}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("Shopify returned a response without GraphQL data.")
        return data

    async def list_products(self, first: int = 25) -> list[dict[str, Any]]:
        if not 1 <= first <= 100:
            raise ValueError("first must be between 1 and 100.")
        if mock_mode():
            return [
                {
                    "id": "gid://shopify/Product/mock-001",
                    "title": "Filtro industrial Neris (demo)",
                    "handle": "filtro-industrial-demo",
                    "status": "ACTIVE",
                    "totalInventory": 24,
                    "updatedAt": "2026-10-17T00:00:00Z",
                },
                {
                    "id": "gid://shopify/Product/mock-002",
                    "title": "Componente HVAC (demo)",
                    "handle": "componente-hvac-demo",
                    "status": "ACTIVE",
                    "totalInventory": 8,
                    "updatedAt": "2026-10-17T00:00:00Z",
                },
            ][:first]
        data = await self._query(
            """
            query Products($first: Int!) {
              products(first: $first) {
                nodes {
                  id
                  title
                  handle
                  status
                  totalInventory
                  updatedAt
                }
              }
            }
            """,
            {"first": first},
        )
        return data["products"]["nodes"]

    async def list_recent_orders(self, first: int = 25) -> list[dict[str, Any]]:
        if not 1 <= first <= 100:
            raise ValueError("first must be between 1 and 100.")
        if mock_mode():
            return [
                {
                    "id": "gid://shopify/Order/mock-001",
                    "name": "#DEMO-1001",
                    "createdAt": "2026-10-17T00:00:00Z",
                    "displayFinancialStatus": "PAID",
                    "displayFulfillmentStatus": "UNFULFILLED",
                    "totalPriceSet": {
                        "shopMoney": {"amount": "149.90", "currencyCode": "BRL"}
                    },
                }
            ][:first]
        data = await self._query(
            """
            query Orders($first: Int!) {
              orders(first: $first, sortKey: CREATED_AT, reverse: true) {
                nodes {
                  id
                  name
                  createdAt
                  displayFinancialStatus
                  displayFulfillmentStatus
                  totalPriceSet {
                    shopMoney { amount currencyCode }
                  }
                }
              }
            }
            """,
            {"first": first},
        )
        return data["orders"]["nodes"]

    async def product_opportunity_snapshot(
        self, *, days: int = 30, first: int = 50
    ) -> dict[str, Any]:
        if not 1 <= days <= 90 or not 1 <= first <= 100:
            raise ValueError("days must be 1-90 and first must be 1-100.")
        if mock_mode():
            return {
                "source": "Shopify (dados de demonstração)",
                "window_days": days,
                "orders_analyzed": 2,
                "catalog": [
                    {
                        "id": "demo-filter",
                        "title": "Filtro industrial Neris (demo)",
                        "status": "ACTIVE",
                        "inventory": 24,
                        "units_sold": 14,
                        "sales_revenue": 2098.6,
                        "currency": "BRL",
                    },
                    {
                        "id": "demo-hvac",
                        "title": "Componente HVAC (demo)",
                        "status": "ACTIVE",
                        "inventory": 8,
                        "units_sold": 3,
                        "sales_revenue": 449.7,
                        "currency": "BRL",
                    },
                ],
                "limitations": [
                    "Valores simulados; não representam pedidos ou produtos reais.",
                    "Custos e margens não foram fornecidos.",
                ],
            }
        products = await self.list_products(100)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        data = await self._query(
            """
            query ProductSales($first: Int!, $query: String!) {
              orders(first: $first, query: $query, sortKey: CREATED_AT, reverse: true) {
                nodes {
                  lineItems(first: 50) {
                    nodes {
                      title
                      quantity
                      product { id title }
                      discountedTotalSet { shopMoney { amount currencyCode } }
                    }
                  }
                }
              }
            }
            """,
            {
                "first": first,
                "query": f"created_at:>={since}",
            },
        )
        aggregates: dict[str, dict[str, Any]] = {}
        orders = data.get("orders", {}).get("nodes", [])
        for order in orders:
            for item in order.get("lineItems", {}).get("nodes", []):
                product = item.get("product") or {}
                product_id = product.get("id")
                if not product_id:
                    continue
                total = (item.get("discountedTotalSet") or {}).get("shopMoney") or {}
                try:
                    amount = float(total.get("amount", 0))
                    quantity = int(item.get("quantity", 0))
                except (TypeError, ValueError):
                    continue
                aggregate = aggregates.setdefault(
                    product_id,
                    {
                        "id": product_id,
                        "title": product.get("title") or item.get("title", "Produto sem título"),
                        "units_sold": 0,
                        "sales_revenue": 0.0,
                        "currency": total.get("currencyCode"),
                    },
                )
                aggregate["units_sold"] += quantity
                aggregate["sales_revenue"] += amount

        catalog = []
        for product in products:
            sales = aggregates.get(product["id"], {})
            catalog.append(
                {
                    "id": product["id"],
                    "title": product["title"],
                    "status": product["status"],
                    "inventory": product["totalInventory"],
                    "units_sold": sales.get("units_sold", 0),
                    "sales_revenue": round(sales.get("sales_revenue", 0.0), 2),
                    "currency": sales.get("currency"),
                }
            )
        return {
            "source": "Shopify Admin API",
            "window_days": days,
            "orders_analyzed": len(orders),
            "catalog": catalog,
            "limitations": [
                "O recorte contém somente os pedidos recentes retornados pela API.",
                "Custos, margem, devoluções, frete e fornecedores não foram consultados.",
                "Vendas observadas não garantem demanda futura.",
            ],
        }

    async def sync_inventory_snapshot(self, first: int = 100) -> int:
        """Read Shopify inventory and upsert the snapshot into Supabase."""
        products = await self.list_products(first)
        return await repository.upsert_shopify_inventory(products)

    async def set_available_quantity(
        self,
        *,
        inventory_item_id: str,
        location_id: str,
        quantity: int,
        expected_quantity: int,
        reference_uri: str,
    ) -> dict[str, Any]:
        """Apply an explicitly requested inventory correction with optimistic locking."""
        if (
            not inventory_item_id.startswith("gid://shopify/InventoryItem/")
            or not location_id.startswith("gid://shopify/Location/")
            or not reference_uri.startswith("https://")
            or quantity < 0
            or expected_quantity < 0
        ):
            raise ValueError("Provide valid Shopify IDs, quantities, and an HTTPS reference.")
        if mock_mode():
            return {
                "mock": True,
                "inventory_item_id": inventory_item_id,
                "location_id": location_id,
                "quantity": quantity,
                "expected_quantity": expected_quantity,
            }

        data = await self._query(
            """
            mutation SetAvailable($input: InventorySetQuantitiesInput!) {
              inventorySetQuantities(input: $input) {
                inventoryAdjustmentGroup {
                  createdAt
                  reason
                  changes { name delta quantityAfterChange }
                }
                userErrors { field message code }
              }
            }
            """,
            {
                "input": {
                    "name": "available",
                    "reason": "correction",
                    "referenceDocumentUri": reference_uri,
                    "quantities": [
                        {
                            "inventoryItemId": inventory_item_id,
                            "locationId": location_id,
                            "quantity": quantity,
                            "compareQuantity": expected_quantity,
                        }
                    ],
                }
            },
        )
        result = data["inventorySetQuantities"]
        if result["userErrors"]:
            raise RuntimeError(f"Shopify rejected inventory update: {result['userErrors']}")
        return result["inventoryAdjustmentGroup"]
