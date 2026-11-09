import os
import unittest
from unittest.mock import patch

from core.storage import SupabaseRepository


class SupabaseRepositoryUsageMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_validated_aggregate_metrics(self):
        metrics = {
            "active_users_7d": 12,
            "evolution_feedback": {
                "yes": 4,
                "not_sure": 2,
                "no": 1,
                "responses": 7,
            },
        }

        class FakeQuery:
            def execute(self):
                return type("Response", (), {"data": metrics})()

        class FakeClient:
            def rpc(self, function_name):
                self.function_name = function_name
                return FakeQuery()

        repository = SupabaseRepository()
        client = FakeClient()
        with (
            patch.dict(os.environ, {"NERIS_MOCK_MODE": "false"}),
            patch.object(repository, "_service_client", return_value=client),
        ):
            result = await repository.neris_admin_usage_metrics()

        self.assertEqual(client.function_name, "get_neris_admin_usage_metrics")
        self.assertEqual(result, metrics)

    async def test_rejects_inconsistent_feedback_aggregate(self):
        metrics = {
            "active_users_7d": 1,
            "evolution_feedback": {
                "yes": 1,
                "not_sure": 0,
                "no": 0,
                "responses": 0,
            },
        }

        class FakeQuery:
            def execute(self):
                return type("Response", (), {"data": metrics})()

        class FakeClient:
            def rpc(self, _function_name):
                return FakeQuery()

        repository = SupabaseRepository()
        with (
            patch.dict(os.environ, {"NERIS_MOCK_MODE": "false"}),
            patch.object(repository, "_service_client", return_value=FakeClient()),
        ):
            with self.assertRaisesRegex(RuntimeError, "inconsistent"):
                await repository.neris_admin_usage_metrics()

    async def test_does_not_read_live_database_in_mock_mode(self):
        repository = SupabaseRepository()
        with patch.dict(os.environ, {"NERIS_MOCK_MODE": "true"}):
            self.assertIsNone(await repository.neris_admin_usage_metrics())
