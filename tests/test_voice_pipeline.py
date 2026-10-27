import os
import zipfile
from io import BytesIO
import unittest
from unittest.mock import patch

from agents.base import AgentDefinition, AgentRuntime
from agents import AGENT_DEFINITIONS
from core.command_router import Intent, classify_intent
from core.voice_pipeline import VoiceCommand, VoiceCommandType, parse_voice_command
from connectors.cakto_connector import CaktoConnector
from core.project_studio import ProjectStudio, decode_visual_reference
from hud.server import AgentRegistry, AgentStatus, _lead_readiness_score
from core.storage import SupabaseRepository
from agents.market_agents import PRODUCT_SOURCING_SKILLS, SOCIAL_MEDIA_SKILLS


class VoiceCommandTests(unittest.TestCase):
    def test_parses_stop_command_with_punctuation(self):
        self.assertEqual(
            parse_voice_command("Neris, pare!").type,
            VoiceCommandType.STOP,
        )

    def test_parses_continue_command(self):
        self.assertEqual(
            parse_voice_command("Neris, por favor, continue."),
            VoiceCommand(VoiceCommandType.CONTINUE),
        )

    def test_parses_improvement_and_preserves_instruction_text(self):
        command = parse_voice_command("Neris, melhore isso: Reduza a latência.")
        self.assertEqual(command.type, VoiceCommandType.IMPROVE)
        self.assertEqual(command.instruction, "Reduza a latência")

    def test_non_command_transcript_is_not_intercepted(self):
        self.assertIsNone(parse_voice_command("Olá, Neris"))


class AgentRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_snapshot_has_43_agents_with_whatsapp_pending(self):
        registry = AgentRegistry()
        agents = await registry.snapshot()

        self.assertEqual(len(agents), 43)
        self.assertEqual(
            next(agent for agent in agents if agent["id"] == "agent-40")["status"],
            AgentStatus.PENDING_INTEGRATION,
        )
        self.assertTrue(
            all(
                agent["status"] == AgentStatus.OFFLINE
                for agent in agents
                if agent["id"] != "agent-40"
            )
        )
        self.assertEqual(AGENT_DEFINITIONS[-4].id, "agent-40")
        self.assertEqual(AGENT_DEFINITIONS[-2].id, "agent-42")
        self.assertEqual(AGENT_DEFINITIONS[-1].id, "agent-43")

    async def test_worker_status_updates_are_published(self):
        registry = AgentRegistry()
        updates = await registry.subscribe()
        await registry.update("agent-01", AgentStatus.RUNNING)

        event = updates.get_nowait()
        self.assertEqual(event["type"], "agent_update")
        self.assertEqual(event["agent"]["status"], AgentStatus.RUNNING)
        await registry.unsubscribe(updates)


class JarvisIntentTests(unittest.TestCase):
    def test_classifies_local_greetings_and_commands(self):
        self.assertEqual(classify_intent("Bom dia")[0], Intent.GREETING)
        self.assertEqual(classify_intent("Neris, pare!")[0], Intent.STOP)
        self.assertEqual(classify_intent("Neris, continue")[0], Intent.CONTINUE)
        self.assertEqual(
            classify_intent("Neris, melhore isso: reduza a latência")[0],
            Intent.IMPROVE,
        )

    def test_routes_general_requests_to_ai(self):
        self.assertEqual(classify_intent("Como reduzir o consumo?")[0], Intent.QUESTION)


class MockCaktoAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_metrics_are_injected_into_pricing_agent_prompt(self):
        class CapturingBrain:
            prompt = ""

            async def complete(self, messages, *, system_instruction, max_tokens=768):
                self.prompt = messages[-1]["content"]
                return "Analise simulada concluida."

        async def status_callback(agent_id, status, detail):
            return None

        brain = CapturingBrain()
        runtime = AgentRuntime(
            (
                AgentDefinition(
                    "agent-10",
                    "Pricing Analyst",
                    "Analyze aggregate, non-sensitive sales metrics.",
                ),
            ),
            brain,
            status_callback,
        )
        with patch.dict(os.environ, {"NERIS_MOCK_MODE": "true"}):
            metrics = await CaktoConnector().sales_metrics()
            await runtime.start()
            try:
                result = await runtime.submit("agent-10", "Analise o desempenho.")
            finally:
                await runtime.stop()

        self.assertEqual(result, "Analise simulada concluida.")
        self.assertEqual(metrics["source"], "Cakto (simulado)")
        self.assertIn("nao representam dados reais", brain.prompt)
        self.assertIn('"page_views": 3200', brain.prompt)


class ProjectStudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_studio_returns_safe_downloadable_prototype(self):
        class UnusedAgents:
            async def submit(self, *args, **kwargs):
                raise AssertionError("Mock mode must not call the AI agent.")

        class MockVision:
            async def describe_visual_reference(self, image, *, mime_type):
                return "Analise visual simulada."

        studio = ProjectStudio(UnusedAgents(), MockVision())
        with patch.dict(os.environ, {"NERIS_MOCK_MODE": "true"}):
            project = await studio.generate(
                name="Jogo Demo",
                kind="game",
                brief="Um jogo de pontuacao",
            )

        self.assertEqual(project.file_count, 2)
        with zipfile.ZipFile(BytesIO(project.archive)) as archive:
            self.assertIn("index.html", archive.namelist())
            self.assertIn("NERIS-BUILD-NOTES.txt", archive.namelist())
            page = archive.read("index.html").decode()
            self.assertIn("Marcar ponto", page)
            self.assertIn("Pontuacao", page)

    async def test_visual_upload_requires_explicit_consent_and_valid_image(self):
        class UnusedAgents:
            async def submit(self, *args, **kwargs):
                raise AssertionError("Expected input validation to stop this request.")

        class MockVision:
            async def describe_visual_reference(self, image, *, mime_type):
                return "Descricao de layout"

        studio = ProjectStudio(UnusedAgents(), MockVision())
        image_b64 = "iVBORw0KGgo="
        with patch.dict(os.environ, {"NERIS_MOCK_MODE": "true"}):
            with self.assertRaisesRegex(ValueError, "Confirme o envio"):
                await studio.generate(
                    name="Ref",
                    kind="website",
                    brief="Site baseado em imagem autorizada",
                    image_base64=image_b64,
                    image_mime_type="image/png",
                )
            image = decode_visual_reference(image_b64, "image/png")
            self.assertEqual(image, b"\x89PNG\r\n\x1a\n")
            with self.assertRaisesRegex(ValueError, "nao corresponde"):
                decode_visual_reference("bm90LWltYWdl", "image/jpeg")


class CustomerLeadPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_customer_leads_are_filtered_by_owner_and_excluded_from_private_panel(self):
        repository = SupabaseRepository()
        with patch.dict(os.environ, {"NERIS_MOCK_MODE": "true"}):
            first = await repository.add_customer_lead(
                "customer-one",
                {"empresa_nome": "Empresa A", "segmento": "Industrial"},
            )
            second = await repository.add_customer_lead(
                "customer-two",
                {"empresa_nome": "Empresa B", "segmento": "E-commerce"},
            )
            await repository.add_lead({"empresa_nome": "Lead do site"})

            first_customer_leads = await repository.customer_leads("customer-one")
            second_customer_leads = await repository.customer_leads("customer-two")
            personal_leads = await repository.recent_leads()
            foreign_lead = await repository.customer_lead("customer-one", second["id"])

        self.assertEqual([item["id"] for item in first_customer_leads], [first["id"]])
        self.assertEqual([item["id"] for item in second_customer_leads], [second["id"]])
        self.assertEqual([item["empresa_nome"] for item in personal_leads], ["Lead do site"])
        self.assertIsNone(foreign_lead)

    def test_lead_score_is_explained_as_non_calibrated_readiness(self):
        self.assertEqual(
            _lead_readiness_score(
                {
                    "empresa_nome": "Empresa",
                    "segmento": "Industrial",
                    "contato_email": "contato@example.com",
                    "contato_whatsapp": "5511999999999",
                    "consentimento_contato": True,
                }
            ),
            80,
        )


class SpecialistSkillTests(unittest.TestCase):
    def test_product_and_social_agents_have_the_requested_skill_counts(self):
        self.assertEqual(len(PRODUCT_SOURCING_SKILLS), 40)
        self.assertEqual(len(SOCIAL_MEDIA_SKILLS), 25)
        self.assertEqual(AGENT_DEFINITIONS[-6].id, "agent-38")
        self.assertEqual(AGENT_DEFINITIONS[-5].id, "agent-39")


class ShopifyProductSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_product_opportunity_snapshot_is_identified_as_demo(self):
        from connectors.shopify_connector import ShopifyConnector

        with patch.dict(os.environ, {"NERIS_MOCK_MODE": "true"}):
            result = await ShopifyConnector().product_opportunity_snapshot()

        self.assertEqual(result["source"], "Shopify (dados de demonstração)")
        self.assertEqual(len(result["catalog"]), 2)
        self.assertIn("Custos e margens", result["limitations"][1])


if __name__ == "__main__":
    unittest.main()
