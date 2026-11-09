import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from hud import server


class FakeProjectStudio:
    def __init__(self):
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            name=kwargs["name"],
            summary="Generated project",
            archive=b"project archive",
            file_count=1,
        )


class CodesXModeTests(unittest.IsolatedAsyncioTestCase):
    async def _generate(self, *, mode, kind, plan, status="ativo", trial_active=False):
        body = server.ProjectBuildRequest(
            name="Projeto teste",
            kind=kind,
            brief="Descreva as funcionalidades do projeto.",
            mode=mode,
        )
        studio = FakeProjectStudio()
        with patch.object(server.app.state, "project_studio", studio, create=True):
            response = await server.generate_customer_project(
                body,
                {
                    "plano": plan,
                    "status_assinatura": status,
                    "trial_active": trial_active,
                },
            )
        return response, studio

    async def test_pro_and_ultra_can_generate_each_codesx_mode(self):
        for plan in ("Neris Pro", "Neris Ultra Max"):
            for mode, kind in (("xperte-jogos", "game"), ("criador-saas", "saas")):
                with self.subTest(plan=plan, mode=mode):
                    response, studio = await self._generate(
                        mode=mode,
                        kind=kind,
                        plan=plan,
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(studio.calls[0]["kind"], kind)
                    self.assertIn("CodesX", studio.calls[0]["brief"])

    async def test_free_and_neris_56_cannot_use_codesx_modes(self):
        for plan in ("Neris 3.5", "Neris 5.6"):
            with self.subTest(plan=plan):
                with self.assertRaises(HTTPException) as raised:
                    await self._generate(
                        mode="xperte-jogos",
                        kind="game",
                        plan=plan,
                    )
                self.assertEqual(raised.exception.status_code, 403)

    async def test_trial_and_inactive_subscriptions_cannot_use_codesx_modes(self):
        for user in (
            {"plan": "Neris Pro", "status": "ativo", "trial_active": True},
            {"plan": "Neris Pro", "status": "inativo", "trial_active": False},
        ):
            with self.subTest(user=user):
                with self.assertRaises(HTTPException) as raised:
                    await self._generate(
                        mode="criador-saas",
                        kind="saas",
                        plan=user["plan"],
                        status=user["status"],
                        trial_active=user["trial_active"],
                    )
                self.assertEqual(raised.exception.status_code, 403)

    async def test_mode_and_project_kind_must_match(self):
        with self.assertRaises(HTTPException) as raised:
            await self._generate(
                mode="criador-saas",
                kind="game",
                plan="Neris Pro",
            )
        self.assertEqual(raised.exception.status_code, 422)

    async def test_existing_generic_project_access_for_neris_56_is_preserved(self):
        body = server.ProjectBuildRequest(
            name="Site teste",
            kind="website",
            brief="Um site institucional.",
        )
        studio = FakeProjectStudio()
        with patch.object(server.app.state, "project_studio", studio, create=True):
            response = await server.generate_customer_project(
                body,
                {"plano": "Neris 5.6", "status_assinatura": "ativo"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(studio.calls[0]["kind"], "website")


if __name__ == "__main__":
    unittest.main()
