import base64
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from hud import server


class FakeVision:
    def __init__(self):
        self.calls = []

    async def plan_room_from_reference(self, image, *, mime_type, design_request):
        self.calls.append((image, mime_type, design_request))
        return "Sugestão de layout para o ambiente."


class RoomVisionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.body = server.RoomPlanRequest(
            image_base64=base64.b64encode(b"\xff\xd8\xffphoto").decode("ascii"),
            image_mime_type="image/jpeg",
            design_request="Sugira uma sala mais clara e uma posição para o sofá.",
            image_consent=True,
        )

    async def _request(self, user, body=None, vision=None):
        model = vision or FakeVision()
        with patch.object(server.app.state, "vision_ai", model, create=True):
            result = await server.generate_customer_room_plan(body or self.body, user)
        return result, model

    async def test_active_pro_and_ultra_receive_visual_layout_suggestions(self):
        for plan in ("Neris Pro", "Neris Ultra Max"):
            with self.subTest(plan=plan):
                result, vision = await self._request(
                    {"plano": plan, "status_assinatura": "ativo", "trial_active": False}
                )
                self.assertIn("layout", result["analysis"])
                self.assertIn("nao mede", result["notice"])
                self.assertEqual(vision.calls[0][1], "image/jpeg")

    async def test_free_neris_56_trial_and_inactive_accounts_are_denied(self):
        users = (
            {"plano": "Neris 3.5", "status_assinatura": "ativo"},
            {"plano": "Neris 5.6", "status_assinatura": "ativo"},
            {"plano": "Neris Pro", "status_assinatura": "ativo", "trial_active": True},
            {"plano": "Neris Ultra Max", "status_assinatura": "inativo"},
        )
        for user in users:
            with self.subTest(user=user):
                vision = FakeVision()
                with patch.object(server.app.state, "vision_ai", vision, create=True):
                    with self.assertRaises(HTTPException) as raised:
                        await server.generate_customer_room_plan(self.body, user)
                self.assertEqual(raised.exception.status_code, 403)
                self.assertEqual(vision.calls, [])

    async def test_photo_requires_explicit_consent(self):
        body = self.body.model_copy(update={"image_consent": False})
        with self.assertRaises(HTTPException) as raised:
            await self._request({"plano": "Neris Pro"}, body=body)
        self.assertEqual(raised.exception.status_code, 422)

    async def test_invalid_image_is_rejected_before_model_call(self):
        body = self.body.model_copy(
            update={"image_base64": base64.b64encode(b"not an image").decode("ascii")}
        )
        vision = FakeVision()
        with patch.object(server.app.state, "vision_ai", vision, create=True):
            with self.assertRaises(HTTPException) as raised:
                await server.generate_customer_room_plan(
                    body,
                    {"plano": "Neris Pro", "status_assinatura": "ativo"},
                )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(vision.calls, [])


if __name__ == "__main__":
    unittest.main()
