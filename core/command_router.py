"""Intent classification and safe command dispatch inspired by JarvisN."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from agents.base import AgentRuntime
from core.brain import ChatMessage, NerisBrain
from core.voice_pipeline import VoiceCommandType, parse_voice_command


class Intent(StrEnum):
    GREETING = "greeting"
    STOP = "stop"
    CONTINUE = "continue"
    IMPROVE = "improve"
    QUESTION = "question"


@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    response: str


def classify_intent(text: str) -> tuple[Intent, str | None]:
    """Classify common voice commands locally; route general questions to AI."""
    command = parse_voice_command(text)
    if command:
        intent = {
            VoiceCommandType.STOP: Intent.STOP,
            VoiceCommandType.CONTINUE: Intent.CONTINUE,
            VoiceCommandType.IMPROVE: Intent.IMPROVE,
        }[command.type]
        return intent, command.instruction

    normalized = re.sub(r"[^\w\s]", " ", text.casefold())
    normalized = " ".join(normalized.split())
    if re.fullmatch(r"(oi|ola|bom dia|boa tarde|boa noite|ola neris|oi neris)", normalized):
        return Intent.GREETING, None
    return Intent.QUESTION, None


class CommandRouter:
    def __init__(self, brain: NerisBrain, agents: AgentRuntime) -> None:
        self._brain = brain
        self._agents = agents

    async def dispatch(self, text: str) -> IntentResult:
        if not text.strip() or len(text) > 6000:
            raise ValueError("Command text must contain 1-6000 characters.")
        intent, instruction = classify_intent(text)
        if intent == Intent.GREETING:
            return IntentResult(intent, "Olá. Neris à sua disposição. O que vamos resolver?")
        if intent == Intent.STOP:
            await self._agents.pause()
            return IntentResult(
                intent,
                "Novas tarefas da colmeia foram pausadas. Inferências remotas já iniciadas "
                "podem concluir; a interrupção de áudio é tratada pelo Pipecat.",
            )
        if intent == Intent.CONTINUE:
            await self._agents.resume()
            return IntentResult(intent, "A fila de tarefas pausadas foi retomada.")
        if intent == Intent.IMPROVE:
            if not instruction:
                raise ValueError("Diga 'Neris, melhore isso' e informe a alteração desejada.")
            response = await self._agents.submit("agent-27", instruction)
            return IntentResult(
                intent,
                "Análise de engenharia concluída. Nenhuma alteração foi aplicada "
                f"automaticamente. Resultado: {response}",
            )

        response = await self._brain.answer(
            [ChatMessage(role="user", content=text)]
        )
        return IntentResult(Intent.QUESTION, response)
